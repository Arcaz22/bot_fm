import logging
import re
from app.domain.llm.ports import LLMPort
from app.domain.finance.ports import FinanceRepoPort
from app.domain.finance import rules
from app.domain.finance import category_keywords
from app.domain.finance.exceptions import FinanceError, InsufficientBalanceError
from app.application.dtos.extraction import ExtractedTransaction

logger = logging.getLogger(__name__)


AMOUNT_PATTERN = r'\b\d+(?:[.,]\d+)?\s*(?:rb|ribu|k|jt|juta)?\b'
SELF_PATTERN = r'(?:saya|aku|gue|gw)'
CASH_WITHDRAWAL_PATTERN = r'\b(?:tarik\s+tunai|penarikan\s+tunai|cash\s+withdrawal|withdraw(?:al)?\s+cash)\b'


def _clean_counterparty_name(name: str) -> str:
    cleaned = re.sub(
        r'\b(?:rp|idr|uang|duit|sebesar|senilai|ke|dari|sama|kepada)\b',
        ' ',
        name,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(AMOUNT_PATTERN, ' ', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip(" ,.-")
    return cleaned.title()


def _text_without_amount(text: str) -> str:
    cleaned = re.sub(AMOUNT_PATTERN, ' ', text.lower())
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


def _extract_debt_hint(text: str) -> tuple[str | None, str | None]:
    text_lower = text.lower().strip()
    text_no_amount = _text_without_amount(text_lower)

    patterns = [
        ("PAY", rf'\b(?:bayar|lunasin|lunas(?:kan)?)\s+(?:hutang|utang)\s+(?:ke|sama|kepada)\s+(.+?)$'),
        ("LEND", rf'^(.+?)\s+(?:hutang|utang|berhutang|berutang|pinjam|minjem|pinjem)\s+(?:ke|sama|kepada|dari)\s+{SELF_PATTERN}\b'),
        ("BORROW", rf'\b{SELF_PATTERN}?\s*(?:hutang|utang|berhutang|berutang)\s+(?:ke|sama|kepada)\s+(.+?)$'),
        ("BORROW", rf'\b{SELF_PATTERN}?\s*(?:pinjam|minjem|pinjem)\s+(?:uang|duit)?\s*(?:dari|ke|sama|kepada)\s+(.+?)$'),
        ("LEND", r'\b(?:piutang|pinjemin|pinjamin|pinjamkan|meminjamkan)\s+(?:ke|sama|kepada)?\s*(.+?)$'),
        ("LEND", r'\b(?:kasih|beri)\s+pinjam\s+(?:ke|sama|kepada)?\s*(.+?)$'),
    ]

    for action, pattern in patterns:
        match = re.search(pattern, text_no_amount)
        if match:
            name = _clean_counterparty_name(match.group(1))
            if name:
                return action, name

    return None, None


def _extract_amount(text: str) -> float | None:
    match = re.search(r'\b(\d+(?:[.,]\d+)?)\s*(rb|ribu|k|jt|juta)?\b', text.lower())
    if not match:
        return None

    raw_amount, suffix = match.groups()
    amount = float(raw_amount.replace(",", "."))

    if suffix in {"rb", "ribu", "k"}:
        amount *= 1000
    elif suffix in {"jt", "juta"}:
        amount *= 1000000

    return amount


def _is_cash_withdrawal(text: str) -> bool:
    return bool(re.search(CASH_WITHDRAWAL_PATTERN, text, flags=re.IGNORECASE))


# Keywords that signal the message is NOT a simple single-wallet expense.
# Any hit here disqualifies the regex fast-path and forces the LLM call,
# since transfer/income parsing needs judgment the regex isn't trusted with.
_FAST_PATH_DISQUALIFIERS = (
    "transfer", "kirim", "pindahin", "pindah saldo",  # transfer-like
    "gaji", "dapat", "terima", "masuk", "bonus", "dividen", "cashback", "refund",  # income-like
)


def _is_simple_expense_candidate(text: str) -> bool:
    """Conservative guard: only allow the fast path for unambiguous expenses."""
    text_lower = text.lower()
    return not any(keyword in text_lower for keyword in _FAST_PATH_DISQUALIFIERS)


class TransactionService:
    def __init__(self, llm: LLMPort, repo: FinanceRepoPort):
        self.llm = llm
        self.repo = repo

    async def process_natural_language(self, user_id: int, text: str) -> str:
        try:
            debt_action, counterparty_name = _extract_debt_hint(text)
            amount_hint = _extract_amount(text)
            is_cash_withdrawal = _is_cash_withdrawal(text)

            if debt_action and counterparty_name and amount_hint:
                data = ExtractedTransaction(
                    amount=amount_hint,
                    category="Loan",
                    wallet_name="BCA",
                    description=text[:50],
                    transaction_type="EXPENSE" if debt_action in {"LEND", "PAY"} else "INCOME",
                    debt_action=debt_action,
                    counterparty_name=counterparty_name
                )
            elif (
                amount_hint
                and not is_cash_withdrawal
                and _is_simple_expense_candidate(text)
                and (fast_category := category_keywords.guess_category(text))
                and (fast_wallet := category_keywords.guess_wallet(text))
            ):
                # High-confidence simple expense (amount + category keyword +
                # wallet keyword all matched) — skip the Gemini call entirely.
                logger.info(
                    f"Fast-path (no LLM call): amount={amount_hint}, "
                    f"category={fast_category}, wallet={fast_wallet}"
                )
                data = ExtractedTransaction(
                    amount=amount_hint,
                    category=fast_category,
                    wallet_name=fast_wallet,
                    description=text[:50],
                    transaction_type="EXPENSE",
                    debt_action="NONE",
                    counterparty_name=None,
                )
            else:
                raw_data = await self.llm.parse_transaction(text)
                if "error" in raw_data:
                    if is_cash_withdrawal and amount_hint:
                        raw_data = {
                            "amount": amount_hint,
                            "category": "Cash Withdrawal",
                            "wallet_name": "BCA",
                            "target_wallet_name": "Cash",
                            "description": text[:50],
                            "transaction_type": "TRANSFER",
                            "debt_action": "NONE",
                            "counterparty_name": None,
                        }
                    else:
                        return "🤖 Maaf, saya gagal paham. Coba kalimat simpel: 'Makan 20rb pake OVO' atau 'Transfer 50rb dari BCA ke Gopay'"

                data = ExtractedTransaction(**raw_data)

            # Tarik tunai adalah perpindahan aset dari rekening ke uang fisik,
            # bukan pengeluaran. Jangan bergantung pada klasifikasi LLM untuk ini.
            if is_cash_withdrawal:
                data.transaction_type = "TRANSFER"
                data.target_wallet_name = "Cash"
                data.category = "Cash Withdrawal"
                data.debt_action = "NONE"
                data.counterparty_name = None

                if rules.normalize_wallet_name(data.wallet_name) == "Cash":
                    data.wallet_name = "BCA"

            # Fallback wallet default jika tidak ada wallet_name
            if not getattr(data, "wallet_name", None):
                data.wallet_name = "BCA"

            try:
                tl = text.lower()
                if getattr(data, "debt_action", "NONE") == "NONE":
                    if "bayar hutang" in tl or "lunasin hutang" in tl:
                        data.debt_action = "PAY"

                debt_action, counterparty_name = _extract_debt_hint(text)
                if debt_action and data.debt_action == "NONE":
                    data.debt_action = debt_action
                if counterparty_name and not data.counterparty_name:
                    data.counterparty_name = counterparty_name
                if data.debt_action == "PAY":
                    data.transaction_type = "EXPENSE"
            except Exception:
                pass

        except Exception as e:
            logger.error(f"LLM/DTO Error: {e}")
            return "Terjadi kesalahan saat memproses pesan (Parsing Error)."

        try:
            rules.validate_transaction_amount(data.amount)

            if data.debt_action in {"BORROW", "LEND"} and data.counterparty_name:
                counterparty_name = data.counterparty_name.strip()
                if not counterparty_name:
                    return "Nama pihak lawan hutang wajib diisi."

                direction = "I_OWE" if data.debt_action == "BORROW" else "THEY_OWE"
                await self.repo.create_debt(
                    owner_user_id=user_id,
                    counterparty_name=counterparty_name,
                    direction=direction,
                    amount=data.amount,
                    description=data.description,
                    notes=f"Auto from debt note ({data.debt_action})"
                )

                if data.debt_action == "BORROW":
                    return (
                        f"🤝 **Hutang Tercatat!**\n\n"
                        f"Anda berhutang ke {counterparty_name}\n"
                        f"💰 Rp {data.amount:,.0f}\n\n"
                    )

                return (
                    f"🤝 **Piutang Tercatat!**\n\n"
                    f"{counterparty_name} berhutang ke Anda\n"
                    f"💰 Rp {data.amount:,.0f}\n\n"
                    "Saldo tidak berubah karena ini hanya catatan piutang."
                )

            clean_wallet_name = rules.normalize_wallet_name(data.wallet_name)
            wallet = await self.repo.get_wallet_by_name(user_id, clean_wallet_name)

            if not wallet:
                wallet = await self.repo.create_wallet(user_id, clean_wallet_name)

            target_wallet = None
            if data.transaction_type == "TRANSFER" and data.target_wallet_name:
                clean_target_name = rules.normalize_wallet_name(data.target_wallet_name)

                target_wallet = await self.repo.get_wallet_by_name(user_id, clean_target_name)

                if not target_wallet:
                    target_wallet = await self.repo.create_wallet(user_id, clean_target_name)

            category = None
            if data.category:
                cat_type = data.transaction_type.lower()
                category = await self.repo.get_category_by_name(
                    user_id, data.category, cat_type
                )

                if not category:
                    category = await self.repo.create_category(
                        user_id, data.category, cat_type
                    )

            trx = await self.repo.create_transaction(
                user_id=user_id,
                wallet_id=wallet.id,
                target_wallet_id=target_wallet.id if target_wallet else None,
                category_id=category.id if category else None,
                amount=data.amount,
                type=data.transaction_type.lower(),
                description=data.description
            )

            debt_note = ""
            if getattr(data, "debt_action", "NONE") != "NONE" and getattr(data, "counterparty_name", None):
                counterparty_name = data.counterparty_name.strip()

                if counterparty_name:
                    action = data.debt_action

                    if action == "BORROW":
                        await self.repo.create_debt(
                            owner_user_id=user_id,
                            counterparty_name=counterparty_name,
                            direction="I_OWE",
                            amount=data.amount,
                            description=data.description,
                            notes=f"Auto from transaction {trx.id} (BORROW)"
                        )
                        debt_note = f"\n🤝 Hutang tercatat: Anda berhutang ke {counterparty_name}."

                    elif action == "LEND":
                        await self.repo.create_debt(
                            owner_user_id=user_id,
                            counterparty_name=counterparty_name,
                            direction="THEY_OWE",
                            amount=data.amount,
                            description=data.description,
                            notes=f"Auto from transaction {trx.id} (LEND)"
                        )
                        debt_note = f"\n🤝 Piutang tercatat: {counterparty_name} berhutang ke Anda."

                    elif action == "PAY":
                        open_debt = None

                        try:
                            open_debt = await self.repo.get_latest_open_debt_with_counterparty(
                                owner_user_id=user_id,
                                counterparty_name=counterparty_name,
                                direction="I_OWE"
                            )
                        except Exception:
                            open_debt = None

                        if not open_debt:
                            try:
                                owed_list = await self.repo.get_debts_owed(user_id, status="pending")
                                if owed_list:
                                    open_debt = owed_list[0]
                            except Exception:
                                open_debt = None

                        if open_debt:
                            original_debt_amount = float(open_debt.amount)
                            updated_debt = await self.repo.mark_debt_as_paid(
                                debt_id=open_debt.id,
                                transaction_id=trx.id,
                                paid_amount=data.amount
                            )

                            target_name = (
                                open_debt.counterparty.display_name
                                if getattr(open_debt, "counterparty", None) and getattr(open_debt.counterparty, "display_name", None)
                                else counterparty_name
                            )
                            if updated_debt.status == "paid":
                                debt_note = f"\n✅ Hutang ke {target_name} ditandai lunas."
                            else:
                                debt_note = (
                                    f"\n✅ Pembayaran hutang ke {target_name} dicatat."
                                    f"\n💰 Sisa hutang: Rp {float(updated_debt.amount):,.0f}"
                                )
                                if data.amount > original_debt_amount:
                                    debt_note += f"\nℹ️ Pembayaran melebihi sisa hutang Rp {original_debt_amount:,.0f}."
                        else:
                            debt_note = "\nℹ️ Tidak ditemukan hutang pending yang cocok, hanya mencatat transaksi."

            if data.transaction_type == "EXPENSE":
                icon = "🔴"
            elif data.transaction_type == "INCOME":
                icon = "🟢"
            else:
                icon = "🔄"

            wallet_info = f"💳 {wallet.name}"
            if target_wallet:
                wallet_info += f" ➡️ {target_wallet.name}"

            return (
                f"{icon} **Transaksi Tercatat!**\n\n"
                f"📝 {data.description}\n"
                f"💰 Rp {data.amount:,.0f}\n"
                f"📂 {category.name if category else '-'}\n"
                f"{wallet_info}"
                f"{debt_note}"
            )

        except InsufficientBalanceError as e:
            return f"⛔ **Gagal:** {str(e)}"
        except FinanceError as e:
            return f"⚠️ **Error:** {str(e)}"
        except Exception as e:
            logger.error(f"System Error: {e}")
            return "Terjadi kesalahan sistem database."

    async def get_balance_summary(self, user_id: int) -> str:
        wallets = await self.repo.get_user_wallets(user_id)

        if not wallets:
            return "🤷‍♂️ Belum ada dompet terdaftar. Coba catat transaksi dulu."

        report = "📊 **Saldo Saat Ini:**\n\n"
        total_assets = 0

        for w in wallets:
            balance = await self.repo.get_wallet_balance(w.id, user_id)
            total_assets += balance
            report += f"💳 **{w.name}:** Rp {balance:,.0f}\n"

        report += f"\n💰 **Total Aset:** Rp {total_assets:,.0f}"
        return report

    async def get_last_transactions(self, user_id: int) -> str:
        trxs = await self.repo.get_recent_transactions(user_id, limit=5)

        if not trxs:
            return "📭 Belum ada riwayat transaksi."

        report = "🕓 **5 Transaksi Terakhir:**\n\n"
        for t in trxs:
            if t.type == 'expense': icon = "🔴"
            elif t.type == 'income': icon = "🟢"
            else: icon = "🔄"

            date_str = t.trx_date.strftime("%d/%m")

            desc = t.description or "-"
            if len(desc) > 20: desc = desc[:17] + "..."

            report += f"{icon} `{date_str}` **{desc}**\n"
            report += f"   Rp {t.amount:,.0f} ({t.wallet.name})\n"

        return report

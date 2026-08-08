import logging
import re
from app.domain.llm.ports import LLMPort
from app.domain.finance.ports import FinanceRepoPort
from app.domain.finance import rules
from app.domain.finance import category_keywords
from app.domain.finance.exceptions import FinanceError, InsufficientBalanceError
from app.application.dtos.extraction import ExtractedTransaction

logger = logging.getLogger(__name__)


NUMBER_PATTERN = r'\d+(?:(?:[.,]\d{3})+|[.,]\d+)?'
AMOUNT_PATTERN = rf'\b{NUMBER_PATTERN}\s*(?:rb|ribu|k|jt|juta)?\b'
SELF_PATTERN = r'(?:saya|aku|gue|gw)'
CASH_WITHDRAWAL_PATTERN = r'\b(?:tarik\s+tunai|penarikan\s+tunai|cash\s+withdrawal|withdraw(?:al)?\s+cash)\b'
BALANCE_SETUP_KEYWORDS = (
    "saldo",
    "saldo awal",
    "set saldo",
    "atur saldo",
    "setup wallet",
    "set wallet",
    "atur wallet",
    "setup ewallet",
    "set ewallet",
    "atur ewallet",
    "migrasi",
    "migration",
    "import saldo",
)

JOINT_SAVINGS_KEYWORDS = (
    "tabungan bersama",
    "patungan",
    "setoran bersama",
    "iuran tabungan",
)
PERSONAL_SAVINGS_KEYWORDS = (
    "nabung",
    "menabung",
    "tabungan pribadi",
    "ke tabungan",
    "masuk tabungan",
)
INVESTMENT_KEYWORDS = (
    "investasi",
    "rdn",
    "saham",
    "reksadana",
    "rekasadana",
    "stockbit",
    "ajaib",
    "crypto",
    "kripto",
)
INVESTMENT_TARGETS = (
    ("rdn", "RDN"),
    ("stockbit", "stockbit"),
    ("ajaib", "Ajaib"),
    ("crypto", "Crypto"),
    ("kripto", "Crypto"),
)


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


def _parse_amount_value(raw_amount: str, suffix: str | None = None) -> float:
    separators = [char for char in raw_amount if char in {".", ","}]

    if separators:
        last_separator = separators[-1]
        last_separator_index = raw_amount.rfind(last_separator)
        decimal_digits = len(raw_amount) - last_separator_index - 1
        has_mixed_separators = "." in separators and "," in separators
        has_repeated_separators = separators.count(last_separator) > 1
        suffix_multiplier = suffix in {"rb", "ribu", "k", "jt", "juta"}

        if (
            has_mixed_separators
            or has_repeated_separators
            or (decimal_digits == 3 and not suffix_multiplier)
        ):
            normalized = re.sub(r"[.,]", "", raw_amount)
        else:
            normalized = raw_amount.replace(",", ".")
    else:
        normalized = raw_amount

    amount = float(normalized)

    if suffix in {"rb", "ribu", "k"}:
        amount *= 1000
    elif suffix in {"jt", "juta"}:
        amount *= 1000000

    return amount


def _extract_amount(text: str) -> float | None:
    matches = list(re.finditer(rf'\b({NUMBER_PATTERN})\s*(rb|ribu|k|jt|juta)?\b', text.lower()))
    if not matches:
        return None

    match = next((item for item in matches if item.group(2)), matches[0])
    raw_amount, suffix = match.groups()
    return _parse_amount_value(raw_amount, suffix)


def _is_cash_withdrawal(text: str) -> bool:
    return bool(re.search(CASH_WITHDRAWAL_PATTERN, text, flags=re.IGNORECASE))


def _extract_balance_setup(text: str) -> tuple[str, float] | None:
    amount = _extract_amount(text)
    wallet_name = category_keywords.guess_wallet(text)
    if amount is None or wallet_name is None:
        return None

    text_lower = text.lower()
    has_setup_keyword = any(keyword in text_lower for keyword in BALANCE_SETUP_KEYWORDS)
    if has_setup_keyword:
        return wallet_name, amount

    return None


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in keywords)


def _extract_source_wallet(text: str) -> str | None:
    text_lower = text.lower()
    source_match = re.search(r'\b(?:dari|from)\s+([a-zA-Z0-9][\w .+-]{0,40})', text_lower)
    if source_match:
        source_text = source_match.group(1)
        source_text = re.split(r'\b(?:ke|untuk|buat|via|pakai|pake)\b', source_text, maxsplit=1)[0]
        source_wallet = category_keywords.guess_wallet(source_text)
        if source_wallet:
            return source_wallet

    return None


def _extract_transfer_target(text: str) -> str | None:
    text_lower = text.lower()
    target_match = re.search(r'\b(?:ke|to|menuju)\s+([a-zA-Z0-9][\w .+-]{0,40})', text_lower)
    if not target_match:
        return None

    target_text = target_match.group(1)
    target_text = re.split(r'\b(?:dari|untuk|buat|via|pakai|pake)\b', target_text, maxsplit=1)[0]
    return category_keywords.guess_wallet(target_text)


def _investment_target(text: str) -> str:
    text_lower = text.lower()
    explicit_target = _extract_transfer_target(text)
    if explicit_target and explicit_target not in {"Tabungan"}:
        return explicit_target

    for keyword, wallet_name in INVESTMENT_TARGETS:
        if keyword in text_lower:
            return wallet_name

    return "Investasi"


def _apply_asset_allocation_rules(data: ExtractedTransaction, text: str) -> None:
    source_wallet = _extract_source_wallet(text)

    if _contains_any(text, JOINT_SAVINGS_KEYWORDS):
        data.transaction_type = "EXPENSE"
        data.category = "Joint Savings"
        data.target_wallet_name = None
        data.debt_action = "NONE"
        data.counterparty_name = None
        if source_wallet:
            data.wallet_name = source_wallet
        elif rules.normalize_wallet_name(data.wallet_name) in {"Tabungan", "RDN", "Investasi"}:
            data.wallet_name = "BCA"
        return

    if _contains_any(text, INVESTMENT_KEYWORDS):
        target_wallet_name = _investment_target(text)
        data.transaction_type = "TRANSFER"
        data.category = "Investment"
        data.target_wallet_name = target_wallet_name
        data.debt_action = "NONE"
        data.counterparty_name = None
        if source_wallet:
            data.wallet_name = source_wallet
        elif rules.normalize_wallet_name(data.wallet_name) == rules.normalize_wallet_name(target_wallet_name):
            data.wallet_name = "BCA"
        return

    if _contains_any(text, PERSONAL_SAVINGS_KEYWORDS):
        target_wallet_name = _extract_transfer_target(text) or "Tabungan"
        data.transaction_type = "TRANSFER"
        data.category = "Savings"
        data.target_wallet_name = target_wallet_name
        data.debt_action = "NONE"
        data.counterparty_name = None
        if source_wallet:
            data.wallet_name = source_wallet
        elif rules.normalize_wallet_name(data.wallet_name) == rules.normalize_wallet_name(target_wallet_name):
            data.wallet_name = "BCA"


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
            balance_setup = _extract_balance_setup(text)
            if balance_setup:
                wallet_name, amount = balance_setup
                rules.validate_transaction_amount(amount)

                clean_wallet_name = rules.normalize_wallet_name(wallet_name)
                wallet = await self.repo.get_wallet_by_name(user_id, clean_wallet_name)

                if not wallet:
                    wallet = await self.repo.create_wallet(
                        user_id,
                        clean_wallet_name,
                        initial_balance=amount,
                    )
                else:
                    current_balance = await self.repo.get_wallet_balance(wallet.id, user_id)
                    current_initial = float(getattr(wallet, "initial_balance", 0) or 0)
                    new_initial = current_initial + (amount - current_balance)
                    wallet = await self.repo.set_wallet_initial_balance(
                        user_id,
                        wallet.id,
                        new_initial,
                    )

                return (
                    "💼 **Saldo Wallet Diatur!**\n\n"
                    f"💳 {wallet.name}\n"
                    f"💰 Rp {amount:,.0f}\n\n"
                    "Saldo ini dicatat sebagai saldo migrasi/manual, bukan transfer dari wallet lain."
                )

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
                if amount_hint:
                    data.amount = amount_hint

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

            _apply_asset_allocation_rules(data, text)

            # Fallback wallet default jika tidak ada wallet_name
            if not getattr(data, "wallet_name", None):
                data.wallet_name = "BCA"

            data.category = category_keywords.normalize_category(
                data.category,
                data.transaction_type,
            )

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
                    data.category = category_keywords.normalize_category(
                        data.category,
                        data.transaction_type,
                    )
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

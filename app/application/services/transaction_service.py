import logging
from app.domain.llm.ports import LLMPort
from app.domain.finance.ports import FinanceRepoPort
from app.domain.finance import rules
from app.domain.finance.exceptions import FinanceError, InsufficientBalanceError
from app.application.dtos.extraction import ExtractedTransaction

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self, llm: LLMPort, repo: FinanceRepoPort):
        self.llm = llm
        self.repo = repo

    async def process_natural_language(self, user_id: int, text: str) -> str:
        try:
            raw_data = await self.llm.parse_transaction(text)
            if "error" in raw_data:
                return "🤖 Maaf, saya gagal paham. Coba kalimat simpel: 'Makan 20rb pake OVO' atau 'Transfer 50rb dari BCA ke Gopay'"

            data = ExtractedTransaction(**raw_data)

            # Fallback wallet default jika tidak ada wallet_name
            if not getattr(data, "wallet_name", None):
                data.wallet_name = "BCA"

            try:
                tl = text.lower()
                if getattr(data, "debt_action", "NONE") == "NONE":
                    if "bayar hutang" in tl or "lunasin hutang" in tl:
                        data.debt_action = "PAY"
            except Exception:
                pass

        except Exception as e:
            logger.error(f"LLM/DTO Error: {e}")
            return "Terjadi kesalahan saat memproses pesan (Parsing Error)."

        try:
            rules.validate_transaction_amount(data.amount)

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
                counterparty = await self.repo.find_user_by_name_or_username(data.counterparty_name)

                if counterparty:
                    action = data.debt_action

                    if action == "BORROW":
                        await self.repo.create_debt(
                            creditor_user_id=counterparty.id,
                            debtor_user_id=user_id,
                            amount=data.amount,
                            description=data.description,
                            notes=f"Auto from transaction {trx.id} (BORROW)"
                        )
                        debt_note = f"\n🤝 Hutang tercatat: Anda berhutang ke {counterparty.first_name}."

                    elif action == "LEND":
                        await self.repo.create_debt(
                            creditor_user_id=user_id,
                            debtor_user_id=counterparty.id,
                            amount=data.amount,
                            description=data.description,
                            notes=f"Auto from transaction {trx.id} (LEND)"
                        )
                        debt_note = f"\n🤝 Piutang tercatat: {counterparty.first_name} berhutang ke Anda."

                    elif action == "PAY":
                        open_debt = None

                        try:
                            open_debt = await self.repo.get_latest_open_debt_between(
                                creditor_user_id=counterparty.id,
                                debtor_user_id=user_id
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
                            await self.repo.mark_debt_as_paid(
                                debt_id=open_debt.id,
                                transaction_id=trx.id
                            )

                            target_name = (
                                open_debt.creditor.first_name
                                if getattr(open_debt, "creditor", None) and getattr(open_debt.creditor, "first_name", None)
                                else counterparty.first_name
                            )
                            debt_note = f"\n✅ Hutang ke {target_name} ditandai lunas."
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

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
        # ==========================================================
        # 1. AI EXTRACTION & DTO VALIDATION
        # ==========================================================
        try:
            raw_data = await self.llm.parse_transaction(text)

            if "error" in raw_data:
                return "🤖 Maaf, saya gagal paham. Coba kalimat simpel: 'Makan 20rb pake OVO' atau 'Transfer 50rb dari BCA ke Gopay'"

            data = ExtractedTransaction(**raw_data)
        except Exception as e:
            logger.error(f"LLM/DTO Error: {e}")
            return "Terjadi kesalahan saat memproses pesan (Parsing Error)."

        try:
            # ==========================================================
            # 2. BUSINESS RULES VALIDATION
            # ==========================================================
            rules.validate_transaction_amount(data.amount)

            # ==========================================================
            # 3. HANDLE SOURCE WALLET (Dompet Asal)
            # ==========================================================
            clean_wallet_name = rules.normalize_wallet_name(data.wallet_name)
            wallet = await self.repo.get_wallet_by_name(user_id, clean_wallet_name)

            if not wallet:
                wallet = await self.repo.create_wallet(user_id, clean_wallet_name)

            # ==========================================================
            # 4. HANDLE TARGET WALLET (Khusus TRANSFER)
            # ==========================================================
            target_wallet = None
            if data.transaction_type == "TRANSFER" and data.target_wallet_name:
                clean_target_name = rules.normalize_wallet_name(data.target_wallet_name)

                # Cek apakah wallet tujuan ada?
                target_wallet = await self.repo.get_wallet_by_name(user_id, clean_target_name)

                # Auto-create target wallet jika belum ada
                if not target_wallet:
                    target_wallet = await self.repo.create_wallet(user_id, clean_target_name)

            # ==========================================================
            # 5. HANDLE CATEGORY
            # ==========================================================
            category = None
            if data.category:
                # Cari category, pastikan typenya sesuai (EXPENSE/INCOME/TRANSFER)
                # Gunakan lowercase untuk konsistensi DB
                cat_type = data.transaction_type.lower()
                category = await self.repo.get_category_by_name(
                    user_id, data.category, cat_type
                )

                # Auto-create category jika belum ada
                if not category:
                    category = await self.repo.create_category(
                        user_id, data.category, cat_type
                    )

            # ==========================================================
            # 6. SIMPAN TRANSAKSI (REPOSITORY)
            # ==========================================================
            trx = await self.repo.create_transaction(
                user_id=user_id,
                wallet_id=wallet.id,
                # Masukkan ID target wallet jika ada (utk Transfer)
                target_wallet_id=target_wallet.id if target_wallet else None,
                category_id=category.id if category else None,
                amount=data.amount,
                type=data.transaction_type.lower(), # 'expense', 'income', 'transfer'
                description=data.description
            )

            # ==========================================================
            # 7. FORMAT RESPONSE
            # ==========================================================
            # Tentukan Icon
            if data.transaction_type == "EXPENSE":
                icon = "🔴" # Merah untuk keluar
            elif data.transaction_type == "INCOME":
                icon = "🟢" # Hijau untuk masuk
            else:
                icon = "🔄" # Putar untuk transfer

            # Format teks dompet
            wallet_info = f"💳 {wallet.name}"
            if target_wallet:
                wallet_info += f" ➡️ {target_wallet.name}"

            return (
                f"{icon} **Transaksi Tercatat!**\n\n"
                f"📝 {data.description}\n"
                f"💰 Rp {data.amount:,.0f}\n"
                f"📂 {category.name if category else '-'}\n"
                f"{wallet_info}"
            )

        except InsufficientBalanceError as e:
            return f"⛔ **Gagal:** {str(e)}"
        except FinanceError as e:
            return f"⚠️ **Error:** {str(e)}"
        except Exception as e:
            logger.error(f"System Error: {e}")
            return "Terjadi kesalahan sistem database."

    async def get_balance_summary(self, user_id: int) -> str:
        """Mengambil rekap saldo semua wallet"""
        wallets = await self.repo.get_user_wallets(user_id)

        if not wallets:
            return "🤷‍♂️ Belum ada dompet terdaftar. Coba catat transaksi dulu."

        report = "📊 **Saldo Saat Ini:**\n\n"
        total_assets = 0

        for w in wallets:
            # Hitung saldo real-time
            balance = await self.repo.get_wallet_balance(w.id, user_id)
            total_assets += balance
            report += f"💳 **{w.name}:** Rp {balance:,.0f}\n"

        report += f"\n💰 **Total Aset:** Rp {total_assets:,.0f}"
        return report

    async def get_last_transactions(self, user_id: int) -> str:
        """Mengambil 5 transaksi terakhir"""
        trxs = await self.repo.get_recent_transactions(user_id, limit=5)

        if not trxs:
            return "📭 Belum ada riwayat transaksi."

        report = "🕓 **5 Transaksi Terakhir:**\n\n"
        for t in trxs:
            # Tentukan icon
            if t.type == 'expense': icon = "🔴"
            elif t.type == 'income': icon = "🟢"
            else: icon = "🔄"

            # Format tanggal (DD/MM)
            date_str = t.trx_date.strftime("%d/%m")

            # Format Deskripsi
            desc = t.description or "-"
            if len(desc) > 20: desc = desc[:17] + "..."

            report += f"{icon} `{date_str}` **{desc}**\n"
            report += f"   Rp {t.amount:,.0f} ({t.wallet.name})\n"

        return report

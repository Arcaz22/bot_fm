import logging
import difflib
import re
from app.domain.membership.rules import resolve_usage_period
from typing import Set

from app.application.services.transaction_service import TransactionService
from app.presentation.schemas.telegram import Update, Message
from app.domain.telegram.entities import TelegramUser
from app.domain.telegram.rules import ensure_active
from app.domain.telegram.ports import TelegramUserRepo, TelegramNotifier
from app.domain.membership.ports import MembershipRepoPort
from app.core.settings import settings

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://dashboard-fm-azure.vercel.app/"

HELP_COMMANDS = {"/fitur", "/help", "/menu", "/bantuan"}
DASHBOARD_COMMANDS = {"/saldo", "/riwayat", "/history", "/hutang", "/piutang"}
SYSTEM_COMMANDS = {"/start", "/phone"}
KNOWN_COMMANDS = sorted(SYSTEM_COMMANDS | HELP_COMMANDS | DASHBOARD_COMMANDS)
NLP_FEATURE_FORMATS = {
    "/investment": [
        "`investasi RDN 1jt dari BCA`",
        "`investasi saham 1jt dari BCA`",
    ],
    "/investasi": [
        "`investasi RDN 1jt dari BCA`",
        "`investasi saham 1jt dari BCA`",
    ],
    "/rdn": [
        "`investasi RDN 1jt dari BCA`",
        "`setor RDN 1jt dari BCA`",
    ],
    "/tabungan": [
        "`nabung 500rb dari BCA`",
        "`transfer 500rb dari BCA ke Tabungan`",
    ],
    "/nabung": [
        "`nabung 500rb dari BCA`",
        "`transfer 500rb dari BCA ke Tabungan`",
    ],
    "/transfer": [
        "`transfer 100rb dari BCA ke Gopay`",
        "`kirim 100rb dari BCA ke Dana`",
    ],
    "/struk": [
        "kirim foto struk langsung ke bot",
        "kirim foto struk dengan caption `belanja bulanan`",
    ],
    "/receipt": [
        "kirim foto struk langsung ke bot",
        "kirim foto struk dengan caption `belanja bulanan`",
    ],
}


def _normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D", "", phone_number or "")
    if digits.startswith("0"):
        return f"62{digits[1:]}"
    return digits


def _detect_intent(text: str) -> str:
    """
    Hybrid Intent Detection dengan prioritas eksplisit:
    1. Dashboard data request (saldo, riwayat, query hutang/piutang)
    2. Debt action (catat/bayar hutang)
    3. Transaction (default fallback ke LLM)

    Menggunakan token-based matching untuk menghindari false positive substring.
    """
    text_lower = text.lower().strip()

    tokens: Set[str] = set(re.findall(r'\b[a-z0-9]+\b', text_lower))

    HISTORY_PHRASES = [
        "riwayat", "history", "histori", "catatan transaksi",
        "5 terakhir", "transaksi terakhir", "transaksi sebelumnya"
    ]

    MENU_KEYWORDS = {"menu", "help", "fitur", "bantuan"}
    GREETING_KEYWORDS = {"halo", "hello", "hai", "hi", "test", "tes"}
    DEBT_KEYWORDS = {
        "hutang", "utang", "piutang", "berhutang", "berutang",
        "pinjam", "minjem", "pinjem", "pinjamin", "pinjemin",
        "pinjamkan", "meminjamkan",
    }
    DEBT_QUERY_CTX = {"berapa", "cek", "lihat", "sisa", "daftar", "list", "ada", "punya"}
    DEBT_ACTION_CTX = {"bayar", "lunas", "lunasin", "setor", "kirim", "transfer"}

    BALANCE_KEYWORDS = {"saldo", "balance", "kekayaan", "dana", "aset", "asset"}
    BALANCE_NEGATIVE = {
        "beli", "bayar", "transfer", "kirim", "masuk", "keluar",
        "topup", "deposit", "tarik", "withdraw"
    }

    # 1. PRIORITAS 1: Semua permintaan baca data diarahkan ke dashboard.
    if any(phrase in text_lower for phrase in HISTORY_PHRASES):
        logger.debug(f"Intent DASHBOARD detected by history phrase match: '{text}'")
        return "dashboard"

    if tokens & MENU_KEYWORDS:
        logger.debug(f"Intent HELP detected by menu/help keyword: '{text}'")
        return "help"

    if len(tokens) <= 2 and tokens & GREETING_KEYWORDS:
        logger.debug(f"Intent HELP detected by greeting/test keyword: '{text}'")
        return "help"

    # 2. PRIORITAS 2: Debt Logic
    has_debt_keyword = bool(tokens & DEBT_KEYWORDS)

    if has_debt_keyword:
        has_action = bool(tokens & DEBT_ACTION_CTX)
        has_query = bool(tokens & DEBT_QUERY_CTX)
        has_amount = bool(re.search(r'\b\d+(?:[.,]\d+)?\s*(?:rb|ribu|k|jt|juta)?\b', text_lower))

        if has_action:
            logger.debug(f"Intent TRANSACTION detected: debt payment action '{text}'")
            return "transaction"
        elif has_amount and not has_query:
            logger.debug(f"Intent TRANSACTION detected: debt record with amount '{text}'")
            return "transaction"
        elif has_query or len(tokens) <= 4:
            logger.debug(f"Intent DASHBOARD detected by debt query context: '{text}'")
            return "dashboard"
        logger.debug(f"Intent TRANSACTION detected: debt keyword ambiguous '{text}'")
        return "transaction"

    # 3. PRIORITAS 3: Balance Logic (dengan Negative Lookahead)
    has_balance_keyword = bool(tokens & BALANCE_KEYWORDS)
    has_negative_ctx = bool(tokens & BALANCE_NEGATIVE)

    if has_balance_keyword:
        if has_negative_ctx:
            logger.debug(f"Intent TRANSACTION detected: balance keyword excluded by context '{text}'")
            return "transaction"
        else:
            logger.debug(f"Intent DASHBOARD detected by balance query: '{text}'")
            return "dashboard"

    # 4. PRIORITAS 4: History (single word fallback)
    if any(kw in tokens for kw in {"riwayat", "history", "histori"}):
        logger.debug(f"Intent DASHBOARD detected by history single word fallback: '{text}'")
        return "dashboard"

    has_amount = bool(re.search(r'\b\d+(?:[.,]\d+)?\s*(?:rb|ribu|k|jt|juta)?\b', text_lower))
    has_transaction_keyword = bool(tokens & {
        "makan", "minum", "beli", "belanja", "bayar", "transfer", "kirim",
        "gaji", "gajian", "bonus", "masuk", "keluar", "topup", "deposit",
        "tarik", "withdraw", "ovo", "gopay", "dana", "bca", "mandiri",
        "bni", "bri", "cash", "tunai",
    })

    if has_amount or has_transaction_keyword:
        logger.debug(f"Intent TRANSACTION detected by amount/keyword: '{text}'")
        return "transaction"

    logger.debug(f"Intent HELP detected as non-financial fallback: '{text}'")
    return "help"


def _get_features_message() -> str:
    return (
        "📌 **Fitur Bot Keuangan**\n\n"
        "Bot ini dipakai untuk **mencatat data keuangan** lewat chat. "
        "Untuk melihat saldo, riwayat transaksi, hutang, dan piutang, buka dashboard:\n"
        f"{DASHBOARD_URL}\n\n"
        "⚙️ **Perintah**\n"
        "• `/start` - mulai pakai bot dan daftar akun Telegram\n"
        "• `/phone` - simpan nomor Telegram untuk login dashboard\n"
        "• `/fitur`, `/help`, `/menu`, atau `/bantuan` - tampilkan panduan ini\n"
        "• `/saldo`, `/riwayat`, `/history`, `/hutang`, `/piutang` - buka data di dashboard\n\n"
        "Untuk mencatat transaksi, jangan pakai `/`. Tulis kalimat biasa seperti contoh di bawah.\n\n"
        "💬 **Catat transaksi**\n"
        "Ketik transaksi seperti ngobrol, tanpa format khusus.\n"
        "• `makan siang 25rb pake OVO`\n"
        "• `gajian 5 juta masuk BCA`\n"
        "• `transfer 100rb dari BCA ke Gopay`\n\n"
        "💼 **Atur saldo awal wallet**\n"
        "• `set saldo BCA 2 juta`\n"
        "• `saldo awal Gopay 150rb`\n\n"
        "🏦 **Tabungan, investasi, dan tarik tunai**\n"
        "• `nabung 500rb dari BCA`\n"
        "• `investasi saham 1jt dari BCA`\n"
        "• `tarik tunai 300rb dari BCA`\n\n"
        "🤝 **Catat hutang/piutang**\n"
        "• `hutang ke (nama) 100k`\n"
        "• `(nama) hutang ke saya 100k`\n"
        "• `bayar hutang ke (nama) 50k`\n\n"
        "🧾 **Catat dari struk**\n"
        "Kirim foto struk atau nota belanja. Bot akan membaca item dan menyimpannya sebagai transaksi.\n"
        "Tambahkan caption jika ingin menyimpan catatan tambahan."
    )


def _get_unknown_command_message(command: str) -> str:
    if command in NLP_FEATURE_FORMATS:
        examples = "\n".join(f"• {item}" for item in NLP_FEATURE_FORMATS[command])
        return (
            f"`{command}` bukan format command untuk mencatat data.\n\n"
            "Tulis sebagai kalimat biasa, contoh:\n"
            f"{examples}\n\n"
            "Ketik `/menu` untuk melihat contoh fitur lain."
        )

    suggestions = difflib.get_close_matches(command, KNOWN_COMMANDS, n=3, cutoff=0.45)
    if not suggestions:
        suggestions = ["/menu"]

    suggestion_text = ", ".join(f"`{item}`" for item in suggestions)
    return (
        f"Perintah `{command}` belum dikenali.\n\n"
        f"Mungkin maksud Anda: {suggestion_text}\n"
        "Ketik `/menu` untuk melihat format penulisan dan contoh fitur."
    )


def _get_dashboard_redirect_message() -> str:
    return (
        "Data saldo, riwayat transaksi, hutang, dan piutang sekarang tersedia di dashboard.\n"
        f"Buka: {DASHBOARD_URL}"
    )


class HandleTelegramUpdate:
    def __init__(
        self,
        user_repo: TelegramUserRepo,
        notifier: TelegramNotifier,
        trans_service: TransactionService,
        membership_repo: MembershipRepoPort
    ):
        self.user_repo = user_repo
        self.notifier = notifier
        self.trans_service = trans_service
        self.membership_repo = membership_repo

    async def _check_feature_quota(self, user: TelegramUser, feature_key: str) -> bool:
        """Cek limit fitur (mis. ai_parse_transaction, receipt_scan)
        berdasarkan plan aktif user di membership. True kalau boleh lanjut,
        dan otomatis increment usage-nya."""
        subscription = await self.membership_repo.get_active_subscription(user.id)
        if not subscription:
            # Pengaman: harusnya tidak pernah kejadian karena /start sudah
            # auto-assign free plan, tapi kalau ada data lama/race condition,
            # assign sekarang juga daripada memblokir user tanpa plan sama sekali.
            subscription = await self.membership_repo.ensure_free_subscription(user.id)

        feature = await self.membership_repo.get_plan_feature(subscription.plan_id, feature_key)
        if not feature or not feature.is_enabled:
            await self.notifier.send_message(
                user.id,
                f"⚠️ Fitur ini tidak tersedia di plan Anda saat ini.\n\nUpgrade di {DASHBOARD_URL}",
            )
            return False

        if feature.limit_value is None:
            return True  # unlimited di plan ini

        period_start, period_end = resolve_usage_period(feature.limit_period)
        used = await self.membership_repo.get_usage(user.id, feature_key, period_start, period_end)

        if used >= feature.limit_value:
            await self.notifier.send_message(
                user.id,
                (
                    f"⚠️ Jatah pemakaian fitur ini sudah habis untuk periode ini "
                    f"({used}/{feature.limit_value}).\n\n"
                    f"Upgrade plan Anda di {DASHBOARD_URL}"
                ),
            )
            return False

        await self.membership_repo.increment_usage(user.id, feature_key, period_start, period_end)
        return True

    async def _handle_photo(self, msg, user: TelegramUser, chat_id: int) -> None:
        """Handle pesan foto — proses sebagai struk belanja."""
        from app.application.dtos.extraction import ReceiptContext
        from app.core.di import resolve_process_receipt_usecase

        if not await self._check_feature_quota(user, "receipt_scan"):
            return

        await self.notifier.send_message(chat_id, "📸 Sedang membaca struk, tunggu sebentar...")

        # Ambil foto resolusi tertinggi (terakhir di array)
        largest_photo = msg.photo[-1]
        file_path = await self.notifier.get_file(largest_photo.file_id)
        if not file_path:
            await self.notifier.send_message(chat_id, "❌ Gagal mengunduh foto dari Telegram.")
            return

        image_bytes = await self.notifier.download_file(file_path)
        if not image_bytes:
            await self.notifier.send_message(chat_id, "❌ Gagal mengunduh foto.")
            return

        caption = (msg.caption or "").strip()
        context = ReceiptContext(notes=caption) if caption else None

        usecase = await resolve_process_receipt_usecase()
        result = await usecase.extract_and_save(
            user_id=chat_id,
            image_bytes=image_bytes,
            context=context
        )
        msg_response = result.get("message") or result.get("error", "❌ Gagal memproses struk.")
        await self.notifier.send_message(chat_id, msg_response)

    async def _send_phone_prompt(self, chat_id: int) -> None:
        await self.notifier.send_message(
            chat_id,
            (
                "Bagikan nomor telepon Telegram Anda untuk login dashboard.\n"
                f"Dashboard bisa diakses di {DASHBOARD_URL}"
            ),
            reply_markup={
                "keyboard": [[{"text": "Bagikan nomor telepon", "request_contact": True}]],
                "resize_keyboard": True,
                "one_time_keyboard": True,
            },
        )

    async def _handle_contact(self, msg: Message, user: TelegramUser, chat_id: int) -> None:
        contact = msg.contact
        if not contact:
            return

        if contact.user_id and contact.user_id != chat_id:
            await self.notifier.send_message(chat_id, "Nomor harus berasal dari akun Telegram Anda sendiri.")
            return

        phone_number = _normalize_phone(contact.phone_number)
        if not phone_number:
            await self.notifier.send_message(chat_id, "Nomor telepon tidak valid.")
            return

        user.phone_number = phone_number
        await self.user_repo.upsert(user)
        await self.notifier.send_message(
            chat_id,
            (
                "Nomor telepon tersimpan.\n"
                f"Sekarang Anda bisa login dashboard di {DASHBOARD_URL} dengan nomor itu."
            ),
            reply_markup={"remove_keyboard": True},
        )

    async def execute(self, update: Update) -> None:
        logger.info(f"Update diterima: {update.model_dump()}")

        if not update.message:
            logger.warning("No message in update")
            return

        msg: Message = update.message
        chat_id = msg.chat.id
        text = (msg.text or "").strip()
        command = text.split(maxsplit=1)[0].lower().split("@", 1)[0] if text.startswith("/") else ""

        logger.info(f"Processing message from {chat_id}: '{text}'")

        # --- 1. User Management ---
        user = await self.user_repo.get(chat_id)

        if not user:
            logger.info(f"User baru: {chat_id}")
            user = TelegramUser(
                id=chat_id,
                first_name=msg.chat.first_name,
                username=getattr(msg.chat, "username", None),
                is_active=True
            )
            await self.user_repo.upsert(user)
            # User baru otomatis masuk plan free. Upgrade dilakukan lewat
            # dashboard (payment flow tidak ditangani bot ini sama sekali).
            await self.membership_repo.ensure_free_subscription(chat_id)

        # --- 2. Active State Check ---
        try:
            ensure_active(user)
        except Exception as e:
            await self.notifier.send_message(chat_id, f"⛔ {str(e)}")
            return

        # --- 3. Command Handling (Legacy & System) ---
        if msg.photo:
            logger.info(f"Photo message received from {chat_id}")
            await self._handle_photo(msg, user, chat_id)
            return

        if msg.contact:
            logger.info(f"Contact message received from {chat_id}")
            await self._handle_contact(msg, user, chat_id)
            return

        if command == "/start":
            message = (
                f"Yo {user.first_name}! 🎉\n"
                "Dompetmu layak punya teman yang ngerti—dan yep, itu aku! 😏\n"
                "Ayo catat, pantau, dan rayakan tiap langkah kecilmu menuju finansial sehat! 🚀"
            )
            if not user.phone_number:
                message += (
                    "\n\nBagikan nomor telepon Telegram Anda untuk login dashboard.\n"
                    f"Dashboard bisa diakses di {DASHBOARD_URL}"
                )
            else:
                message += f"\n\nDashboard bisa diakses di {DASHBOARD_URL}"
            await self.notifier.send_message(
                chat_id,
                message,
                reply_markup=None if user.phone_number else {
                    "keyboard": [[{"text": "Bagikan nomor telepon", "request_contact": True}]],
                    "resize_keyboard": True,
                    "one_time_keyboard": True,
                },
            )
            return

        if command == "/phone":
            await self._send_phone_prompt(chat_id)
            return

        if command in HELP_COMMANDS:
            logger.info(f"Feature guide command for user {chat_id}")
            await self.notifier.send_message(chat_id, _get_features_message())
            return

        # Command baca data lama tidak lagi mengambil data dari Telegram.
        if command in DASHBOARD_COMMANDS:
            logger.info(f"Deprecated data command {command} for user {chat_id}, redirecting to dashboard")
            await self.notifier.send_message(chat_id, _get_dashboard_redirect_message())
            return

        if command:
            logger.info(f"Unknown command {command} for user {chat_id}")
            await self.notifier.send_message(chat_id, _get_unknown_command_message(command))
            return

        # --- 4. Intent-Based Routing (Hanya jika IDLE) ---
        if user.current_state == "IDLE":
            intent = _detect_intent(text)
            logger.info(f"User {chat_id} | Detected Intent: [{intent}] | Text: '{text}'")

            if intent == "dashboard":
                logger.info(f"Routing data request to DASHBOARD for user {chat_id}")
                await self.notifier.send_message(chat_id, _get_dashboard_redirect_message())
                return

            if intent == "help":
                logger.info(f"Routing to HELP handler for user {chat_id}")
                await self.notifier.send_message(chat_id, _get_features_message())
                return

            # Default: Transaction via LLM
            logger.info(f"Routing to LLM TRANSACTION handler for user {chat_id}")
            if not await self._check_feature_quota(user, "ai_parse_transaction"):
                return

            response_text = await self.trans_service.process_natural_language(chat_id, text)
            await self.notifier.send_message(chat_id, response_text)
            return

        # --- 5. Fallback: User tidak dalam state IDLE ---
        logger.info(f"User {chat_id} in state '{user.current_state}', forwarding to LLM")
        if not await self._check_feature_quota(user, "ai_parse_transaction"):
            return

        response_text = await self.trans_service.process_natural_language(chat_id, text)
        await self.notifier.send_message(chat_id, response_text)

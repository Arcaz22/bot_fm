import base64
import hashlib
import hmac
import json
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from app.core.settings import settings
from app.domain.llm.ports import LLMPort
from app.infrastructure.db.models import SubDetection, SubPayment, SubSubscription, TrsTransaction
from app.infrastructure.db.repositories.membership import SqlMembershipRepo
from app.infrastructure.db.repositories.subscription import SubscriptionRepo
from app.infrastructure.email.gmail_client import GmailClient, normalize_gmail_message
from app.infrastructure.security.token_crypto import decrypt_token, encrypt_token


CANDIDATE_PATTERN = re.compile(
    r"\b("
    r"invoice|receipt|billing|renewal|subscription|subscribed|payment|paid|trial|"
    r"tagihan|pembayaran|langganan|perpanjangan|berlangganan"
    r")\b",
    re.IGNORECASE,
)
NEGATIVE_PATTERN = re.compile(
    r"\b(otp|login|sign in|security alert|newsletter|promo|promotion|discount|diskon|rekomendasi)\b",
    re.IGNORECASE,
)


class SubscriptionService:
    def __init__(
        self,
        repo: SubscriptionRepo,
        membership_repo: SqlMembershipRepo,
        llm: Optional[LLMPort] = None,
        gmail_client: Optional[GmailClient] = None,
    ):
        self.repo = repo
        self.membership_repo = membership_repo
        self.llm = llm
        self.gmail_client = gmail_client or GmailClient()

    async def ensure_email_account_limit(self, user_id: int) -> None:
        subscription = await self.membership_repo.get_active_subscription(user_id)
        if not subscription:
            subscription = await self.membership_repo.ensure_free_subscription(user_id)

        feature = await self.membership_repo.get_plan_feature(
            subscription.plan_id,
            "subscription_email_account_limit",
        )
        limit = feature.limit_value if feature else 0
        if limit is None:
            return

        used = await self.repo.count_connected_email_accounts(user_id)
        if used >= limit:
            raise ValueError(f"Limit email account plan tercapai ({used}/{limit})")

    def build_google_auth_url(self, user_id: int) -> str:
        state = _sign_oauth_state({"user_id": user_id, "ts": int(datetime.utcnow().timestamp())})
        return self.gmail_client.build_auth_url(state)

    async def handle_google_callback(self, state: str, code: str) -> object:
        data = _verify_oauth_state(state)
        user_id = int(data["user_id"])
        await self.ensure_email_account_limit(user_id)

        token = await self.gmail_client.exchange_code(code)
        access_token = token.get("access_token")
        refresh_token = token.get("refresh_token")
        if not access_token:
            raise ValueError("Google tidak mengembalikan access_token")

        profile = await self.gmail_client.get_profile(access_token)
        email_address = profile.get("emailAddress")
        if not email_address:
            raise ValueError("Gagal membaca email address Gmail")

        scopes = {
            "scope": token.get("scope") or settings.GMAIL_OAUTH_SCOPES,
            "token_type": token.get("token_type"),
            "expires_in": token.get("expires_in"),
        }
        return await self.repo.upsert_email_account(
            user_id=user_id,
            provider="google",
            email_address=email_address,
            encrypted_access_token=encrypt_token(access_token),
            encrypted_refresh_token=encrypt_token(refresh_token),
            scopes=scopes,
        )

    async def scan_email_account(self, user_id: int, email_account_id: int, max_results: Optional[int] = None) -> dict:
        if not self.llm:
            raise ValueError("LLM client belum tersedia untuk scan email")

        account = await self.repo.get_email_account(user_id, email_account_id)
        if not account:
            raise ValueError("Email account tidak ditemukan")
        if account.provider != "google":
            raise ValueError("Provider email belum didukung")
        if account.status == "disconnected":
            raise ValueError("Email account sudah disconnected")

        account.status = "syncing"
        await self.repo.session.commit()

        scanned = 0
        candidates = 0
        created = 0
        skipped = 0
        try:
            access_token = await self._valid_access_token(account)
            message_ids = await self.gmail_client.list_candidate_message_ids(
                access_token,
                max_results or settings.SUBSCRIPTION_SCAN_MAX_EMAILS,
            )

            last_message_id = None
            for message_id in message_ids:
                scanned += 1
                last_message_id = message_id
                if await self.repo.detection_exists(account.id, message_id):
                    skipped += 1
                    continue

                raw_message = await self.gmail_client.get_message(access_token, message_id)
                email = normalize_gmail_message(raw_message)
                if not _is_candidate_email(email):
                    skipped += 1
                    continue

                candidates += 1
                result = await self.llm.parse_subscription_email(email)
                if not result.get("is_subscription") or float(result.get("confidence") or 0) < 0.5:
                    skipped += 1
                    continue

                detection = _detection_from_llm(account, email, result)
                self.repo.session.add(detection)
                created += 1

            await self.repo.session.commit()
            await self.repo.set_email_account_sync_state(account, "connected", sync_cursor=last_message_id)
        except httpx.HTTPStatusError as exc:
            status = "needs_reauth" if exc.response.status_code in {401, 403} else "error"
            await self.repo.set_email_account_sync_state(account, status, error_message=str(exc))
            raise ValueError(f"Gagal scan Gmail: HTTP {exc.response.status_code}") from exc
        except Exception as exc:
            await self.repo.set_email_account_sync_state(account, "error", error_message=str(exc))
            raise

        return {
            "email_account": account,
            "scanned": scanned,
            "candidates": candidates,
            "detections_created": created,
            "detections_skipped": skipped,
        }

    async def _valid_access_token(self, account) -> str:
        access_token = decrypt_token(account.encrypted_access_token)
        refresh_token = decrypt_token(account.encrypted_refresh_token)
        if access_token:
            return access_token
        if not refresh_token:
            raise ValueError("Refresh token Gmail tidak tersedia, user harus reauth")

        token = await self.gmail_client.refresh_access_token(refresh_token)
        new_access_token = token.get("access_token")
        if not new_access_token:
            raise ValueError("Gagal refresh access token Gmail")
        account.encrypted_access_token = encrypt_token(new_access_token)
        await self.repo.session.commit()
        return new_access_token

    async def create_manual_subscription(
        self,
        user_id: int,
        merchant_name: str,
        amount: float,
        currency: str = "IDR",
        billing_period: str = "monthly",
        plan_name: Optional[str] = None,
        next_billing_date: Optional[date] = None,
        wallet_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> SubSubscription:
        subscription = SubSubscription(
            owner_telegram_user_id=user_id,
            merchant_name=merchant_name.strip(),
            plan_name=plan_name.strip() if plan_name else None,
            amount=amount,
            currency=(currency or "IDR").upper(),
            billing_period=billing_period,
            next_billing_date=next_billing_date,
            wallet_id=wallet_id,
            category_id=category_id,
            status="active",
            source="manual",
        )
        return await self.repo.add(subscription)

    async def update_detection(self, user_id: int, detection_id: int, data: dict) -> object:
        detection = await self.repo.get_detection(user_id, detection_id)
        if not detection:
            raise ValueError("Detection tidak ditemukan")
        if detection.status != "needs_review":
            raise ValueError("Detection yang sudah diproses tidak bisa diedit")

        for key, value in data.items():
            setattr(detection, key, value)
        return await self.repo.commit_refresh(detection)

    async def confirm_detection(
        self,
        user_id: int,
        detection_id: int,
        subscription_id: Optional[int] = None,
        wallet_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> SubSubscription:
        detection = await self.repo.get_detection(user_id, detection_id)
        if not detection:
            raise ValueError("Detection tidak ditemukan")
        if detection.status != "needs_review":
            raise ValueError("Detection sudah diproses")
        if not detection.merchant_name or detection.amount is None:
            raise ValueError("Merchant dan amount wajib diisi sebelum confirm")

        if subscription_id:
            subscription = await self.repo.get_subscription(user_id, subscription_id)
            if not subscription:
                raise ValueError("Subscription tujuan merge tidak ditemukan")
            detection.status = "merged"
        else:
            subscription = SubSubscription(
                owner_telegram_user_id=user_id,
                email_account_id=detection.email_account_id,
                merchant_name=detection.merchant_name,
                plan_name=detection.plan_name,
                amount=detection.amount,
                currency=(detection.currency or "IDR").upper(),
                billing_period=detection.billing_period,
                next_billing_date=detection.next_billing_date,
                wallet_id=wallet_id,
                category_id=category_id,
                status="active",
                source="email_scan",
            )
            self.repo.session.add(subscription)
            detection.status = "confirmed"

        await self.repo.session.commit()
        await self.repo.session.refresh(subscription)
        return subscription

    async def ignore_detection(self, user_id: int, detection_id: int) -> object:
        detection = await self.repo.get_detection(user_id, detection_id)
        if not detection:
            raise ValueError("Detection tidak ditemukan")
        if detection.status != "needs_review":
            raise ValueError("Detection sudah diproses")
        detection.status = "ignored"
        return await self.repo.commit_refresh(detection)

    async def update_subscription(self, user_id: int, subscription_id: int, data: dict) -> SubSubscription:
        subscription = await self.repo.get_subscription(user_id, subscription_id)
        if not subscription:
            raise ValueError("Subscription tidak ditemukan")

        for key, value in data.items():
            if key == "currency" and value:
                value = value.upper()
            setattr(subscription, key, value)
        return await self.repo.commit_refresh(subscription)

    async def cancel_subscription(self, user_id: int, subscription_id: int) -> SubSubscription:
        subscription = await self.repo.get_subscription(user_id, subscription_id)
        if not subscription:
            raise ValueError("Subscription tidak ditemukan")
        subscription.status = "cancelled"
        subscription.cancelled_at = datetime.utcnow()
        return await self.repo.commit_refresh(subscription)

    async def mark_paid(
        self,
        user_id: int,
        subscription_id: int,
        amount: Optional[float] = None,
        paid_at: Optional[datetime] = None,
        billing_period_start: Optional[date] = None,
        billing_period_end: Optional[date] = None,
        source: str = "manual",
        create_transaction: bool = False,
        wallet_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> SubPayment:
        subscription = await self.repo.get_subscription(user_id, subscription_id)
        if not subscription:
            raise ValueError("Subscription tidak ditemukan")
        if subscription.status != "active":
            raise ValueError("Hanya subscription active yang bisa ditandai paid")

        paid_at = paid_at or datetime.utcnow()
        payment_amount = amount if amount is not None else float(subscription.amount)
        transaction_id = None

        if create_transaction:
            effective_wallet_id = wallet_id or subscription.wallet_id
            if not effective_wallet_id:
                raise ValueError("wallet_id wajib diisi untuk membuat transaction")
            trx = TrsTransaction(
                owner_telegram_user_id=user_id,
                wallet_id=effective_wallet_id,
                category_id=category_id if category_id is not None else subscription.category_id,
                trx_date=paid_at.date(),
                type="expense",
                amount=payment_amount,
                description=f"Subscription payment: {subscription.merchant_name}",
            )
            self.repo.session.add(trx)
            await self.repo.session.flush()
            transaction_id = trx.id

        payment = SubPayment(
            owner_telegram_user_id=user_id,
            subscription_id=subscription.id,
            transaction_id=transaction_id,
            amount=payment_amount,
            currency=subscription.currency,
            paid_at=paid_at,
            billing_period_start=billing_period_start,
            billing_period_end=billing_period_end,
            source=source,
        )
        self.repo.session.add(payment)

        subscription.next_billing_date = _advance_next_billing_date(
            subscription.next_billing_date or paid_at.date(),
            subscription.billing_period,
        )
        await self.repo.session.commit()
        await self.repo.session.refresh(payment)
        return payment


def _advance_next_billing_date(current: date, billing_period: str) -> Optional[date]:
    if billing_period == "weekly":
        return current + timedelta(days=7)
    if billing_period == "monthly":
        return _add_months(current, 1)
    if billing_period == "yearly":
        return _add_months(current, 12)
    if billing_period == "one_time":
        return None
    return current


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _sign_oauth_state(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    signature = hmac.new(settings.TELEGRAM_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _verify_oauth_state(state: str) -> dict:
    try:
        encoded, signature = state.split(".", 1)
        expected = hmac.new(settings.TELEGRAM_TOKEN.encode(), encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature mismatch")
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        data = json.loads(payload)
        if int(datetime.utcnow().timestamp()) - int(data.get("ts") or 0) > 600:
            raise ValueError("state expired")
        return data
    except Exception as exc:
        raise ValueError("OAuth state tidak valid") from exc


def _is_candidate_email(email: dict) -> bool:
    text = " ".join(
        str(email.get(key) or "")
        for key in ("subject", "sender", "snippet", "body")
    )
    return bool(CANDIDATE_PATTERN.search(text)) and not bool(NEGATIVE_PATTERN.search(text))


def _detection_from_llm(account, email: dict, result: dict) -> SubDetection:
    return SubDetection(
        owner_telegram_user_id=account.owner_telegram_user_id,
        email_account_id=account.id,
        source_message_id=email["message_id"],
        merchant_name=result.get("merchant_name"),
        plan_name=result.get("plan_name"),
        amount=result.get("amount"),
        currency=(result.get("currency") or "IDR").upper(),
        billing_period=result.get("billing_period") or "unknown",
        billing_date=_parse_date(result.get("billing_date")),
        next_billing_date=_parse_date(result.get("next_billing_date")),
        payment_method=result.get("payment_method"),
        confidence=result.get("confidence"),
        status="needs_review",
        raw_subject=email.get("subject"),
        raw_sender=email.get("sender"),
        llm_payload=result,
    )


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None

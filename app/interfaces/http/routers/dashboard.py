import base64
import hashlib
import hmac
import json
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.settings import settings
from app.core.di import get_telegram_client
from app.infrastructure.db.base import get_db
from app.infrastructure.db.models import (
    MstCategory,
    MstCounterparty,
    MstWallet,
    SysTelegramUser,
    TrsDebt,
    TrsTransaction,
)
from app.infrastructure.telegram.client import TelegramClient

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
bearer_scheme = HTTPBearer(auto_error=False)

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
OTP_TTL_SECONDS = 60 * 5
JWT_ALGORITHM = "HS256"
ASSET_ALLOCATION_CATEGORIES = ("Savings", "Investment")
JOINT_SAVINGS_CATEGORY = "Joint Savings"


class DashboardTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: dict[str, Any]


class DashboardOtpRequest(BaseModel):
    phone_number: str


class DashboardOtpVerifyRequest(BaseModel):
    phone_number: str
    otp: str


class DashboardOtpResponse(BaseModel):
    message: str
    expires_in: int = OTP_TTL_SECONDS


class DashboardUser(BaseModel):
    id: int
    first_name: str
    username: Optional[str] = None


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(data: str) -> str:
    return _b64url_encode(hmac.new(settings.TELEGRAM_TOKEN.encode(), data.encode(), hashlib.sha256).digest())


def _normalize_phone(phone_number: str) -> str:
    digits = re.sub(r"\D", "", phone_number or "")
    if digits.startswith("0"):
        return f"62{digits[1:]}"
    return digits


def _hash_otp(otp: str) -> str:
    return hmac.new(settings.TELEGRAM_TOKEN.encode(), otp.encode(), hashlib.sha256).hexdigest()


def _create_access_token(user: SysTelegramUser) -> str:
    expires_at = int((datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)).timestamp())
    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "first_name": user.first_name,
        "username": user.username,
        "exp": expires_at,
    }
    encoded_header = _b64url_encode(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{encoded_header}.{encoded_payload}"
    signature = _sign(signing_input)
    return f"{signing_input}.{signature}"


async def get_current_dashboard_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> SysTelegramUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Authorization harus menggunakan Bearer token")

    token = credentials.credentials.strip()
    try:
        encoded_header, encoded_payload, signature = token.split(".", 2)
        header = json.loads(_b64url_decode(encoded_header))
        if header.get("alg") != JWT_ALGORITHM or header.get("typ") != "JWT":
            raise ValueError("invalid jwt header")

        signing_input = f"{encoded_header}.{encoded_payload}"
        expected_signature = _sign(signing_input)
        if not hmac.compare_digest(signature, expected_signature):
            raise ValueError("invalid signature")

        payload = json.loads(_b64url_decode(encoded_payload))
        if int(payload["exp"]) < int(datetime.now(timezone.utc).timestamp()):
            raise HTTPException(status_code=401, detail="Token sudah expired")

        user_id = int(payload["sub"])
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Token dashboard tidak valid")

    user = await session.get(SysTelegramUser, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User dashboard tidak aktif")
    return user


async def _get_user_by_phone(session: AsyncSession, phone_number: str) -> SysTelegramUser:
    normalized_phone = _normalize_phone(phone_number)
    if not normalized_phone:
        raise HTTPException(status_code=400, detail="Nomor telepon tidak valid")

    stmt = select(SysTelegramUser).where(SysTelegramUser.phone_number == normalized_phone)
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=404, detail="Nomor belum terdaftar. Bagikan nomor telepon lewat bot dulu.")
    return user


def _date_filter(start_date: Optional[date], end_date: Optional[date]):
    filters = []
    if start_date:
        filters.append(TrsTransaction.trx_date >= start_date)
    if end_date:
        filters.append(TrsTransaction.trx_date <= end_date)
    return filters


@router.post("/auth/otp/request", response_model=DashboardOtpResponse)
async def request_dashboard_otp(
    payload: DashboardOtpRequest,
    session: AsyncSession = Depends(get_db),
    telegram: TelegramClient = Depends(get_telegram_client),
):
    """
    Kirim OTP dashboard ke bot Telegram berdasarkan nomor telepon yang sudah terdaftar.
    """
    user = await _get_user_by_phone(session, payload.phone_number)
    otp = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = int((datetime.now(timezone.utc) + timedelta(seconds=OTP_TTL_SECONDS)).timestamp())

    temp_data = dict(user.temp_data or {})
    temp_data["dashboard_otp"] = {
        "hash": _hash_otp(otp),
        "expires_at": expires_at,
    }
    user.temp_data = temp_data
    await session.commit()

    sent = await telegram.send_message(
        user.id,
        f"Kode OTP dashboard Anda: {otp}\nBerlaku 5 menit.",
        parse_mode=None,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="Gagal mengirim OTP ke Telegram")

    return DashboardOtpResponse(message="OTP dikirim ke bot Telegram.")


@router.post("/auth/otp/verify", response_model=DashboardTokenResponse)
async def verify_dashboard_otp(
    payload: DashboardOtpVerifyRequest,
    session: AsyncSession = Depends(get_db),
):
    """
    Verifikasi OTP dari bot Telegram dan buat token dashboard.
    """
    user = await _get_user_by_phone(session, payload.phone_number)
    otp_data = (user.temp_data or {}).get("dashboard_otp") or {}
    expires_at = int(otp_data.get("expires_at") or 0)
    if expires_at < int(datetime.now(timezone.utc).timestamp()):
        raise HTTPException(status_code=401, detail="OTP sudah expired")

    otp = re.sub(r"\D", "", payload.otp or "")
    if not hmac.compare_digest(_hash_otp(otp), otp_data.get("hash") or ""):
        raise HTTPException(status_code=401, detail="OTP tidak valid")

    temp_data = dict(user.temp_data or {})
    temp_data.pop("dashboard_otp", None)
    user.temp_data = temp_data
    await session.commit()

    token = _create_access_token(user)
    return DashboardTokenResponse(
        access_token=token,
        expires_in=TOKEN_TTL_SECONDS,
        user={
            "id": user.id,
            "first_name": user.first_name,
            "username": user.username,
        },
    )


@router.get("/me", response_model=DashboardUser)
async def get_me(current_user: SysTelegramUser = Depends(get_current_dashboard_user)):
    return DashboardUser(id=current_user.id, first_name=current_user.first_name, username=current_user.username)


@router.get("/summary")
async def get_dashboard_summary(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    filters = [
        TrsTransaction.owner_telegram_user_id == current_user.id,
        *_date_filter(start_date, end_date),
    ]

    totals_stmt = select(
        func.coalesce(func.sum(case((TrsTransaction.type == "income", TrsTransaction.amount), else_=0)), 0),
        func.coalesce(func.sum(case((TrsTransaction.type == "expense", TrsTransaction.amount), else_=0)), 0),
        func.coalesce(func.count(TrsTransaction.id), 0),
    ).where(*filters)
    total_income, total_expense, transaction_count = (await session.execute(totals_stmt)).one()

    allocation_stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                MstCategory.name == "Savings",
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                MstCategory.name == "Investment",
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "expense",
                                MstCategory.name == JOINT_SAVINGS_CATEGORY,
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .select_from(TrsTransaction)
        .outerjoin(MstCategory, TrsTransaction.category_id == MstCategory.id)
        .where(*filters)
    )
    total_savings, total_investment, total_joint_savings = (await session.execute(allocation_stmt)).one()
    total_asset_allocation = float(total_savings) + float(total_investment)

    debt_stmt = select(
        func.coalesce(func.sum(case((TrsDebt.direction == "I_OWE", TrsDebt.amount), else_=0)), 0),
        func.coalesce(func.sum(case((TrsDebt.direction == "THEY_OWE", TrsDebt.amount), else_=0)), 0),
    ).where(
        TrsDebt.owner_telegram_user_id == current_user.id,
        TrsDebt.status == "pending",
    )
    total_debt, total_receivable = (await session.execute(debt_stmt)).one()

    wallet_balance = await _get_total_wallet_balance(session, current_user.id)

    return {
        "user_id": current_user.id,
        "period": {"start_date": start_date, "end_date": end_date},
        "total_income": float(total_income),
        "total_expense": float(total_expense),
        "total_joint_savings": float(total_joint_savings),
        "total_savings": float(total_savings),
        "total_investment": float(total_investment),
        "total_asset_allocation": total_asset_allocation,
        "net_cashflow": float(total_income) - float(total_expense),
        "net_after_asset_allocation": float(total_income) - float(total_expense) - total_asset_allocation,
        "wallet_balance": wallet_balance,
        "pending_debt": float(total_debt),
        "pending_receivable": float(total_receivable),
        "transaction_count": int(transaction_count),
    }


@router.get("/charts/cashflow")
async def get_cashflow_chart(
    period: Literal["daily", "monthly"] = Query(default="daily"),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    bucket = func.date_trunc("month", TrsTransaction.trx_date) if period == "monthly" else TrsTransaction.trx_date
    stmt = (
        select(
            bucket.label("period"),
            func.coalesce(func.sum(case((TrsTransaction.type == "income", TrsTransaction.amount), else_=0)), 0).label("income"),
            func.coalesce(func.sum(case((TrsTransaction.type == "expense", TrsTransaction.amount), else_=0)), 0).label("expense"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "expense",
                                MstCategory.name == JOINT_SAVINGS_CATEGORY,
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("joint_savings"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                MstCategory.name == "Savings",
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("savings"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                MstCategory.name == "Investment",
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("investment"),
        )
        .select_from(TrsTransaction)
        .outerjoin(MstCategory, TrsTransaction.category_id == MstCategory.id)
        .where(
            TrsTransaction.owner_telegram_user_id == current_user.id,
            *_date_filter(start_date, end_date),
        )
        .group_by(bucket)
        .order_by(bucket)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "chart": "line",
        "period": period,
        "items": [
            {
                "period": row.period.isoformat(),
                "income": float(row.income),
                "expense": float(row.expense),
                "joint_savings": float(row.joint_savings),
                "savings": float(row.savings),
                "investment": float(row.investment),
                "asset_allocation": float(row.savings) + float(row.investment),
                "net": float(row.income) - float(row.expense),
                "net_after_asset_allocation": (
                    float(row.income)
                    - float(row.expense)
                    - float(row.savings)
                    - float(row.investment)
                ),
            }
            for row in rows
        ],
    }


@router.get("/charts/expenses-by-category")
async def get_expenses_by_category_chart(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    stmt = (
        select(
            func.coalesce(MstCategory.name, "Uncategorized").label("category"),
            func.coalesce(func.sum(TrsTransaction.amount), 0).label("amount"),
        )
        .select_from(TrsTransaction)
        .outerjoin(MstCategory, TrsTransaction.category_id == MstCategory.id)
        .where(
            TrsTransaction.owner_telegram_user_id == current_user.id,
            TrsTransaction.type == "expense",
            *_date_filter(start_date, end_date),
        )
        .group_by(MstCategory.name)
        .order_by(func.sum(TrsTransaction.amount).desc())
    )
    rows = (await session.execute(stmt)).all()
    return {
        "chart": "donut",
        "items": [{"category": row.category, "amount": float(row.amount)} for row in rows],
    }


@router.get("/charts/asset-allocation")
async def get_asset_allocation_chart(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    target_wallet = aliased(MstWallet)
    stmt = (
        select(
            MstCategory.name.label("category"),
            func.coalesce(target_wallet.name, "Unknown").label("target_wallet"),
            func.coalesce(func.sum(TrsTransaction.amount), 0).label("amount"),
        )
        .select_from(TrsTransaction)
        .join(MstCategory, TrsTransaction.category_id == MstCategory.id)
        .outerjoin(target_wallet, TrsTransaction.target_wallet_id == target_wallet.id)
        .where(
            TrsTransaction.owner_telegram_user_id == current_user.id,
            TrsTransaction.type == "transfer",
            MstCategory.name.in_(ASSET_ALLOCATION_CATEGORIES),
            *_date_filter(start_date, end_date),
        )
        .group_by(MstCategory.name, target_wallet.name)
        .order_by(func.sum(TrsTransaction.amount).desc())
    )
    rows = (await session.execute(stmt)).all()
    total = sum(float(row.amount) for row in rows)
    return {
        "chart": "donut",
        "items": [
            {
                "category": row.category,
                "target_wallet": row.target_wallet,
                "amount": float(row.amount),
            }
            for row in rows
        ],
        "total": total,
    }


@router.get("/charts/wallet-balances")
async def get_wallet_balances_chart(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    items = await _get_wallet_balances(session, current_user.id)
    return {"chart": "bar", "items": items}


@router.get("/recent-transactions")
async def get_recent_transactions(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    target_wallet = aliased(MstWallet)
    stmt = (
        select(TrsTransaction, MstWallet.name, MstCategory.name, target_wallet.name)
        .join(MstWallet, TrsTransaction.wallet_id == MstWallet.id)
        .outerjoin(MstCategory, TrsTransaction.category_id == MstCategory.id)
        .outerjoin(target_wallet, TrsTransaction.target_wallet_id == target_wallet.id)
        .where(TrsTransaction.owner_telegram_user_id == current_user.id)
        .order_by(TrsTransaction.trx_date.desc(), TrsTransaction.created_at.desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return {
        "items": [
            {
                "id": trx.id,
                "date": trx.trx_date.isoformat(),
                "type": trx.type,
                "amount": float(trx.amount),
                "description": trx.description,
                "wallet": wallet_name,
                "category": category_name,
                "target_wallet": target_wallet_name,
            }
            for trx, wallet_name, category_name, target_wallet_name in rows
        ]
    }


@router.get("/debts/summary")
async def get_dashboard_debt_summary(
    current_user: SysTelegramUser = Depends(get_current_dashboard_user),
    session: AsyncSession = Depends(get_db),
):
    stmt = (
        select(TrsDebt, MstCounterparty.display_name)
        .join(MstCounterparty, TrsDebt.counterparty_id == MstCounterparty.id)
        .where(
            TrsDebt.owner_telegram_user_id == current_user.id,
            TrsDebt.status == "pending",
        )
        .order_by(TrsDebt.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    return {
        "chart": "stacked_bar",
        "items": [
            {
                "id": debt.id,
                "counterparty": counterparty_name,
                "direction": debt.direction,
                "amount": float(debt.amount),
                "description": debt.description,
                "created_at": debt.created_at.isoformat(),
            }
            for debt, counterparty_name in rows
        ],
    }


async def _get_total_wallet_balance(session: AsyncSession, user_id: int) -> float:
    balances = await _get_wallet_balances(session, user_id)
    return sum(item["balance"] for item in balances)


async def _get_wallet_balances(session: AsyncSession, user_id: int) -> list[dict[str, Any]]:
    stmt = (
        select(
            MstWallet.id,
            MstWallet.name,
            MstWallet.initial_balance,
            func.coalesce(func.sum(case((TrsTransaction.type == "income", TrsTransaction.amount), else_=0)), 0).label("income"),
            func.coalesce(func.sum(case((TrsTransaction.type == "expense", TrsTransaction.amount), else_=0)), 0).label("expense"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                TrsTransaction.wallet_id == MstWallet.id,
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("transfer_out"),
            func.coalesce(
                func.sum(
                    case(
                        (
                            and_(
                                TrsTransaction.type == "transfer",
                                TrsTransaction.target_wallet_id == MstWallet.id,
                            ),
                            TrsTransaction.amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ).label("transfer_in"),
        )
        .select_from(MstWallet)
        .outerjoin(
            TrsTransaction,
            and_(
                TrsTransaction.owner_telegram_user_id == user_id,
                (
                    (TrsTransaction.wallet_id == MstWallet.id)
                    | (TrsTransaction.target_wallet_id == MstWallet.id)
                ),
            ),
        )
        .where(
            MstWallet.owner_telegram_user_id == user_id,
            MstWallet.is_active == True,
        )
        .group_by(MstWallet.id, MstWallet.name, MstWallet.initial_balance)
        .order_by(MstWallet.name)
    )
    rows = (await session.execute(stmt)).all()
    return [
        {
            "wallet_id": row.id,
            "wallet": row.name,
            "initial_balance": float(row.initial_balance),
            "income": float(row.income),
            "expense": float(row.expense),
            "transfer_in": float(row.transfer_in),
            "transfer_out": float(row.transfer_out),
            "balance": float(row.initial_balance)
            + float(row.income)
            - float(row.expense)
            + float(row.transfer_in)
            - float(row.transfer_out),
        }
        for row in rows
    ]

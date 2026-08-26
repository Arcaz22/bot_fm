import base64
import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.core.settings import settings


GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"


class GmailClient:
    def __init__(self, timeout: float = 30) -> None:
        self.timeout = timeout

    def build_auth_url(self, state: str) -> str:
        _require_oauth_settings()
        params = {
            "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
            "redirect_uri": settings.GMAIL_OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": settings.GMAIL_OAUTH_SCOPES,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{GMAIL_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict[str, Any]:
        _require_oauth_settings()
        payload = {
            "code": code,
            "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
            "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
            "redirect_uri": settings.GMAIL_OAUTH_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(GMAIL_TOKEN_URL, data=payload)
            response.raise_for_status()
            return response.json()

    async def refresh_access_token(self, refresh_token: str) -> dict[str, Any]:
        _require_oauth_settings()
        payload = {
            "client_id": settings.GMAIL_OAUTH_CLIENT_ID,
            "client_secret": settings.GMAIL_OAUTH_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(GMAIL_TOKEN_URL, data=payload)
            response.raise_for_status()
            return response.json()

    async def get_profile(self, access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/profile",
                headers=_auth_headers(access_token),
            )
            response.raise_for_status()
            return response.json()

    async def list_candidate_message_ids(self, access_token: str, max_results: int) -> list[str]:
        query = (
            "newer_than:365d "
            "(invoice OR receipt OR billing OR renewal OR subscription OR subscribed "
            "OR payment OR paid OR trial OR tagihan OR pembayaran OR langganan)"
        )
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages",
                headers=_auth_headers(access_token),
                params={"q": query, "maxResults": max_results},
            )
            response.raise_for_status()
            body = response.json()
            return [item["id"] for item in body.get("messages", [])]

    async def get_message(self, access_token: str, message_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{GMAIL_API_BASE}/users/me/messages/{message_id}",
                headers=_auth_headers(access_token),
                params={"format": "full"},
            )
            response.raise_for_status()
            return response.json()


def _require_oauth_settings() -> None:
    missing = [
        name for name, value in {
            "GMAIL_OAUTH_CLIENT_ID": settings.GMAIL_OAUTH_CLIENT_ID,
            "GMAIL_OAUTH_CLIENT_SECRET": settings.GMAIL_OAUTH_CLIENT_SECRET,
            "GMAIL_OAUTH_REDIRECT_URI": settings.GMAIL_OAUTH_REDIRECT_URI,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Konfigurasi OAuth Gmail belum lengkap: {', '.join(missing)}")


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def normalize_gmail_message(message: dict[str, Any]) -> dict[str, Any]:
    payload = message.get("payload") or {}
    headers = {item.get("name", "").lower(): item.get("value", "") for item in payload.get("headers", [])}
    date_value = _parse_email_date(headers.get("date"))
    body = _extract_body(payload)
    snippet = html.unescape(message.get("snippet") or "")

    return {
        "message_id": message.get("id"),
        "thread_id": message.get("threadId"),
        "subject": headers.get("subject") or "",
        "sender": headers.get("from") or "",
        "date": date_value.isoformat() if date_value else None,
        "snippet": snippet,
        "body": body[:4000],
    }


def _parse_email_date(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _extract_body(payload: dict[str, Any]) -> str:
    parts = payload.get("parts") or []
    if parts:
        chunks = [_extract_body(part) for part in parts]
        return "\n".join(chunk for chunk in chunks if chunk).strip()

    body = payload.get("body") or {}
    data = body.get("data")
    if not data:
        return ""
    try:
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="ignore")
        return html.unescape(decoded)
    except Exception:
        return ""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, Query, status
from google.cloud.firestore_v1 import AsyncClient
from starlette.responses import RedirectResponse

from app.config import Settings
from app.deps import get_app_settings, get_firestore
from app.errors import ApiError
from app.repositories import oauth_state
from app.repositories.google import delete_google_connection, get_google_connection, upsert_google_connection
from app.schemas import GoogleAuthStatus

router = APIRouter(prefix="/api/auth/google", tags=["google-auth"])

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_TTL_SECONDS = 10 * 60
SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def require_google_config(settings: Settings) -> None:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "not_configured",
            "Google OAuth client id and secret are not configured.",
        )


@router.get("/start")
async def start_google_auth(
    org_id: Annotated[str, Query(min_length=1)],
    db: AsyncClient = Depends(get_firestore),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    require_google_config(settings)
    state = secrets.token_urlsafe(32)
    await oauth_state.remember_state(db, state, org_id, ttl_seconds=STATE_TTL_SECONDS)
    params = {
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return RedirectResponse(f"{AUTH_URL}?{urlencode(params)}", status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def google_auth_callback(
    code: Annotated[str, Query(min_length=1)],
    state: Annotated[str, Query(min_length=1)],
    db: AsyncClient = Depends(get_firestore),
    settings: Settings = Depends(get_app_settings),
) -> RedirectResponse:
    require_google_config(settings)
    org_id = await oauth_state.consume_state(db, state)
    if org_id is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_state", "Google OAuth state is invalid.")

    token_payload = await exchange_code_for_token(code, settings)
    email = await fetch_google_email(token_payload)
    await upsert_google_connection(db, org_id, google_connection_payload(token_payload, email))
    return RedirectResponse(
        f"{settings.frontend_base_url.rstrip('/')}/{settings.google_oauth_success_path.strip('/')}"
    )


@router.get("/status", response_model=GoogleAuthStatus)
async def google_auth_status(
    org_id: Annotated[str, Query(min_length=1)],
    db: AsyncClient = Depends(get_firestore),
) -> GoogleAuthStatus:
    connection = await get_google_connection(db, org_id)
    return GoogleAuthStatus(
        connected=connection is not None,
        email=connection.get("email") if connection else None,
    )


@router.post("/disconnect")
async def disconnect_google(
    org_id: Annotated[str, Query(min_length=1)],
    db: AsyncClient = Depends(get_firestore),
) -> dict[str, bool]:
    await delete_google_connection(db, org_id)
    return {"ok": True}


async def exchange_code_for_token(code: str, settings: Settings) -> dict[str, Any]:
    body = {
        "code": code,
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "redirect_uri": settings.google_oauth_redirect_uri,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(TOKEN_URL, data=body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "google_oauth_failed",
            "Google OAuth token exchange failed.",
        ) from exc

    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "google_oauth_failed",
            "Google OAuth token response was invalid.",
        )
    return payload


async def fetch_google_email(token_payload: dict[str, Any]) -> str | None:
    access_token = token_payload.get("access_token")
    if not isinstance(access_token, str):
        return None
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
            response.raise_for_status()
    except httpx.HTTPError:
        return None

    payload = response.json()
    if isinstance(payload, dict) and isinstance(payload.get("email"), str):
        return str(payload["email"])
    return None


def google_connection_payload(token_payload: dict[str, Any], email: str | None) -> dict[str, Any]:
    now = datetime.now(UTC)
    expires_in = token_payload.get("expires_in")
    expires_delta = int(expires_in) if isinstance(expires_in, int) else 3600
    access_token = token_payload["access_token"]
    if not isinstance(access_token, str):
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "google_oauth_failed",
            "Google OAuth token response was invalid.",
        )

    refresh_token = token_payload.get("refresh_token")
    scope = token_payload.get("scope")
    return {
        "email": email,
        "access_token": access_token,
        "refresh_token": refresh_token if isinstance(refresh_token, str) else None,
        "scope": scope if isinstance(scope, str) else None,
        "expires_at": now + timedelta(seconds=expires_delta),
    }

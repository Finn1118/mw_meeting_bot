from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from google.cloud.firestore_v1 import AsyncClient
from httpx import AsyncClient as HttpAsyncClient
from pytest_httpx import HTTPXMock

from app.config import Settings
from app.deps import get_app_settings
from app.main import app
from app.repositories.google import get_google_connection, upsert_google_connection
from app.routers.google_auth import TOKEN_URL, USERINFO_URL

ORG_ID = "org_123"


def google_settings() -> Settings:
    return Settings(
        recall_api_key="test-key",
        google_oauth_client_id="client-id",
        google_oauth_client_secret="client-secret",
        google_oauth_redirect_uri="http://testserver/api/auth/google/callback",
        frontend_base_url="http://frontend.test",
        disable_gcs_upload=True,
    )


def google_settings_without_credentials() -> Settings:
    return Settings(
        recall_api_key="test-key",
        google_oauth_client_id=None,
        google_oauth_client_secret=None,
        disable_gcs_upload=True,
    )


@pytest.mark.asyncio
async def test_google_status_when_not_connected(client: HttpAsyncClient) -> None:
    response = await client.get(f"/api/auth/google/status?org_id={ORG_ID}")

    assert response.status_code == 200
    assert response.json() == {"connected": False, "email": None}


@pytest.mark.asyncio
async def test_google_start_returns_not_configured_without_credentials(client: HttpAsyncClient) -> None:
    app.dependency_overrides[get_app_settings] = google_settings_without_credentials

    response = await client.get(f"/api/auth/google/start?org_id={ORG_ID}")

    assert response.status_code == 503
    assert response.json() == {
        "error": "not_configured",
        "message": "Google OAuth client id and secret are not configured.",
    }


@pytest.mark.asyncio
async def test_google_callback_persists_tokens(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
    httpx_mock: HTTPXMock,
) -> None:
    app.dependency_overrides[get_app_settings] = google_settings
    start_response = await client.get(f"/api/auth/google/start?org_id={ORG_ID}", follow_redirects=False)
    query = parse_qs(urlparse(start_response.headers["location"]).query)
    state = query["state"][0]

    httpx_mock.add_response(
        method="POST",
        url=TOKEN_URL,
        json={
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly",
        },
    )
    httpx_mock.add_response(
        method="GET",
        url=USERINFO_URL,
        json={"email": "finn@example.com"},
    )

    response = await client.get(
        f"/api/auth/google/callback?code=auth-code&state={state}",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == "http://frontend.test/meetings/calendar"
    connection = await get_google_connection(firestore_client, ORG_ID)

    assert connection is not None
    assert connection["email"] == "finn@example.com"
    assert connection["access_token"] == "access-token"
    assert connection["refresh_token"] == "refresh-token"
    assert connection["expires_at"].replace(tzinfo=UTC) > datetime.now(UTC)


@pytest.mark.asyncio
async def test_google_disconnect_deletes_connection(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
) -> None:
    now = datetime.now(UTC)
    await upsert_google_connection(
        firestore_client,
        ORG_ID,
        {
            "email": "finn@example.com",
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "scope": "calendar",
            "expires_at": now,
        },
    )

    response = await client.post(f"/api/auth/google/disconnect?org_id={ORG_ID}")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert await get_google_connection(firestore_client, ORG_ID) is None

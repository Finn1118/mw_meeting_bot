import re
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from app.routers.google_auth import TOKEN_URL
from app.services.url_parser import parse_meeting_url

CALENDAR_EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
REFRESH_WINDOW = timedelta(seconds=60)
URL_RE = re.compile(r"https?://[^\s<>)\"']+")


class GoogleCalendarError(Exception):
    pass


async def ensure_fresh_token(
    connection: dict[str, object],
    settings: Settings,
) -> tuple[str, dict[str, object] | None]:
    expires_at = connection["expires_at"]
    if not isinstance(expires_at, datetime):
        raise GoogleCalendarError("missing_expiration")
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at > datetime.now(UTC) + REFRESH_WINDOW:
        access_token = connection.get("access_token")
        if not isinstance(access_token, str):
            raise GoogleCalendarError("missing_access_token")
        return access_token, None

    refresh_token = connection.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise GoogleCalendarError("missing_refresh_token")

    body = {
        "client_id": settings.google_oauth_client_id,
        "client_secret": settings.google_oauth_client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(TOKEN_URL, data=body)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("refresh_failed") from exc

    payload = response.json()
    access_token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(access_token, str):
        raise GoogleCalendarError("invalid_refresh_response")

    expires_in = payload.get("expires_in")
    expires_delta = int(expires_in) if isinstance(expires_in, int) else 3600
    updates = {
        "access_token": access_token,
        "expires_at": datetime.now(UTC) + timedelta(seconds=expires_delta),
        "updated_at": datetime.now(UTC),
    }
    return access_token, updates


async def list_primary_events(
    access_token: str,
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    params = {
        "singleEvents": "true",
        "orderBy": "startTime",
        "timeMin": time_min.isoformat().replace("+00:00", "Z"),
        "timeMax": time_max.isoformat().replace("+00:00", "Z"),
        "maxResults": "50",
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                CALENDAR_EVENTS_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise GoogleCalendarError("events_failed") from exc

    payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def extract_meeting_link(event: dict[str, Any]) -> dict[str, str] | None:
    for candidate in meeting_link_candidates(event):
        try:
            parsed = parse_meeting_url(candidate)
        except ValueError:
            continue
        return {"platform": parsed.platform, "url": parsed.normalized_url}
    return None


def meeting_link_candidates(event: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    hangout_link = event.get("hangoutLink")
    if isinstance(hangout_link, str):
        candidates.append(hangout_link)

    conference_data = event.get("conferenceData")
    if isinstance(conference_data, dict):
        entry_points = conference_data.get("entryPoints")
        if isinstance(entry_points, list):
            for entry in entry_points:
                if isinstance(entry, dict) and isinstance(entry.get("uri"), str):
                    candidates.append(entry["uri"])

    for field_name in ("location", "description"):
        value = event.get(field_name)
        if isinstance(value, str):
            candidates.extend(extract_urls(value))

    return candidates


def extract_urls(value: str) -> list[str]:
    return [match.group(0).rstrip(".,;]") for match in URL_RE.finditer(value)]

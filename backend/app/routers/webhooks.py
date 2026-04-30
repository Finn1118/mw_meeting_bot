import json
from binascii import Error as BinasciiError
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from svix.webhooks import Webhook, WebhookVerificationError

from app.config import Settings
from app.deps import get_app_settings, get_recall_client, get_session
from app.errors import ApiError
from app.events import bus
from app.models import Meeting, WebhookLog
from app.services.recall import RecallClient
from app.services.transcript import parse_transcript

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])

STATUS_BY_EVENT = {
    "bot.joining_call": "joining",
    "bot.in_waiting_room": "waiting_room",
    "bot.in_call_not_recording": "in_call_not_recording",
    "bot.in_call_recording": "recording",
    "bot.recording_permission_denied": "failed",
    "bot.call_ended": "processing",
    "bot.done": "processing",
    "transcript.failed": "failed",
    "bot.fatal": "failed",
}


@router.post("/recall")
async def recall_webhook(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    recall_client: RecallClient = Depends(get_recall_client),
) -> dict[str, bool]:
    raw_body = await request.body()
    headers = dict(request.headers)
    event_id = request.headers.get("webhook-id")
    if event_id is None:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_webhook", "Missing Svix webhook id.")

    try:
        payload = Webhook(settings.recall_webhook_secret).verify(raw_body, headers)
    except (WebhookVerificationError, BinasciiError) as exc:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_signature", "Invalid webhook signature.") from exc

    if not isinstance(payload, dict):
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_payload", "Webhook payload must be an object.")

    existing_log = await session.scalar(select(WebhookLog).where(WebhookLog.event_id == event_id))
    if existing_log is not None:
        return {"ok": True}

    event_type = str(payload.get("event", ""))
    data = payload.get("data", {})
    data_dict = data if isinstance(data, dict) else {}
    bot_id = extract_bot_id(data_dict)

    session.add(
        WebhookLog(
            bot_id=bot_id,
            event_type=event_type,
            event_id=event_id,
            payload=payload,
            received_at=datetime.now(UTC),
        )
    )

    meeting = await find_meeting_for_webhook(session, bot_id)
    if meeting is not None:
        await dispatch_webhook_event(
            event_type=event_type,
            data=data_dict,
            meeting=meeting,
            session=session,
            settings=settings,
            recall_client=recall_client,
        )

    await session.commit()
    if meeting is not None:
        await bus.publish(
            meeting.id,
            {"meeting_id": meeting.id, "status": meeting.status, "event": event_type},
        )

    return {"ok": True}


async def find_meeting_for_webhook(session: AsyncSession, bot_id: str | None) -> Meeting | None:
    if bot_id is None:
        return None
    return await session.scalar(select(Meeting).where(Meeting.bot_id == bot_id))


async def dispatch_webhook_event(
    *,
    event_type: str,
    data: dict[str, Any],
    meeting: Meeting,
    session: AsyncSession,
    settings: Settings,
    recall_client: RecallClient,
) -> None:
    now = datetime.now(UTC)
    meeting.updated_at = now

    if event_type in STATUS_BY_EVENT:
        if event_type == "bot.done" and meeting.status in {"complete", "failed"}:
            return
        meeting.status = STATUS_BY_EVENT[event_type]
        if event_type in {"bot.recording_permission_denied", "bot.fatal", "transcript.failed"}:
            meeting.sub_code = extract_sub_code(data, event_type)
        if event_type == "bot.call_ended":
            meeting.ended_at = now
        return

    if event_type == "recording.done":
        meeting.recording_id = extract_nested_id(data, "recording")
        return

    if event_type == "transcript.done":
        transcript_id = extract_nested_id(data, "transcript")
        if transcript_id is None:
            meeting.status = "failed"
            meeting.sub_code = "missing_transcript_id"
            return

        meeting.transcript_id = transcript_id
        transcript_metadata = await recall_client.get_transcript(transcript_id)
        download_url = extract_download_url(transcript_metadata)
        raw_transcript = await recall_client.download_transcript_json(download_url)
        transcript_path = save_transcript_json(settings.blobs_dir, meeting.id, raw_transcript)
        await parse_transcript(meeting.id, raw_transcript, session)
        meeting.transcript_path = str(transcript_path)
        meeting.status = "complete"


def extract_bot_id(data: dict[str, Any]) -> str | None:
    direct = data.get("bot_id")
    if isinstance(direct, str):
        return direct
    return extract_nested_id(data, "bot")


def extract_nested_id(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if isinstance(value, dict) and isinstance(value.get("id"), str):
        return value["id"]
    return None


def extract_sub_code(data: dict[str, Any], event_type: str) -> str:
    for key in ("sub_code", "code", "reason"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    if event_type == "bot.recording_permission_denied":
        return "recording_permission_denied"
    return event_type.replace(".", "_")


def extract_download_url(transcript_metadata: dict[str, object]) -> str:
    data = transcript_metadata.get("data")
    if isinstance(data, dict) and isinstance(data.get("download_url"), str):
        return data["download_url"]
    raise ValueError("missing_transcript_download_url")


def save_transcript_json(blobs_dir: str, meeting_id: str, raw_transcript: list[object]) -> Path:
    directory = Path(blobs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"transcript_{meeting_id}.json"
    path.write_text(json.dumps(raw_transcript), encoding="utf-8")
    return path

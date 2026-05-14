from datetime import UTC, datetime
from typing import Any

from google.cloud.firestore_v1 import AsyncClient


TERMINAL_STATUSES = {"complete", "failed"}


def utc_now() -> datetime:
    return datetime.now(UTC)


def org_ref(db: AsyncClient, org_id: str) -> Any:
    return db.collection("organizations").document(org_id)


def meetings_ref(db: AsyncClient, org_id: str) -> Any:
    return org_ref(db, org_id).collection("meetings")


def meeting_ref(db: AsyncClient, org_id: str, meeting_id: str) -> Any:
    return meetings_ref(db, org_id).document(meeting_id)


def segments_ref(db: AsyncClient, org_id: str, meeting_id: str) -> Any:
    return meeting_ref(db, org_id, meeting_id).collection("segments")


def _org_id_from_doc_path(path: str) -> str | None:
    parts = path.split("/")
    if len(parts) >= 4 and parts[0] == "organizations" and parts[2] == "meetings":
        return parts[1]
    return None


def _public_meeting_data(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": data["id"],
        "meeting_url": data["meeting_url"],
        "platform": data["platform"],
        "title": data.get("title"),
        "org_id": data["org_id"],
        "created_by_uid": data.get("created_by_uid"),
        "platform_conversation_id": data.get("platform_conversation_id"),
        "bot_id": data.get("bot_id"),
        "recording_id": data.get("recording_id"),
        "transcript_id": data.get("transcript_id"),
        "status": data["status"],
        "sub_code": data.get("sub_code"),
        "started_at": data.get("started_at"),
        "ended_at": data.get("ended_at"),
        "duration_sec": data.get("duration_sec"),
        "transcript_path": data.get("transcript_path"),
        "recording_path": data.get("recording_path"),
        "created_at": data["created_at"],
        "updated_at": data["updated_at"],
        "deleted_at": data.get("deleted_at"),
        "participants": data.get("participants", []),
        "segments": data.get("segments", []),
    }


async def create_meeting(db: AsyncClient, data: dict[str, Any]) -> dict[str, Any]:
    await meeting_ref(db, data["org_id"], data["id"]).set(data)
    created = await get_meeting(db, data["org_id"], data["id"])
    if created is None:
        raise RuntimeError("created_meeting_not_found")
    return created


async def get_meeting(db: AsyncClient, org_id: str, meeting_id: str) -> dict[str, Any] | None:
    snapshot = await meeting_ref(db, org_id, meeting_id).get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    if data.get("deleted_at") is not None:
        return None

    segment_docs = [
        doc
        async for doc in segments_ref(db, org_id, meeting_id).order_by("start_ms").stream()
    ]
    data["segments"] = [doc.to_dict() or {} for doc in segment_docs]
    return _public_meeting_data(data)


async def list_meetings(
    db: AsyncClient,
    org_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
    platform: str | None = None,
) -> dict[str, Any]:
    docs = [doc async for doc in meetings_ref(db, org_id).stream()]
    items: list[dict[str, Any]] = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("deleted_at") is not None:
            continue
        if platform is not None and data.get("platform") != platform:
            continue
        item = await get_meeting(db, org_id, data["id"])
        if item is not None:
            items.append(item)

    def sort_key(item: dict[str, Any]) -> tuple[bool, datetime]:
        when = item.get("started_at") or item.get("created_at")
        if not isinstance(when, datetime):
            when = datetime.min.replace(tzinfo=UTC)
        return (item.get("started_at") is not None, when)

    items.sort(key=sort_key, reverse=True)
    return {"items": items[offset : offset + limit], "total": len(items)}


async def update_meeting(
    db: AsyncClient,
    org_id: str,
    meeting_id: str,
    updates: dict[str, Any],
) -> dict[str, Any] | None:
    existing = await get_meeting(db, org_id, meeting_id)
    if existing is None:
        return None
    updates["updated_at"] = utc_now()
    await meeting_ref(db, org_id, meeting_id).update(updates)
    return await get_meeting(db, org_id, meeting_id)


async def soft_delete_meeting(db: AsyncClient, org_id: str, meeting_id: str) -> bool:
    existing = await get_meeting(db, org_id, meeting_id)
    if existing is None:
        return False
    now = utc_now()
    await meeting_ref(db, org_id, meeting_id).update({"deleted_at": now, "updated_at": now})
    return True


async def list_active_polling_meetings(db: AsyncClient) -> list[dict[str, Any]]:
    docs = [doc async for doc in db.collection_group("meetings").stream()]
    meetings: list[dict[str, Any]] = []
    for doc in docs:
        data = doc.to_dict() or {}
        if data.get("deleted_at") is not None:
            continue
        if not data.get("bot_id"):
            continue
        if data.get("status") in TERMINAL_STATUSES:
            continue
        org_id = data.get("org_id") or _org_id_from_doc_path(doc.reference.path)
        if not isinstance(org_id, str):
            continue
        data["org_id"] = org_id
        meetings.append(_public_meeting_data(data))
    return meetings


async def add_transcript_data(
    db: AsyncClient,
    org_id: str,
    meeting_id: str,
    participants: list[dict[str, Any]],
    segments: list[dict[str, Any]],
) -> None:
    batch = db.batch()
    batch.update(meeting_ref(db, org_id, meeting_id), {"participants": participants})
    for index, segment in enumerate(segments):
        segment_id = f"{segment['start_ms']:012d}_{index:04d}"
        batch.set(segments_ref(db, org_id, meeting_id).document(segment_id), segment)
    await batch.commit()


async def update_participant_display_name(
    db: AsyncClient,
    org_id: str,
    meeting_id: str,
    participant_id: int,
    display_name: str,
) -> dict[str, Any] | None:
    meeting = await get_meeting(db, org_id, meeting_id)
    if meeting is None:
        return None

    participants = list(meeting.get("participants", []))
    participant: dict[str, Any] | None = None
    for item in participants:
        if item.get("id") == participant_id:
            item["display_name"] = display_name
            participant = item
            break
    if participant is None:
        return None

    batch = db.batch()
    batch.update(
        meeting_ref(db, org_id, meeting_id),
        {"participants": participants, "updated_at": utc_now()},
    )
    async for doc in segments_ref(db, org_id, meeting_id).stream():
        data = doc.to_dict() or {}
        if data.get("participant_id") == participant_id:
            batch.update(doc.reference, {"speaker_label": display_name})
    await batch.commit()
    return participant

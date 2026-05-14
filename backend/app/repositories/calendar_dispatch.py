from datetime import datetime
from typing import Any

from google.cloud.firestore_v1 import AsyncClient


def dispatch_ref(db: AsyncClient, org_id: str, google_event_id: str) -> Any:
    return (
        db.collection("organizations")
        .document(org_id)
        .collection("calendarDispatches")
        .document(google_event_id)
    )


async def get_dispatch(db: AsyncClient, org_id: str, google_event_id: str) -> dict[str, Any] | None:
    snapshot = await dispatch_ref(db, org_id, google_event_id).get()
    return snapshot.to_dict() if snapshot.exists else None


async def is_event_dispatched(db: AsyncClient, org_id: str, google_event_id: str) -> bool:
    return await get_dispatch(db, org_id, google_event_id) is not None


async def record_dispatch(
    db: AsyncClient,
    org_id: str,
    google_event_id: str,
    *,
    meeting_id: str | None,
    meeting_url: str,
    event_title: str | None,
    event_start: datetime | None,
    dispatched_at: datetime,
    status: str,
) -> None:
    await dispatch_ref(db, org_id, google_event_id).set(
        {
            "google_event_id": google_event_id,
            "meeting_id": meeting_id,
            "meeting_url": meeting_url,
            "event_title": event_title,
            "event_start": event_start,
            "dispatched_at": dispatched_at,
            "status": status,
        }
    )

from datetime import UTC, datetime, timedelta
from typing import Any

from google.cloud.firestore_v1 import AsyncClient


COLLECTION = "oauth_states"


def _state_ref(db: AsyncClient, state: str) -> Any:
    return db.collection(COLLECTION).document(state)


async def remember_state(
    db: AsyncClient,
    state: str,
    org_id: str,
    ttl_seconds: int = 600,
) -> None:
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
    await _state_ref(db, state).set({"org_id": org_id, "expires_at": expires_at})


async def consume_state(db: AsyncClient, state: str) -> str | None:
    ref = _state_ref(db, state)
    snapshot = await ref.get()
    if not snapshot.exists:
        return None
    data = snapshot.to_dict() or {}
    await ref.delete()

    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime):
        normalized = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
        if normalized <= datetime.now(UTC):
            return None

    org_id = data.get("org_id")
    return org_id if isinstance(org_id, str) and org_id else None

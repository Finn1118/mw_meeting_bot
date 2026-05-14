from datetime import UTC, datetime
from typing import Any

from google.cloud.firestore_v1 import AsyncClient


GOOGLE_INTEGRATION_ID = "google"


def utc_now() -> datetime:
    return datetime.now(UTC)


def google_ref(db: AsyncClient, org_id: str) -> Any:
    return (
        db.collection("organizations")
        .document(org_id)
        .collection("integrations")
        .document(GOOGLE_INTEGRATION_ID)
    )


async def get_google_connection(db: AsyncClient, org_id: str) -> dict[str, Any] | None:
    snapshot = await google_ref(db, org_id).get()
    return snapshot.to_dict() if snapshot.exists else None


async def upsert_google_connection(
    db: AsyncClient,
    org_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now()
    existing = await get_google_connection(db, org_id)
    if existing is None:
        payload = {"auto_dispatch_enabled": False, **data, "created_at": now, "updated_at": now}
        await google_ref(db, org_id).set(payload)
        return payload

    payload = {**existing, **data, "updated_at": now}
    await google_ref(db, org_id).set(payload)
    return payload


async def delete_google_connection(db: AsyncClient, org_id: str) -> None:
    await google_ref(db, org_id).delete()


async def set_auto_dispatch(
    db: AsyncClient,
    org_id: str,
    enabled: bool,
) -> dict[str, Any] | None:
    connection = await get_google_connection(db, org_id)
    if connection is None:
        return None
    connection["auto_dispatch_enabled"] = enabled
    connection["updated_at"] = utc_now()
    await google_ref(db, org_id).set(connection)
    return connection


async def list_auto_dispatch_connections(db: AsyncClient) -> list[tuple[str, dict[str, Any]]]:
    docs = [doc async for doc in db.collection_group("integrations").stream()]
    connections: list[tuple[str, dict[str, Any]]] = []
    for doc in docs:
        if doc.id != GOOGLE_INTEGRATION_ID:
            continue
        data = doc.to_dict() or {}
        if not data.get("auto_dispatch_enabled"):
            continue
        parts = doc.reference.path.split("/")
        if len(parts) >= 4 and parts[0] == "organizations":
            connections.append((parts[1], data))
    return connections

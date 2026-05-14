from datetime import UTC, datetime

import pytest
from google.cloud.firestore_v1 import AsyncClient
from httpx import AsyncClient as HttpAsyncClient

from app.repositories import meetings as meetings_repo
from app.services.recall import RecallApiError
from tests.conftest import FakeRecallClient

ORG_ID = "org_123"


def now() -> datetime:
    return datetime.now(UTC)


async def seed_meeting(
    db: AsyncClient,
    *,
    meeting_id: str = "meeting_123",
    org_id: str = ORG_ID,
    platform: str = "meet",
    status: str = "complete",
) -> dict[str, object]:
    timestamp = now()
    meeting = {
        "id": meeting_id,
        "meeting_url": "https://meet.google.com/abc-defg-hij",
        "platform": platform,
        "title": None,
        "org_id": org_id,
        "created_by_uid": None,
        "platform_conversation_id": None,
        "bot_id": None,
        "recording_id": None,
        "transcript_id": None,
        "status": status,
        "sub_code": None,
        "started_at": None,
        "ended_at": None,
        "duration_sec": None,
        "transcript_path": None,
        "recording_path": None,
        "deleted_at": None,
        "participants": [],
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    return await meetings_repo.create_meeting(db, meeting)


@pytest.mark.asyncio
async def test_create_meeting_happy_path(
    client: HttpAsyncClient,
    fake_recall_client: FakeRecallClient,
) -> None:
    response = await client.post(
        "/api/meetings",
        json={
            "meeting_url": "https://meet.google.com/abc-defg-hij",
            "title": "Standup",
            "org_id": ORG_ID,
            "created_by_uid": "user_123",
            "platform_conversation_id": "conv_123",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meeting_url"] == "https://meet.google.com/abc-defg-hij"
    assert body["platform"] == "meet"
    assert body["title"] == "Standup"
    assert body["org_id"] == ORG_ID
    assert body["created_by_uid"] == "user_123"
    assert body["platform_conversation_id"] == "conv_123"
    assert body["bot_id"] == "bot_test_123"
    assert body["status"] == "bot_created"
    assert fake_recall_client.created_bot_requests == [
        ("https://meet.google.com/abc-defg-hij", "Test Notetaker")
    ]


@pytest.mark.asyncio
async def test_create_meeting_requires_org_id(client: HttpAsyncClient) -> None:
    response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_meetings_filters_by_org_id(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
) -> None:
    await seed_meeting(firestore_client, meeting_id="meeting_org_1", org_id="org_1")
    await seed_meeting(firestore_client, meeting_id="meeting_org_2", org_id="org_2")

    response = await client.get("/api/meetings?org_id=org_1")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == "meeting_org_1"


@pytest.mark.asyncio
async def test_org_scoped_get_rejects_other_org(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
) -> None:
    await seed_meeting(firestore_client, meeting_id="meeting_123", org_id="org_1")

    response = await client.get("/api/meetings/meeting_123?org_id=org_2")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "message": "Meeting not found."}


@pytest.mark.asyncio
async def test_request_id_header_is_echoed(client: HttpAsyncClient) -> None:
    response = await client.get("/api/health", headers={"X-Request-Id": "req_test_123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req_test_123"


@pytest.mark.asyncio
async def test_create_meeting_rejects_invalid_url(client: HttpAsyncClient) -> None:
    response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://example.com", "org_id": ORG_ID},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": "invalid_url",
        "message": "Meeting URL is not supported.",
    }


@pytest.mark.asyncio
async def test_create_meeting_marks_failed_on_recall_error(
    client: HttpAsyncClient,
    fake_recall_client: FakeRecallClient,
) -> None:
    fake_recall_client.create_bot_error = RecallApiError(500, "server error")

    response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij", "org_id": ORG_ID},
    )

    assert response.status_code == 502
    assert response.json() == {
        "error": "recall_api_error",
        "message": "Recall API request failed.",
    }

    list_response = await client.get(f"/api/meetings?org_id={ORG_ID}")
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["status"] == "failed"
    assert item["sub_code"] == "dispatch_error"


@pytest.mark.asyncio
async def test_get_missing_meeting_returns_404(client: HttpAsyncClient) -> None:
    response = await client.get(f"/api/meetings/missing?org_id={ORG_ID}")

    assert response.status_code == 404
    assert response.json() == {"error": "not_found", "message": "Meeting not found."}


@pytest.mark.asyncio
async def test_delete_meeting_soft_deletes(client: HttpAsyncClient) -> None:
    create_response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij", "org_id": ORG_ID},
    )
    meeting_id = create_response.json()["id"]

    delete_response = await client.delete(f"/api/meetings/{meeting_id}?org_id={ORG_ID}")
    assert delete_response.status_code == 204

    get_response = await client.get(f"/api/meetings/{meeting_id}?org_id={ORG_ID}")
    assert get_response.status_code == 404

    list_response = await client.get(f"/api/meetings?org_id={ORG_ID}")
    assert list_response.status_code == 200
    assert list_response.json() == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_update_meeting_title(client: HttpAsyncClient) -> None:
    create_response = await client.post(
        "/api/meetings",
        json={"meeting_url": "https://meet.google.com/abc-defg-hij", "org_id": ORG_ID},
    )
    meeting_id = create_response.json()["id"]

    response = await client.patch(
        f"/api/meetings/{meeting_id}?org_id={ORG_ID}",
        json={"title": "New title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New title"


@pytest.mark.asyncio
async def test_rename_participant_updates_segment_labels(
    client: HttpAsyncClient,
    firestore_client: AsyncClient,
) -> None:
    meeting = await seed_meeting(firestore_client, meeting_id="meeting_123", org_id=ORG_ID)
    meeting["participants"] = [
        {
            "id": 1,
            "meeting_id": "meeting_123",
            "recall_id": "1",
            "name": "Alice",
            "display_name": None,
            "is_host": False,
        }
    ]
    await meetings_repo.update_meeting(firestore_client, ORG_ID, "meeting_123", {"participants": meeting["participants"]})
    await meetings_repo.add_transcript_data(
        firestore_client,
        ORG_ID,
        "meeting_123",
        meeting["participants"],
        [
            {
                "id": 1,
                "meeting_id": "meeting_123",
                "participant_id": 1,
                "speaker_label": "Alice",
                "text": "Hello team",
                "start_ms": 500,
                "end_ms": 1300,
            }
        ],
    )

    response = await client.patch(
        f"/api/meetings/meeting_123/participants/1?org_id={ORG_ID}",
        json={"display_name": "Alice Cooper"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Alice Cooper"
    updated = await meetings_repo.get_meeting(firestore_client, ORG_ID, "meeting_123")
    assert updated is not None
    assert updated["segments"][0]["speaker_label"] == "Alice Cooper"

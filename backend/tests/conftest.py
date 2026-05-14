from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient as HttpAsyncClient

from app.config import Settings
from app.deps import get_app_settings, get_firestore, get_recall_client
from app.main import app


class FakeSnapshot:
    def __init__(self, reference: "FakeDocument", data: dict[str, Any] | None) -> None:
        self.reference = reference
        self.id = reference.id
        self.exists = data is not None
        self._data = deepcopy(data) if data is not None else None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._data)


class FakeBatch:
    def __init__(self) -> None:
        self._operations: list[tuple[str, FakeDocument, dict[str, Any]]] = []

    def set(self, ref: "FakeDocument", data: dict[str, Any]) -> None:
        self._operations.append(("set", ref, data))

    def update(self, ref: "FakeDocument", data: dict[str, Any]) -> None:
        self._operations.append(("update", ref, data))

    async def commit(self) -> None:
        for operation, ref, data in self._operations:
            if operation == "set":
                await ref.set(data)
            else:
                await ref.update(data)


class FakeFirestore:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> "FakeCollection":
        return FakeCollection(self, (name,))

    def collection_group(self, name: str) -> "FakeCollectionGroup":
        return FakeCollectionGroup(self, name)

    def batch(self) -> FakeBatch:
        return FakeBatch()

    async def close(self) -> None:
        return None


class FakeCollection:
    def __init__(self, db: FakeFirestore, path: tuple[str, ...]) -> None:
        self.db = db
        self.path = path
        self._order_by: str | None = None

    def document(self, document_id: str) -> "FakeDocument":
        return FakeDocument(self.db, self.path + (document_id,))

    def order_by(self, field: str) -> "FakeCollection":
        clone = FakeCollection(self.db, self.path)
        clone._order_by = field
        return clone

    async def stream(self) -> AsyncIterator[FakeSnapshot]:
        docs: list[FakeSnapshot] = []
        prefix = "/".join(self.path) + "/"
        expected_len = len(self.path) + 1
        for path, data in self.db.store.items():
            parts = path.split("/")
            if len(parts) == expected_len and path.startswith(prefix):
                docs.append(FakeSnapshot(FakeDocument(self.db, tuple(parts)), data))
        if self._order_by is not None:
            docs.sort(key=lambda snapshot: (snapshot.to_dict() or {}).get(self._order_by))
        for doc in docs:
            yield doc


class FakeCollectionGroup:
    def __init__(self, db: FakeFirestore, name: str) -> None:
        self.db = db
        self.name = name

    async def stream(self) -> AsyncIterator[FakeSnapshot]:
        for path, data in self.db.store.items():
            parts = path.split("/")
            if len(parts) >= 2 and parts[-2] == self.name:
                yield FakeSnapshot(FakeDocument(self.db, tuple(parts)), data)


class FakeDocument:
    def __init__(self, db: FakeFirestore, path: tuple[str, ...]) -> None:
        self.db = db
        self.path_parts = path
        self.path = "/".join(path)
        self.id = path[-1]
        parent_path = path[:-1]
        self.parent = FakeCollection(db, parent_path)

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self.db, self.path_parts + (name,))

    async def get(self) -> FakeSnapshot:
        return FakeSnapshot(self, self.db.store.get(self.path))

    async def set(self, data: dict[str, Any]) -> None:
        self.db.store[self.path] = deepcopy(data)

    async def update(self, data: dict[str, Any]) -> None:
        existing = self.db.store.setdefault(self.path, {})
        existing.update(deepcopy(data))

    async def delete(self) -> None:
        self.db.store.pop(self.path, None)


class FakeRecallClient:
    def __init__(self) -> None:
        self.bot_response: dict[str, object] = {"id": "bot_test_123"}
        self.create_bot_error: Exception | None = None
        self.created_bot_requests: list[tuple[str, str]] = []
        self.transcript_metadata: dict[str, object] = {
            "id": "transcript_123",
            "data": {"download_url": "https://example.test/transcript.json"},
        }
        self.transcript_json: list[object] = []
        self.transcript_requests: list[str] = []
        self.download_requests: list[str] = []

    async def create_bot(self, meeting_url: str, bot_name: str) -> dict[str, object]:
        self.created_bot_requests.append((meeting_url, bot_name))
        if self.create_bot_error is not None:
            raise self.create_bot_error
        return self.bot_response

    async def get_transcript(self, transcript_id: str) -> dict[str, object]:
        self.transcript_requests.append(transcript_id)
        return self.transcript_metadata

    async def download_transcript_json(self, download_url: str) -> list[object]:
        self.download_requests.append(download_url)
        return self.transcript_json


@pytest.fixture
async def firestore_client() -> AsyncIterator[FakeFirestore]:
    db = FakeFirestore()
    yield db
    db.store.clear()


@pytest.fixture
def fake_recall_client() -> FakeRecallClient:
    return FakeRecallClient()


@pytest.fixture
async def client(
    firestore_client: FakeFirestore,
    fake_recall_client: FakeRecallClient,
) -> AsyncIterator[HttpAsyncClient]:
    def override_get_firestore() -> FakeFirestore:
        return firestore_client

    def override_get_recall_client() -> FakeRecallClient:
        return fake_recall_client

    def override_get_app_settings() -> Settings:
        return Settings(
            recall_api_key="test-key",
            recall_webhook_secret=None,
            public_webhook_base_url=None,
            recall_bot_name="Test Notetaker",
            disable_gcs_upload=True,
        )

    app.dependency_overrides[get_firestore] = override_get_firestore
    app.dependency_overrides[get_recall_client] = override_get_recall_client
    app.dependency_overrides[get_app_settings] = override_get_app_settings

    async with HttpAsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()

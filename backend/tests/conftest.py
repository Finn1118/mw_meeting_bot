from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.deps import get_app_settings, get_recall_client, get_session
from app.main import app
from app.models import Base


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
async def db_sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield sessionmaker

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def fake_recall_client() -> FakeRecallClient:
    return FakeRecallClient()


@pytest.fixture
async def client(
    db_sessionmaker: async_sessionmaker[AsyncSession],
    fake_recall_client: FakeRecallClient,
    tmp_path: Path,
) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with db_sessionmaker() as session:
            yield session

    def override_get_recall_client() -> FakeRecallClient:
        return fake_recall_client

    def override_get_app_settings() -> Settings:
        return Settings(
            recall_api_key="test-key",
            recall_webhook_secret="whsec_dGVzdA==",
            public_webhook_base_url="https://example.com",
            recall_bot_name="Test Notetaker",
            blobs_dir=str(tmp_path / "blobs"),
        )

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_recall_client] = override_get_recall_client
    app.dependency_overrides[get_app_settings] = override_get_app_settings

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()

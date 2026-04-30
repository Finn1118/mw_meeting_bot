from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import AsyncSessionLocal
from app.services.recall import RecallClient


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


def get_recall_client() -> RecallClient:
    settings = get_settings()
    return RecallClient(api_key=settings.recall_api_key, region=settings.recall_region)


def get_app_settings() -> Settings:
    return get_settings()

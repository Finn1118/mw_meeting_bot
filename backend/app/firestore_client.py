from functools import lru_cache

from google.cloud.firestore_v1 import AsyncClient

from app.config import get_settings


@lru_cache
def get_firestore_client() -> AsyncClient:
    settings = get_settings()
    return AsyncClient(project=settings.firestore_project_id)

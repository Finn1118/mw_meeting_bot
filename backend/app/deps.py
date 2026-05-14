from google.cloud.firestore_v1 import AsyncClient

from app.config import Settings, get_settings
from app.firestore_client import get_firestore_client
from app.services.recall import RecallClient


def get_firestore() -> AsyncClient:
    return get_firestore_client()


def get_recall_client() -> RecallClient:
    settings = get_settings()
    return RecallClient(api_key=settings.recall_api_key, region=settings.recall_region)


def get_app_settings() -> Settings:
    return get_settings()

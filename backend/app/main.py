from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import ApiError, api_error_handler
from app.routers.events import router as events_router
from app.routers.meetings import router as meetings_router
# from app.routers.webhooks import router as webhooks_router
from app.services.poller import BotPoller
from app.services.recall import RecallClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    recall = RecallClient(api_key=settings.recall_api_key, region=settings.recall_region)
    poller = BotPoller(settings=settings, recall=recall)
    await poller.start()
    try:
        yield
    finally:
        await poller.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Meeting Transcription API", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, bool | str]:
        return {"ok": True, "version": "0.1.0"}

    app.include_router(meetings_router)
    app.include_router(events_router)
    # Webhook router disabled -- using polling instead. Re-enable by:
    # 1. Setting RECALL_WEBHOOK_SECRET and PUBLIC_WEBHOOK_BASE_URL in .env
    # 2. Registering the webhook endpoint in the Recall dashboard
    # 3. Uncommenting the line below and the polling task in lifespan()
    # app.include_router(webhooks_router)

    return app


app = create_app()

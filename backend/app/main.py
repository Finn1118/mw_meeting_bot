from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import Response

from app.config import get_settings
from app.errors import ApiError, api_error_handler
from app.routers.calendar import router as calendar_router
from app.routers.events import router as events_router
from app.routers.google_auth import router as google_auth_router
from app.routers.meetings import router as meetings_router
from app.services.calendar_auto_dispatcher import CalendarAutoDispatcher
from app.services.poller import BotPoller
from app.services.recall import RecallClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    recall: RecallClient | None = None
    poller: BotPoller | None = None
    calendar_dispatcher: CalendarAutoDispatcher | None = None
    if settings.enable_poller:
        recall = RecallClient(api_key=settings.recall_api_key, region=settings.recall_region)
        poller = BotPoller(settings=settings, recall=recall)
        await poller.start()
    if settings.enable_google_calendar:
        recall = recall or RecallClient(api_key=settings.recall_api_key, region=settings.recall_region)
        calendar_dispatcher = CalendarAutoDispatcher(settings=settings, recall=recall)
        await calendar_dispatcher.start()
    try:
        yield
    finally:
        if calendar_dispatcher is not None:
            await calendar_dispatcher.stop()
        if poller is not None:
            await poller.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Meeting Transcription API", version="0.1.0", lifespan=lifespan)
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health() -> dict[str, bool | str]:
        return {"ok": True, "version": "0.1.0"}

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid4().hex
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response

    app.include_router(meetings_router)
    app.include_router(events_router)
    if settings.enable_google_calendar:
        app.include_router(google_auth_router)
        app.include_router(calendar_router)

    return app


app = create_app()

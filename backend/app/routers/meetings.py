import logging
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from google.cloud.firestore_v1 import AsyncClient

from app.config import Settings
from app.deps import get_app_settings, get_firestore, get_recall_client
from app.errors import ApiError
from app.repositories import meetings as meetings_repo
from app.schemas import (
    ErrorResponse,
    MeetingCreate,
    MeetingList,
    MeetingRead,
    MeetingUpdate,
    ParticipantRead,
    ParticipantUpdate,
)
from app.services.recall import RecallApiError, RecallClient, RecallPoolExhausted
from app.services.url_parser import parse_meeting_url

router = APIRouter(prefix="/api/meetings", tags=["meetings"])
logger = logging.getLogger("uvicorn.error")

FirestoreDep = Annotated[AsyncClient, Depends(get_firestore)]
RecallDep = Annotated[RecallClient, Depends(get_recall_client)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def error_response(status_code: int, error: str, message: str) -> ApiError:
    return ApiError(status_code=status_code, **ErrorResponse(error=error, message=message).model_dump())


def utc_now() -> datetime:
    return datetime.now(UTC)


def bot_id_from_response(response: dict[str, object]) -> str:
    bot_id = response.get("id")
    if not isinstance(bot_id, str) or not bot_id:
        raise ValueError("missing_bot_id")
    return bot_id


async def get_active_meeting_or_404(
    db: AsyncClient,
    org_id: str,
    meeting_id: str,
) -> dict[str, object]:
    meeting = await meetings_repo.get_meeting(db, org_id, meeting_id)
    if meeting is None:
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Meeting not found.")
    return meeting


@router.post(
    "",
    response_model=MeetingRead,
    responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 507: {"model": ErrorResponse}},
)
async def create_meeting(
    payload: MeetingCreate,
    db: FirestoreDep,
    recall_client: RecallDep,
    settings: SettingsDep,
) -> MeetingRead:
    try:
        parsed_url = parse_meeting_url(payload.meeting_url)
    except ValueError as exc:
        raise error_response(status.HTTP_400_BAD_REQUEST, "invalid_url", "Meeting URL is not supported.") from exc

    now = utc_now()
    meeting: dict[str, Any] = {
        "id": uuid4().hex,
        "meeting_url": parsed_url.normalized_url,
        "platform": parsed_url.platform,
        "title": payload.title,
        "org_id": payload.org_id,
        "created_by_uid": payload.created_by_uid,
        "platform_conversation_id": payload.platform_conversation_id,
        "bot_id": None,
        "recording_id": None,
        "transcript_id": None,
        "status": "dispatching",
        "sub_code": None,
        "started_at": None,
        "ended_at": None,
        "duration_sec": None,
        "transcript_path": None,
        "recording_path": None,
        "deleted_at": None,
        "participants": [],
        "created_at": now,
        "updated_at": now,
    }
    await meetings_repo.create_meeting(db, meeting)

    try:
        bot_response = await recall_client.create_bot(
            meeting_url=parsed_url.normalized_url,
            bot_name=settings.recall_bot_name,
        )
        updated = await meetings_repo.update_meeting(
            db,
            payload.org_id,
            str(meeting["id"]),
            {"bot_id": bot_id_from_response(bot_response), "status": "bot_created"},
        )
    except RecallPoolExhausted as exc:
        logger.warning("Recall bot pool exhausted during dispatch: status=%s body=%s", exc.status_code, exc.body)
        await meetings_repo.update_meeting(
            db,
            payload.org_id,
            str(meeting["id"]),
            {"status": "failed", "sub_code": "dispatch_error"},
        )
        raise error_response(status.HTTP_507_INSUFFICIENT_STORAGE, "recall_pool_exhausted", "Recall bot pool is exhausted. Try again later.") from exc
    except (RecallApiError, httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, RecallApiError):
            logger.warning("Recall dispatch failed: status=%s body=%s", exc.status_code, exc.body)
        else:
            logger.warning("Recall dispatch failed before API response: %s", exc)
        await meetings_repo.update_meeting(
            db,
            payload.org_id,
            str(meeting["id"]),
            {"status": "failed", "sub_code": "dispatch_error"},
        )
        raise error_response(status.HTTP_502_BAD_GATEWAY, "recall_api_error", "Recall API request failed.") from exc

    return MeetingRead.model_validate(updated)


@router.get("", response_model=MeetingList)
async def list_meetings(
    db: FirestoreDep,
    org_id: Annotated[str, Query(min_length=1)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    platform: Annotated[str | None, Query(pattern="^(zoom|meet|teams)$")] = None,
) -> MeetingList:
    result = await meetings_repo.list_meetings(
        db,
        org_id,
        limit=limit,
        offset=offset,
        platform=platform,
    )
    return MeetingList.model_validate(result)


@router.get("/{meeting_id}", response_model=MeetingRead, responses={404: {"model": ErrorResponse}})
async def get_meeting(
    meeting_id: str,
    db: FirestoreDep,
    org_id: Annotated[str, Query(min_length=1)],
) -> MeetingRead:
    meeting = await get_active_meeting_or_404(db, org_id, meeting_id)
    return MeetingRead.model_validate(meeting)


@router.patch("/{meeting_id}", response_model=MeetingRead, responses={404: {"model": ErrorResponse}})
async def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    db: FirestoreDep,
    org_id: Annotated[str, Query(min_length=1)],
) -> MeetingRead:
    meeting = await meetings_repo.update_meeting(db, org_id, meeting_id, {"title": payload.title})
    if meeting is None:
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Meeting not found.")
    return MeetingRead.model_validate(meeting)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
async def delete_meeting(
    meeting_id: str,
    db: FirestoreDep,
    org_id: Annotated[str, Query(min_length=1)],
) -> Response:
    if not await meetings_repo.soft_delete_meeting(db, org_id, meeting_id):
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Meeting not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{meeting_id}/participants/{participant_id}",
    response_model=ParticipantRead,
    responses={404: {"model": ErrorResponse}},
)
async def update_participant(
    meeting_id: str,
    participant_id: int,
    payload: ParticipantUpdate,
    db: FirestoreDep,
    org_id: Annotated[str, Query(min_length=1)],
) -> ParticipantRead:
    participant = await meetings_repo.update_participant_display_name(
        db,
        org_id,
        meeting_id,
        participant_id,
        payload.display_name,
    )
    if participant is None:
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Participant not found.")
    return ParticipantRead.model_validate(participant)

import logging
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import ColumnElement, Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.deps import get_app_settings, get_recall_client, get_session
from app.errors import ApiError
from app.models import Meeting, Participant, TranscriptSegment
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

SessionDep = Annotated[AsyncSession, Depends(get_session)]
RecallDep = Annotated[RecallClient, Depends(get_recall_client)]
SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def error_response(status_code: int, error: str, message: str) -> ApiError:
    return ApiError(status_code=status_code, **ErrorResponse(error=error, message=message).model_dump())


def utc_now() -> datetime:
    return datetime.now(UTC)


def meeting_read(meeting: Meeting) -> MeetingRead:
    return MeetingRead.model_validate(meeting)


def bot_id_from_response(response: dict[str, object]) -> str:
    bot_id = response.get("id")
    if not isinstance(bot_id, str) or not bot_id:
        raise ValueError("missing_bot_id")
    return bot_id


async def get_active_meeting_or_404(
    session: AsyncSession,
    meeting_id: str,
    org_id: str | None = None,
) -> Meeting:
    filters = [Meeting.id == meeting_id, Meeting.deleted_at.is_(None)]
    if org_id is not None:
        filters.append(Meeting.org_id == org_id)

    meeting = await session.scalar(
        select(Meeting)
        .where(*filters)
        .options(selectinload(Meeting.participants), selectinload(Meeting.segments))
    )
    if meeting is None:
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Meeting not found.")
    return meeting


@router.post("", response_model=MeetingRead, responses={400: {"model": ErrorResponse}, 502: {"model": ErrorResponse}, 507: {"model": ErrorResponse}})
async def create_meeting(
    payload: MeetingCreate,
    session: SessionDep,
    recall_client: RecallDep,
    settings: SettingsDep,
) -> MeetingRead:
    try:
        parsed_url = parse_meeting_url(payload.meeting_url)
    except ValueError as exc:
        raise error_response(status.HTTP_400_BAD_REQUEST, "invalid_url", "Meeting URL is not supported.") from exc

    now = utc_now()
    meeting = Meeting(
        id=uuid4().hex,
        meeting_url=parsed_url.normalized_url,
        platform=parsed_url.platform,
        title=payload.title,
        org_id=payload.org_id,
        created_by_uid=payload.created_by_uid,
        platform_conversation_id=payload.platform_conversation_id,
        status="dispatching",
        created_at=now,
        updated_at=now,
    )
    session.add(meeting)
    await session.flush()

    try:
        bot_response = await recall_client.create_bot(
            meeting_url=parsed_url.normalized_url,
            bot_name=settings.recall_bot_name,
        )
        meeting.bot_id = bot_id_from_response(bot_response)
        meeting.status = "bot_created"
        meeting.updated_at = utc_now()
        await session.commit()
    except RecallPoolExhausted as exc:
        logger.warning("Recall bot pool exhausted during dispatch: status=%s body=%s", exc.status_code, exc.body)
        meeting.status = "failed"
        meeting.sub_code = "dispatch_error"
        meeting.updated_at = utc_now()
        await session.commit()
        raise error_response(status.HTTP_507_INSUFFICIENT_STORAGE, "recall_pool_exhausted", "Recall bot pool is exhausted. Try again later.") from exc
    except (RecallApiError, httpx.HTTPError, ValueError) as exc:
        if isinstance(exc, RecallApiError):
            logger.warning("Recall dispatch failed: status=%s body=%s", exc.status_code, exc.body)
        else:
            logger.warning("Recall dispatch failed before API response: %s", exc)
        meeting.status = "failed"
        meeting.sub_code = "dispatch_error"
        meeting.updated_at = utc_now()
        await session.commit()
        raise error_response(status.HTTP_502_BAD_GATEWAY, "recall_api_error", "Recall API request failed.") from exc

    await session.refresh(meeting, attribute_names=["participants", "segments"])
    return meeting_read(meeting)


@router.get("", response_model=MeetingList)
async def list_meetings(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    platform: Annotated[str | None, Query(pattern="^(zoom|meet|teams)$")] = None,
    org_id: Annotated[str | None, Query(min_length=1)] = None,
) -> MeetingList:
    filters: list[ColumnElement[bool]] = [Meeting.deleted_at.is_(None)]
    if platform is not None:
        filters.append(Meeting.platform == platform)
    if org_id is not None:
        filters.append(Meeting.org_id == org_id)

    total = await session.scalar(select(func.count()).select_from(Meeting).where(*filters))
    query: Select[tuple[Meeting]] = (
        select(Meeting)
        .where(*filters)
        .options(selectinload(Meeting.participants), selectinload(Meeting.segments))
        .order_by(Meeting.started_at.is_not(None), Meeting.started_at.desc(), Meeting.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    meetings = list((await session.scalars(query)).all())
    return MeetingList(items=[meeting_read(meeting) for meeting in meetings], total=total or 0)


@router.get("/{meeting_id}", response_model=MeetingRead, responses={404: {"model": ErrorResponse}})
async def get_meeting(
    meeting_id: str,
    session: SessionDep,
    org_id: Annotated[str | None, Query(min_length=1)] = None,
) -> MeetingRead:
    meeting = await get_active_meeting_or_404(session, meeting_id, org_id)
    return meeting_read(meeting)


@router.patch("/{meeting_id}", response_model=MeetingRead, responses={404: {"model": ErrorResponse}})
async def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    session: SessionDep,
    org_id: Annotated[str | None, Query(min_length=1)] = None,
) -> MeetingRead:
    meeting = await get_active_meeting_or_404(session, meeting_id, org_id)
    meeting.title = payload.title
    meeting.updated_at = utc_now()
    await session.commit()
    await session.refresh(meeting, attribute_names=["participants", "segments"])
    return meeting_read(meeting)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT, responses={404: {"model": ErrorResponse}})
async def delete_meeting(
    meeting_id: str,
    session: SessionDep,
    org_id: Annotated[str | None, Query(min_length=1)] = None,
) -> Response:
    meeting = await get_active_meeting_or_404(session, meeting_id, org_id)
    meeting.deleted_at = utc_now()
    meeting.updated_at = utc_now()
    await session.commit()
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
    session: SessionDep,
    org_id: Annotated[str | None, Query(min_length=1)] = None,
) -> ParticipantRead:
    await get_active_meeting_or_404(session, meeting_id, org_id)
    participant = await session.scalar(
        select(Participant).where(
            Participant.id == participant_id,
            Participant.meeting_id == meeting_id,
        )
    )
    if participant is None:
        raise error_response(status.HTTP_404_NOT_FOUND, "not_found", "Participant not found.")

    participant.display_name = payload.display_name
    await session.execute(
        update(TranscriptSegment)
        .where(
            TranscriptSegment.meeting_id == meeting_id,
            TranscriptSegment.participant_id == participant_id,
        )
        .values(speaker_label=payload.display_name)
    )

    meeting = await session.scalar(select(Meeting).where(Meeting.id == meeting_id))
    if meeting is not None:
        meeting.updated_at = utc_now()
    await session.commit()
    await session.refresh(participant)
    return ParticipantRead.model_validate(participant)

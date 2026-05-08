from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error: str
    message: str


class MeetingCreate(BaseModel):
    meeting_url: str = Field(min_length=1)
    title: str | None = None
    org_id: str | None = None
    created_by_uid: str | None = None
    platform_conversation_id: str | None = None


class MeetingUpdate(BaseModel):
    title: str | None = None


class ParticipantUpdate(BaseModel):
    display_name: str = Field(min_length=1)


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: str
    recall_id: str | None
    name: str
    display_name: str | None
    is_host: bool


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    meeting_id: str
    participant_id: int | None
    speaker_label: str
    text: str
    start_ms: int
    end_ms: int


class MeetingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    meeting_url: str
    platform: str
    title: str | None
    org_id: str | None
    created_by_uid: str | None
    platform_conversation_id: str | None
    bot_id: str | None
    recording_id: str | None
    transcript_id: str | None
    status: str
    sub_code: str | None
    started_at: datetime | None
    ended_at: datetime | None
    duration_sec: int | None
    transcript_path: str | None
    recording_path: str | None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
    participants: list[ParticipantRead] = []
    segments: list[TranscriptSegmentRead] = []


class MeetingList(BaseModel):
    items: list[MeetingRead]
    total: int


class GoogleAuthStatus(BaseModel):
    connected: bool
    email: str | None


class CalendarMeetingLink(BaseModel):
    platform: str
    url: str


class CalendarEventRead(BaseModel):
    id: str
    title: str
    start: str | None
    end: str | None
    organizer_email: str | None
    html_link: str | None
    meeting_link: CalendarMeetingLink | None


class CalendarEventList(BaseModel):
    items: list[CalendarEventRead]


class AutoDispatchSetting(BaseModel):
    enabled: bool


class AutoDispatchUpdate(BaseModel):
    enabled: bool

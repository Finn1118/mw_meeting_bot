from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


class Meeting(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    meeting_url: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    org_id: Mapped[str | None] = mapped_column(String, index=True)
    created_by_uid: Mapped[str | None] = mapped_column(String, index=True)
    platform_conversation_id: Mapped[str | None] = mapped_column(String, index=True)
    bot_id: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    recording_id: Mapped[str | None] = mapped_column(String, index=True)
    transcript_id: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="dispatching")
    sub_code: Mapped[str | None] = mapped_column(String)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    transcript_path: Mapped[str | None] = mapped_column(String)
    recording_path: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)

    participants = relationship(
        "Participant",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )
    segments = relationship(
        "TranscriptSegment",
        back_populates="meeting",
        cascade="all, delete-orphan",
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    recall_id: Mapped[str | None] = mapped_column(String)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    is_host: Mapped[bool] = mapped_column(Boolean, default=False)
    meeting = relationship("Meeting", back_populates="participants")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id"), nullable=False)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id"))
    speaker_label: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    meeting = relationship("Meeting", back_populates="segments")


Index("ix_segments_meeting_start", TranscriptSegment.meeting_id, TranscriptSegment.start_ms)


class WebhookLog(Base):
    __tablename__ = "webhook_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bot_id: Mapped[str | None] = mapped_column(String, index=True)
    event_type: Mapped[str] = mapped_column(String)
    event_id: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    __table_args__ = (Index("uq_wh_event", "event_id", unique=True),)


class GoogleConnection(Base):
    __tablename__ = "google_connection"

    id: Mapped[str] = mapped_column(String, primary_key=True, default="demo")
    email: Mapped[str | None] = mapped_column(String)
    auto_dispatch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    scope: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CalendarDispatch(Base):
    __tablename__ = "calendar_dispatches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    google_event_id: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    meeting_id: Mapped[str | None] = mapped_column(ForeignKey("meetings.id"), index=True)
    meeting_url: Mapped[str] = mapped_column(String, nullable=False)
    event_title: Mapped[str | None] = mapped_column(String)
    event_start: Mapped[datetime | None] = mapped_column(DateTime)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from google.cloud.firestore_v1 import AsyncClient

from app.config import Settings
from app.events import bus
from app.firestore_client import get_firestore_client
from app.repositories import meetings as meetings_repo
from app.services.gcs_storage import save_transcript_json
from app.services.recall import RecallApiError, RecallClient
from app.services.transcript import parse_transcript

logger = logging.getLogger("uvicorn.error")

TERMINAL_STATUSES = {"complete", "failed"}

RECALL_STATUS_MAP = {
    "joining_call": "joining",
    "in_waiting_room": "waiting_room",
    "in_call_not_recording": "in_call_not_recording",
    "in_call_recording": "recording",
    "recording_permission_denied": "failed",
    "call_ended": "processing",
    "done": "processing",
    "fatal": "failed",
}


class BotPoller:
    def __init__(
        self,
        settings: Settings,
        recall: RecallClient,
        db: AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.recall = recall
        self.db = db or get_firestore_client()
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="bot-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            await self._task

    async def _run(self) -> None:
        logger.info("Bot poller started (interval=%ss)", self.settings.poll_interval_seconds)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Poller tick raised; continuing")
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self.settings.poll_interval_seconds,
                )
            except TimeoutError:
                pass
        logger.info("Bot poller stopped")

    async def _tick(self) -> None:
        meetings = await meetings_repo.list_active_polling_meetings(self.db)
        for meeting in meetings:
            await self._poll_one(meeting)

    async def _poll_one(self, meeting: dict[str, Any]) -> None:
        bot_id = meeting.get("bot_id")
        if not isinstance(bot_id, str):
            return

        try:
            bot = await self.recall.get_bot(bot_id)
        except RecallApiError as exc:
            logger.warning("get_bot failed for %s: %s", bot_id, exc)
            return

        latest_status = latest_recall_status(bot)
        if latest_status is None:
            return

        recall_code = latest_status.get("code")
        sub_code = latest_status.get("sub_code")
        new_status = RECALL_STATUS_MAP.get(recall_code if isinstance(recall_code, str) else "", str(meeting["status"]))
        updates: dict[str, Any] = {}

        if new_status != meeting["status"]:
            updates["status"] = new_status
            updates["sub_code"] = sub_code if isinstance(sub_code, str) else None

        if recall_code == "done" and meeting["status"] != "complete":
            finalized = await self._try_finalize_transcript(meeting, bot)
            updates.update(finalized)

        if not updates:
            return

        updated = await meetings_repo.update_meeting(
            self.db,
            str(meeting["org_id"]),
            str(meeting["id"]),
            updates,
        )
        await bus.publish(
            str(meeting["id"]),
            {
                "meeting_id": str(meeting["id"]),
                "status": updated["status"] if updated else updates.get("status", meeting["status"]),
                "sub_code": updated.get("sub_code") if updated else updates.get("sub_code"),
            },
        )

    async def _try_finalize_transcript(
        self,
        meeting: dict[str, Any],
        bot: dict[str, object],
    ) -> dict[str, Any]:
        recording = first_recording(bot)
        if recording is None:
            return {}

        transcript = transcript_shortcut(recording)
        if transcript is None:
            return {}

        transcript_id = transcript.get("id")
        status_code = nested_status_code(transcript)
        if status_code != "done" or not isinstance(transcript_id, str):
            return {}

        metadata = await self.recall.get_transcript(transcript_id)
        download_url = transcript_download_url(metadata)
        if download_url is None:
            return {}

        org_id = str(meeting["org_id"])
        meeting_id = str(meeting["id"])
        raw_transcript = await self.recall.download_transcript_json(download_url)
        transcript_key = save_transcript_json(self.settings, org_id, meeting_id, raw_transcript)
        participants, segments = await parse_transcript(meeting_id, raw_transcript)
        await meetings_repo.add_transcript_data(self.db, org_id, meeting_id, participants, segments)

        updates: dict[str, Any] = {
            "transcript_path": transcript_key,
            "transcript_id": transcript_id,
            "status": "complete",
            "updated_at": datetime.now(UTC),
        }
        recording_id = recording.get("id")
        if isinstance(recording_id, str):
            updates["recording_id"] = recording_id
        return updates


def latest_recall_status(bot: dict[str, object]) -> dict[str, Any] | None:
    changes = bot.get("status_changes")
    if not isinstance(changes, list) or not changes:
        return None
    latest = changes[-1]
    return latest if isinstance(latest, dict) else None


def first_recording(bot: dict[str, object]) -> dict[str, Any] | None:
    recordings = bot.get("recordings")
    if not isinstance(recordings, list) or not recordings:
        return None
    recording = recordings[0]
    return recording if isinstance(recording, dict) else None


def transcript_shortcut(recording: dict[str, Any]) -> dict[str, Any] | None:
    media_shortcuts = recording.get("media_shortcuts")
    if isinstance(media_shortcuts, dict):
        transcript = media_shortcuts.get("transcript")
        if isinstance(transcript, dict):
            return transcript

    transcript = recording.get("transcript")
    if isinstance(transcript, dict):
        return transcript
    return None


def nested_status_code(value: dict[str, Any]) -> str | None:
    status = value.get("status")
    if isinstance(status, dict) and isinstance(status.get("code"), str):
        return str(status["code"])
    status_code = value.get("status_code")
    return str(status_code) if isinstance(status_code, str) else None


def transcript_download_url(metadata: dict[str, object]) -> str | None:
    data = metadata.get("data")
    if isinstance(data, dict) and isinstance(data.get("download_url"), str):
        return str(data["download_url"])
    return None

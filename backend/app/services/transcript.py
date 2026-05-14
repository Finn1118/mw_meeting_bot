import logging
from typing import Any

logger = logging.getLogger(__name__)


def relative_seconds_to_ms(value: object) -> int:
    if not isinstance(value, int | float):
        raise ValueError("timestamp_not_numeric")
    return int(value * 1000)


async def parse_transcript(
    meeting_id: str,
    raw: list[object],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing_participants: dict[str, dict[str, Any]] = {}
    participants: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []

    for utterance in raw:
        try:
            participant_data, words = validate_utterance_shape(utterance)
            recall_id = str(participant_data["id"])
            name = str(participant_data["name"])
            is_host = bool(participant_data.get("is_host", False))

            participant = existing_participants.get(recall_id)
            if participant is None:
                participant_id = int(recall_id) if recall_id.isdigit() else len(participants) + 1
                participant = {
                    "id": participant_id,
                    "meeting_id": meeting_id,
                    "recall_id": recall_id,
                    "name": name,
                    "display_name": None,
                    "is_host": is_host,
                }
                existing_participants[recall_id] = participant
                participants.append(participant)

            text = " ".join(str(word["text"]) for word in words)
            segment = {
                "id": len(segments) + 1,
                "meeting_id": meeting_id,
                "participant_id": participant["id"],
                "speaker_label": participant["display_name"] or participant["name"],
                "text": text,
                "start_ms": relative_seconds_to_ms(words[0]["start_timestamp"]["relative"]),
                "end_ms": relative_seconds_to_ms(words[-1]["end_timestamp"]["relative"]),
            }
            segments.append(segment)
        except (KeyError, TypeError, ValueError) as exc:
            # TODO(Cursor Build Prompt, transcript parser section): keep expanding tolerated shapes as Recall samples appear.
            logger.warning("Skipping malformed transcript utterance: %s", exc)

    return participants, segments


def validate_utterance_shape(utterance: object) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(utterance, dict):
        raise ValueError("utterance_not_object")

    participant = utterance["participant"]
    words = utterance["words"]
    if not isinstance(participant, dict):
        raise ValueError("participant_not_object")
    if not isinstance(words, list) or not words:
        raise ValueError("words_not_non_empty_list")

    for word in words:
        if not isinstance(word, dict):
            raise ValueError("word_not_object")
        if not isinstance(word.get("start_timestamp"), dict):
            raise ValueError("missing_start_timestamp")
        if not isinstance(word.get("end_timestamp"), dict):
            raise ValueError("missing_end_timestamp")

    return participant, words

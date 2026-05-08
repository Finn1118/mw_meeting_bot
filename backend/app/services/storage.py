import json
from pathlib import Path


def transcript_key(meeting_id: str) -> str:
    return f"transcripts/{meeting_id}.json"


def local_blob_path(blobs_dir: str, key: str) -> Path:
    return Path(blobs_dir) / key


def save_transcript_json(blobs_dir: str, meeting_id: str, raw_transcript: list[object]) -> str:
    key = transcript_key(meeting_id)
    path = local_blob_path(blobs_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw_transcript), encoding="utf-8")
    return key

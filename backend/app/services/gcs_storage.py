import json

import google.cloud.storage as storage  # type: ignore[import-untyped]

from app.config import Settings


def transcript_blob_name(org_id: str, meeting_id: str) -> str:
    return f"organizations/{org_id}/meetings/{meeting_id}/transcript.json"


def transcript_gs_uri(bucket_name: str, org_id: str, meeting_id: str) -> str:
    return f"gs://{bucket_name}/{transcript_blob_name(org_id, meeting_id)}"


def save_transcript_json(
    settings: Settings,
    org_id: str,
    meeting_id: str,
    raw_transcript: list[object],
) -> str:
    bucket_name = settings.firebase_storage_bucket
    blob_name = transcript_blob_name(org_id, meeting_id)
    gs_uri = transcript_gs_uri(bucket_name, org_id, meeting_id)
    if settings.disable_gcs_upload:
        return gs_uri

    client = storage.Client(project=settings.firestore_project_id)
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(
        json.dumps(raw_transcript),
        content_type="application/json",
    )
    return gs_uri

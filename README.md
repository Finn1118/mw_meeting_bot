# mw_meeting_bot

Python/FastAPI service for the Millionways meeting notetaker. It dispatches Recall.ai bots, tracks live meeting state, stores meeting metadata in Firestore, and writes transcript JSON blobs to Firebase Storage.

## Architecture

Firebase Functions remain the authenticated edge: they verify Firebase Auth and org membership, then call this Cloud Run service through `MEETING_BOT_SERVICE_URL`.

```text
Millionways Vue UI
        |
        v
Firebase Functions        auth + org checks
        |
        v
Cloud Run: mw_meeting_bot Recall workflow, polling, SSE
        |
        +-- Firestore: organizations/{orgId}/meetings/{meetingId}
        +-- Firebase Storage: transcript JSON blobs
        +-- Recall.ai: bot dispatch and transcription
```

## Firestore layout

```text
organizations/{orgId}/meetings/{meetingId}
  participants: [{ id, recall_id, name, display_name, is_host }]
  ...
  segments/{segmentId}
    { id, meeting_id, participant_id, speaker_label, text, start_ms, end_ms }

organizations/{orgId}/integrations/google
  { email, access_token, refresh_token, scope, expires_at, auto_dispatch_enabled }

organizations/{orgId}/calendarDispatches/{googleEventId}
  { meeting_id, meeting_url, event_title, event_start, dispatched_at, status }
```

Transcript blobs are stored at:

```text
gs://<bucket>/organizations/{orgId}/meetings/{meetingId}/transcript.json
```

## Features

- Dispatch a Recall.ai bot to Zoom, Google Meet, or Microsoft Teams.
- Poll Recall for live status and transcript readiness.
- Stream status updates to the UI over SSE.
- Store meeting metadata, participants, and transcript segments in Firestore.
- Store raw transcript JSON in Firebase Storage.
- Rename speakers and soft-delete meetings.
- Keep the existing Google Calendar OAuth + auto-dispatch flow, now backed by Firestore.

## Local development

Prerequisites:

- Python 3.12
- `uv`
- Node.js/Firebase CLI if running emulators
- Recall.ai API key

Install backend dependencies:

```bash
cd backend
python -m uv sync
```

Run with Firebase emulators:

```bash
# From a Firebase project checkout, or any folder with firebase-tools available
firebase emulators:start --only firestore --project mw-meeting-bot-test
```

Start the API:

```bash
cd backend
$env:FIRESTORE_EMULATOR_HOST="127.0.0.1:8080"   # PowerShell
python -m uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

For local tests, `DISABLE_GCS_UPLOAD=true` avoids writing transcript blobs to real GCS.

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RECALL_API_KEY` | Yes | - | Recall.ai API key |
| `RECALL_REGION` | No | `us-east-1` | Recall region; must match the key |
| `RECALL_BOT_NAME` | No | `Notetaker` | Bot display name |
| `POLL_INTERVAL_SECONDS` | No | `5` | Recall polling interval |
| `ENABLE_POLLER` | No | `true` | Start background bot poller |
| `FIRESTORE_PROJECT_ID` | Yes | `millionways-platform` | Firestore project id |
| `FIREBASE_STORAGE_BUCKET` | Yes | `millionways-platform.firebasestorage.app` | Transcript blob bucket |
| `DISABLE_GCS_UPLOAD` | No | `false` | Skip real GCS upload for tests/local emulators |
| `ALLOWED_ORIGINS` | No | `http://127.0.0.1:5173` | CORS origins |
| `FRONTEND_BASE_URL` | No | `http://127.0.0.1:5173` | OAuth redirect target after callback |
| `GOOGLE_OAUTH_SUCCESS_PATH` | No | `/meetings/calendar` | Frontend route after a successful calendar OAuth callback |
| `ENABLE_GOOGLE_CALENDAR` | No | `true` | Enable calendar routes and auto-dispatcher |
| `GOOGLE_OAUTH_CLIENT_ID` | If calendar | - | Millionways-owned Google OAuth client id |
| `GOOGLE_OAUTH_CLIENT_SECRET` | If calendar | - | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | If calendar | `http://127.0.0.1:8000/api/auth/google/callback` | Must match Google Cloud Console |

In Cloud Run, authentication to Firestore and Firebase Storage comes from the runtime service account. No service account JSON file should be mounted in production.

## Docker / Cloud Run

Build locally:

```bash
docker build -t mw-meeting-bot .
```

Run locally against emulators:

```bash
docker run --rm -p 8080:8080 ^
  -e RECALL_API_KEY=test-key ^
  -e FIRESTORE_PROJECT_ID=mw-meeting-bot-test ^
  -e FIRESTORE_EMULATOR_HOST=host.docker.internal:8080 ^
  -e DISABLE_GCS_UPLOAD=true ^
  mw-meeting-bot
```

Cloud Run should be configured with:

- min instances: `1` (poller/calendar dispatcher need an always-running process)
- port: `8080`
- service account access to Firestore and Firebase Storage
- Secret Manager access for Recall and Google OAuth secrets
- `MEETING_BOT_SERVICE_URL` set in Firebase Functions to the Cloud Run URL

## API surface

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/meetings` | Dispatch a bot; requires `org_id` |
| `GET` | `/api/meetings?org_id=...` | List meetings for an org |
| `GET` | `/api/meetings/{id}?org_id=...` | Get meeting detail |
| `PATCH` | `/api/meetings/{id}?org_id=...` | Update title |
| `DELETE` | `/api/meetings/{id}?org_id=...` | Soft-delete meeting |
| `PATCH` | `/api/meetings/{id}/participants/{pid}?org_id=...` | Rename speaker |
| `GET` | `/api/events?meeting_id=...&org_id=...` | SSE status stream |
| `GET` | `/api/auth/google/start?org_id=...` | Start Google Calendar OAuth |
| `GET` | `/api/auth/google/callback` | OAuth callback |
| `GET` | `/api/auth/google/status?org_id=...` | Calendar connection status |
| `POST` | `/api/auth/google/disconnect?org_id=...` | Disconnect calendar |
| `GET` | `/api/calendar/events?org_id=...` | List upcoming calendar events |
| `GET` | `/api/calendar/auto-dispatch?org_id=...` | Read auto-dispatch setting |
| `PATCH` | `/api/calendar/auto-dispatch?org_id=...` | Toggle auto-dispatch |

## Notes

- Firestore composite indexes may be required as usage grows. The current poller filters collection-group results in process to avoid requiring an index during initial deployment.
- Recall Calendar V2 and the `notes@millionways.ai` invite flow are separate follow-up work. This branch keeps the existing Google Calendar connection and auto-dispatch behavior, backed by Firestore.

# mw_meeting_bot

A Python/FastAPI backend service that integrates [Recall.ai](https://recall.ai) with the Millionways platform. It handles bot dispatch, live meeting status, transcript capture, and Google Calendar auto-dispatch for Zoom, Google Meet, and Microsoft Teams meetings.

## Architecture

This service is designed to run as a **Cloud Run container** alongside the existing Millionways Firebase infrastructure. Firebase Cloud Functions act as an authenticated gateway — they verify the user's Firebase Auth token and org membership, then forward requests to this service.

```
Millionways Vue frontend
        │  Firebase callable / SSE
        ▼
Firebase Cloud Functions          ← auth + org checks (existing)
        │  ID-token-authenticated HTTP
        ▼
mw_meeting_bot  (this service)    ← Recall workflow, polling, SSE, data
        │
        ├── Cloud SQL (Postgres)  ← meeting + transcript metadata
        ├── Firebase Storage      ← transcript JSON blobs
        └── Recall.ai             ← bot dispatch + transcription
```

The Firebase Functions layer already exists in `millionways-platform` and is ready to deploy. The bridge client (`functions/src/services/meetingBotClient.ts`) routes all meeting requests to this service using `MEETING_BOT_SERVICE_URL`.

## Features

- **Bot dispatch** — POST a meeting URL and a Recall.ai bot joins within seconds
- **Live status updates** — Server-Sent Events stream pushes status changes to the UI in real time
- **Transcript capture** — polls Recall for transcript readiness, parses speaker-diarized segments, stores to DB
- **Speaker renaming** — display names persisted per-participant, reflected in transcript
- **Soft delete** — meetings are archived, not hard-deleted
- **Google Calendar integration** — users connect their Google Calendar; the auto-dispatcher monitors upcoming meetings and dispatches bots automatically
- **Per-org data isolation** — all meetings are scoped to `org_id` and `created_by_uid`

## Tech stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| Framework | FastAPI + Uvicorn |
| ORM / migrations | SQLAlchemy 2 (async) + Alembic |
| Database (local) | SQLite via `aiosqlite` |
| Database (production) | Cloud SQL Postgres via `asyncpg` |
| HTTP client | `httpx` (async) |
| Package manager | `uv` |
| Real-time | `sse-starlette` (SSE) |
| Calendar OAuth | Google OAuth 2.0 (`calendar.readonly` scope) |

## API surface

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/meetings` | Dispatch a bot to a meeting |
| `GET` | `/api/meetings` | List meetings (filterable by org, platform) |
| `GET` | `/api/meetings/{id}` | Get a single meeting with transcript |
| `PATCH` | `/api/meetings/{id}` | Update meeting title |
| `DELETE` | `/api/meetings/{id}` | Soft-delete a meeting |
| `PATCH` | `/api/meetings/{id}/participants/{pid}` | Rename a speaker |
| `GET` | `/api/events` | SSE stream for live meeting status |
| `GET` | `/api/auth/google/start` | Start Google Calendar OAuth flow |
| `GET` | `/api/auth/google/callback` | OAuth callback |
| `GET` | `/api/auth/google/status` | Check if Google Calendar is connected |
| `POST` | `/api/auth/google/disconnect` | Disconnect Google Calendar |
| `GET` | `/api/calendar/events` | List upcoming calendar events |
| `GET` | `/api/calendar/auto-dispatch` | Get auto-dispatch setting |
| `PATCH` | `/api/calendar/auto-dispatch` | Toggle auto-dispatch on/off |

## Local development

### Prerequisites

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/) — `pip install uv`
- Node.js + `pnpm` (for the standalone dev frontend)
- A [Recall.ai](https://recall.ai) API key

### Setup

```bash
# 1. Clone and enter the repo
git clone https://github.com/Finn1118/mw_meeting_bot.git
cd mw_meeting_bot

# 2. Copy and fill in env vars
cp .env.example .env
# Set RECALL_API_KEY and RECALL_REGION at minimum

# 3. Create the Python virtual environment and install deps
cd backend
uv venv
uv sync

# 4. Run database migrations
uv run alembic upgrade head

# 5. Start the backend
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

To run with the **Millionways platform frontend** (recommended):

```bash
# In millionways-platform/functions — start the Firebase Functions emulator
FUNCTIONS_DISCOVERY_TIMEOUT=60000 npm run serve

# In millionways-platform — start the Vue dev server pointing at the emulator
VITE_USE_FUNCTIONS_EMULATOR=true npm run dev
```

To run with the **standalone dev frontend** (for isolated backend testing):

```bash
cd frontend
pnpm install
pnpm dev
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `RECALL_API_KEY` | Yes | — | Recall.ai API key |
| `RECALL_REGION` | No | `us-east-1` | Recall.ai region (must match key) |
| `RECALL_BOT_NAME` | No | `Notetaker` | Display name shown in meetings |
| `POLL_INTERVAL_SECONDS` | No | `5` | How often to poll Recall for status |
| `ENABLE_POLLER` | No | `true` | Start the background polling loop |
| `DATABASE_URL` | No | SQLite (local) | SQLAlchemy DB URL; use `postgresql+asyncpg://...` in production |
| `ALLOWED_ORIGINS` | No | `http://127.0.0.1:5173` | Comma-separated CORS origins |
| `FRONTEND_BASE_URL` | No | `http://127.0.0.1:5173` | Redirect target after OAuth |
| `ENABLE_GOOGLE_CALENDAR` | No | `true` | Enable calendar routes and auto-dispatcher |
| `GOOGLE_OAUTH_CLIENT_ID` | If calendar | — | Google OAuth client ID |
| `GOOGLE_OAUTH_CLIENT_SECRET` | If calendar | — | Google OAuth client secret |
| `GOOGLE_OAUTH_REDIRECT_URI` | If calendar | `http://127.0.0.1:8000/api/auth/google/callback` | Must match OAuth client config |
| `ENABLE_WEBHOOKS` | No | `false` | Enable Recall webhook receiver (alternative to polling) |
| `RECALL_WEBHOOK_SECRET` | If webhooks | — | Webhook signature verification secret |

## Production deployment (Cloud Run)

### What you need

- Cloud Run service (min-instances=1, 512MB+ memory)
- Cloud SQL Postgres instance
- Firebase Storage bucket write access for the Cloud Run service account
- Secret Manager secrets: `RECALL_API_KEY`, `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `DATABASE_URL`
- `MEETING_BOT_SERVICE_URL` set in Firebase Functions environment config



### Switching from polling to webhooks

Set `RECALL_WEBHOOK_SECRET` and `PUBLIC_WEBHOOK_BASE_URL`, register `/api/webhooks/recall` in the Recall dashboard, then set `ENABLE_WEBHOOKS=true` and `ENABLE_POLLER=false`.

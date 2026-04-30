# Local Meeting Transcription App

Local-first web app for dispatching a Recall.ai bot to Zoom, Google Meet, or Microsoft Teams meetings and viewing saved transcripts.

## Run Locally

1. Install prerequisites: Python 3.12, `uv`, Node.js, `pnpm`, and a Recall.ai API key.
2. Copy `.env.example` to `.env` and fill in the required Recall and webhook values.
3. Create the backend environment from `backend/` with `uv venv`.
4. Install backend dependencies from `backend/` as they are added in later steps.
5. Run backend migrations once Alembic is configured.
6. Start the backend on `127.0.0.1:8000`.
7. Install frontend dependencies from `frontend/` with `pnpm install`.
8. Start the frontend on `127.0.0.1:5173`.
9. Configure your tunnel to forward Recall webhooks to `/api/webhooks/recall`.
10. Open the frontend and paste a supported meeting URL.

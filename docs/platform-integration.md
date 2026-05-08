# Future Platform Integration

This repo stays self-contained for now. The goal is to keep the meeting bot service easy to migrate into the Millionways platform later without editing `millionways-platform` during prototype work.

See `docs/platform-api-contract.md` for the stabilized HTTP contract and the callable function mapping now used by the platform bridge layer.

## Intended Production Shape

```text
Vue/Firebase platform UI
  -> Firebase callable function
  -> Cloud Run FastAPI meeting-bot service
  -> Recall.ai
  -> Postgres and GCS
```

The callable function should own Firebase Auth and organization membership checks. The FastAPI service should stay focused on meeting lifecycle, Recall API calls, transcript parsing, and persistence.

## Platform Field Mapping

The meeting bot API already accepts optional platform-shaped fields:

- `org_id`: future Firebase organization id from `organizations/{orgId}`.
- `created_by_uid`: Firebase user id that dispatched the bot.
- `platform_conversation_id`: future Firestore conversation document id under `organizations/{orgId}/conversations/{conversationId}`.

These fields are optional so local development can continue without auth.

## Future Callable Contracts

### `meetingDispatch`

Validates the Firebase user is a member of `orgId`, creates or receives a platform conversation id, then calls:

```http
POST /api/meetings
```

Payload:

```json
{
  "meeting_url": "https://meet.google.com/abc-defg-hij",
  "title": "Weekly sync",
  "org_id": "org_123",
  "created_by_uid": "firebase_uid",
  "platform_conversation_id": "conversation_doc_id"
}
```

### `meetingList`

Validates membership and calls:

```http
GET /api/meetings?org_id=org_123
```

Optional filters can include `platform`, `limit`, and `offset`.

### `meetingGet`

Validates membership and calls:

```http
GET /api/meetings/{meeting_id}?org_id=org_123
```

The `org_id` query parameter prevents accidentally returning a meeting from a different organization.

### `meetingRenameParticipant`

Validates membership and calls:

```http
PATCH /api/meetings/{meeting_id}/participants/{participant_id}?org_id=org_123
```

Payload:

```json
{
  "display_name": "Alice Smith"
}
```

## Service-To-Service Auth

Follow the existing Millionways Cloud Run bridge pattern:

- Store the bot service base URL as `MEETING_BOT_SERVICE_URL`.
- For non-local URLs, use `GoogleAuth().getIdTokenClient(audience)`.
- Send `Authorization: Bearer <identityToken>`.
- Grant the Firebase Functions service account `roles/run.invoker` on the Cloud Run service.
- Forward `X-Request-Id` and log it in both services.

Local emulator calls to `localhost` or `127.0.0.1` can skip the identity token.

## Later Deployment Tasks

- Add a backend Dockerfile and Cloud Run service definition.
- Move `DATABASE_URL` from SQLite to Postgres.
- Move raw transcript blobs from local disk to GCS behind `backend/app/services/storage.py`.
- Prefer Recall webhooks in production when dashboard access and signing secret are available.
- Keep parsed transcript segments in the database so the UI does not depend on blob reads.

## Google Calendar Migration Notes

The local Google Calendar integration is intentionally single-account and server-side:

- `GET /api/auth/google/start` begins OAuth consent.
- `GET /api/auth/google/callback` stores the demo connection in `google_connection`.
- `GET /api/calendar/events?days=7` lists upcoming events and extracts supported meeting links.

This is enough to validate Calendar visibility without building platform auth locally. When moved behind `millionways-platform`, the connection table should evolve from one demo row to user/org-scoped rows keyed by:

- `org_id`
- `created_by_uid`
- provider, currently `google`

The future Firebase callable wrapper should validate `requireOrgMember`, pass the Firebase UID and org id to the meeting bot service, and call these same calendar endpoints or their user-scoped equivalents. The platform can keep using Firebase Auth for identity while this service owns Google Calendar token refresh and Calendar API calls.

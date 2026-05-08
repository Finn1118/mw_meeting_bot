# Meeting Bot API Contract (Phase 1)

This document stabilizes the API contract consumed by the live Millionways platform bridge layer.

## Scope

- HTTP API implemented by `mw_meeting_bot` (`/api/meetings`, `/api/auth/google`, `/api/calendar`).
- Callable wrappers implemented in `millionways-platform/functions` that enforce Firebase auth + org membership.
- Calendar integration functions required for live usage (connect, status, events, auto-dispatch).

## Contract Rules

- Breaking changes require a contract version update and coordinated platform rollout.
- Existing fields are backward-compatible unless explicitly marked deprecated.
- Error payload shape is stable:

```json
{
  "error": "machine_readable_code",
  "message": "Human readable message."
}
```

- `X-Request-Id` is accepted and echoed to support cross-service tracing.
- Org scoping is enforced via `org_id` query params for meeting read/update operations.

## Stable HTTP Endpoints

### Meetings

- `POST /api/meetings`
  - Request body:
    - `meeting_url` (required string)
    - `title` (optional string)
    - `org_id` (optional string)
    - `created_by_uid` (optional string)
    - `platform_conversation_id` (optional string)
  - Success: `200` with `MeetingRead`
  - Errors: `400 invalid_url`, `502 recall_api_error`, `507 recall_pool_exhausted`

- `GET /api/meetings`
  - Query:
    - `org_id` (optional string, required in platform bridge)
    - `platform` (optional: `zoom|meet|teams`)
    - `limit` (1-100), `offset` (>=0)
  - Success: `200` with `{ items: MeetingRead[], total: number }`

- `GET /api/meetings/{meeting_id}`
  - Query: `org_id` (optional string, required in platform bridge)
  - Success: `200` with `MeetingRead`
  - Error: `404 not_found`

- `PATCH /api/meetings/{meeting_id}`
  - Query: `org_id` (optional string, required in platform bridge)
  - Request body: `title` (nullable string)
  - Success: `200` with `MeetingRead`
  - Error: `404 not_found`

- `DELETE /api/meetings/{meeting_id}`
  - Query: `org_id` (optional string, required in platform bridge)
  - Success: `204`
  - Error: `404 not_found`

- `PATCH /api/meetings/{meeting_id}/participants/{participant_id}`
  - Query: `org_id` (optional string, required in platform bridge)
  - Request body: `display_name` (required string)
  - Success: `200` with `ParticipantRead`
  - Errors: `404 not_found`

### Google OAuth

- `GET /api/auth/google/start`
  - Returns `302` redirect to Google OAuth consent
  - Errors: `503 not_configured`

- `GET /api/auth/google/callback`
  - Query: `code`, `state`
  - Stores connection, then redirects to platform calendar page
  - Errors: `400 invalid_state`, `502 google_oauth_failed`

- `GET /api/auth/google/status`
  - Success: `{ connected: boolean, email: string | null }`

- `POST /api/auth/google/disconnect`
  - Success: `{ ok: true }`

### Calendar

- `GET /api/calendar/events`
  - Query: `days` (1-30, default 7)
  - Success: `{ items: CalendarEventRead[] }`
  - Errors: `409 not_connected`, `503 google_unavailable`

- `GET /api/calendar/auto-dispatch`
  - Success: `{ enabled: boolean }`

- `PATCH /api/calendar/auto-dispatch`
  - Request body: `{ enabled: boolean }`
  - Success: `{ enabled: boolean }`
  - Error: `409 not_connected`

## Platform Callable Function Mapping (Phase 2)

The live platform calls these Firebase callable functions:

- `meetingDispatch`
- `meetingList`
- `meetingGet`
- `meetingUpdate`
- `meetingDelete`
- `meetingRenameParticipant`
- `meetingGoogleAuthStart`
- `meetingGoogleAuthStatus`
- `meetingGoogleDisconnect`
- `meetingCalendarEvents`
- `meetingAutoDispatchGet`
- `meetingAutoDispatchUpdate`

Each callable:

- Requires authenticated Firebase user.
- Requires org membership (`orgId`) via `requireOrgMember`.
- Forwards requests to this service.
- Maps service errors into appropriate Firebase `HttpsError` codes.

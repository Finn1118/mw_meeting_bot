export type MeetingPlatform = 'zoom' | 'meet' | 'teams'

export type MeetingStatus =
  | 'dispatching'
  | 'bot_created'
  | 'joining'
  | 'waiting_room'
  | 'in_call_not_recording'
  | 'recording'
  | 'processing'
  | 'complete'
  | 'failed'

export type ApiErrorBody = {
  error: string
  message: string
}

export type MeetingCreate = {
  meeting_url: string
  title?: string
  org_id?: string
  created_by_uid?: string
  platform_conversation_id?: string
}

export type MeetingUpdate = {
  title?: string | null
}

export type ParticipantUpdate = {
  display_name: string
}

export type ParticipantRead = {
  id: number
  meeting_id: string
  recall_id: string | null
  name: string
  display_name: string | null
  is_host: boolean
}

export type TranscriptSegmentRead = {
  id: number
  meeting_id: string
  participant_id: number | null
  speaker_label: string
  text: string
  start_ms: number
  end_ms: number
}

export type MeetingRead = {
  id: string
  meeting_url: string
  platform: MeetingPlatform
  title: string | null
  org_id: string | null
  created_by_uid: string | null
  platform_conversation_id: string | null
  bot_id: string | null
  recording_id: string | null
  transcript_id: string | null
  status: MeetingStatus
  sub_code: string | null
  started_at: string | null
  ended_at: string | null
  duration_sec: number | null
  transcript_path: string | null
  recording_path: string | null
  created_at: string
  updated_at: string
  deleted_at: string | null
  participants: ParticipantRead[]
  segments: TranscriptSegmentRead[]
}

export type MeetingList = {
  items: MeetingRead[]
  total: number
}

export type HealthResponse = {
  ok: boolean
  version: string
}

export type GoogleAuthStatus = {
  connected: boolean
  email: string | null
}

export type CalendarMeetingLink = {
  platform: MeetingPlatform
  url: string
}

export type CalendarEventRead = {
  id: string
  title: string
  start: string | null
  end: string | null
  organizer_email: string | null
  html_link: string | null
  meeting_link: CalendarMeetingLink | null
}

export type CalendarEventList = {
  items: CalendarEventRead[]
}

export type AutoDispatchSetting = {
  enabled: boolean
}

export type SseUpdate = {
  meeting_id?: string
  status?: MeetingStatus
  event?: string
  [key: string]: unknown
}

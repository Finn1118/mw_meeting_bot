import type { MeetingStatus } from '../types'

export type StatusCopy = {
  label: string
  description: string
  className: string
  showLiveDot?: boolean
}

export const STATUS_COPY: Record<MeetingStatus, StatusCopy> = {
  dispatching: {
    label: 'Dispatching',
    description: 'Sending bot to meeting...',
    className: 'border-zinc-700 bg-zinc-800 text-zinc-200',
  },
  bot_created: {
    label: 'Queued',
    description: 'Bot created. Waiting to join.',
    className: 'border-zinc-700 bg-zinc-800 text-zinc-200',
  },
  joining: {
    label: 'Joining',
    description: 'Bot is joining the meeting...',
    className: 'border-blue-500/40 bg-blue-500/10 text-blue-200',
  },
  waiting_room: {
    label: 'Waiting',
    description: 'Admit "Notetaker" from the meeting waiting room.',
    className: 'border-yellow-500/40 bg-yellow-500/10 text-yellow-200',
  },
  in_call_not_recording: {
    label: 'In call',
    description: 'Bot joined. Waiting for recording permission.',
    className: 'border-blue-500/40 bg-blue-500/10 text-blue-200',
  },
  recording: {
    label: 'Recording',
    description: 'Bot is recording the meeting.',
    className: 'border-red-500/40 bg-red-500/10 text-red-200',
    showLiveDot: true,
  },
  processing: {
    label: 'Processing',
    description: 'Meeting ended. Generating transcript...',
    className: 'border-blue-500/40 bg-blue-500/10 text-blue-200',
  },
  complete: {
    label: 'Complete',
    description: 'Transcript ready.',
    className: 'border-emerald-500/40 bg-emerald-500/10 text-emerald-200',
  },
  failed: {
    label: 'Failed',
    description: 'Bot failed.',
    className: 'border-red-500/40 bg-red-500/10 text-red-200',
  },
}

export const FAILURE_COPY: Record<string, string> = {
  zoom_email_required: "This Zoom meeting requires a registered email. We don't support that yet.",
  zoom_internal_error: 'Zoom rejected the bot. This is usually transient. Try again.',
  bot_kicked_from_call: 'The host removed the bot from the meeting.',
  timeout_exceeded_waiting_room: 'Bot waited in the waiting room too long without being admitted.',
  call_ended_by_platform_waiting_room_timeout:
    'Microsoft Teams kicked the bot from the waiting room.',
  recording_permission_denied: 'The host denied recording permission.',
}

export function failedStatusCopy(subCode: string | null): string {
  if (!subCode) {
    return 'Bot failed. Try again.'
  }
  return FAILURE_COPY[subCode] ?? `Bot failed. Code: ${subCode}. Try again.`
}

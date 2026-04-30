import clsx from 'clsx'

import type { MeetingStatus } from '../types'

type StatusCopy = {
  label: string
  description: string
  className: string
  showLiveDot?: boolean
}

const STATUS_COPY: Record<MeetingStatus, StatusCopy> = {
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

type StatusBadgeProps = {
  status: MeetingStatus
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const copy = STATUS_COPY[status]

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium',
        copy.className,
      )}
    >
      {copy.showLiveDot ? <span className="h-1.5 w-1.5 rounded-full bg-red-400" /> : null}
      {copy.label}
    </span>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import type { ChangeEvent } from 'react'
import { Link, useParams } from 'react-router-dom'

import { apiClient } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import { TranscriptView } from '../components/TranscriptView'
import { useSSE } from '../hooks/useSSE'
import { failedStatusCopy, STATUS_COPY } from '../lib/statusCopy'
import type { MeetingRead, MeetingStatus } from '../types'

const IN_FLIGHT_STATUSES: MeetingStatus[] = [
  'dispatching',
  'bot_created',
  'joining',
  'waiting_room',
  'in_call_not_recording',
  'recording',
  'processing',
]

export function ConversationDetail() {
  const { id } = useParams()
  const [meeting, setMeeting] = useState<MeetingRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [titleDraft, setTitleDraft] = useState('')
  const [titleState, setTitleState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [retrying, setRetrying] = useState(false)
  const missingMeetingId = !id
  const { latestEvent, connectionState } = useSSE(id)
  const handledCompleteEventRef = useRef<string | null>(null)

  const refreshMeeting = useCallback(async (meetingId: string): Promise<void> => {
    try {
      const refreshed = await apiClient.getMeeting(meetingId)
      setMeeting(refreshed)
      setTitleDraft(refreshed.title || '')
    } catch {
      setError('Could not refresh this conversation.')
    }
  }, [])

  const saveTitle = useCallback(async (): Promise<void> => {
    if (!meeting) {
      return
    }
    const nextTitle = titleDraft.trim()
    if (nextTitle === (meeting.title || '')) {
      return
    }

    setTitleState('saving')
    try {
      const updated = await apiClient.updateMeeting(meeting.id, { title: nextTitle || null })
      setMeeting(updated)
      setTitleDraft(updated.title || '')
      setTitleState('saved')
    } catch {
      setTitleState('error')
    }
  }, [meeting, titleDraft])

  useEffect(() => {
    if (!id) {
      return undefined
    }

    const meetingId = id
    let ignore = false
    async function loadMeeting(): Promise<void> {
      try {
        const loaded = await apiClient.getMeeting(meetingId)
        if (!ignore) {
          setMeeting(loaded)
          setTitleDraft(loaded.title || '')
        }
      } catch {
        if (!ignore) {
          setError('Could not load this conversation.')
        }
      }
    }

    void loadMeeting()
    return () => {
      ignore = true
    }
  }, [id])

  useEffect(() => {
    if (!latestEvent || !meeting || latestEvent.meeting_id !== meeting.id) {
      return undefined
    }

    if (latestEvent.status) {
      queueMicrotask(() => {
        setMeeting((current) =>
          current
            ? {
                ...current,
                status: latestEvent.status ?? current.status,
                sub_code:
                  typeof latestEvent.sub_code === 'string'
                    ? latestEvent.sub_code
                    : current.sub_code,
              }
            : current,
        )
      })
    }

    if (latestEvent.status === 'complete') {
      const eventKey = `${meeting.id}:${meeting.updated_at}:${meeting.transcript_id ?? 'pending'}`
      if (handledCompleteEventRef.current === eventKey) {
        return undefined
      }
      handledCompleteEventRef.current = eventKey
      queueMicrotask(() => {
        void refreshMeeting(meeting.id)
      })
    }
    return undefined
  }, [latestEvent, meeting, refreshMeeting])

  useEffect(() => {
    if (!meeting) {
      return undefined
    }
    const trimmedDraft = titleDraft.trim()
    const currentTitle = meeting.title || ''
    if (trimmedDraft === currentTitle) {
      return undefined
    }

    const timer = setTimeout(() => {
      void saveTitle()
    }, 700)

    return () => clearTimeout(timer)
  }, [meeting, saveTitle, titleDraft])

  async function retryMeeting(): Promise<void> {
    if (!meeting) {
      return
    }

    setRetrying(true)
    try {
      const created = await apiClient.createMeeting({
        meeting_url: meeting.meeting_url,
        ...(meeting.title ? { title: meeting.title } : {}),
        ...(meeting.org_id ? { org_id: meeting.org_id } : {}),
        ...(meeting.created_by_uid ? { created_by_uid: meeting.created_by_uid } : {}),
        ...(meeting.platform_conversation_id
          ? { platform_conversation_id: meeting.platform_conversation_id }
          : {}),
      })
      window.location.assign(`/meetings/${created.id}`)
    } catch {
      setError('Could not retry this meeting.')
    } finally {
      setRetrying(false)
    }
  }

  function handleParticipantRenamed(participantId: number, displayName: string): void {
    setMeeting((current) => {
      if (!current) {
        return current
      }
      return {
        ...current,
        participants: current.participants.map((participant) =>
          participant.id === participantId ? { ...participant, display_name: displayName } : participant,
        ),
        segments: current.segments.map((segment) =>
          segment.participant_id === participantId
            ? { ...segment, speaker_label: displayName }
            : segment,
        ),
      }
    })
  }

  function handleTitleChange(event: ChangeEvent<HTMLInputElement>): void {
    setTitleDraft(event.target.value)
    setTitleState('idle')
  }

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto max-w-4xl">
        <Link className="text-sm text-zinc-400 transition hover:text-zinc-100" to="/">
          Back to conversations
        </Link>

        <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6">
          {missingMeetingId ? (
            <p className="text-sm text-red-300">Meeting id is missing.</p>
          ) : error ? (
            <p className="text-sm text-red-300">{error}</p>
          ) : meeting ? (
            <>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">
                    Conversation
                  </p>
                  <input
                    className="mt-2 w-full rounded-xl border border-transparent bg-transparent px-0 text-3xl font-semibold tracking-tight text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-zinc-800 focus:bg-zinc-950 focus:px-3"
                    onBlur={() => void saveTitle()}
                    onChange={handleTitleChange}
                    placeholder="Untitled meeting"
                    value={titleDraft}
                  />
                  <p className="mt-2 text-xs text-zinc-500">
                    {meeting.platform.toUpperCase()} · {meeting.started_at || 'Not started'} ·{' '}
                    {connectionState}
                    {titleState === 'saving' ? ' · saving title' : null}
                    {titleState === 'saved' ? ' · title saved' : null}
                    {titleState === 'error' ? ' · title save failed' : null}
                  </p>
                </div>
                <StatusBadge status={meeting.status} />
              </div>
              <div className="mt-8">
                {IN_FLIGHT_STATUSES.includes(meeting.status) ? (
                  <StatusPanel status={meeting.status} />
                ) : meeting.status === 'failed' ? (
                  <FailedPanel
                    onRetry={() => void retryMeeting()}
                    retrying={retrying}
                    subCode={meeting.sub_code}
                  />
                ) : (
                  <TranscriptView
                    meeting={meeting}
                    onParticipantRenamed={handleParticipantRenamed}
                  />
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-zinc-400">Loading conversation...</p>
          )}
        </div>
      </section>
    </main>
  )
}

function StatusPanel({ status }: { status: MeetingStatus }) {
  const copy = STATUS_COPY[status]
  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-6">
      <div className="flex items-center gap-3">
        <div className="h-4 w-4 animate-spin rounded-full border-2 border-zinc-700 border-t-zinc-100" />
        <div>
          <p className="font-medium text-zinc-100">{copy.label}</p>
          <p className="mt-1 text-sm text-zinc-400">{copy.description}</p>
        </div>
      </div>
    </div>
  )
}

function FailedPanel({
  onRetry,
  retrying,
  subCode,
}: {
  onRetry: () => void
  retrying: boolean
  subCode: string | null
}) {
  return (
    <div className="rounded-2xl border border-red-500/30 bg-red-500/10 p-6">
      <p className="font-medium text-red-100">Meeting failed</p>
      <p className="mt-2 text-sm text-red-200">{failedStatusCopy(subCode)}</p>
      <button
        className="mt-4 rounded-xl bg-red-100 px-4 py-2 text-sm font-medium text-red-950 disabled:opacity-60"
        disabled={retrying}
        onClick={onRetry}
        type="button"
      >
        {retrying ? 'Trying again...' : 'Try again'}
      </button>
    </div>
  )
}

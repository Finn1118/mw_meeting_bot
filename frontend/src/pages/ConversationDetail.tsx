import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { apiClient } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { MeetingRead } from '../types'

export function ConversationDetail() {
  const { id } = useParams()
  const [meeting, setMeeting] = useState<MeetingRead | null>(null)
  const [error, setError] = useState<string | null>(null)
  const missingMeetingId = !id

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
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-sm uppercase tracking-[0.2em] text-zinc-500">
                    Conversation
                  </p>
                  <h1 className="mt-2 text-3xl font-semibold tracking-tight">
                    {meeting.title || 'Untitled meeting'}
                  </h1>
                </div>
                <StatusBadge status={meeting.status} />
              </div>
              <p className="mt-5 text-sm text-zinc-400">
                Conversation detail and transcript controls are built in the next step.
              </p>
            </>
          ) : (
            <p className="text-sm text-zinc-400">Loading conversation...</p>
          )}
        </div>
      </section>
    </main>
  )
}

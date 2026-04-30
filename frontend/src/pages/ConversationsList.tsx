import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { apiClient } from '../api/client'
import { StatusBadge } from '../components/StatusBadge'
import type { MeetingList, MeetingPlatform, MeetingRead } from '../types'

type PlatformFilter = 'all' | MeetingPlatform

export function ConversationsList() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<PlatformFilter>('all')
  const [data, setData] = useState<MeetingList | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let ignore = false

    async function loadMeetings(): Promise<void> {
      setLoading(true)
      setError(null)
      try {
        const list = await apiClient.listMeetings({
          limit: 50,
          offset: 0,
          ...(filter === 'all' ? {} : { platform: filter }),
        })
        if (!ignore) {
          setData(list)
        }
      } catch {
        if (!ignore) {
          setError('Could not load conversations.')
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    void loadMeetings()

    function handleVisibilityChange(): void {
      if (document.visibilityState === 'visible') {
        void loadMeetings()
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      ignore = true
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [filter])

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto max-w-6xl">
        <header className="flex flex-col gap-4 border-b border-zinc-800 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-[0.2em] text-zinc-500">
              Local Meeting Transcription
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight">My Conversations</h1>
          </div>
          <Link
            className="inline-flex w-fit items-center rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 transition hover:bg-white"
            to="/meetings/new"
          >
            New meeting
          </Link>
        </header>

        <div className="mt-6 flex items-center gap-3">
          <label className="text-sm text-zinc-400" htmlFor="platform-filter">
            Platform
          </label>
          <select
            className="rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
            id="platform-filter"
            onChange={(event) => setFilter(event.target.value as PlatformFilter)}
            value={filter}
          >
            <option value="all">All</option>
            <option value="zoom">Zoom</option>
            <option value="meet">Meet</option>
            <option value="teams">Teams</option>
          </select>
        </div>

        <div className="mt-6 overflow-hidden rounded-2xl border border-zinc-800 bg-zinc-900/60">
          {loading ? (
            <div className="p-8 text-sm text-zinc-400">Loading conversations...</div>
          ) : error ? (
            <div className="p-8 text-sm text-red-300">{error}</div>
          ) : data && data.items.length > 0 ? (
            <table className="w-full border-collapse text-left text-sm">
              <thead className="border-b border-zinc-800 text-xs uppercase tracking-wide text-zinc-500">
                <tr>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Title</th>
                  <th className="px-4 py-3 font-medium">Platform</th>
                  <th className="px-4 py-3 font-medium">Started</th>
                  <th className="px-4 py-3 font-medium">Duration</th>
                  <th className="px-4 py-3 font-medium">Participants</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((meeting) => (
                  <tr
                    className="cursor-pointer border-b border-zinc-800/70 transition last:border-0 hover:bg-zinc-800/40"
                    key={meeting.id}
                    onClick={() => navigate(`/meetings/${meeting.id}`)}
                  >
                    <td className="px-4 py-4">
                      <StatusBadge status={meeting.status} />
                    </td>
                    <td className="px-4 py-4 text-zinc-100">{meetingTitle(meeting)}</td>
                    <td className="px-4 py-4 text-zinc-300">{platformLabel(meeting.platform)}</td>
                    <td className="px-4 py-4 text-zinc-400">{relativeTime(meeting.started_at)}</td>
                    <td className="px-4 py-4 text-zinc-400">{formatDuration(meeting.duration_sec)}</td>
                    <td className="px-4 py-4 text-zinc-400">{participantsSummary(meeting)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-10 text-center">
              <p className="text-zinc-100">No meetings yet.</p>
              <p className="mt-2 text-sm text-zinc-500">Paste a meeting link to start.</p>
            </div>
          )}
        </div>
      </section>
    </main>
  )
}

function meetingTitle(meeting: MeetingRead): string {
  return meeting.title?.trim() || 'Untitled meeting'
}

function platformLabel(platform: MeetingPlatform): string {
  const labels: Record<MeetingPlatform, string> = {
    zoom: 'Zoom',
    meet: 'Google Meet',
    teams: 'Microsoft Teams',
  }
  return labels[platform]
}

function relativeTime(value: string | null): string {
  if (!value) {
    return 'Not started'
  }
  const elapsedMs = Date.now() - new Date(value).getTime()
  const minutes = Math.max(1, Math.round(elapsedMs / 60_000))
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  return `${Math.round(hours / 24)}d ago`
}

function formatDuration(durationSec: number | null): string {
  if (durationSec === null) {
    return '—'
  }
  const minutes = Math.floor(durationSec / 60)
  const seconds = durationSec % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

function participantsSummary(meeting: MeetingRead): string {
  if (meeting.participants.length === 0) {
    return 'No participants'
  }
  const names = meeting.participants
    .slice(0, 2)
    .map((participant) => participant.display_name || participant.name)
  const extraCount = meeting.participants.length - names.length
  return extraCount > 0 ? `${names.join(', ')} +${extraCount}` : names.join(', ')
}

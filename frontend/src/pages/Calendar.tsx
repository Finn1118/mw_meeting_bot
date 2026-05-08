import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { ApiClientError, apiClient } from '../api/client'
import type { CalendarEventList, CalendarEventRead, MeetingPlatform } from '../types'

export function Calendar() {
  const [status, setStatus] = useState<{ connected: boolean; email: string | null } | null>(null)
  const [events, setEvents] = useState<CalendarEventList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [disconnecting, setDisconnecting] = useState(false)
  const [autoDispatchEnabled, setAutoDispatchEnabled] = useState(false)
  const [updatingAutoDispatch, setUpdatingAutoDispatch] = useState(false)

  useEffect(() => {
    let ignore = false

    async function load(): Promise<void> {
      setLoading(true)
      setError(null)
      try {
        const nextStatus = await apiClient.googleAuthStatus()
        if (ignore) {
          return
        }
        setStatus(nextStatus)
        if (nextStatus.connected) {
          const [nextEvents, autoDispatch] = await Promise.all([
            apiClient.listCalendarEvents(7),
            apiClient.getCalendarAutoDispatch(),
          ])
          if (!ignore) {
            setEvents(nextEvents)
            setAutoDispatchEnabled(autoDispatch.enabled)
          }
        }
      } catch (caught) {
        if (!ignore) {
          setError(errorCopy(caught))
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    void load()
    return () => {
      ignore = true
    }
  }, [])

  function connectGoogle(): void {
    window.location.assign('/api/auth/google/start')
  }

  async function disconnectGoogle(): Promise<void> {
    setDisconnecting(true)
    setError(null)
    try {
      await apiClient.disconnectGoogle()
      setStatus({ connected: false, email: null })
      setEvents(null)
      setAutoDispatchEnabled(false)
    } catch (caught) {
      setError(errorCopy(caught))
    } finally {
      setDisconnecting(false)
    }
  }

  async function toggleAutoDispatch(): Promise<void> {
    const nextEnabled = !autoDispatchEnabled
    setUpdatingAutoDispatch(true)
    setError(null)
    try {
      const nextSetting = await apiClient.updateCalendarAutoDispatch(nextEnabled)
      setAutoDispatchEnabled(nextSetting.enabled)
    } catch (caught) {
      setError(errorCopy(caught))
    } finally {
      setUpdatingAutoDispatch(false)
    }
  }

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto max-w-5xl">
        <Link className="text-sm text-zinc-400 transition hover:text-zinc-100" to="/">
          Back to conversations
        </Link>

        <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6 shadow-2xl shadow-black/20">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-sm font-medium uppercase tracking-[0.2em] text-zinc-500">
                Google Calendar
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight">Upcoming meetings</h1>
              <p className="mt-3 max-w-2xl text-sm text-zinc-400">
                Connect one Google account and preview upcoming calendar events with meeting links.
                Auto-dispatch is available for local testing, but is off by default.
              </p>
            </div>

            {status?.connected ? (
              <button
                className="rounded-xl border border-zinc-700 px-4 py-2.5 text-sm text-zinc-200 transition hover:bg-zinc-800 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={disconnecting}
                onClick={() => void disconnectGoogle()}
                type="button"
              >
                {disconnecting ? 'Disconnecting...' : 'Disconnect'}
              </button>
            ) : null}
          </div>

          <div className="mt-8">
            {loading ? (
              <p className="text-sm text-zinc-400">Loading calendar status...</p>
            ) : error ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error}
              </div>
            ) : status?.connected ? (
              <ConnectedCalendar
                autoDispatchEnabled={autoDispatchEnabled}
                email={status.email}
                events={events?.items ?? []}
                onToggleAutoDispatch={() => void toggleAutoDispatch()}
                updatingAutoDispatch={updatingAutoDispatch}
              />
            ) : (
              <div className="rounded-2xl border border-zinc-800 bg-zinc-950/70 p-6">
                <p className="text-zinc-100">Google Calendar is not connected.</p>
                <p className="mt-2 text-sm text-zinc-500">
                  You will be redirected to Google to grant read-only calendar access.
                </p>
                <button
                  className="mt-5 rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 transition hover:bg-white"
                  onClick={connectGoogle}
                  type="button"
                >
                  Connect Google Calendar
                </button>
              </div>
            )}
          </div>
        </div>
      </section>
    </main>
  )
}

function ConnectedCalendar({
  autoDispatchEnabled,
  email,
  events,
  onToggleAutoDispatch,
  updatingAutoDispatch,
}: {
  autoDispatchEnabled: boolean
  email: string | null
  events: CalendarEventRead[]
  onToggleAutoDispatch: () => void
  updatingAutoDispatch: boolean
}) {
  return (
    <div>
      <p className="text-sm text-zinc-400">
        Connected{email ? ` as ${email}` : ''}. Showing events from the next 7 days.
      </p>
      <div className="mt-5 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="font-medium text-zinc-100">Auto-dispatch calendar meetings</p>
            <p className="mt-2 max-w-2xl text-sm text-zinc-500">
              Off by default. When enabled, the local backend checks for supported meeting links
              starting soon and sends the bot once per calendar event.
            </p>
          </div>
          <button
            className={`rounded-xl px-4 py-2.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-60 ${
              autoDispatchEnabled
                ? 'bg-emerald-400 text-emerald-950 hover:bg-emerald-300'
                : 'border border-zinc-700 text-zinc-200 hover:bg-zinc-800'
            }`}
            disabled={updatingAutoDispatch}
            onClick={onToggleAutoDispatch}
            type="button"
          >
            {updatingAutoDispatch
              ? 'Updating...'
              : autoDispatchEnabled
                ? 'Auto-dispatch on'
                : 'Auto-dispatch off'}
          </button>
        </div>
      </div>
      <div className="mt-5 overflow-hidden rounded-2xl border border-zinc-800">
        {events.length > 0 ? (
          <table className="w-full border-collapse text-left text-sm">
            <thead className="border-b border-zinc-800 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-4 py-3 font-medium">Event</th>
                <th className="px-4 py-3 font-medium">When</th>
                <th className="px-4 py-3 font-medium">Organizer</th>
                <th className="px-4 py-3 font-medium">Meeting link</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event) => (
                <tr className="border-b border-zinc-800/70 last:border-0" key={event.id}>
                  <td className="px-4 py-4 text-zinc-100">
                    {event.html_link ? (
                      <a
                        className="transition hover:text-white hover:underline"
                        href={event.html_link}
                        rel="noreferrer"
                        target="_blank"
                      >
                        {event.title}
                      </a>
                    ) : (
                      event.title
                    )}
                  </td>
                  <td className="px-4 py-4 text-zinc-400">{formatEventTime(event)}</td>
                  <td className="px-4 py-4 text-zinc-400">{event.organizer_email ?? 'Unknown'}</td>
                  <td className="px-4 py-4">{meetingLinkCell(event)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="p-8 text-sm text-zinc-400">No upcoming calendar events found.</div>
        )}
      </div>
    </div>
  )
}

function meetingLinkCell(event: CalendarEventRead) {
  if (!event.meeting_link) {
    return <span className="text-zinc-500">No supported link found</span>
  }
  return (
    <a
      className="inline-flex rounded-full border border-zinc-700 px-3 py-1 text-xs font-medium text-zinc-200 transition hover:bg-zinc-800"
      href={event.meeting_link.url}
      rel="noreferrer"
      target="_blank"
    >
      {platformLabel(event.meeting_link.platform)}
    </a>
  )
}

function formatEventTime(event: CalendarEventRead): string {
  if (!event.start) {
    return 'Time unknown'
  }
  const start = formatDateTime(event.start)
  return event.end ? `${start} - ${formatDateTime(event.end)}` : start
}

function formatDateTime(value: string): string {
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return parsed.toLocaleString(undefined, {
    dateStyle: 'medium',
    timeStyle: value.includes('T') ? 'short' : undefined,
  })
}

function platformLabel(platform: MeetingPlatform): string {
  const labels: Record<MeetingPlatform, string> = {
    zoom: 'Zoom',
    meet: 'Google Meet',
    teams: 'Microsoft Teams',
  }
  return labels[platform]
}

function errorCopy(caught: unknown): string {
  if (caught instanceof ApiClientError) {
    if (caught.error === 'not_configured') {
      return 'Google OAuth is not configured yet. Add GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.'
    }
    if (caught.error === 'not_connected') {
      return 'Google Calendar is not connected.'
    }
    return caught.message
  }
  return 'Calendar request failed.'
}

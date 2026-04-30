import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiClientError, apiClient } from '../api/client'
import { parseMeetingUrl } from '../lib/meetingUrl'

const ERROR_COPY: Record<string, string> = {
  invalid_url: 'Paste a valid Zoom, Google Meet, or Microsoft Teams meeting link.',
  recall_api_error: 'Recall could not create the bot. Check your API key and try again.',
  recall_pool_exhausted: 'Recall bot capacity is temporarily exhausted. Try again shortly.',
}

export function NewMeeting() {
  const navigate = useNavigate()
  const [meetingUrl, setMeetingUrl] = useState('')
  const [title, setTitle] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    setError(null)

    try {
      parseMeetingUrl(meetingUrl)
    } catch {
      setError(ERROR_COPY.invalid_url)
      return
    }

    setSubmitting(true)
    try {
      const meeting = await apiClient.createMeeting({
        meeting_url: meetingUrl.trim(),
        ...(title.trim() ? { title: title.trim() } : {}),
      })
      navigate(`/meetings/${meeting.id}`)
    } catch (caught) {
      if (caught instanceof ApiClientError) {
        setError(ERROR_COPY[caught.error] ?? caught.message)
      } else {
        setError('Something went wrong while creating the meeting.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto max-w-2xl">
        <Link className="text-sm text-zinc-400 transition hover:text-zinc-100" to="/">
          Back to conversations
        </Link>

        <div className="mt-6 rounded-2xl border border-zinc-800 bg-zinc-900/70 p-6 shadow-2xl shadow-black/20">
          <p className="text-sm font-medium uppercase tracking-[0.2em] text-zinc-500">
            New meeting
          </p>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight">Send a bot to record</h1>
          <p className="mt-3 text-sm text-zinc-400">
            Paste a Zoom, Google Meet, or Microsoft Teams link. The backend dispatches the Recall
            bot and starts tracking status changes.
          </p>

          <form className="mt-8 space-y-5" onSubmit={(event) => void handleSubmit(event)}>
            <label className="block">
              <span className="text-sm font-medium text-zinc-300">Meeting link</span>
              <textarea
                className="mt-2 min-h-32 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-zinc-600"
                onChange={(event) => setMeetingUrl(event.target.value)}
                placeholder="Paste your Zoom, Google Meet, or Microsoft Teams link..."
                value={meetingUrl}
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-zinc-300">Title optional</span>
              <input
                className="mt-2 w-full rounded-xl border border-zinc-800 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none transition placeholder:text-zinc-600 focus:border-zinc-600"
                onChange={(event) => setTitle(event.target.value)}
                placeholder="Weekly team sync"
                value={title}
              />
            </label>

            {error ? (
              <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                {error}
              </div>
            ) : null}

            <button
              className="rounded-xl bg-zinc-100 px-4 py-2.5 text-sm font-medium text-zinc-950 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
              disabled={submitting}
              type="submit"
            >
              {submitting ? 'Dispatching...' : 'Create meeting'}
            </button>
          </form>
        </div>
      </section>
    </main>
  )
}

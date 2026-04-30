import { useState } from 'react'
import type { FormEvent } from 'react'

import { apiClient } from '../api/client'
import type { ParticipantRead } from '../types'

type SpeakerLabelProps = {
  meetingId: string
  participant: ParticipantRead
  onRenamed: (participantId: number, displayName: string) => void
}

export function SpeakerLabel({ meetingId, participant, onRenamed }: SpeakerLabelProps) {
  const currentName = participant.display_name || participant.name
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState(currentName)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault()
    const displayName = draft.trim()
    if (!displayName) {
      setError('Speaker name is required.')
      return
    }

    setSaving(true)
    setError(null)
    onRenamed(participant.id, displayName)
    try {
      await apiClient.renameParticipant(meetingId, participant.id, { display_name: displayName })
      setOpen(false)
    } catch {
      setError('Could not rename speaker.')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="relative inline-block">
      <button
        className="rounded-md text-left font-medium text-zinc-100 underline decoration-zinc-700 underline-offset-4 transition hover:text-white"
        onClick={() => {
          setDraft(currentName)
          setOpen((value) => !value)
        }}
        type="button"
      >
        {currentName}
      </button>

      {open ? (
        <form
          className="absolute left-0 top-8 z-10 w-64 rounded-xl border border-zinc-700 bg-zinc-950 p-3 shadow-2xl shadow-black/40"
          onSubmit={(event) => void handleSubmit(event)}
        >
          <label className="block text-xs font-medium uppercase tracking-wide text-zinc-500">
            Rename speaker
            <input
              className="mt-2 w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-zinc-600"
              onChange={(event) => setDraft(event.target.value)}
              value={draft}
            />
          </label>
          {error ? <p className="mt-2 text-xs text-red-300">{error}</p> : null}
          <div className="mt-3 flex justify-end gap-2">
            <button
              className="rounded-lg px-3 py-1.5 text-xs text-zinc-400 transition hover:text-zinc-100"
              onClick={() => setOpen(false)}
              type="button"
            >
              Cancel
            </button>
            <button
              className="rounded-lg bg-zinc-100 px-3 py-1.5 text-xs font-medium text-zinc-950 disabled:opacity-60"
              disabled={saving}
              type="submit"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </form>
      ) : null}
    </div>
  )
}

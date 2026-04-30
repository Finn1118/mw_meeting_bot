import { useMemo, useState } from 'react'

import { SpeakerLabel } from './SpeakerLabel'
import type { MeetingRead, ParticipantRead, TranscriptSegmentRead } from '../types'

type SegmentGroup = {
  participantId: number | null
  speakerLabel: string
  segments: TranscriptSegmentRead[]
}

type TranscriptViewProps = {
  meeting: MeetingRead
  onParticipantRenamed?: (participantId: number, displayName: string) => void
}

export function TranscriptView({ meeting, onParticipantRenamed }: TranscriptViewProps) {
  const [displayNames, setDisplayNames] = useState<Record<number, string>>({})
  const participantById = useMemo(
    () => new Map(meeting.participants.map((participant) => [participant.id, participant])),
    [meeting.participants],
  )
  const groups = useMemo(() => groupConsecutiveSegments(meeting.segments), [meeting.segments])

  function handleRenamed(participantId: number, displayName: string): void {
    setDisplayNames((current) => ({ ...current, [participantId]: displayName }))
    onParticipantRenamed?.(participantId, displayName)
  }

  if (groups.length === 0) {
    return (
      <div className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-6 text-sm text-zinc-400">
        Transcript is complete, but no segments were returned.
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {groups.map((group, index) => {
        const participant = participantForGroup(group, participantById, displayNames)
        return (
          <article
            className="rounded-2xl border border-zinc-800 bg-zinc-900/60 p-5"
            key={`${group.participantId ?? 'unknown'}-${index}`}
          >
            <div className="mb-4">
              {participant ? (
                <SpeakerLabel
                  meetingId={meeting.id}
                  onRenamed={handleRenamed}
                  participant={participant}
                />
              ) : (
                <span className="font-medium text-zinc-100">{group.speakerLabel}</span>
              )}
            </div>
            <div className="space-y-3">
              {group.segments.map((segment) => (
                <p className="leading-7 text-zinc-300" key={segment.id}>
                  <button
                    className="mr-3 rounded-md bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-500 transition hover:text-zinc-200"
                    onClick={() => console.log('Audio playback coming soon.', segment.start_ms)}
                    title="Audio playback coming soon."
                    type="button"
                  >
                    {formatTimestamp(segment.start_ms)}
                  </button>
                  {segment.text}
                </p>
              ))}
            </div>
          </article>
        )
      })}
    </div>
  )
}

function groupConsecutiveSegments(segments: TranscriptSegmentRead[]): SegmentGroup[] {
  const groups: SegmentGroup[] = []
  for (const segment of segments) {
    const last = groups.at(-1)
    if (last && last.participantId === segment.participant_id) {
      last.segments.push(segment)
    } else {
      groups.push({
        participantId: segment.participant_id,
        speakerLabel: segment.speaker_label,
        segments: [segment],
      })
    }
  }
  return groups
}

function participantForGroup(
  group: SegmentGroup,
  participantById: Map<number, ParticipantRead>,
  displayNames: Record<number, string>,
): ParticipantRead | null {
  if (group.participantId === null) {
    return null
  }
  const participant = participantById.get(group.participantId)
  if (!participant) {
    return null
  }
  return {
    ...participant,
    display_name: displayNames[group.participantId] ?? participant.display_name,
  }
}

function formatTimestamp(startMs: number): string {
  const totalSeconds = Math.floor(startMs / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${seconds.toString().padStart(2, '0')}`
}

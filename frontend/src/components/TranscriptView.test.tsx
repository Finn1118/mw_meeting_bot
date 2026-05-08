import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { TranscriptView } from './TranscriptView'
import type { MeetingRead } from '../types'

const baseMeeting: MeetingRead = {
  id: 'meeting_123',
  meeting_url: 'https://meet.google.com/abc-defg-hij',
  platform: 'meet',
  title: 'Team sync',
  org_id: null,
  created_by_uid: null,
  platform_conversation_id: null,
  bot_id: 'bot_123',
  recording_id: null,
  transcript_id: 'transcript_123',
  status: 'complete',
  sub_code: null,
  started_at: null,
  ended_at: null,
  duration_sec: null,
  transcript_path: null,
  recording_path: null,
  created_at: '2026-04-30T00:00:00Z',
  updated_at: '2026-04-30T00:00:00Z',
  deleted_at: null,
  participants: [
    {
      id: 1,
      meeting_id: 'meeting_123',
      recall_id: 'alice',
      name: 'Alice',
      display_name: null,
      is_host: true,
    },
    {
      id: 2,
      meeting_id: 'meeting_123',
      recall_id: 'bob',
      name: 'Bob',
      display_name: null,
      is_host: false,
    },
  ],
  segments: [
    {
      id: 10,
      meeting_id: 'meeting_123',
      participant_id: 1,
      speaker_label: 'Alice',
      text: 'Hello team',
      start_ms: 500,
      end_ms: 1300,
    },
    {
      id: 11,
      meeting_id: 'meeting_123',
      participant_id: 1,
      speaker_label: 'Alice',
      text: 'Quick update',
      start_ms: 2000,
      end_ms: 3000,
    },
    {
      id: 12,
      meeting_id: 'meeting_123',
      participant_id: 2,
      speaker_label: 'Bob',
      text: 'Sounds good',
      start_ms: 65_000,
      end_ms: 66_000,
    },
  ],
}

describe('TranscriptView', () => {
  it('groups consecutive segments and renders timestamp buttons', () => {
    render(<TranscriptView meeting={baseMeeting} />)

    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
    expect(screen.getByText('Hello team')).toBeInTheDocument()
    expect(screen.getByText('Quick update')).toBeInTheDocument()
    expect(screen.getByText('Sounds good')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '0:00' })).toHaveAttribute(
      'title',
      'Audio playback coming soon.',
    )
    expect(screen.getByRole('button', { name: '1:05' })).toBeInTheDocument()
  })

  it('logs timestamp clicks for the future audio player', () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined)
    render(<TranscriptView meeting={baseMeeting} />)

    fireEvent.click(screen.getByRole('button', { name: '0:00' }))

    expect(logSpy).toHaveBeenCalledWith('Audio playback coming soon.', 500)
    logSpy.mockRestore()
  })
})

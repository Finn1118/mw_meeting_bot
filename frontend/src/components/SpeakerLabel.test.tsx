import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { apiClient } from '../api/client'
import { SpeakerLabel } from './SpeakerLabel'
import type { ParticipantRead } from '../types'

vi.mock('../api/client', () => ({
  apiClient: {
    renameParticipant: vi.fn(),
  },
}))

const participant: ParticipantRead = {
  id: 1,
  meeting_id: 'meeting_123',
  recall_id: 'alice',
  name: 'Alice',
  display_name: null,
  is_host: true,
}

describe('SpeakerLabel', () => {
  beforeEach(() => {
    vi.mocked(apiClient.renameParticipant).mockReset()
  })

  it('opens a rename popover and saves the new speaker name', async () => {
    vi.mocked(apiClient.renameParticipant).mockResolvedValue({
      ...participant,
      display_name: 'Alice Cooper',
    })
    const onRenamed = vi.fn()

    render(
      <SpeakerLabel
        meetingId="meeting_123"
        onRenamed={onRenamed}
        participant={participant}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Alice' }))
    fireEvent.change(screen.getByLabelText(/rename speaker/i), {
      target: { value: 'Alice Cooper' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(onRenamed).toHaveBeenCalledWith(1, 'Alice Cooper')
    await waitFor(() =>
      expect(apiClient.renameParticipant).toHaveBeenCalledWith('meeting_123', 1, {
        display_name: 'Alice Cooper',
      }),
    )
  })
})

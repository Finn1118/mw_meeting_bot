import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiClientError, apiClient } from './client'

const fetchMock = vi.fn<typeof fetch>()

globalThis.fetch = fetchMock

describe('apiClient', () => {
  afterEach(() => {
    fetchMock.mockReset()
  })

  it('creates a meeting with the expected request body', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          id: 'meeting_123',
          meeting_url: 'https://meet.google.com/abc-defg-hij',
          platform: 'meet',
          title: 'Standup',
          org_id: 'org_123',
          created_by_uid: 'user_123',
          platform_conversation_id: 'conv_123',
          bot_id: 'bot_123',
          recording_id: null,
          transcript_id: null,
          status: 'bot_created',
          sub_code: null,
          started_at: null,
          ended_at: null,
          duration_sec: null,
          transcript_path: null,
          recording_path: null,
          created_at: '2026-04-30T00:00:00Z',
          updated_at: '2026-04-30T00:00:00Z',
          deleted_at: null,
          participants: [],
          segments: [],
        }),
        { status: 200 },
      ),
    )

    const meeting = await apiClient.createMeeting({
      meeting_url: 'https://meet.google.com/abc-defg-hij',
      title: 'Standup',
      org_id: 'org_123',
      created_by_uid: 'user_123',
      platform_conversation_id: 'conv_123',
    })

    expect(meeting.id).toBe('meeting_123')
    expect(fetchMock).toHaveBeenCalledWith('/api/meetings', {
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
      body: JSON.stringify({
        meeting_url: 'https://meet.google.com/abc-defg-hij',
        title: 'Standup',
        org_id: 'org_123',
        created_by_uid: 'user_123',
        platform_conversation_id: 'conv_123',
      }),
    })
  })

  it('builds list query params', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ items: [], total: 0 }), { status: 200 }),
    )

    await apiClient.listMeetings({ limit: 10, offset: 20, platform: 'zoom', org_id: 'org_123' })

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/meetings?limit=10&offset=20&platform=zoom&org_id=org_123',
      {
        headers: { 'Content-Type': 'application/json' },
      },
    )
  })

  it('throws typed errors for non-2xx responses', async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ error: 'invalid_url', message: 'Meeting URL is not supported.' }), {
        status: 400,
      }),
    )

    await expect(
      apiClient.createMeeting({ meeting_url: 'https://example.com' }),
    ).rejects.toMatchObject({
      status: 400,
      error: 'invalid_url',
      message: 'Meeting URL is not supported.',
    } satisfies Partial<ApiClientError>)
  })

  it('returns undefined for 204 responses', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

    await expect(apiClient.deleteMeeting('meeting_123')).resolves.toBeUndefined()
  })

  it('updates calendar auto-dispatch setting', async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ enabled: true }), { status: 200 }))

    await expect(apiClient.updateCalendarAutoDispatch(true)).resolves.toEqual({ enabled: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/calendar/auto-dispatch', {
      headers: { 'Content-Type': 'application/json' },
      method: 'PATCH',
      body: JSON.stringify({ enabled: true }),
    })
  })
})

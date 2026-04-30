import type {
  HealthResponse,
  MeetingCreate,
  MeetingList,
  MeetingPlatform,
  MeetingRead,
  MeetingUpdate,
  ParticipantRead,
  ParticipantUpdate,
} from '../types'

export class ApiClientError extends Error {
  readonly status: number
  readonly error: string

  constructor(
    message: string,
    status: number,
    error: string,
  ) {
    super(message)
    this.name = 'ApiClientError'
    this.status = status
    this.error = error
  }
}

const API_BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers,
    },
    ...init,
  })

  if (!response.ok) {
    throw await parseApiError(response)
  }

  if (response.status === 204) {
    return undefined as T
  }

  return (await response.json()) as T
}

async function parseApiError(response: Response): Promise<ApiClientError> {
  try {
    const body = (await response.json()) as { error?: unknown; message?: unknown }
    const error = typeof body.error === 'string' ? body.error : 'request_failed'
    const message = typeof body.message === 'string' ? body.message : response.statusText
    return new ApiClientError(message, response.status, error)
  } catch {
    return new ApiClientError(response.statusText, response.status, 'request_failed')
  }
}

function meetingListQuery(params?: {
  limit?: number
  offset?: number
  platform?: MeetingPlatform
}): string {
  const search = new URLSearchParams()
  if (params?.limit !== undefined) {
    search.set('limit', String(params.limit))
  }
  if (params?.offset !== undefined) {
    search.set('offset', String(params.offset))
  }
  if (params?.platform !== undefined) {
    search.set('platform', params.platform)
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

export const apiClient = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>('/api/health')
  },

  createMeeting(payload: MeetingCreate): Promise<MeetingRead> {
    return request<MeetingRead>('/api/meetings', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  listMeetings(params?: {
    limit?: number
    offset?: number
    platform?: MeetingPlatform
  }): Promise<MeetingList> {
    return request<MeetingList>(`/api/meetings${meetingListQuery(params)}`)
  },

  getMeeting(id: string): Promise<MeetingRead> {
    return request<MeetingRead>(`/api/meetings/${encodeURIComponent(id)}`)
  },

  updateMeeting(id: string, payload: MeetingUpdate): Promise<MeetingRead> {
    return request<MeetingRead>(`/api/meetings/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    })
  },

  deleteMeeting(id: string): Promise<void> {
    return request<void>(`/api/meetings/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },

  renameParticipant(
    meetingId: string,
    participantId: number,
    payload: ParticipantUpdate,
  ): Promise<ParticipantRead> {
    return request<ParticipantRead>(
      `/api/meetings/${encodeURIComponent(meetingId)}/participants/${participantId}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      },
    )
  },
}

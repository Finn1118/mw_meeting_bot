import { useEffect, useRef, useState } from 'react'

import type { SseUpdate } from '../types'

export type SseConnectionState = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'closed'

export type UseSseResult = {
  latestEvent: SseUpdate | null
  connectionState: SseConnectionState
}

const MAX_RECONNECT_DELAY_MS = 10_000

export function useSSE(meetingId: string | null | undefined): UseSseResult {
  const [latestEvent, setLatestEvent] = useState<SseUpdate | null>(null)
  const [connectionState, setConnectionState] = useState<SseConnectionState>('idle')
  const reconnectAttempt = useRef(0)

  useEffect(() => {
    if (!meetingId) {
      return undefined
    }

    const activeMeetingId = meetingId
    let closed = false
    let eventSource: EventSource | null = null
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    function connect(): void {
      setConnectionState(reconnectAttempt.current === 0 ? 'connecting' : 'reconnecting')
      eventSource = new EventSource(`/api/events?meeting_id=${encodeURIComponent(activeMeetingId)}`)

      eventSource.addEventListener('open', () => {
        reconnectAttempt.current = 0
        setConnectionState('open')
      })

      eventSource.addEventListener('update', (event) => {
        setLatestEvent(JSON.parse(event.data) as SseUpdate)
      })

      eventSource.addEventListener('error', () => {
        eventSource?.close()
        if (closed) {
          return
        }

        reconnectAttempt.current += 1
        const delay = Math.min(
          1000 * 2 ** (reconnectAttempt.current - 1),
          MAX_RECONNECT_DELAY_MS,
        )
        setConnectionState('reconnecting')
        reconnectTimer = setTimeout(connect, delay)
      })
    }

    connect()

    return () => {
      closed = true
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      eventSource?.close()
      setConnectionState('closed')
    }
  }, [meetingId])

  if (!meetingId) {
    return { latestEvent: null, connectionState: 'idle' }
  }

  return { latestEvent, connectionState }
}

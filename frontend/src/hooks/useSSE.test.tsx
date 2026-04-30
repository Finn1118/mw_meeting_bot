import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useSSE } from './useSSE'

type Listener = (event: MessageEvent<string> | Event) => void

class FakeEventSource {
  static instances: FakeEventSource[] = []

  readonly listeners = new Map<string, Listener[]>()
  readonly url: string
  closed = false

  constructor(url: string) {
    this.url = url
    FakeEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: Listener): void {
    const existing = this.listeners.get(type) ?? []
    existing.push(listener)
    this.listeners.set(type, existing)
  }

  close(): void {
    this.closed = true
  }

  emit(type: string, data?: string): void {
    const event = data === undefined ? new Event(type) : new MessageEvent(type, { data })
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event)
    }
  }
}

describe('useSSE', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('opens an EventSource and exposes update payloads', () => {
    const { result, unmount } = renderHook(() => useSSE('meeting_123'))

    expect(FakeEventSource.instances[0]?.url).toBe('/api/events?meeting_id=meeting_123')
    expect(result.current.connectionState).toBe('connecting')

    act(() => {
      FakeEventSource.instances[0]?.emit('open')
    })
    expect(result.current.connectionState).toBe('open')

    act(() => {
      FakeEventSource.instances[0]?.emit(
        'update',
        JSON.stringify({ meeting_id: 'meeting_123', status: 'recording' }),
      )
    })
    expect(result.current.latestEvent).toEqual({
      meeting_id: 'meeting_123',
      status: 'recording',
    })

    unmount()
    expect(FakeEventSource.instances[0]?.closed).toBe(true)
  })

  it('reconnects with backoff after an error', () => {
    const { result } = renderHook(() => useSSE('meeting_123'))

    act(() => {
      FakeEventSource.instances[0]?.emit('error')
    })

    expect(FakeEventSource.instances[0]?.closed).toBe(true)
    expect(result.current.connectionState).toBe('reconnecting')
    expect(FakeEventSource.instances).toHaveLength(1)

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(FakeEventSource.instances).toHaveLength(2)
    expect(FakeEventSource.instances[1]?.url).toBe('/api/events?meeting_id=meeting_123')
  })

  it('stays idle without a meeting id', () => {
    const { result } = renderHook(() => useSSE(null))

    expect(result.current.connectionState).toBe('idle')
    expect(result.current.latestEvent).toBeNull()
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})

import type { MeetingPlatform } from '../types'

export type ParsedMeetingUrl = {
  platform: MeetingPlatform
  normalizedUrl: string
}

// Keep these in sync with backend/app/services/url_parser.py.
const ZOOM_RE =
  /^https?:\/\/(?:[a-z0-9-]+\.)?(?:zoom\.us|zoomgov\.com)\/(?:j|my|w|wc\/join)\/[A-Za-z0-9_./?&=%-]+/i
const MEET_RE = /^https?:\/\/meet\.google\.com\/[a-z]{3}-[a-z]{4}-[a-z]{3}(?:\?.*)?$/i
const TEAMS_RE =
  /^https?:\/\/teams\.(?:microsoft|live)\.com\/(?:l\/meetup-join|meet)\/[A-Za-z0-9%_.\-/?&=]+/i

export function parseMeetingUrl(url: string): ParsedMeetingUrl {
  const normalizedUrl = url.trim()
  if (ZOOM_RE.test(normalizedUrl)) {
    return { platform: 'zoom', normalizedUrl }
  }
  if (MEET_RE.test(normalizedUrl)) {
    return { platform: 'meet', normalizedUrl }
  }
  if (TEAMS_RE.test(normalizedUrl)) {
    return { platform: 'teams', normalizedUrl }
  }
  throw new Error('invalid_url')
}

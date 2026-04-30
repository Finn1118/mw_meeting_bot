import re
from dataclasses import dataclass


@dataclass
class ParsedMeetingUrl:
    platform: str
    normalized_url: str


ZOOM_RE = re.compile(
    r"^https?://(?:[a-z0-9-]+\.)?(?:zoom\.us|zoomgov\.com)/(?:j|my|w|wc/join)/[A-Za-z0-9_./?&=%-]+",
    re.IGNORECASE,
)
MEET_RE = re.compile(
    r"^https?://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}(?:\?.*)?$",
    re.IGNORECASE,
)
TEAMS_RE = re.compile(
    r"^https?://teams\.(?:microsoft|live)\.com/(?:l/meetup-join|meet)/[A-Za-z0-9%_.\-/?&=]+",
    re.IGNORECASE,
)


def parse_meeting_url(url: str) -> ParsedMeetingUrl:
    """Raises ValueError('invalid_url') if no platform matches."""
    url = url.strip()
    if ZOOM_RE.match(url):
        return ParsedMeetingUrl("zoom", url)
    if MEET_RE.match(url):
        return ParsedMeetingUrl("meet", url)
    if TEAMS_RE.match(url):
        return ParsedMeetingUrl("teams", url)
    raise ValueError("invalid_url")

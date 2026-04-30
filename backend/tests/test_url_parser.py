import pytest

from app.services.url_parser import ParsedMeetingUrl, parse_meeting_url


@pytest.mark.parametrize(
    ("url", "platform"),
    [
        ("https://us02web.zoom.us/j/1234567890?pwd=abc", "zoom"),
        ("https://zoom.us/j/1234", "zoom"),
        ("https://meet.google.com/abc-defg-hij", "meet"),
        ("https://teams.microsoft.com/l/meetup-join/19%3ameeting_xxx", "teams"),
        ("https://teams.live.com/meet/123", "teams"),
    ],
)
def test_parse_valid_meeting_urls(url: str, platform: str) -> None:
    assert parse_meeting_url(url) == ParsedMeetingUrl(platform=platform, normalized_url=url)


def test_parse_strips_surrounding_whitespace() -> None:
    assert parse_meeting_url("  https://zoom.us/j/1234  ") == ParsedMeetingUrl(
        platform="zoom",
        normalized_url="https://zoom.us/j/1234",
    )


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not a url",
        "http://example.com",
        "https://meet.google.com/AB-CDEF-GHI",
        "https://zoom.us/",
    ],
)
def test_parse_invalid_meeting_urls(url: str) -> None:
    with pytest.raises(ValueError, match="invalid_url"):
        parse_meeting_url(url)

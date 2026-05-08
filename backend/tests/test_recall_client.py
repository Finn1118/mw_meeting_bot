import pytest
from pytest_httpx import HTTPXMock

from app.services.recall import RecallApiError, RecallClient, RecallPoolExhausted


def make_client() -> RecallClient:
    return RecallClient(api_key="test-key", region="us-east-1")


@pytest.mark.asyncio
async def test_create_bot_success(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://us-east-1.recall.ai/api/v1/bot/",
        json={"id": "bot_123"},
    )

    response = await make_client().create_bot(
        meeting_url="https://meet.google.com/abc-defg-hij",
        bot_name="Notetaker",
    )

    assert response == {"id": "bot_123"}
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["Authorization"] == "Token test-key"
    assert request.read() == (
        b'{"meeting_url":"https://meet.google.com/abc-defg-hij",'
        b'"bot_name":"Notetaker",'
        b'"recording_config":{"transcript":{"provider":{"meeting_captions":{"language_code":"en"}},'
        b'"diarization":{"use_separate_streams_when_available":true}},'
        b'"video_mixed_mp4":{},'
        b'"retention":{"type":"timed","hours":24}},'
        b'"webhook_url":null}'
    )


@pytest.mark.asyncio
async def test_create_bot_maps_507_to_pool_exhausted(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://us-east-1.recall.ai/api/v1/bot/",
        status_code=507,
        text="pool exhausted",
    )

    with pytest.raises(RecallPoolExhausted) as exc_info:
        await make_client().create_bot(
            meeting_url="https://meet.google.com/abc-defg-hij",
            bot_name="Notetaker",
        )

    assert exc_info.value.status_code == 507
    assert exc_info.value.body == "pool exhausted"


@pytest.mark.asyncio
async def test_create_bot_maps_generic_500_to_recall_api_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="POST",
        url="https://us-east-1.recall.ai/api/v1/bot/",
        status_code=500,
        text="server error",
    )

    with pytest.raises(RecallApiError) as exc_info:
        await make_client().create_bot(
            meeting_url="https://meet.google.com/abc-defg-hij",
            bot_name="Notetaker",
        )

    assert not isinstance(exc_info.value, RecallPoolExhausted)
    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "server error"


@pytest.mark.asyncio
async def test_transcript_download_flow(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        method="GET",
        url="https://us-east-1.recall.ai/api/v1/transcript/transcript_123/",
        json={"id": "transcript_123", "data": {"download_url": "https://example-s3.test/raw.json"}},
    )
    raw_transcript: list[object] = [
        {
            "participant": {"id": 12345, "name": "Alice Smith", "is_host": True},
            "words": [
                {
                    "text": "Hello",
                    "start_timestamp": {"relative": 0.5},
                    "end_timestamp": {"relative": 0.9},
                }
            ],
        }
    ]
    httpx_mock.add_response(
        method="GET",
        url="https://example-s3.test/raw.json",
        json=raw_transcript,
    )

    client = make_client()
    metadata = await client.get_transcript("transcript_123")
    downloaded = await client.download_transcript_json("https://example-s3.test/raw.json")

    assert metadata == {
        "id": "transcript_123",
        "data": {"download_url": "https://example-s3.test/raw.json"},
    }
    assert downloaded == raw_transcript

    requests = httpx_mock.get_requests()
    assert requests[0].headers["Authorization"] == "Token test-key"
    assert "Authorization" not in requests[1].headers

from collections.abc import Mapping
from typing import cast

import httpx


JsonObject = dict[str, object]
JsonPayload = JsonObject | list[object]


class RecallApiError(Exception):
    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Recall API returned {status_code}: {body}")


class RecallPoolExhausted(RecallApiError):
    pass


class RecallClient:
    def __init__(self, api_key: str, region: str) -> None:
        self._api_key = api_key
        self._base_url = f"https://{region}.recall.ai"
        self._timeout = httpx.Timeout(30.0)

    async def create_bot(self, meeting_url: str, bot_name: str) -> JsonObject:
        body: JsonObject = {
            "meeting_url": meeting_url,
            "bot_name": bot_name,
            "recording_config": {
                "transcript": {
                    "provider": {"recallai_async": {"language_code": "en"}},
                    "diarization": {"use_separate_streams_when_available": True},
                },
                "video_mixed_mp4": {},
                "retention": {"type": "timed", "hours": 24},
            },
            "webhook_url": None,
        }
        return await self._recall_request("POST", "/api/v1/bot/", json_body=body)

    async def get_bot(self, bot_id: str) -> JsonObject:
        return await self._recall_request("GET", f"/api/v1/bot/{bot_id}/")

    async def get_transcript(self, transcript_id: str) -> JsonObject:
        return await self._recall_request("GET", f"/api/v1/transcript/{transcript_id}/")

    async def download_transcript_json(self, download_url: str) -> list[object]:
        response = await self._request_with_connection_retry("GET", download_url)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise ValueError("transcript_download_not_list")
        return payload

    async def leave_call(self, bot_id: str) -> None:
        await self._recall_request("POST", f"/api/v1/bot/{bot_id}/leave_call/")

    async def _recall_request(
        self,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, object] | None = None,
    ) -> JsonObject:
        response = await self._request_with_connection_retry(
            method,
            f"{self._base_url}{path}",
            headers={"Authorization": f"Token {self._api_key}"},
            json_body=json_body,
        )
        if response.status_code < 200 or response.status_code >= 300:
            error_cls = RecallPoolExhausted if response.status_code == 507 else RecallApiError
            raise error_cls(response.status_code, response.text)

        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("recall_response_not_object")
        return cast(JsonObject, payload)

    async def _request_with_connection_retry(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, object] | None = None,
    ) -> httpx.Response:
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    return await client.request(method, url, headers=headers, json=json_body)
            except httpx.ConnectError:
                if attempt == 1:
                    raise

        raise RuntimeError("unreachable retry state")

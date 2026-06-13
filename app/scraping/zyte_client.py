from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx


class ZyteClientError(RuntimeError):
    pass


@dataclass(frozen=True)
class ZyteFetchResult:
    url: str
    status_code: int | None
    html: str
    rendered: bool
    screenshot: bytes | None = None
    raw: dict | None = None


class ZyteClient:
    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.zyte.com/v1/extract",
        timeout: float = 45.0,
    ) -> None:
        if not api_key:
            raise ValueError("Zyte API key is required")
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout

    async def fetch_http(self, url: str) -> ZyteFetchResult:
        payload = {
            "url": url,
            "httpResponseBody": True,
            "httpResponseHeaders": True,
        }
        data = await self._request(payload)
        html = _decode_base64_text(data.get("httpResponseBody"))
        status_code = _status_from_response(data)
        return ZyteFetchResult(url=url, status_code=status_code, html=html, rendered=False, raw=data)

    async def fetch_browser_html(self, url: str, screenshot: bool = False) -> ZyteFetchResult:
        payload = {
            "url": url,
            "browserHtml": True,
        }
        if screenshot:
            payload["screenshot"] = True
        data = await self._request(payload)
        screenshot_bytes = _decode_base64_bytes(data.get("screenshot")) if screenshot else None
        return ZyteFetchResult(
            url=url,
            status_code=None,
            html=data.get("browserHtml") or "",
            rendered=True,
            screenshot=screenshot_bytes,
            raw=data,
        )

    async def _request(self, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.api_url,
                json=payload,
                auth=(self.api_key, ""),
            )
        if response.status_code >= 400:
            raise ZyteClientError(f"Zyte request failed with HTTP {response.status_code}: {response.text[:500]}")
        return response.json()


def _decode_base64_text(value: str | None) -> str:
    if not value:
        return ""
    return base64.b64decode(value).decode("utf-8", errors="replace")


def _decode_base64_bytes(value: str | None) -> bytes | None:
    if not value:
        return None
    return base64.b64decode(value)


def _status_from_response(data: dict) -> int | None:
    status = data.get("statusCode")
    if isinstance(status, int):
        return status
    metadata = data.get("httpResponseMetadata") or {}
    status = metadata.get("statusCode")
    return status if isinstance(status, int) else None


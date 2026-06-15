from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class ImagePayload:
    url: str
    mime_type: str
    data: bytes


class ImageFetchError(RuntimeError):
    pass


class CachedImageFetcher:
    def __init__(
        self,
        timeout_seconds: float = 8.0,
        max_bytes: int = 5_000_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.client = client
        self._cache: dict[str, ImagePayload] = {}

    async def fetch_many(self, urls: tuple[str, ...], limit: int) -> list[ImagePayload]:
        payloads: list[ImagePayload] = []
        for url in urls[:limit]:
            try:
                payloads.append(await self.fetch(url))
            except ImageFetchError:
                continue
        return payloads

    async def fetch(self, url: str) -> ImagePayload:
        if url in self._cache:
            return self._cache[url]

        if self.client:
            payload = await self._fetch_with_client(self.client, url)
        else:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=True) as client:
                payload = await self._fetch_with_client(client, url)

        self._cache[url] = payload
        return payload

    async def _fetch_with_client(self, client: httpx.AsyncClient, url: str) -> ImagePayload:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ImageFetchError(str(exc)) from exc

        content = response.content
        if len(content) > self.max_bytes:
            raise ImageFetchError(f"image exceeds {self.max_bytes} bytes")

        mime_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        if not mime_type.startswith("image/"):
            raise ImageFetchError(f"unsupported image content type: {mime_type or 'unknown'}")

        return ImagePayload(url=url, mime_type=mime_type, data=content)

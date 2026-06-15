from __future__ import annotations

import base64
import json
from typing import Protocol
from dataclasses import dataclass

import httpx

from app.domain.models import DealerSettings, ListingSnapshot
from app.services.image_fetcher import CachedImageFetcher, ImagePayload


@dataclass(frozen=True)
class ImageRiskResult:
    risk_adjustment: float
    reasons: tuple[str, ...]
    image_count: int
    summary: str | None = None
    confidence: float = 0.0


class ImageRiskAnalyzer(Protocol):
    async def analyze(self, listing: ListingSnapshot, settings: DealerSettings) -> ImageRiskResult:
        ...


class DeterministicImageRiskAnalyzer:
    async def analyze(self, listing: ListingSnapshot, settings: DealerSettings) -> ImageRiskResult:
        image_count = min(len(listing.image_urls), settings.max_images_per_candidate)
        reasons: list[str] = []
        risk_adjustment = 0.0

        if image_count == 0:
            reasons.append("no_listing_images")
            risk_adjustment -= 12
        elif image_count < 4:
            reasons.append("too_few_listing_images")
            risk_adjustment -= 6
        elif image_count < settings.max_images_per_candidate:
            reasons.append("partial_image_set")
            risk_adjustment -= 2
        else:
            reasons.append("sufficient_image_set")

        return ImageRiskResult(
            risk_adjustment=risk_adjustment,
            reasons=tuple(reasons),
            image_count=image_count,
            summary="Deterministic image coverage check.",
            confidence=0.5,
        )


class GeminiImageRiskAnalyzer:
    def __init__(
        self,
        api_key: str,
        api_url: str,
        model: str,
        image_fetcher: CachedImageFetcher,
        fallback_analyzer: ImageRiskAnalyzer | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.image_fetcher = image_fetcher
        self.fallback_analyzer = fallback_analyzer or DeterministicImageRiskAnalyzer()
        self.client = client

    async def analyze(self, listing: ListingSnapshot, settings: DealerSettings) -> ImageRiskResult:
        images = await self.image_fetcher.fetch_many(
            listing.image_urls,
            limit=settings.max_images_per_candidate,
        )
        if not images:
            return await self.fallback_analyzer.analyze(listing, settings)

        payload = self._build_payload(listing, images)
        try:
            response_payload = await self._post_generate_content(payload)
            return self._parse_response(response_payload, image_count=len(images))
        except (GeminiImageRiskError, httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return await self.fallback_analyzer.analyze(listing, settings)

    def _build_payload(self, listing: ListingSnapshot, images: list[ImagePayload]) -> dict:
        parts = [
            {
                "inlineData": {
                    "mimeType": image.mime_type,
                    "data": base64.b64encode(image.data).decode("ascii"),
                }
            }
            for image in images
        ]
        parts.append({"text": _image_analysis_prompt(listing)})
        return {
            "contents": [
                {
                    "role": "user",
                    "parts": parts,
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": _response_schema(),
            },
        }

    async def _post_generate_content(self, payload: dict) -> dict:
        url = f"{self.api_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        if self.client:
            response = await self.client.post(url, params=params, json=payload)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, params=params, json=payload)
        response.raise_for_status()
        parsed = response.json()
        return parsed if isinstance(parsed, dict) else {}

    def _parse_response(self, payload: dict, image_count: int) -> ImageRiskResult:
        text = _first_response_text(payload)
        parsed = json.loads(text)
        raw_adjustment = float(parsed.get("risk_adjustment", 0))
        reasons = parsed.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = ["invalid_gemini_reasons"]
        return ImageRiskResult(
            risk_adjustment=max(-25.0, min(8.0, raw_adjustment)),
            reasons=tuple(str(reason) for reason in reasons if str(reason).strip()) or ("gemini_image_review",),
            image_count=image_count,
            summary=str(parsed.get("summary") or ""),
            confidence=max(0.0, min(1.0, float(parsed.get("confidence", 0)))),
        )


class GeminiImageRiskError(RuntimeError):
    pass


def _first_response_text(payload: dict) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiImageRiskError("Gemini response did not include candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not isinstance(parts, list):
        raise GeminiImageRiskError("Gemini response did not include content parts")
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            return part["text"]
    raise GeminiImageRiskError("Gemini response did not include text")


def _image_analysis_prompt(listing: ListingSnapshot) -> str:
    return (
        "You are evaluating used-car listing photos for a Canadian dealer before a physical visit. "
        "Return only JSON matching the schema. Assess visible exterior damage, mismatched body panels, "
        "paint issues, tire and wheel condition, interior wear, dashboard warning lights if visible, "
        "photo quality, and missing critical angles. Use negative risk_adjustment values for risks. "
        "Use positive values only when photos strongly reduce risk. "
        f"Vehicle: {listing.vehicle.year or ''} {listing.vehicle.make or ''} {listing.vehicle.model or ''} "
        f"{listing.vehicle.trim or ''}. Asking price CAD: {listing.asking_price_cad or 'unknown'}."
    )


def _response_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "risk_adjustment": {"type": "number"},
            "reasons": {
                "type": "array",
                "items": {"type": "string"},
            },
            "summary": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["risk_adjustment", "reasons", "summary", "confidence"],
    }

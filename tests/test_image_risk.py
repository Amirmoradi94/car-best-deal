import json

import httpx
import pytest

from app.domain.models import DealerSettings, ListingSnapshot, VehicleProfile
from app.services.image_fetcher import CachedImageFetcher
from app.services.image_risk import DeterministicImageRiskAnalyzer, GeminiImageRiskAnalyzer


@pytest.mark.asyncio
async def test_cached_image_fetcher_fetches_and_caches_images() -> None:
    request_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=b"image-bytes")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        fetcher = CachedImageFetcher(client=client)

        first = await fetcher.fetch("https://images.example/car.jpg")
        second = await fetcher.fetch("https://images.example/car.jpg")

    assert first.data == b"image-bytes"
    assert second.data == b"image-bytes"
    assert request_count == 1


@pytest.mark.asyncio
async def test_gemini_image_risk_analyzer_posts_images_and_parses_json() -> None:
    gemini_requests: list[httpx.Request] = []

    def image_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "images.example":
            return httpx.Response(200, headers={"content-type": "image/png"}, content=b"png-bytes")
        gemini_requests.append(request)
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "risk_adjustment": -9,
                                            "reasons": ["visible_body_damage", "missing_interior_photos"],
                                            "summary": "Front bumper damage and no interior photos.",
                                            "confidence": 0.82,
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(image_handler)) as client:
        fetcher = CachedImageFetcher(client=client)
        analyzer = GeminiImageRiskAnalyzer(
            api_key="test-key",
            api_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-3.5-flash",
            image_fetcher=fetcher,
            fallback_analyzer=DeterministicImageRiskAnalyzer(),
            client=client,
        )
        result = await analyzer.analyze(_listing_with_images(), DealerSettings(max_images_per_candidate=2))

    assert result.risk_adjustment == -9
    assert result.reasons == ("visible_body_damage", "missing_interior_photos")
    assert result.image_count == 2
    assert result.confidence == 0.82
    assert len(gemini_requests) == 1
    request_payload = json.loads(gemini_requests[0].content)
    assert gemini_requests[0].url.params["key"] == "test-key"
    assert "models/gemini-3.5-flash:generateContent" in str(gemini_requests[0].url)
    assert request_payload["generationConfig"]["responseMimeType"] == "application/json"
    assert request_payload["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
    assert request_payload["contents"][0]["parts"][-1]["text"]


@pytest.mark.asyncio
async def test_gemini_image_risk_analyzer_falls_back_when_images_cannot_be_fetched() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        analyzer = GeminiImageRiskAnalyzer(
            api_key="test-key",
            api_url="https://generativelanguage.googleapis.com/v1beta",
            model="gemini-3.5-flash",
            image_fetcher=CachedImageFetcher(client=client),
            fallback_analyzer=DeterministicImageRiskAnalyzer(),
            client=client,
        )
        result = await analyzer.analyze(_listing_with_images(), DealerSettings(max_images_per_candidate=2))

    assert result.risk_adjustment == -6
    assert result.reasons == ("too_few_listing_images",)


def _listing_with_images() -> ListingSnapshot:
    return ListingSnapshot(
        id="listing-1",
        source_name="autotrader",
        url="https://example.test/listing",
        vehicle=VehicleProfile(year=2020, make="Honda", model="Civic", trim="EX"),
        asking_price_cad=20000,
        image_urls=(
            "https://images.example/one.png",
            "https://images.example/two.png",
        ),
    )

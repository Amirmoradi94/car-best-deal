from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.scraping.contracts import SearchFilters
from app.services.fixture_runner import score_fixture
from app.services.search_pipeline import SearchPipeline


router = APIRouter()


class SearchCreateRequest(BaseModel):
    name: str
    natural_language_query: str | None = None
    structured_filters: dict = Field(default_factory=dict)
    listing_limit: int = 25


class SearchRunResponse(BaseModel):
    status: str
    ranked_opportunities: list[dict]


@router.post("")
def create_search(payload: SearchCreateRequest) -> dict:
    return {"id": "fixture-search", "status": "created", "name": payload.name}


@router.post("/{search_id}/run", response_model=SearchRunResponse)
async def run_search(search_id: str) -> SearchRunResponse:
    pipeline = SearchPipeline()
    scored_items = await pipeline.run_multi_source_batch_search(
        SearchFilters(make="Honda", model="Civic", year_min=2020, limit=25)
    )
    return SearchRunResponse(
        status="completed",
        ranked_opportunities=[
            _opportunity_payload(search_id, scored)
            for scored in scored_items
        ],
    )


def _opportunity_payload(search_id: str, scored) -> dict:
    return {
        "search_id": search_id,
        "listing_id": scored.listing.id,
        "title": f"{scored.listing.vehicle.year} {scored.listing.vehicle.make} {scored.listing.vehicle.model} {scored.listing.vehicle.trim}",
        "source": scored.listing.source_name,
        "asking_price_cad": scored.listing.asking_price_cad,
        "deal_score": scored.deal_score,
        "recommendation": scored.recommendation,
        "estimated_retail_value_cad": scored.pricing.retail_mid_cad,
        "max_buy_price_cad": scored.pricing.max_buy_price_cad,
        "preliminary": scored.pricing.preliminary,
        "is_overpriced": scored.is_overpriced,
        "missing_data": scored.risk.missing_verifications,
        "relevance_score": scored.relevance_score,
        "relevance_reasons": scored.relevance_reasons,
    }

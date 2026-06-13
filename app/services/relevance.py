from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.models import ListingSnapshot
from app.scraping.contracts import SearchFilters


MIN_RELEVANCE_SCORE = 0.45
BORDERLINE_RELEVANCE_SCORE = 0.70


@dataclass(frozen=True)
class SearchIntent:
    query: str | None
    year: int | None
    make: str | None
    model: str | None
    tokens: tuple[str, ...]


@dataclass(frozen=True)
class RelevanceResult:
    score: float
    keep: bool
    penalty_points: float
    reasons: tuple[str, ...]


COMMON_LOCATION_TOKENS = {
    "montreal",
    "montréal",
    "laval",
    "quebec",
    "québec",
    "qc",
    "canada",
    "city",
    "ville",
}


def infer_search_intent(filters: SearchFilters) -> SearchIntent:
    tokens = _tokens(filters.query)
    year = filters.year_min or _first_year(filters.query)
    make = filters.make
    model = filters.model

    if filters.query and (not make or not model):
        non_location_tokens = [token for token in tokens if token not in COMMON_LOCATION_TOKENS and not token.isdigit()]
        if not make and non_location_tokens:
            make = non_location_tokens[0]
        if not model and len(non_location_tokens) >= 2:
            model = non_location_tokens[1]

    relevant_tokens = tuple(
        token
        for token in tokens
        if token not in COMMON_LOCATION_TOKENS and not token.isdigit()
    )
    return SearchIntent(
        query=filters.query,
        year=year,
        make=_norm(make),
        model=_norm(model),
        tokens=relevant_tokens,
    )


def score_listing_relevance(listing: ListingSnapshot, intent: SearchIntent) -> RelevanceResult:
    reasons: list[str] = []
    score = 0.0
    title_text = " ".join(
        item
        for item in [
            str(listing.vehicle.year or ""),
            listing.vehicle.make or "",
            listing.vehicle.model or "",
            listing.vehicle.trim or "",
        ]
        if item
    )
    listing_tokens = set(_tokens(title_text))
    listing_make = _norm(listing.vehicle.make)
    listing_model = _norm(listing.vehicle.model)

    if intent.make:
        if listing_make == intent.make:
            score += 0.35
            reasons.append("make_match")
        elif intent.make in listing_tokens:
            score += 0.20
            reasons.append("make_token_match")
        else:
            reasons.append("make_mismatch")
    else:
        score += 0.15
        reasons.append("make_not_requested")

    if intent.model:
        if listing_model == intent.model:
            score += 0.35
            reasons.append("model_match")
        elif intent.model in listing_tokens:
            score += 0.25
            reasons.append("model_token_match")
        else:
            reasons.append("model_mismatch")
    else:
        score += 0.15
        reasons.append("model_not_requested")

    if intent.year and listing.vehicle.year:
        gap = abs(intent.year - listing.vehicle.year)
        if gap == 0:
            score += 0.15
            reasons.append("year_match")
        elif gap <= 1:
            score += 0.08
            reasons.append("near_year_match")
        else:
            reasons.append("year_mismatch")
    elif intent.year:
        reasons.append("year_missing")
    else:
        score += 0.05
        reasons.append("year_not_requested")

    if intent.tokens:
        overlap = len(set(intent.tokens) & listing_tokens) / len(set(intent.tokens))
        if overlap:
            score += min(0.15, overlap * 0.15)
            reasons.append("query_token_overlap")
        else:
            reasons.append("no_query_token_overlap")
    else:
        score += 0.10
        reasons.append("no_query_tokens")

    score = round(min(score, 1.0), 4)
    keep = score >= MIN_RELEVANCE_SCORE
    penalty = 0.0
    if keep and score < BORDERLINE_RELEVANCE_SCORE:
        penalty = round((BORDERLINE_RELEVANCE_SCORE - score) * 25, 2)
    return RelevanceResult(score=score, keep=keep, penalty_points=penalty, reasons=tuple(reasons))


def _tokens(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(re.findall(r"[a-z0-9]+", value.casefold()))


def _norm(value: str | None) -> str | None:
    if not value:
        return None
    tokens = _tokens(value)
    return " ".join(tokens) if tokens else None


def _first_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None

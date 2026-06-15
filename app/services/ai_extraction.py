from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from html import unescape
from uuid import uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import AIModelOutput
from app.scraping.contracts import ParsedListing, SourceSnapshot
from app.storage.object_store import LocalObjectStore, ObjectStore


@dataclass(frozen=True)
class AIExtractionResult:
    feature: str
    parsed_output: dict
    confidence: float
    output_id: str | None = None
    provider: str = "deterministic"
    model: str = "local-rules"
    model_version: str = "local-rules-v1"
    schema_name: str = "unknown"
    schema_version: int = 1
    validated_output: dict | None = None
    field_confidences: dict | None = None
    evidence_links: list | None = None

    def reference(self) -> dict:
        return {
            "id": self.output_id,
            "feature": self.feature,
            "provider": self.provider,
            "model": self.model,
            "model_version": self.model_version,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
            "confidence": self.confidence,
            "field_confidences": self.field_confidences or {},
            "evidence_links": self.evidence_links or [],
        }


class _AuditOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ListingExtractionOutput(_AuditOutput):
    title: str | None = None
    year: int | None = None
    asking_price_cad: float | None = None
    mileage_km: int | None = None
    risk_flags: list[str] = Field(default_factory=list)
    summary: str | None = None
    confidence: float = 0.0


class RiskLanguageOutput(_AuditOutput):
    risk_flags: list[str] = Field(default_factory=list)
    summary: str
    confidence: float = 0.0


class VehicleHistoryOutput(_AuditOutput):
    source_type: str = "manual"
    title_brand: str = "unknown"
    accident_claims: list[dict] = Field(default_factory=list)
    odometer_issue: bool | None = None
    summary: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ComparableRelevanceOutput(_AuditOutput):
    similarity_adjustment: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    include: bool = True
    confidence: float = 0.0


class ReportNarrativeOutput(_AuditOutput):
    narrative: str
    confidence: float = 0.0
    basis: str | None = None


@dataclass(frozen=True)
class _SchemaSpec:
    name: str
    version: int
    model: type[_AuditOutput]


SCHEMA_SPECS: dict[str, _SchemaSpec] = {
    "listing_extraction_fallback": _SchemaSpec("listing_extraction_fallback", 1, ListingExtractionOutput),
    "risk_language_detection": _SchemaSpec("risk_language_detection", 1, RiskLanguageOutput),
    "vehicle_history_extraction": _SchemaSpec("vehicle_history_extraction", 1, VehicleHistoryOutput),
    "comparable_relevance_ai": _SchemaSpec("comparable_relevance_ai", 1, ComparableRelevanceOutput),
    "report_writing": _SchemaSpec("report_writing", 1, ReportNarrativeOutput),
}


class AIExtractionService:
    def __init__(
        self,
        settings: Settings,
        *,
        session: Session | None = None,
        object_store: ObjectStore | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self.session = session
        self.object_store = object_store or LocalObjectStore(settings.object_store_root)
        self.client = client

    async def listing_fallback(
        self,
        snapshot: SourceSnapshot,
        parsed: ParsedListing,
        *,
        subject_id: str,
    ) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        input_payload = {
            "url": snapshot.url,
            "source_name": snapshot.source_name,
            "parser_confidence": parsed.extraction_confidence,
            "parsed_fields": _parsed_listing_payload(parsed),
            "text_excerpt": _html_to_text(snapshot.html)[:6000],
            "has_screenshot": snapshot.screenshot is not None,
        }
        prompt = "Extract missing used-car listing fields and risk language from listing HTML/text/screenshot evidence."
        parsed_output = await self._extract_json(
            feature="listing_extraction_fallback",
            prompt=prompt,
            input_payload=input_payload,
            fallback=lambda: _deterministic_listing_output(input_payload),
        )
        confidence = float(parsed_output.get("confidence") or 0.0)
        return self._record(
            feature="listing_extraction_fallback",
            subject_type="listing",
            subject_id=subject_id,
            prompt=prompt,
            input_payload=input_payload,
            parsed_output=parsed_output,
            confidence=confidence,
        )

    async def risk_language(
        self,
        *,
        subject_type: str,
        subject_id: str,
        text: str,
    ) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        input_payload = {"text_excerpt": text[:6000]}
        prompt = "Detect used-car risk language and return normalized risk flags."
        parsed_output = await self._extract_json(
            feature="risk_language_detection",
            prompt=prompt,
            input_payload=input_payload,
            fallback=lambda: _deterministic_risk_language(input_payload["text_excerpt"]),
        )
        return self._record(
            feature="risk_language_detection",
            subject_type=subject_type,
            subject_id=subject_id,
            prompt=prompt,
            input_payload=input_payload,
            parsed_output=parsed_output,
            confidence=float(parsed_output.get("confidence") or 0.0),
        )

    async def vehicle_history(
        self,
        *,
        opportunity_id: str,
        text: str,
    ) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        input_payload = {"text_excerpt": text[:12000]}
        prompt = "Extract structured vehicle history facts from dealer-supplied report text."
        parsed_output = await self._extract_json(
            feature="vehicle_history_extraction",
            prompt=prompt,
            input_payload=input_payload,
            fallback=lambda: _deterministic_vehicle_history(input_payload["text_excerpt"]),
        )
        return self._record(
            feature="vehicle_history_extraction",
            subject_type="opportunity",
            subject_id=opportunity_id,
            prompt=prompt,
            input_payload=input_payload,
            parsed_output=parsed_output,
            confidence=float(parsed_output.get("confidence") or 0.0),
        )

    async def comparable_relevance(
        self,
        *,
        target: dict,
        comparable: dict,
    ) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        input_payload = {"target": target, "comparable": comparable}
        prompt = "Assess comparable vehicle relevance for Canadian retail pricing."
        parsed_output = await self._extract_json(
            feature="comparable_relevance_ai",
            prompt=prompt,
            input_payload=input_payload,
            fallback=lambda: _deterministic_comparable_relevance(target, comparable),
        )
        subject_id = f"{target.get('id') or 'target'}::{comparable.get('id') or 'comparable'}"
        return self._record(
            feature="comparable_relevance_ai",
            subject_type="comparable",
            subject_id=subject_id,
            prompt=prompt,
            input_payload=input_payload,
            parsed_output=parsed_output,
            confidence=float(parsed_output.get("confidence") or 0.0),
        )

    def comparable_relevance_sync(
        self,
        *,
        target: dict,
        comparable: dict,
    ) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        prompt = "Assess comparable vehicle relevance for Canadian retail pricing."
        parsed_output = _deterministic_comparable_relevance(target, comparable)
        subject_id = f"{target.get('id') or 'target'}::{comparable.get('id') or 'comparable'}"
        return self._record(
            feature="comparable_relevance_ai",
            subject_type="comparable",
            subject_id=subject_id,
            prompt=prompt,
            input_payload={"target": target, "comparable": comparable},
            parsed_output=parsed_output,
            confidence=float(parsed_output.get("confidence") or 0.0),
        )

    def report_writing(self, *, report_id: str, report_json: dict) -> AIExtractionResult | None:
        if not self._enabled():
            return None
        prompt = "Write a concise dealer-facing report narrative from normalized report JSON."
        input_payload = {"report_json": report_json}
        parsed_output = _deterministic_report_narrative(report_json)
        return self._record(
            feature="report_writing",
            subject_type="decision_report",
            subject_id=report_id,
            prompt=prompt,
            input_payload=input_payload,
            parsed_output=parsed_output,
            confidence=float(parsed_output.get("confidence") or 0.0),
        )

    async def _extract_json(
        self,
        *,
        feature: str,
        prompt: str,
        input_payload: dict,
        fallback,
    ) -> dict:
        if not self._can_use_gemini():
            return fallback()
        try:
            payload = {
                "contents": [{"role": "user", "parts": [{"text": f"{prompt}\n\nInput JSON:\n{json.dumps(input_payload, default=str)}"}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            }
            url = f"{self.settings.gemini_api_url.rstrip('/')}/models/{self.settings.gemini_model}:generateContent"
            params = {"key": self.settings.gemini_api_key}
            if self.client:
                response = await self.client.post(url, params=params, json=payload)
            else:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(url, params=params, json=payload)
            response.raise_for_status()
            parsed = json.loads(_first_response_text(response.json()))
            if isinstance(parsed, dict) and _valid_for_feature(feature, parsed):
                parsed.setdefault("feature", feature)
                return parsed
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, TypeError, ValueError, ValidationError):
            return fallback()
        return fallback()

    def _record(
        self,
        *,
        feature: str,
        subject_type: str,
        subject_id: str | None,
        prompt: str,
        input_payload: dict,
        parsed_output: dict,
        confidence: float,
        status: str = "completed",
        error_message: str | None = None,
    ) -> AIExtractionResult:
        provider = "gemini" if self._can_use_gemini() else "deterministic"
        model = self.settings.gemini_model if provider == "gemini" else "local-rules"
        model_version = self.settings.gemini_model if provider == "gemini" else "local-rules-v1"
        schema = _schema_spec(feature)
        validated_output = _validate_output(schema, parsed_output)
        field_confidences = _field_confidences(validated_output, parsed_output, confidence)
        evidence_links = _evidence_links(feature, subject_type, subject_id, input_payload)
        output_id = str(uuid4())
        base_key = f"ai-model-outputs/{output_id}"
        input_key = f"{base_key}/input.json"
        output_key = f"{base_key}/output.json"
        evidence_links = [*evidence_links, {"type": "ai_input_object", "object_key": input_key}]
        self.object_store.put_text(input_key, json.dumps(input_payload, default=str, sort_keys=True), "application/json")
        self.object_store.put_text(output_key, json.dumps(parsed_output, default=str, sort_keys=True), "application/json")

        if self.session is not None:
            row = AIModelOutput(
                id=output_id,
                feature=feature,
                subject_type=subject_type,
                subject_id=subject_id,
                provider=provider,
                model=model,
                model_version=model_version,
                schema_name=schema.name,
                schema_version=schema.version,
                prompt_hash=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                input_object_key=input_key,
                output_object_key=output_key,
                parsed_output=parsed_output,
                validated_output=validated_output,
                field_confidences=field_confidences,
                evidence_links=evidence_links,
                confidence=max(0.0, min(1.0, confidence)),
                status=status,
                error_message=error_message,
            )
            self.session.add(row)
            self.session.flush()

        return AIExtractionResult(
            feature=feature,
            parsed_output=parsed_output,
            confidence=max(0.0, min(1.0, confidence)),
            output_id=output_id,
            provider=provider,
            model=model,
            model_version=model_version,
            schema_name=schema.name,
            schema_version=schema.version,
            validated_output=validated_output,
            field_confidences=field_confidences,
            evidence_links=evidence_links,
        )

    def _enabled(self) -> bool:
        return bool(self.settings.ai_extraction_enabled)

    def _can_use_gemini(self) -> bool:
        return bool(
            self.settings.ai_extraction_enabled
            and self.settings.gemini_text_analysis_enabled
            and self.settings.gemini_api_key
            and not self.settings.scraping_fixture_mode
        )


def _schema_spec(feature: str) -> _SchemaSpec:
    return SCHEMA_SPECS.get(feature) or _SchemaSpec(feature, 1, _AuditOutput)


def _valid_for_feature(feature: str, parsed_output: dict) -> bool:
    schema = _schema_spec(feature)
    _validate_output(schema, parsed_output)
    return True


def _validate_output(schema: _SchemaSpec, parsed_output: dict) -> dict:
    return schema.model.model_validate(parsed_output).model_dump(mode="json")


def _field_confidences(validated_output: dict, parsed_output: dict, aggregate_confidence: float) -> dict:
    explicit = parsed_output.get("field_confidences") or parsed_output.get("confidence_by_field")
    if isinstance(explicit, dict):
        return {
            str(field): _clamp_confidence(value)
            for field, value in explicit.items()
            if _clamp_confidence(value) is not None
        }

    confidence = _clamp_confidence(aggregate_confidence) or 0.0
    confidences = {}
    for field, value in validated_output.items():
        if field == "confidence":
            continue
        if value is None or value == [] or value == {}:
            continue
        confidences[field] = confidence
    return confidences


def _evidence_links(feature: str, subject_type: str, subject_id: str | None, input_payload: dict) -> list[dict]:
    if feature == "listing_extraction_fallback":
        return [
            _clean_evidence(
                {
                    "type": "source_listing",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "source_name": input_payload.get("source_name"),
                    "url": input_payload.get("url"),
                    "parser_confidence": input_payload.get("parser_confidence"),
                    "text_excerpt_sha256": _text_hash(input_payload.get("text_excerpt")),
                    "has_screenshot": bool(input_payload.get("has_screenshot")),
                }
            )
        ]
    if feature == "risk_language_detection":
        return [
            _clean_evidence(
                {
                    "type": "text_excerpt",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "text_excerpt_sha256": _text_hash(input_payload.get("text_excerpt")),
                }
            )
        ]
    if feature == "vehicle_history_extraction":
        return [
            _clean_evidence(
                {
                    "type": "vehicle_history_text",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "text_excerpt_sha256": _text_hash(input_payload.get("text_excerpt")),
                }
            )
        ]
    if feature == "comparable_relevance_ai":
        target = input_payload.get("target") if isinstance(input_payload.get("target"), dict) else {}
        comparable = input_payload.get("comparable") if isinstance(input_payload.get("comparable"), dict) else {}
        return [
            _clean_evidence(
                {
                    "type": "target_listing",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "listing_id": target.get("id"),
                    "source_url": target.get("source_url") or target.get("url"),
                }
            ),
            _clean_evidence(
                {
                    "type": "comparable_listing",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "listing_id": comparable.get("id"),
                    "source_url": comparable.get("source_url") or comparable.get("url"),
                }
            ),
        ]
    if feature == "report_writing":
        report_json = input_payload.get("report_json") if isinstance(input_payload.get("report_json"), dict) else {}
        summary = report_json.get("summary") if isinstance(report_json.get("summary"), dict) else {}
        evidence = report_json.get("evidence") if isinstance(report_json.get("evidence"), dict) else {}
        return [
            _clean_evidence(
                {
                    "type": "decision_report",
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                    "opportunity_id": summary.get("opportunity_id"),
                    "version": summary.get("version"),
                    "candidate_snapshot_id": evidence.get("candidate_snapshot_id"),
                    "search_run_id": evidence.get("search_run_id"),
                }
            )
        ]
    return [_clean_evidence({"type": "subject", "subject_type": subject_type, "subject_id": subject_id})]


def _clean_evidence(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if value is not None}


def _text_hash(text: object) -> str | None:
    if not isinstance(text, str) or not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clamp_confidence(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return None


def _parsed_listing_payload(parsed: ParsedListing) -> dict:
    return {
        "title": _field_value(parsed.title),
        "asking_price_cad": _field_value(parsed.asking_price_cad),
        "mileage_km": _field_value(parsed.mileage_km),
        "location_city": _field_value(parsed.location_city),
        "location_province": _field_value(parsed.location_province),
        "year": _field_value(parsed.year),
        "make": _field_value(parsed.make),
        "model": _field_value(parsed.model),
        "trim": _field_value(parsed.trim),
        "description": _field_value(parsed.description),
        "raw_fields": parsed.raw_fields,
    }


def _field_value(field) -> object | None:
    return field.value if field is not None else None


def _html_to_text(html: str) -> str:
    text = re.sub(r"<script\b[^>]*>.*?</script>", " ", html, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _deterministic_listing_output(input_payload: dict) -> dict:
    parsed = input_payload.get("parsed_fields") or {}
    text = " ".join(
        str(value)
        for value in [
            parsed.get("title"),
            parsed.get("description"),
            input_payload.get("text_excerpt"),
        ]
        if value
    )
    title = parsed.get("title") or _match(r"((?:19|20)\d{2}\s+[A-Z][A-Za-z-]+\s+[A-Z][A-Za-z0-9-]+(?:\s+[A-Z][A-Za-z0-9-]+)?)", text)
    year = parsed.get("year") or _int(_match(r"\b((?:19|20)\d{2})\b", title or text))
    price = parsed.get("asking_price_cad") or _money(text)
    mileage = parsed.get("mileage_km") or _mileage(text)
    flags = _deterministic_risk_language(" ".join(str(value) for value in [text, title] if value))
    return {
        "title": title,
        "year": year,
        "asking_price_cad": price,
        "mileage_km": mileage,
        "risk_flags": flags["risk_flags"],
        "summary": "Deterministic listing fallback extraction.",
        "confidence": 0.62 if any([title, year, price, mileage, flags["risk_flags"]]) else 0.0,
    }


def _deterministic_risk_language(text: str) -> dict:
    lowered = text.casefold()
    checks = {
        "accident_reported": ["accident", "collision", "claim"],
        "rebuilt_or_salvage": ["rebuilt", "salvage", "branded title"],
        "as_is_sale": ["as-is", "as is", "mechanic special"],
        "warning_lights": ["warning light", "check engine", "airbag light"],
        "lien_or_finance": ["lien", "finance owing", "payout"],
        "odometer_issue": ["odometer", "rollback", "true mileage unknown"],
    }
    flags = [flag for flag, terms in checks.items() if any(term in lowered for term in terms)]
    return {
        "risk_flags": flags,
        "summary": ", ".join(flags) if flags else "No high-risk language detected.",
        "confidence": 0.7 if flags else 0.55,
    }


def _deterministic_vehicle_history(text: str) -> dict:
    risk = _deterministic_risk_language(text)
    accident_amount = _money(text)
    return {
        "source_type": "manual",
        "title_brand": "rebuilt" if "rebuilt" in risk["risk_flags"] else "unknown",
        "accident_claims": (
            [{"amount_cad": accident_amount, "description": "AI extracted accident/claim language.", "severity": "unknown"}]
            if "accident_reported" in risk["risk_flags"]
            else []
        ),
        "odometer_issue": "odometer_issue" in risk["risk_flags"] or None,
        "summary": risk["summary"],
        "risk_flags": risk["risk_flags"],
        "confidence": risk["confidence"],
    }


def _deterministic_comparable_relevance(target: dict, comparable: dict) -> dict:
    reasons = []
    adjustment = 0.0
    if _same(target.get("make"), comparable.get("make")) and _same(target.get("model"), comparable.get("model")):
        reasons.append("same_make_model")
    else:
        reasons.append("make_model_mismatch")
        adjustment -= 0.15
    if target.get("year") and comparable.get("year"):
        gap = abs(int(target["year"]) - int(comparable["year"]))
        if gap > 2:
            reasons.append("wide_year_gap")
            adjustment -= 0.08
    return {
        "similarity_adjustment": adjustment,
        "reasons": reasons,
        "include": adjustment > -0.2,
        "confidence": 0.65,
    }


def _deterministic_report_narrative(report_json: dict) -> dict:
    vehicle = report_json.get("vehicle", {}) if isinstance(report_json.get("vehicle"), dict) else {}
    pricing = report_json.get("pricing", {}) if isinstance(report_json.get("pricing"), dict) else {}
    risk = report_json.get("risk", {}) if isinstance(report_json.get("risk"), dict) else {}
    title = " ".join(str(part) for part in [vehicle.get("year"), vehicle.get("make"), vehicle.get("model"), vehicle.get("trim")] if part) or "This opportunity"
    missing = risk.get("missing_verifications") or []
    max_buy = pricing.get("max_buy_price_cad")
    narrative = f"{title} should be treated as a preliminary opportunity"
    if max_buy is not None:
        narrative += f" with a max-buy target near ${float(max_buy):,.0f} CAD"
    narrative += "."
    if missing:
        narrative += f" Resolve {', '.join(str(item) for item in missing)} before final offer approval."
    return {
        "narrative": narrative,
        "confidence": 0.72,
        "basis": "deterministic_report_writer",
    }


def _first_response_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []
    parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("text"), str):
            return part["text"]
    raise ValueError("Gemini response did not include text")


def _match(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text or "", flags=re.IGNORECASE)
    return match.group(1).strip() if match else None


def _int(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except ValueError:
        return None


def _money(text: str) -> int | None:
    value = _match(r"\$\s*([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{3,5})(?:\.\d{2})?\s*(?:CAD)?", text)
    if value is None:
        value = _match(r"\b([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{3,5})(?:\.\d{2})?\s*CAD\b", text)
    if value is None:
        value = _match(r"\b([1-9]\d{0,2}(?:,\d{3})+|[1-9]\d{4,5})(?:\.\d{2})?\b", text)
    return _int(value)


def _mileage(text: str) -> int | None:
    value = _match(r"([1-9]\d{1,2}(?:,\d{3})+|[1-9]\d{4,5})\s*(?:km|kilometres|kilometers)", text)
    return _int(value)


def _same(left: object, right: object) -> bool:
    return bool(left and right and str(left).strip().casefold() == str(right).strip().casefold())

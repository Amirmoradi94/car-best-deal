from __future__ import annotations

from decimal import Decimal
from html import escape

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    CandidateSnapshot,
    DealerCorrection,
    DecisionReport,
    Opportunity,
    OpportunityDocument,
    OpportunityHistoryProfile,
    OpportunityRecallComplianceEvidence,
    OpportunityTitleEvidence,
    OpportunityWholesaleEvidence,
)
from app.domain.enums import Recommendation, ReportStatus
from app.services.dealer_corrections import (
    adjust_missing_key_data,
    apply_history_profile_corrections,
    apply_listing_corrections,
    apply_vehicle_corrections,
    apply_verification_corrections,
    correction_risk_factors,
    latest_active_correction_map,
    list_dealer_corrections,
    report_corrections_payload,
)
from app.services.comparable_editing import list_opportunity_comparables
from app.services.opportunity_promotion import (
    get_opportunity_with_candidate,
    normalized_visit_checklist,
    opportunity_readiness_warnings,
)
from app.services.opportunity_documents import DOCUMENT_TYPE_LABELS, document_payload, list_opportunity_documents
from app.services.opportunity_title import (
    latest_title_evidence,
    list_title_evidence,
    title_evidence_payload,
    title_risk_factors,
)
from app.services.recall_compliance import (
    RECALL_COMPLIANCE_MISSING_KEY,
    is_recall_compliance_clear,
    latest_recall_compliance_evidence,
    list_recall_compliance_evidence,
    recall_compliance_payload,
    recall_compliance_risk_factors,
)
from app.services.vehicle_history import (
    get_latest_opportunity_history,
    history_report_payload,
    history_risk_factors,
)
from app.services.wholesale_evidence import (
    latest_wholesale_evidence,
    list_wholesale_evidence,
    wholesale_evidence_payload,
    wholesale_risk_factors,
    wholesale_support_payload,
)


def create_decision_report(session: Session, *, opportunity_id: str) -> DecisionReport | None:
    result = get_opportunity_with_candidate(session, opportunity_id)
    if result is None:
        return None

    opportunity, candidate = result
    version = _next_report_version(session, opportunity.id)
    history = get_latest_opportunity_history(session, opportunity.id)
    documents = list_opportunity_documents(session, opportunity_id=opportunity.id) or []
    title_items = list_title_evidence(session, opportunity_id=opportunity.id) or []
    title_evidence = latest_title_evidence(session, opportunity.id)
    recall_compliance_items = list_recall_compliance_evidence(session, opportunity_id=opportunity.id) or []
    recall_compliance = latest_recall_compliance_evidence(session, opportunity.id)
    wholesale_items = list_wholesale_evidence(session, opportunity_id=opportunity.id) or []
    wholesale_evidence = latest_wholesale_evidence(session, opportunity.id)
    corrections = list_dealer_corrections(session, opportunity_id=opportunity.id) or []
    comparables = list_opportunity_comparables(session, opportunity_id=opportunity.id) or {}
    report_json = build_report_json(
        opportunity,
        candidate,
        version=version,
        history=history,
        documents=documents,
        title_evidence=title_evidence,
        title_evidence_items=title_items,
        recall_compliance=recall_compliance,
        recall_compliance_items=recall_compliance_items,
        wholesale_evidence=wholesale_evidence,
        wholesale_evidence_items=wholesale_items,
        dealer_corrections=corrections,
        comparables=comparables,
    )
    report = DecisionReport(
        opportunity_id=opportunity.id,
        version=version,
        status=report_json["summary"]["status"],
        recommendation=report_json["summary"]["recommendation"],
        report_json=report_json,
        confidence_by_section=report_json["confidence_by_section"],
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def get_latest_decision_report(session: Session, opportunity_id: str) -> DecisionReport | None:
    return session.scalar(
        select(DecisionReport)
        .where(DecisionReport.opportunity_id == opportunity_id)
        .order_by(DecisionReport.version.desc(), DecisionReport.created_at.desc())
    )


def get_decision_report(session: Session, report_id: str) -> DecisionReport | None:
    return session.get(DecisionReport, report_id)


def mark_latest_decision_report_stale(session: Session, *, opportunity_id: str) -> DecisionReport | None:
    report = get_latest_decision_report(session, opportunity_id)
    if report is None or report.status == ReportStatus.STALE.value:
        return report

    report.status = ReportStatus.STALE.value
    report_json = dict(report.report_json or {})
    summary = dict(report_json.get("summary", {}))
    summary["status"] = ReportStatus.STALE.value
    report_json["summary"] = summary
    report.report_json = report_json
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def decision_report_payload(report: DecisionReport) -> dict:
    return {
        "id": report.id,
        "opportunity_id": report.opportunity_id,
        "version": report.version,
        "status": report.status,
        "recommendation": report.recommendation,
        "report_json": report.report_json,
        "confidence_by_section": report.confidence_by_section,
        "html_url": f"/api/opportunities/{report.opportunity_id}/reports/latest/html",
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "updated_at": report.updated_at.isoformat() if report.updated_at else None,
    }


def build_report_json(
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
    *,
    version: int,
    history: OpportunityHistoryProfile | None = None,
    documents: list[OpportunityDocument] | None = None,
    title_evidence: OpportunityTitleEvidence | None = None,
    title_evidence_items: list[OpportunityTitleEvidence] | None = None,
    recall_compliance: OpportunityRecallComplianceEvidence | None = None,
    recall_compliance_items: list[OpportunityRecallComplianceEvidence] | None = None,
    wholesale_evidence: OpportunityWholesaleEvidence | None = None,
    wholesale_evidence_items: list[OpportunityWholesaleEvidence] | None = None,
    dealer_corrections: list[DealerCorrection] | None = None,
    comparables: dict | None = None,
) -> dict:
    pricing = candidate.pricing_summary if candidate is not None else {}
    risk = candidate.risk_summary if candidate is not None else {}
    corrections = list(dealer_corrections or [])
    correction_map = latest_active_correction_map(corrections)
    missing_key_data = (
        list(opportunity.missing_key_data)
        if opportunity.missing_key_data is not None
        else list(risk.get("missing_verifications", []) or [])
    )
    if history is not None:
        missing_key_data = [key for key in missing_key_data if key != "vehicle_history"]
    missing_key_data = adjust_missing_key_data(missing_key_data, correction_map)
    status = _report_status(opportunity, missing_key_data)
    recommendation = _recommendation(opportunity, candidate, missing_key_data)
    readiness_warnings = opportunity_readiness_warnings(opportunity)
    visit_checklist = _visit_checklist_payload(opportunity)
    next_actions = _next_actions(opportunity, candidate, missing_key_data)
    uploaded_documents = list(documents or [])
    verification = _verification_payload(
        candidate,
        missing_key_data,
        history,
        uploaded_documents,
        title_evidence,
        recall_compliance,
    )
    verification = apply_verification_corrections(verification, correction_map)
    history_profile = apply_history_profile_corrections(history_report_payload(history), correction_map)
    title_payload = _title_evidence_report_payload(title_evidence, title_evidence_items or [])
    recall_compliance_payload_data = _recall_compliance_report_payload(
        recall_compliance,
        recall_compliance_items or [],
    )
    wholesale_payload = _wholesale_evidence_report_payload(
        wholesale_evidence,
        wholesale_evidence_items or [],
        retail_max_buy_cad=pricing.get("max_buy_price_cad"),
    )
    comparable_payload = dict(comparables or {})
    risk_factors = (
        list(risk.get("risk_factors", []))
        + history_risk_factors(history)
        + title_risk_factors(title_evidence)
        + recall_compliance_risk_factors(recall_compliance)
        + wholesale_risk_factors(wholesale_evidence, retail_max_buy_cad=pricing.get("max_buy_price_cad"))
        + correction_risk_factors(correction_map)
    )
    vehicle_payload = apply_vehicle_corrections(_vehicle_payload(candidate), correction_map)
    listing_payload = apply_listing_corrections(_listing_payload(candidate), correction_map)
    asking_price_cad = listing_payload.get("asking_price_cad")

    return {
        "summary": {
            "opportunity_id": opportunity.id,
            "version": version,
            "status": status,
            "recommendation": recommendation,
            "deal_score": _json_number(opportunity.deal_score),
            "ready_to_visit_blocked": bool(readiness_warnings and opportunity.stage != "ready_to_visit"),
        },
        "vehicle": vehicle_payload,
        "listing": listing_payload,
        "pricing": {
            "asking_price_cad": _json_number(asking_price_cad),
            "retail_low_cad": _json_number(pricing.get("retail_low_cad")),
            "retail_mid_cad": _json_number(pricing.get("retail_mid_cad")),
            "retail_high_cad": _json_number(pricing.get("retail_high_cad")),
            "max_buy_price_cad": _json_number(pricing.get("max_buy_price_cad")),
            "starting_offer_cad": _json_number(pricing.get("starting_offer_cad")),
            "comparable_count": _json_number(pricing.get("comparable_count")),
            "wholesale_supported_max_buy_cad": wholesale_payload["support"].get("supported_max_buy_cad"),
            "wholesale_suggested_opening_bid_cad": wholesale_payload["support"].get("suggested_opening_bid_cad"),
            "preliminary": opportunity.preliminary,
            "is_overpriced": opportunity.is_overpriced,
        },
        "risk": {
            "risk_level": risk.get("risk_level") or "unknown",
            "risk_score": _json_number(risk.get("risk_score")),
            "risk_factors": risk_factors,
            "missing_verifications": missing_key_data,
            "readiness_warnings": readiness_warnings,
        },
        "verification": verification,
        "history_profile": history_profile,
        "title_evidence": title_payload,
        "recall_compliance": recall_compliance_payload_data,
        "wholesale_evidence": wholesale_payload,
        "comparables": comparable_payload,
        "image_review": {
            "image_count": len(candidate.image_urls) if candidate is not None else 0,
            "image_risk_adjustment": _json_number(candidate.image_risk_adjustment) if candidate is not None else None,
            "image_risk_reasons": list(candidate.image_risk_reasons) if candidate is not None else [],
        },
        "workflow": {
            "stage": opportunity.stage,
            "candidate_selected": opportunity.candidate_selected,
            "seller_contact_status": opportunity.seller_contact_status,
            "seller_notes": opportunity.seller_notes,
            "visit_checklist": visit_checklist,
        },
        "visit_checklist": visit_checklist,
        "seller": {
            "contact_status": opportunity.seller_contact_status,
            "notes": opportunity.seller_notes,
            "source_url": candidate.source_url if candidate is not None else None,
        },
        "next_actions": next_actions,
        "evidence": {
            "intake_mode": _intake_mode(candidate),
            "candidate_snapshot_id": candidate.id if candidate is not None else None,
            "search_run_id": candidate.search_run_id if candidate is not None else None,
            "source": candidate.source_name if candidate is not None else None,
            "source_url": candidate.source_url if candidate is not None else None,
            "uploaded_documents": _document_evidence_payload(uploaded_documents),
            "dealer_corrections": report_corrections_payload(corrections),
            "comparables": comparable_payload,
            "confidence_by_section": candidate.confidence_by_section if candidate is not None else {},
        },
        "confidence_by_section": candidate.confidence_by_section if candidate is not None else {},
    }


def render_decision_report_html(report: DecisionReport) -> str:
    data = report.report_json or {}
    summary = data.get("summary", {})
    vehicle = data.get("vehicle", {})
    listing = data.get("listing", {})
    pricing = data.get("pricing", {})
    risk = data.get("risk", {})
    verification = data.get("verification", {})
    history_profile = data.get("history_profile", {})
    title_evidence = data.get("title_evidence", {})
    recall_compliance = data.get("recall_compliance", {})
    wholesale_evidence = data.get("wholesale_evidence", {})
    comparables = data.get("comparables", {})
    image_review = data.get("image_review", {})
    workflow = data.get("workflow", {})
    visit_checklist = data.get("visit_checklist") or workflow.get("visit_checklist") or {}
    next_actions = data.get("next_actions", [])
    evidence = data.get("evidence", {})

    title = _vehicle_title(vehicle)
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Decision Report - {escape(title)}</title>
    <style>
      body {{ margin: 0; background: #f7f8f5; color: #20231f; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.45; }}
      main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 48px; }}
      header, section {{ border: 1px solid #d9ded2; border-radius: 8px; background: #fff; padding: 18px; box-shadow: 0 12px 30px rgba(32, 35, 31, 0.08); }}
      section {{ margin-top: 14px; }}
      h1, h2, h3, p {{ margin: 0; }}
      h1 {{ font-size: 28px; line-height: 1.1; }}
      h2 {{ font-size: 17px; margin-bottom: 10px; }}
      .eyebrow {{ color: #667065; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
      .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }}
      .item {{ border-radius: 8px; background: #f0f2eb; padding: 10px; }}
      .item span {{ display: block; color: #667065; font-size: 12px; font-weight: 700; }}
      .item strong {{ display: block; margin-top: 4px; overflow-wrap: anywhere; }}
      .tags {{ display: flex; flex-wrap: wrap; gap: 6px; }}
      .tag {{ display: inline-flex; min-height: 24px; align-items: center; border-radius: 999px; background: #f0f2eb; padding: 0 8px; font-size: 12px; font-weight: 700; }}
      .warning {{ background: #fff1df; color: #b76521; }}
      .danger {{ background: #fbe4e1; color: #b63b3b; }}
      .good {{ background: #e5f2ea; color: #257247; }}
      ol {{ margin: 0; padding-left: 20px; }}
      a {{ color: #165f46; }}
      @media (max-width: 720px) {{ .grid {{ grid-template-columns: 1fr; }} main {{ padding: 18px 12px 32px; }} }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <p class="eyebrow">Decision Report v{report.version}</p>
        <h1>{escape(title)}</h1>
        <div class="tags" style="margin-top: 12px;">
          {_tag(summary.get("recommendation"), "good" if "buy" in str(summary.get("recommendation", "")) else "warning")}
          {_tag(summary.get("status"))}
          {_tag(f"Score {summary.get('deal_score', '-')}" if summary.get("deal_score") is not None else "Score -")}
        </div>
      </header>
      <section>
        <h2>Pricing</h2>
        <div class="grid">
          {_item("Ask", _money(pricing.get("asking_price_cad")))}
          {_item("Retail mid", _money(pricing.get("retail_mid_cad")))}
          {_item("Max buy", _money(pricing.get("max_buy_price_cad")))}
          {_item("Starting offer", _money(pricing.get("starting_offer_cad")))}
          {_item("Comparables", str(pricing.get("comparable_count") if pricing.get("comparable_count") is not None else comparables.get("included_count", "-")))}
          {_item("Wholesale support", _money(pricing.get("wholesale_supported_max_buy_cad")))}
          {_item("Suggested bid", _money(pricing.get("wholesale_suggested_opening_bid_cad")))}
          {_item("Preliminary", "Yes" if pricing.get("preliminary") else "No")}
          {_item("Overpriced", "Yes" if pricing.get("is_overpriced") else "No")}
        </div>
      </section>
      <section>
        <h2>Vehicle and Listing</h2>
        <div class="grid">
          {_item("VIN", vehicle.get("vin") or "Missing")}
          {_item("Mileage", _km(vehicle.get("mileage_km")))}
          {_item("Location", listing.get("location") or "-")}
          {_item("Source", listing.get("source") or "-")}
          {_item("Stage", workflow.get("stage") or "-")}
          {_item("Contact", workflow.get("seller_contact_status") or "Not contacted")}
        </div>
      </section>
      <section>
        <h2>Risk and Missing Data</h2>
        {_tag_list(risk.get("missing_verifications", []), "danger") if risk.get("missing_verifications") else '<p>No missing key data recorded.</p>'}
        {_tag_list(risk.get("risk_factors", []), "warning")}
      </section>
      <section>
        <h2>Verification</h2>
        <div class="grid">
          {_item("VIN", _verification_status(verification, "vin"))}
          {_item("History", _verification_status(verification, "history"))}
          {_item("Lien/title", _verification_status(verification, "lien_title"))}
          {_item("Recall", _verification_status(verification, "recall"))}
        </div>
      </section>
      <section>
        <h2>Uploaded Evidence</h2>
        {_document_list_html(evidence.get("uploaded_documents", []))}
      </section>
      <section>
        <h2>Dealer Corrections</h2>
        {_dealer_corrections_html(evidence.get("dealer_corrections", []))}
      </section>
      <section>
        <h2>Comparables</h2>
        {_comparables_html(comparables)}
      </section>
      <section>
        <h2>Title and Lien Evidence</h2>
        {_title_evidence_html(title_evidence)}
      </section>
      <section>
        <h2>Recall and Compliance</h2>
        {_recall_compliance_html(recall_compliance)}
      </section>
      <section>
        <h2>Wholesale and Trade-In Evidence</h2>
        {_wholesale_evidence_html(wholesale_evidence)}
      </section>
      <section>
        <h2>History Profile</h2>
        <div class="grid">
          {_item("Status", str(history_profile.get("status") or "missing").replace("_", " "))}
          {_item("Source", history_profile.get("source_name") or history_profile.get("source_type") or "-")}
          {_item("Title brand", history_profile.get("title_brand") or "unknown")}
          {_item("Accident claims", _claim_summary(history_profile))}
          {_item("Owners", str(history_profile.get("owners_count") if history_profile.get("owners_count") is not None else "-"))}
          {_item("Odometer issue", _yes_no_unknown(history_profile.get("odometer_issue")))}
          {_item("Service records", str(history_profile.get("service_records_count") if history_profile.get("service_records_count") is not None else "-"))}
          {_item("Import events", str(history_profile.get("import_event_count", 0)))}
          {_item("Damage/theft flags", _history_flags(history_profile))}
        </div>
        <p style="margin-top: 10px;">{escape(history_profile.get("summary") or "No history summary saved.")}</p>
      </section>
      <section>
        <h2>Image Review</h2>
        <div class="grid">
          {_item("Images", str(image_review.get("image_count", 0)))}
          {_item("Adjustment", str(image_review.get("image_risk_adjustment") or 0))}
        </div>
        {_tag_list(image_review.get("image_risk_reasons", []), "warning")}
      </section>
      <section>
        <h2>Visit Checklist</h2>
        {_checklist_html(visit_checklist)}
      </section>
      <section>
        <h2>Next Actions</h2>
        {_ordered_list(next_actions)}
      </section>
      <section>
        <h2>Seller Notes</h2>
        <p>{escape(workflow.get("seller_notes") or "No seller notes saved.")}</p>
        {_source_link(listing.get("source_url"))}
      </section>
    </main>
  </body>
</html>"""


def _next_report_version(session: Session, opportunity_id: str) -> int:
    current = session.scalar(
        select(func.max(DecisionReport.version)).where(DecisionReport.opportunity_id == opportunity_id)
    )
    return int(current or 0) + 1


def _report_status(opportunity: Opportunity, missing_key_data: list) -> str:
    if missing_key_data:
        return ReportStatus.PARTIAL.value
    if opportunity.preliminary:
        return ReportStatus.PRELIMINARY.value
    return ReportStatus.FULL.value


def _recommendation(
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
    missing_key_data: list,
) -> str:
    if candidate is not None and candidate.recommendation:
        return candidate.recommendation
    if opportunity.is_overpriced:
        return Recommendation.PASS.value
    if missing_key_data:
        return Recommendation.NEEDS_MORE_DATA.value
    return Recommendation.BUY_ONLY_CHEAP.value


def _next_actions(
    opportunity: Opportunity,
    candidate: CandidateSnapshot | None,
    missing_key_data: list,
) -> list[str]:
    actions = []
    visit_checklist = _visit_checklist_payload(opportunity)
    missing_checklist = visit_checklist["missing"]
    if missing_key_data:
        actions.append(f"Resolve missing verification data: {', '.join(missing_key_data)}.")
    if _intake_mode(candidate) == "vin" and "vehicle_history" in set(missing_key_data):
        actions.append("Run or upload vehicle history, lien/title, and recall evidence before treating the VIN report as complete.")
    if missing_checklist:
        actions.append(f"Complete visit checklist items: {', '.join(item['label'] for item in missing_checklist)}.")
    if opportunity.seller_contact_status in (None, "", "to_contact"):
        actions.append("Contact the seller and confirm availability, VIN, ownership, and service records.")
    if candidate is not None and candidate.image_risk_reasons:
        actions.append("Ask for additional photos covering tires, dashboard lights, body panels, and undercarriage.")
    if opportunity.stage not in {"ready_to_visit", "visited", "offer_made", "bought", "passed"}:
        actions.append("Keep the opportunity out of Ready to Visit until required checks are complete or overridden.")
    if not actions:
        actions.append("Prepare the visit checklist and validate condition before making an offer.")
    return actions


def _visit_checklist_payload(opportunity: Opportunity) -> dict:
    checklist = normalized_visit_checklist(opportunity.visit_checklist)
    items = [
        {"key": key, "label": label, "complete": checklist[key]}
        for key, label in [
            ("vin_confirmed", "VIN confirmed"),
            ("service_records_requested", "Service records requested"),
            ("lien_status_checked", "Lien status checked"),
            ("history_report_checked", "History report checked"),
            ("extra_photos_requested", "Extra photos requested"),
            ("visit_appointment_set", "Visit appointment set"),
        ]
    ]
    completed = [item for item in items if item["complete"]]
    missing = [item for item in items if not item["complete"]]
    return {
        "items": items,
        "completed": completed,
        "missing": missing,
        "completed_count": len(completed),
        "total_count": len(items),
    }


def _vehicle_payload(candidate: CandidateSnapshot | None) -> dict:
    if candidate is None:
        return {}
    return {
        "title": candidate.title,
        "year": candidate.year,
        "make": candidate.make,
        "model": candidate.model,
        "trim": candidate.trim,
        "vin": candidate.vin,
        "mileage_km": candidate.mileage_km,
    }


def _listing_payload(candidate: CandidateSnapshot | None) -> dict:
    if candidate is None:
        return {}
    return {
        "source": candidate.source_name,
        "source_url": candidate.source_url,
        "asking_price_cad": _json_number(candidate.asking_price_cad),
        "location": ", ".join([part for part in [candidate.location_city, candidate.location_province] if part]),
    }


def _intake_mode(candidate: CandidateSnapshot | None) -> str:
    if candidate is not None and "single_listing_url" in candidate.relevance_reasons:
        return "single_listing"
    if candidate is not None and "vin_only" in candidate.relevance_reasons:
        return "vin"
    return "discovery"


def _verification_payload(
    candidate: CandidateSnapshot | None,
    missing_key_data: list,
    history: OpportunityHistoryProfile | None = None,
    documents: list[OpportunityDocument] | None = None,
    title_evidence: OpportunityTitleEvidence | None = None,
    recall_compliance: OpportunityRecallComplianceEvidence | None = None,
) -> dict:
    missing = set(missing_key_data or [])
    document_types = {document.document_type for document in documents or []}
    history_source = None
    history_identifier = None
    if history is not None:
        history_source = history.source_name or history.source_type
        history_identifier = history.report_identifier
    elif "carfax_pdf" in document_types:
        history_source = DOCUMENT_TYPE_LABELS["carfax_pdf"]
    return {
        "vin": {
            "status": "verified_format" if candidate is not None and candidate.vin else "missing",
            "value": candidate.vin if candidate is not None else None,
        },
        "history": {
            "status": (
                "provided"
                if history is not None
                else "document_uploaded"
                if "carfax_pdf" in document_types
                else "not_verified"
                if "vehicle_history" in missing
                else "verified"
            ),
            "source": history_source,
            "report_identifier": history_identifier,
        },
        "lien_title": {
            "status": _lien_title_status(missing, document_types, title_evidence),
            "source": (
                title_evidence.provider or title_evidence.source_type
                if title_evidence is not None
                else _document_source_label(
                    document_types,
                    ["lien_release", "uvip", "ppsa_report", "ppsr_report", "ownership_document"],
                )
            ),
            "evidence_id": title_evidence.id if title_evidence is not None else None,
            "lookup_reference": title_evidence.lookup_reference if title_evidence is not None else None,
        },
        "recall": {
            "status": _recall_status(missing, document_types, recall_compliance),
            "source": (
                recall_compliance.provider or recall_compliance.source_type
                if recall_compliance is not None
                else _document_source_label(
                    document_types,
                    [
                        "recall_completion_receipt",
                        "transport_canada_recall_report",
                        "oem_recall_report",
                        "import_compliance_document",
                        "riv_inspection",
                        "statement_of_compliance",
                    ],
                )
            ),
            "evidence_id": recall_compliance.id if recall_compliance is not None else None,
            "lookup_reference": recall_compliance.lookup_reference if recall_compliance is not None else None,
            "compliance_status": (
                recall_compliance.compliance_status if recall_compliance is not None else "unknown"
            ),
            "remedy_status": recall_compliance.remedy_status if recall_compliance is not None else "unknown",
        },
    }


def _lien_title_status(
    missing: set,
    document_types: set[str],
    title_evidence: OpportunityTitleEvidence | None,
) -> str:
    if title_evidence is not None:
        if title_evidence.title_clearance_status in {"clear", "released"}:
            return "verified"
        return title_evidence.title_clearance_status
    if document_types.intersection({"uvip", "ownership_document", "ppsa_report", "ppsr_report"}):
        return "document_uploaded"
    if "lien_verification" in missing:
        return "not_verified"
    return "verified"


def _recall_status(
    missing: set,
    document_types: set[str],
    recall_compliance: OpportunityRecallComplianceEvidence | None,
) -> str:
    if recall_compliance is not None:
        if is_recall_compliance_clear(recall_compliance):
            return "verified"
        return recall_compliance.recall_status
    if document_types.intersection(
        {
            "recall_completion_receipt",
            "transport_canada_recall_report",
            "oem_recall_report",
            "import_compliance_document",
            "riv_inspection",
            "statement_of_compliance",
        }
    ):
        return "document_uploaded"
    if RECALL_COMPLIANCE_MISSING_KEY in missing:
        return "not_verified"
    return "not_checked"


def _claim_summary(history_profile: dict) -> str:
    count = history_profile.get("accident_claim_count") or 0
    total = history_profile.get("accident_claim_total_cad")
    if not count:
        return "0"
    if total is None:
        return str(count)
    return f"{count} / {_money(total)}"


def _yes_no_unknown(value: object) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Unknown"


def _history_flags(history_profile: dict) -> str:
    flags = []
    for key in ["salvage_status", "flood_status", "fire_status", "theft_status"]:
        status = str(history_profile.get(key) or "unknown")
        if status != "clear":
            flags.append(f"{key.replace('_status', '')}: {status}")
    return ", ".join(flags) if flags else "Clear"


def _vehicle_title(vehicle: dict) -> str:
    return (
        vehicle.get("title")
        or " ".join(str(part) for part in [vehicle.get("year"), vehicle.get("make"), vehicle.get("model"), vehicle.get("trim")] if part)
        or "Opportunity"
    )


def _item(label: str, value: str) -> str:
    return f'<div class="item"><span>{escape(label)}</span><strong>{escape(value or "-")}</strong></div>'


def _tag(value: object, tone: str = "") -> str:
    return f'<span class="tag {escape(tone)}">{escape(str(value or "-").replace("_", " "))}</span>'


def _tag_list(items: list, tone: str = "") -> str:
    filtered = [str(item) for item in items if item]
    if not filtered:
        return ""
    return '<div class="tags">' + "".join(_tag(item, tone) for item in filtered) + "</div>"


def _ordered_list(items: list) -> str:
    filtered = [str(item) for item in items if item]
    if not filtered:
        return "<p>No next actions.</p>"
    return "<ol>" + "".join(f"<li>{escape(item)}</li>" for item in filtered) + "</ol>"


def _checklist_html(visit_checklist: dict) -> str:
    items = visit_checklist.get("items", [])
    if not items:
        return "<p>No checklist data.</p>"
    return (
        '<div class="grid">'
        + "".join(
            _item(
                str(item.get("label") or item.get("key") or "Checklist item"),
                "Complete" if item.get("complete") else "Missing",
            )
            for item in items
        )
        + "</div>"
    )


def _source_link(source_url: str | None) -> str:
    if not source_url:
        return ""
    return f'<p style="margin-top: 10px;"><a href="{escape(source_url, quote=True)}" rel="noreferrer">Open source listing</a></p>'


def _document_evidence_payload(documents: list[OpportunityDocument]) -> list[dict]:
    return [
        {
            "id": payload["id"],
            "document_type": payload["document_type"],
            "document_label": payload["document_label"],
            "original_filename": payload["original_filename"],
            "content_type": payload["content_type"],
            "size_bytes": payload["size_bytes"],
            "sha256": payload["sha256"],
            "notes": payload["notes"],
            "download_url": payload["download_url"],
            "created_at": payload["created_at"],
        }
        for payload in (document_payload(document) for document in documents)
    ]


def _title_evidence_report_payload(
    latest: OpportunityTitleEvidence | None,
    evidence_items: list[OpportunityTitleEvidence],
) -> dict:
    return {
        "status": latest.title_clearance_status if latest is not None else "missing",
        "latest": title_evidence_payload(latest) if latest is not None else None,
        "evidence": [title_evidence_payload(item) for item in evidence_items],
    }


def _recall_compliance_report_payload(
    latest: OpportunityRecallComplianceEvidence | None,
    evidence_items: list[OpportunityRecallComplianceEvidence],
) -> dict:
    return {
        "status": "clear" if is_recall_compliance_clear(latest) else latest.recall_status if latest is not None else "missing",
        "latest": recall_compliance_payload(latest) if latest is not None else None,
        "evidence": [recall_compliance_payload(item) for item in evidence_items],
    }


def _wholesale_evidence_report_payload(
    latest: OpportunityWholesaleEvidence | None,
    evidence_items: list[OpportunityWholesaleEvidence],
    *,
    retail_max_buy_cad: object | None,
) -> dict:
    return {
        "status": "supported" if latest is not None and wholesale_support_payload(latest).get("status") == "supported" else "missing" if latest is None else "needs_values",
        "latest": wholesale_evidence_payload(latest) if latest is not None else None,
        "support": wholesale_support_payload(latest, retail_max_buy_cad=retail_max_buy_cad),
        "evidence": [wholesale_evidence_payload(item) for item in evidence_items],
    }


def _document_source_label(document_types: set[str], priority: list[str]) -> str | None:
    for document_type in priority:
        if document_type in document_types:
            return DOCUMENT_TYPE_LABELS.get(document_type, document_type)
    return None


def _document_list_html(documents: list) -> str:
    if not documents:
        return "<p>No documents uploaded.</p>"
    return (
        '<div class="grid">'
        + "".join(
            _item(
                str(document.get("document_label") or document.get("document_type") or "Document"),
                str(document.get("original_filename") or "-"),
            )
            for document in documents
            if isinstance(document, dict)
        )
        + "</div>"
    )


def _dealer_corrections_html(corrections: list) -> str:
    if not corrections:
        return "<p>No dealer corrections saved.</p>"
    return (
        '<div class="grid">'
        + "".join(
            _item(
                ".".join(
                    part
                    for part in [
                        str(correction.get("entity_type") or ""),
                        str(correction.get("field_name") or ""),
                    ]
                    if part
                ),
                _correction_value_summary(correction),
            )
            for correction in corrections
            if isinstance(correction, dict)
        )
        + "</div>"
    )


def _correction_value_summary(correction: dict) -> str:
    value = str(correction.get("new_value") if correction.get("new_value") is not None else "-")
    reason = correction.get("reason")
    return f"{value} - {reason}" if reason else value


def _comparables_html(comparables: dict) -> str:
    items = comparables.get("comparables", []) if isinstance(comparables, dict) else []
    if not items:
        return "<p>No comparables saved.</p>"
    return (
        '<div class="grid">'
        + "".join(
            _item(_comparable_label(comparable), _comparable_value(comparable))
            for comparable in items[:9]
            if isinstance(comparable, dict)
        )
        + "</div>"
    )


def _comparable_label(comparable: dict) -> str:
    return " ".join(
        str(part)
        for part in [
            comparable.get("year"),
            comparable.get("make"),
            comparable.get("model"),
            comparable.get("trim"),
        ]
        if part
    ) or str(comparable.get("source_name") or "Comparable")


def _comparable_value(comparable: dict) -> str:
    state = "included" if comparable.get("included") else f"excluded: {comparable.get('excluded_reason') or 'dealer removed'}"
    score = comparable.get("similarity_score")
    score_text = f" / similarity {score}" if score is not None else ""
    return f"{_money(comparable.get('asking_price_cad'))} / {state}{score_text}"


def _title_evidence_html(title_evidence: dict) -> str:
    latest = title_evidence.get("latest") if isinstance(title_evidence, dict) else None
    if not isinstance(latest, dict):
        return "<p>No title or lien evidence saved.</p>"
    return (
        '<div class="grid">'
        + _item("Status", str(latest.get("title_clearance_status") or "unknown").replace("_", " "))
        + _item("Source", str(latest.get("provider") or latest.get("source_type") or "-").replace("_", " "))
        + _item("Reference", str(latest.get("lookup_reference") or "-"))
        + _item("Seller", str(latest.get("seller_name") or "-"))
        + _item("Registered owner", str(latest.get("registered_owner_name") or "-"))
        + _item("Ownership verified", _yes_no_unknown(latest.get("ownership_verified")))
        + _item("Lienholder", str(latest.get("lienholder_name") or "-"))
        + _item("Lien amount", _money(latest.get("lien_amount_cad")))
        + _item("Payout", _payout_summary(latest))
        + "</div>"
        + (
            f'<p style="margin-top: 10px;">{escape(str(latest.get("notes") or ""))}</p>'
            if latest.get("notes")
            else ""
        )
    )


def _payout_summary(evidence: dict) -> str:
    if evidence.get("payout_required") is False:
        return "Not required"
    parts = []
    if evidence.get("payout_status"):
        parts.append(str(evidence.get("payout_status")).replace("_", " "))
    if evidence.get("payout_amount_cad") is not None:
        parts.append(_money(evidence.get("payout_amount_cad")))
    if evidence.get("payout_due_date"):
        parts.append(str(evidence.get("payout_due_date")))
    return " / ".join(parts) if parts else "Unknown"


def _recall_compliance_html(recall_compliance: dict) -> str:
    latest = recall_compliance.get("latest") if isinstance(recall_compliance, dict) else None
    if not isinstance(latest, dict):
        return "<p>No recall or import compliance evidence saved.</p>"
    return (
        '<div class="grid">'
        + _item("Recall status", str(latest.get("recall_status") or "unknown").replace("_", " "))
        + _item("Compliance", str(latest.get("compliance_status") or "unknown").replace("_", " "))
        + _item("Source", str(latest.get("provider") or latest.get("source_type") or "-").replace("_", " "))
        + _item("Reference", str(latest.get("lookup_reference") or "-"))
        + _item("Campaign", str(latest.get("campaign_number") or "-"))
        + _item("Remedy", str(latest.get("remedy_status") or "unknown").replace("_", " "))
        + _item("Completed", str(latest.get("completion_date") or "-"))
        + _item("Import country", str(latest.get("import_country") or "-"))
        + _item("RIV case", str(latest.get("riv_case_number") or "-"))
        + _item("Inspection", _inspection_summary(latest))
        + "</div>"
        + (
            f'<p style="margin-top: 10px;">{escape(str(latest.get("notes") or ""))}</p>'
            if latest.get("notes")
            else ""
        )
    )


def _inspection_summary(evidence: dict) -> str:
    if evidence.get("inspection_required") is False:
        return "Not required"
    parts = []
    if evidence.get("inspection_required") is True:
        parts.append("Required")
    if evidence.get("inspection_deadline"):
        parts.append(str(evidence.get("inspection_deadline")))
    return " / ".join(parts) if parts else "Unknown"


def _wholesale_evidence_html(wholesale_evidence: dict) -> str:
    latest = wholesale_evidence.get("latest") if isinstance(wholesale_evidence, dict) else None
    support = wholesale_evidence.get("support", {}) if isinstance(wholesale_evidence, dict) else {}
    if not isinstance(latest, dict):
        return "<p>No wholesale or trade-in evidence saved.</p>"
    return (
        '<div class="grid">'
        + _item("Source", str(latest.get("provider") or latest.get("source_type") or "-").replace("_", " "))
        + _item("Reference", str(latest.get("lookup_reference") or "-"))
        + _item("Region", str(latest.get("region") or "-"))
        + _item("Wholesale avg", _money(latest.get("wholesale_avg_cad")))
        + _item("Trade-in", _money(latest.get("trade_in_value_cad")))
        + _item("Auction avg", _money(latest.get("auction_sale_avg_cad")))
        + _item("High bid", _money(latest.get("high_bid_cad")))
        + _item("Bid activity", _bid_activity(latest))
        + _item("Condition", _condition_summary(latest))
        + _item("Supported max", _money(support.get("supported_max_buy_cad")))
        + _item("Opening bid", _money(support.get("suggested_opening_bid_cad")))
        + _item("Retail max over support", "Yes" if support.get("retail_max_exceeds_support") else "No")
        + "</div>"
        + (
            f'<p style="margin-top: 10px;">{escape(str(latest.get("notes") or ""))}</p>'
            if latest.get("notes")
            else ""
        )
    )


def _bid_activity(evidence: dict) -> str:
    parts = []
    if evidence.get("bid_count") is not None:
        parts.append(f"{evidence.get('bid_count')} bids")
    if evidence.get("bidder_count") is not None:
        parts.append(f"{evidence.get('bidder_count')} bidders")
    return " / ".join(parts) if parts else "Unknown"


def _condition_summary(evidence: dict) -> str:
    parts = [str(evidence.get("condition_grade") or "unknown").replace("_", " ")]
    if evidence.get("condition_score") is not None:
        parts.append(str(evidence.get("condition_score")))
    return " / ".join(parts)


def _verification_status(verification: dict, key: str) -> str:
    value = verification.get(key) or {}
    return str(value.get("status") or "-").replace("_", " ")


def _money(value: object) -> str:
    number = _json_number(value)
    if number is None:
        return "-"
    return f"${float(number):,.0f} CAD"


def _km(value: object) -> str:
    number = _json_number(value)
    if number is None:
        return "-"
    return f"{float(number):,.0f} km"


def _json_number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value

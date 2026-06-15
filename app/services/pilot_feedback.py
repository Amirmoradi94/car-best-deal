from __future__ import annotations

from collections import Counter
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Opportunity, OpportunityFeedback
from app.services.decision_reports import get_latest_decision_report


def create_opportunity_feedback(
    session: Session,
    *,
    opportunity_id: str,
    usefulness_rating: int,
    accuracy_rating: int,
    dealer_decision: str,
    missing_info: list[str],
    incorrect_info: list[str],
    notes: str | None,
) -> OpportunityFeedback | None:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return None

    latest_report = get_latest_decision_report(session, opportunity_id)
    feedback = OpportunityFeedback(
        opportunity_id=opportunity_id,
        report_id=latest_report.id if latest_report is not None else None,
        report_version=latest_report.version if latest_report is not None else None,
        usefulness_rating=usefulness_rating,
        accuracy_rating=accuracy_rating,
        dealer_decision=dealer_decision,
        missing_info=_clean_items(missing_info),
        incorrect_info=_clean_items(incorrect_info),
        notes=notes,
    )
    session.add(feedback)
    session.commit()
    session.refresh(feedback)
    return feedback


def list_opportunity_feedback(
    session: Session,
    *,
    opportunity_id: str,
    limit: int = 50,
) -> list[OpportunityFeedback] | None:
    if session.get(Opportunity, opportunity_id) is None:
        return None
    return list(
        session.scalars(
            select(OpportunityFeedback)
            .where(OpportunityFeedback.opportunity_id == opportunity_id)
            .order_by(OpportunityFeedback.created_at.desc())
            .limit(limit)
        )
    )


def list_feedback(session: Session, limit: int = 100) -> list[OpportunityFeedback]:
    return list(
        session.scalars(
            select(OpportunityFeedback)
            .order_by(OpportunityFeedback.created_at.desc())
            .limit(limit)
        )
    )


def feedback_payload(feedback: OpportunityFeedback) -> dict:
    return {
        "id": feedback.id,
        "opportunity_id": feedback.opportunity_id,
        "report_id": feedback.report_id,
        "report_version": feedback.report_version,
        "usefulness_rating": feedback.usefulness_rating,
        "accuracy_rating": feedback.accuracy_rating,
        "dealer_decision": feedback.dealer_decision,
        "missing_info": feedback.missing_info,
        "incorrect_info": feedback.incorrect_info,
        "notes": feedback.notes,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        "updated_at": feedback.updated_at.isoformat() if feedback.updated_at else None,
    }


def feedback_summary_payload(feedback_items: list[OpportunityFeedback]) -> dict:
    opportunity_ids = {item.opportunity_id for item in feedback_items}
    usefulness = [_number(item.usefulness_rating) for item in feedback_items]
    accuracy = [_number(item.accuracy_rating) for item in feedback_items]
    decision_counts = Counter(item.dealer_decision for item in feedback_items)
    missing_info_counts = Counter(
        entry
        for item in feedback_items
        for entry in _clean_items(item.missing_info)
    )
    incorrect_info_counts = Counter(
        entry
        for item in feedback_items
        for entry in _clean_items(item.incorrect_info)
    )
    return {
        "total_feedback": len(feedback_items),
        "tested_opportunities": len(opportunity_ids),
        "average_usefulness": _average(usefulness),
        "average_accuracy": _average(accuracy),
        "decision_counts": dict(sorted(decision_counts.items())),
        "common_missing_info": _counter_payload(missing_info_counts),
        "common_incorrect_info": _counter_payload(incorrect_info_counts),
    }


def _counter_payload(counter: Counter) -> list[dict]:
    return [
        {"value": value, "count": count}
        for value, count in counter.most_common(10)
    ]


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _clean_items(items: list[str] | None) -> list[str]:
    return [str(item).strip() for item in (items or []) if str(item).strip()]


def _number(value):
    if isinstance(value, Decimal):
        return float(value)
    return value

from __future__ import annotations

import smtplib
from datetime import UTC, datetime
from decimal import Decimal
from email.message import EmailMessage
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import Alert, CandidateSnapshot, DealerAccount, DealerSettingsModel, Search

HIGH_SCORE_ALERT = "high_score"
PRICE_DROP_ALERT = "price_drop"
IN_APP_CHANNEL = "in_app"
EMAIL_CHANNEL = "email"


def generate_alerts_for_search_run(
    session: Session,
    *,
    search: Search,
    search_run_id: str,
    settings: Settings,
) -> list[Alert]:
    if not search.alerts_enabled:
        return []
    candidates = list(
        session.scalars(
            select(CandidateSnapshot)
            .where(CandidateSnapshot.search_run_id == search_run_id)
            .order_by(CandidateSnapshot.rank.asc())
        )
    )
    threshold = _candidate_score_threshold(session, search.dealer_account_id)
    generated: list[Alert] = []
    for candidate in candidates:
        if _number(candidate.deal_score) >= threshold:
            generated.extend(
                _create_channel_alerts(
                    session,
                    search=search,
                    candidate=candidate,
                    alert_type=HIGH_SCORE_ALERT,
                    title=f"High-score listing: {candidate.title or 'Candidate'}",
                    body=(
                        f"{candidate.source_name} candidate scored {_number(candidate.deal_score):.0f}, "
                        f"meeting the alert threshold of {threshold:.0f}."
                    ),
                    metadata={
                        "threshold": threshold,
                        "deal_score": _number(candidate.deal_score),
                        "asking_price_cad": _number(candidate.asking_price_cad),
                        "source_name": candidate.source_name,
                        "source_url": candidate.source_url,
                    },
                    settings=settings,
                )
            )

        previous = _previous_candidate_snapshot(session, candidate)
        if (
            previous is not None
            and candidate.asking_price_cad is not None
            and previous.asking_price_cad is not None
            and _number(candidate.asking_price_cad) < _number(previous.asking_price_cad)
        ):
            generated.extend(
                _create_channel_alerts(
                    session,
                    search=search,
                    candidate=candidate,
                    alert_type=PRICE_DROP_ALERT,
                    title=f"Price drop: {candidate.title or 'Candidate'}",
                    body=(
                        f"{candidate.source_name} price dropped from "
                        f"${_number(previous.asking_price_cad):,.0f} to ${_number(candidate.asking_price_cad):,.0f}."
                    ),
                    metadata={
                        "old_price_cad": _number(previous.asking_price_cad),
                        "new_price_cad": _number(candidate.asking_price_cad),
                        "deal_score": _number(candidate.deal_score),
                        "source_name": candidate.source_name,
                        "source_url": candidate.source_url,
                        "previous_candidate_snapshot_id": previous.id,
                    },
                    settings=settings,
                )
            )
    return generated


def list_alerts(session: Session, *, limit: int = 50, include_read: bool = True) -> list[Alert]:
    statement = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if not include_read:
        statement = (
            select(Alert)
            .where(Alert.status != "read")
            .order_by(Alert.created_at.desc())
            .limit(limit)
        )
    return list(session.scalars(statement))


def mark_alert_read(session: Session, alert_id: str) -> Alert | None:
    alert = session.get(Alert, alert_id)
    if alert is None:
        return None
    alert.status = "read"
    alert.read_at = datetime.now(UTC)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    return alert


def alert_payload(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "dealer_account_id": alert.dealer_account_id,
        "search_id": alert.search_id,
        "search_run_id": alert.search_run_id,
        "candidate_snapshot_id": alert.candidate_snapshot_id,
        "opportunity_id": alert.opportunity_id,
        "alert_type": alert.alert_type,
        "title": alert.title,
        "body": alert.body,
        "channel": alert.channel,
        "status": alert.status,
        "recipient_email": alert.recipient_email,
        "sent_at": alert.sent_at.isoformat() if alert.sent_at else None,
        "read_at": alert.read_at.isoformat() if alert.read_at else None,
        "metadata": alert.metadata_json,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


def _create_channel_alerts(
    session: Session,
    *,
    search: Search,
    candidate: CandidateSnapshot,
    alert_type: str,
    title: str,
    body: str,
    metadata: dict[str, Any],
    settings: Settings,
) -> list[Alert]:
    alerts: list[Alert] = []
    if search.in_app_alerts_enabled:
        alert = _create_alert(
            session,
            search=search,
            candidate=candidate,
            alert_type=alert_type,
            title=title,
            body=body,
            channel=IN_APP_CHANNEL,
            status="unread",
            metadata=metadata,
        )
        if alert is not None:
            alerts.append(alert)
    if search.email_alerts_enabled:
        dealer = session.get(DealerAccount, search.dealer_account_id)
        alert = _create_alert(
            session,
            search=search,
            candidate=candidate,
            alert_type=alert_type,
            title=title,
            body=body,
            channel=EMAIL_CHANNEL,
            status="pending",
            metadata=metadata,
            recipient_email=dealer.email if dealer else None,
        )
        if alert is not None:
            _send_email_alert(session, alert, settings=settings)
            alerts.append(alert)
    return alerts


def _create_alert(
    session: Session,
    *,
    search: Search,
    candidate: CandidateSnapshot,
    alert_type: str,
    title: str,
    body: str,
    channel: str,
    status: str,
    metadata: dict[str, Any],
    recipient_email: str | None = None,
) -> Alert | None:
    alert = Alert(
        dealer_account_id=search.dealer_account_id,
        search_id=search.id,
        search_run_id=candidate.search_run_id,
        candidate_snapshot_id=candidate.id,
        opportunity_id=candidate.opportunity_id,
        alert_type=alert_type,
        title=title,
        body=body,
        channel=channel,
        status=status,
        recipient_email=recipient_email,
        metadata_json=metadata,
    )
    session.add(alert)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    session.refresh(alert)
    return alert


def _send_email_alert(session: Session, alert: Alert, *, settings: Settings) -> None:
    if settings.alert_email_dry_run or not settings.smtp_host or not alert.recipient_email:
        alert.status = "skipped"
        alert.sent_at = datetime.now(UTC)
        alert.metadata_json = {
            **(alert.metadata_json or {}),
            "email_delivery": "dry_run" if settings.alert_email_dry_run else "missing_smtp_or_recipient",
        }
        session.add(alert)
        session.commit()
        session.refresh(alert)
        return

    message = EmailMessage()
    message["From"] = settings.alert_email_from
    message["To"] = alert.recipient_email
    message["Subject"] = alert.title
    message.set_content(f"{alert.body}\n\nOpen listing: {(alert.metadata_json or {}).get('source_url', '')}")
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            if settings.smtp_use_tls:
                smtp.starttls()
            if settings.smtp_username and settings.smtp_password:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        alert.status = "failed"
        alert.metadata_json = {**(alert.metadata_json or {}), "email_error": str(exc)}
    else:
        alert.status = "sent"
        alert.sent_at = datetime.now(UTC)
    session.add(alert)
    session.commit()
    session.refresh(alert)


def _previous_candidate_snapshot(session: Session, candidate: CandidateSnapshot) -> CandidateSnapshot | None:
    return session.scalar(
        select(CandidateSnapshot)
        .where(
            CandidateSnapshot.id != candidate.id,
            CandidateSnapshot.search_run_id != candidate.search_run_id,
            or_(
                CandidateSnapshot.source_url == candidate.source_url,
                CandidateSnapshot.listing_id == candidate.listing_id,
            ),
            CandidateSnapshot.asking_price_cad.is_not(None),
        )
        .order_by(CandidateSnapshot.created_at.desc())
        .limit(1)
    )


def _candidate_score_threshold(session: Session, dealer_account_id: str) -> float:
    settings = session.scalar(
        select(DealerSettingsModel).where(DealerSettingsModel.dealer_account_id == dealer_account_id)
    )
    if settings is None:
        return 75.0
    return _number(settings.candidate_score_threshold)


def _number(value) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)

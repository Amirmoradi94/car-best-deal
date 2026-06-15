# Implementation Plan: In-App and Email Alerts

## Objective

Add an alert workflow for saved-search monitoring so dealers can see high-score listings and price drops in the dashboard, and optionally receive email notifications.

## Current State

- `searches` already has `alerts_enabled`, `email_alerts_enabled`, and `in_app_alerts_enabled`.
- There is no `alerts` table, alert generation service, alert inbox API, email delivery path, high-score trigger, or price-drop trigger.
- Search runs persist candidate snapshots with deal score, source URL, listing ID, price, and pricing/risk summaries.

## Scope

1. Create an `alerts` table and ORM model.
2. Expose alert settings on saved-search create/detail/list/update responses.
3. Generate alerts after saved-search runs.
4. Support in-app alerts and email alert rows independently.
5. Add an SMTP sender with dry-run default for local development.
6. Add inbox/list/read API routes.
7. Add dashboard controls and inbox rendering.
8. Cover the workflow with API/service/migration/dashboard tests.

## Alert Rules

High-score alert:

```text
candidate.deal_score >= dealer_settings.candidate_score_threshold
```

Price-drop alert:

```text
current_candidate.asking_price_cad < previous_candidate.asking_price_cad
```

Previous candidates are matched by source URL first and listing ID second, excluding the current search run.

## Channels

- `in_app`: persisted with status `unread`, shown in the dashboard inbox.
- `email`: persisted separately and sent through SMTP when configured. Local default is dry-run, which marks email alerts as `skipped` and records the reason.

## Deduplication

Alerts are deduplicated by:

- dealer account
- search
- alert type
- channel
- source URL/listing identity
- current candidate snapshot

This prevents duplicate in-app/email rows if generation is retried for the same run.

## API

- `GET /api/alerts`
  - Lists recent alerts.
- `PATCH /api/alerts/{alert_id}/read`
  - Marks an in-app alert read.

## Operations

Email settings:

```env
ALERT_EMAIL_DRY_RUN=true
ALERT_EMAIL_FROM=alerts@car-dealer.local
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
```

Dry-run mode is the safe default for local development and tests.

## Verification

- Scheduled or manual saved-search runs create high-score in-app alerts when enabled.
- Email alerts create email rows and mark dry-run delivery as skipped.
- Price drops are detected by comparing with prior candidate snapshots.
- Inbox API lists alerts and can mark in-app alerts read.
- Dashboard includes alert settings and an alert inbox.

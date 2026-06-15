<claude-mem-context>
# Memory Context

# [car-dealer] recent context, 2026-06-15 1:37pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision 🚨security_alert 🔐security_note
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (19,794t read) | 670,707t work | 97% savings

### Jun 15, 2026
7880 12:14a 🟣 Integration Tests Added for Alert Generation, Email Dry-Run, and Price-Drop Detection
7881 " 🔄 Test Client Gains testing_session() Helper; Dashboard Tests Assert Alert UI Presence
7882 " 🟣 Alerts Table Migration Assertion Added; Alembic Version Bumped to 4c6d8e2a91b7
7883 " ✅ SMTP and Alert Email Environment Variables Added to .env.example
7884 12:15a ✅ SMTP Alert Env Vars Mirrored to .env.postgres.example
7885 " ✅ Alert System Documented in backend-readme.md
7886 " 🔵 First Test Run Reveals Two Alert Implementation Gaps
7887 " 🔴 High-Score Alert Test Fixed by Seeding DealerSettingsModel with Low Score Threshold
7888 12:16a 🟣 Alert System Fully Implemented and All 5 Tests Passing
7889 " 🟣 Full Test Suite Passes After Alert System Implementation — 105 Passed, 2 Skipped
7890 " ⚖️ Next Feature: Dealer Settings Management — Plan Created
7891 " 🔵 Dealer Settings Gap: GET /api/settings Returns Hardcoded Defaults, No PATCH Route, Search Pipeline Ignores DB
7892 12:17a ⚖️ Dealer Settings Management Implementation Plan Written
7893 " 🟣 Dealer Settings Service Created with DB-Backed Get/Update/Domain Conversion
7894 " 🔄 Hardcoded settings.py Route Deleted in Preparation for DB-Backed Replacement
7895 12:18a 🟣 Settings API Rebuilt with DB-Backed GET, New PATCH Endpoint, and Pydantic Validation
7896 " 🟣 SearchPipeline Accepts Injected DealerSettings, Falls Back to Hardcoded Defaults
7897 " 🟣 Search Execution Now Loads DealerSettings from DB Before Constructing SearchPipeline
7898 " 🟣 Dealer Settings Panel Added to Dashboard HTML Above Search Form
7899 " 🟣 Dashboard JS Wired for Settings Load, Save, and State Tracking
7900 12:19a 🟣 Settings Panel Helpers Implemented: settingsPayload, renderSettings, applySettingsDefaults
7901 " 🟣 csvTerms() Helper Added and saveSettingsButton Included in Global Loading State
7902 " 🟣 Settings Panel CSS Added to Dashboard Stylesheet
7903 " 🔴 settingsPayload() Fixed: || Replaced with ?? for All Numeric Settings Fields
7904 " 🔵 test_dashboard.py Patch Failed — Context Lines Don't Match Current File
7905 12:20a 🔴 test_dashboard.py Smoke Test Assertions for Settings UI Applied Successfully on Second Attempt
7906 " 🟣 Settings API Persistence Integration Test Added to test_dashboard.py
7907 " 🟣 Scoring Integration Test Added: Search Run Uses Persisted Dealer Settings for Cap and Target Profit
7908 " ✅ Dealer Settings Section Added to backend-readme.md
7909 " 🔵 PATCH /api/settings Returns 200 but Does Not Persist — Settings Updates Silently Lost
7910 12:21a 🔴 PATCH /api/settings Fixed: target_profit_cad Now Maps to default_target_profit_cad Column
7911 " 🟣 Dealer Settings Management Feature Complete — 107 Tests Passing, No Regressions
7913 12:34a ⚖️ Natural-Language Search Interpretation Feature Planned for Implementation
7914 1:07p 🔵 Car-Dealer Project Structure Mapped for Price-Drop Tracking Feature
7915 " 🔵 Price-Drop Alert Logic Already Partially Implemented in alerts.py
7916 " 🔵 DB Schema: ListingSnapshotModel and CandidateSnapshot Store Price but No Price History Chain
7917 1:08p 🔵 Alembic Migration Head is b7f2a91c6d3e (ai_model_outputs) — Price-Drop Feature Needs New Migration
7918 " 🔵 Price-Drop Detection Test Already Passes Using CandidateSnapshot Cross-Run Comparison
7919 1:09p ⚖️ Price-Drop Tracking: Architecture Decision to Reuse listings + listing_snapshots Tables
7920 " 🟣 New Service app/services/price_history.py Created for Listing Price History Persistence
7921 " 🟣 previsit_persistence.py Updated to Record Listing Price History per Candidate
7922 1:10p 🟣 alerts.py Upgraded: Price-Drop Detection Now Uses listing_snapshots History First, Falls Back to CandidateSnapshot
7923 " 🟣 Tests Updated to Assert Listing + ListingSnapshot Rows Written and Price History Embedded in pricing_summary
7924 " 🔵 _candidate_payload() Already Exposes Full pricing_summary — No API Route Changes Needed for price_history
7925 1:11p 🔵 Tests Run via uv run --extra dev pytest — Not Bare pytest
7926 " 🟣 All 60 Tests Pass After Price-Drop Tracking Implementation
7927 " 🟣 Full Test Suite Passes: 118 Passed, 2 Skipped (Postgres Runtime), 0 Failed
7930 " 🔵 backend-readme.md Has Stale Price-Drop Alert Description; Git Working Tree Contains Both AI Audit Trail and Price-Drop Changes Uncommitted
7931 1:12p ✅ backend-readme.md Updated with Accurate Price-Drop Tracking Documentation
7933 " 🔵 Dashboard Candidate Pricing Section Does Not Expose price_history — UI Gap Identified

Access 671k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
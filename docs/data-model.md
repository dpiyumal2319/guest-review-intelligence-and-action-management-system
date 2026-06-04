# Data Model

## Model Goals

The data model supports auditability, operational dashboarding, NLP reproducibility, and ticket workflow tracking. It intentionally separates raw source payloads from normalized review records and separates review action state from ticket lifecycle state.

## Reference Configuration

### `review_sources`

Defines the MVP review platforms the system can ingest and report on.

Important fields:

- `code`: stable source identifier such as `google_business_profile`, `booking_com`, or `tripadvisor`.
- `name`: display name.
- `is_verified_channel`: whether this is treated as a review-platform channel in the MVP.
- `connector_key`: API/CLI connector key.
- `metadata`: source policy and connector metadata.

There is no product-facing dataset, Apify, Reddit, social-listening, or source-type model in the MVP.

### `departments`

Operational ownership units such as front office, housekeeping, food and beverage, engineering, guest relations, and sales/revenue.

Used by analysis routing, issue summaries, tickets, and dashboard filters.

### `issue_categories`

Operational issue taxonomy:

- cleanliness;
- room condition;
- food and beverage;
- service delay;
- staff behavior;
- noise/events;
- pricing/value;
- booking/check-in;
- amenities/facilities;
- positive general;
- other/uncategorized.

### `category_department_mappings`

Maps issue categories to owning departments. One mapping can be primary, with optional secondary mappings for cross-functional routing.

### `reputation_risk_thresholds`

Stores category-specific low-rating, negative-sentiment, urgent-confidence, and recurrence-count thresholds. These document escalation expectations for the transparent Reputation Risk score.

### `demo_roles`

Seeded role definitions for prototype behavior and documentation. This is not production authentication.

## Ingestion Records

### `ingestion_runs`

Audits each connector import attempt.

Tracked counts:

- `records_seen`;
- `records_created`;
- `records_updated`;
- `records_skipped`;
- `records_duplicate_flagged`;
- `error_count`;
- `errors`.

Run statuses include completed and failed depending on importer behavior.

### `raw_reviews`

Stores original provider-shaped payloads for audit and reprocessing.

Important fields:

- `source_code`;
- `external_review_id`;
- `ingestion_run_id`;
- `raw_payload`;
- `payload_hash`;
- `ingested_at`.

The unique key is `(source_code, external_review_id)` so repeated imports update existing rows rather than duplicating source records.

## Normalized Reviews

### `normalized_reviews`

Canonical review record used by analysis, dashboards, and ticket workflows.

Important fields:

- `raw_review_id`: one-to-one link to preserved raw payload.
- `source_code` and `external_review_id`: stable source identity.
- `reviewer_name`: public display name when available; avoid treating it as verified private identity.
- `review_date`, `rating`, `language`, `title`, `body`: core review content.
- `content_hash`: normalized hash of body/title/rating/language for content dedupe.
- `is_content_duplicate` and `duplicate_of_review_id`: content duplicate flagging.
- `sentiment_label`, `sentiment_score`, `issue_category_code`, `reputation_risk`, `department_code`: denormalized latest analysis summary for API compatibility and fast dashboard reads.
- `action_status`: review input workflow state: `new`, `reviewed`, `ticket_created`, or `ignored`.
- `normalized_payload`: canonical source-specific metadata.
- `updated_at`.

The unique key is `(source_code, external_review_id)`.

## Review Analysis

### `review_analyses`

Stores the latest active NLP/scoring output for each normalized review.

Important fields:

- `review_id`: one-to-one link to the normalized review.
- `sentiment_label`, `sentiment_score`, `sentiment_confidence`;
- `issue_category_code`;
- `reputation_risk_score`, `reputation_risk_label`;
- `department_code`;
- `model_name`, `model_version`, `analysis_version`;
- `explanation_factors`;
- `analyzed_at`;
- `is_active`.

V1 stores the latest active analysis per review rather than a full analysis history. Reanalysis updates this row and synchronizes summary columns back to `normalized_reviews`.

### `review_issue_category_predictions`

Stores ranked issue-category predictions for an analysis.

Important fields:

- `analysis_id`;
- `category_code`;
- `confidence`;
- `rank`;
- `is_primary`;
- `department_code`;
- `model_name`, `model_version`;
- `analyzed_at`.

This keeps the data model multi-label capable even when the operational UI uses the top-ranked category as the primary issue.

## Action Tickets

### `action_tickets`

Corrective-action item owned by a department.

Tickets can originate from:

- a single review via `review_id`;
- a category/department recurrence via `source_group_type = category_department_recurrence`;
- a semantic cluster via `source_group_type = semantic_cluster`.

Important fields:

- `review_id`: nullable for recurring issue tickets.
- `department_code`: owning department.
- `source_group_type`, `source_group_key`, `source_group_label`: recurring issue source identity.
- `source_category_code`: source issue category when applicable.
- `source_cluster_id`: semantic cluster identifier when applicable.
- `source_review_ids`: review IDs included in the source group.
- `priority`: `low`, `medium`, `high`, or `urgent`.
- `status`: `open`, `in_progress`, `blocked`, `resolved`, or `verified`.
- `assignee_name`, `assignee_email`;
- `due_date`;
- `notes`;
- `created_at`, `updated_at`.

When a ticket is created, relevant source reviews move to `action_status = ticket_created`.

### `ticket_events`

Append-only ticket event history.

Tracked event types include:

- `created`;
- `status_change`;
- `priority_change`;
- `department_change`;
- `assignment_change`;
- `note_added`.

Each event stores old/new values where relevant, a note, and `occurred_at`.

## Model Metadata

Model metadata is stored with analysis outputs, not only in code:

- `model_name` identifies the analyzer or classifier.
- `model_version` identifies the active model version or artifact identifier.
- `analysis_version` identifies the analysis contract.
- `analyzed_at` records when the output was generated.
- `explanation_factors` stores transparent feature contributions and routing notes.

Staff-facing review responses hide model metadata from normal UI views while keeping it available in persisted analysis records for technical audit.

## Data Flow Summary

1. A connector creates an `ingestion_runs` row.
2. Raw source data is upserted into `raw_reviews`.
3. Canonical data is upserted into `normalized_reviews`.
4. Content duplicates are flagged by normalized content hash.
5. `analyze_and_persist_review` creates or updates `review_analyses` and `review_issue_category_predictions`.
6. Dashboard endpoints read normalized records plus active analysis.
7. Ticket endpoints create `action_tickets`, append `ticket_events`, and update review action status.

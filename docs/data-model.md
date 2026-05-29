# Data Model

## Model Goals

The data model is designed to support auditability, operational dashboarding, NLP reproducibility, and ticket workflow tracking. It intentionally separates source payload preservation from normalized records and separates review action state from ticket lifecycle state.

## Reference Configuration

### `review_sources`

Defines every source the system can ingest or report on.

Important fields:

- `code`: stable source identifier.
- `name`: display name.
- `source_type`: `verified_review`, `social_listening`, `seed_dataset`, or `apify_dataset_import`.
- `is_verified_channel`: whether the source should be counted in default verified-review KPIs.
- `connector_key`: API-triggerable connector key when applicable.
- `metadata`: source policy and connector metadata.

Default dashboard behavior excludes `source_type = social_listening` unless explicitly included or selected.

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

### `severity_thresholds`

Stores category-specific low-rating, negative-sentiment, urgent-confidence, and recurrence-count thresholds. These explain escalation expectations even when the current severity algorithm uses deterministic scoring.

### `demo_roles`

Seeded role definitions for prototype behavior and documentation. This is not production authentication.

## Ingestion Records

### `ingestion_runs`

Audits each import attempt.

Tracked counts:

- `records_seen`;
- `records_created`;
- `records_updated`;
- `records_skipped`;
- `records_duplicate_flagged`;
- `error_count`;
- `errors`.

Run statuses include completed, completed with errors, and failed depending on importer behavior.

### `raw_reviews`

Stores original provider or dataset payloads for audit and reprocessing.

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
- `sentiment_label`, `sentiment_score`, `issue_category_code`, `severity`, `department_code`: denormalized latest analysis summary for API compatibility and fast dashboard reads.
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
- `severity_score`, `severity_label`;
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

This keeps the data model multi-label capable even when the first operational classifier emits one primary category.

## Action Tickets

### `action_tickets`

Corrective-action item owned by a department.

Tickets can originate from:

- a single review via `review_id`;
- a category recurrence via `source_group_type = category_recurrence`;
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
- `assignment_change`;
- `note_added`.

Each event stores old/new values where relevant, a note, and `occurred_at`.

## Model Metadata

Model metadata is stored with analysis outputs, not only in code:

- `model_name` identifies the analyzer or classifier.
- `model_version` identifies the fallback version or trained artifact version.
- `analysis_version` identifies the analysis contract.
- `analyzed_at` records when the output was generated.
- `explanation_factors` stores transparent feature contributions and routing notes.

The issue classifier runtime also supports:

- `ISSUE_CLASSIFIER_MODEL_PATH`;
- `ISSUE_CLASSIFIER_MODEL_VERSION`;
- default artifact path `apps/api/artifacts/ml/issue_classifier.pkl`.

## Data Flow Summary

1. A connector/importer creates an `ingestion_runs` row.
2. Raw source data is upserted into `raw_reviews`.
3. Canonical data is upserted into `normalized_reviews`.
4. Content duplicates are flagged by normalized content hash.
5. `analyze_and_persist_review` creates or updates `review_analyses` and `review_issue_category_predictions`.
6. Dashboard endpoints read normalized records plus active analysis.
7. Ticket endpoints create `action_tickets`, append `ticket_events`, and update review action status.

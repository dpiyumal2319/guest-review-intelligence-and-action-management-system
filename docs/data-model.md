# Data Model

## Model Goals

The data model supports auditability, operational dashboarding, NLP reproducibility, and issue lifecycle tracking. It intentionally separates raw source payloads from normalized review records, and separates review analysis from issue state.

## Reference Configuration

### `review_sources`

Defines the MVP review platforms the system can ingest and report on.

Important fields:
- `code`: stable source identifier such as `google_business_profile`, `booking_com`, or `tripadvisor`.
- `name`: display name.
- `is_verified_channel`: whether this is treated as a verified review-platform channel.
- `connector_key`: API/CLI connector key.
- `metadata`: source policy and connector metadata (JSON).

All three sources have `is_verified_channel = True` and `connector_mode = "mock_official_shaped"`.

### `departments`

Operational ownership units. Six departments with their current risk weights:

| Code | Name | Risk Weight | Service Level (hrs) |
|---|---|---|---|
| `front_office` | Front Office | 12 | 24 |
| `housekeeping` | Housekeeping | 14 | 24 |
| `food_beverage` | Food and Beverage | 12 | 24 |
| `engineering` | Engineering | 16 | 48 |
| `guest_relations` | Guest Relations | 12 | 24 |
| `management` | Management | 18 | 72 |

Used by analysis routing, detected issues, semantic clusters, and dashboard filters. Risk weight feeds directly into Reputation Risk scoring (not scaled).

### `demo_roles`

Four seeded roles for prototype behavior and documentation. This is not production authentication.

| Code | Name | Permissions | Department Scope |
|---|---|---|---|
| `admin` | Prototype Admin | config:read/write, reviews:read, issues:manage, analytics:read | `["*"]` |
| `operations_manager` | Operations Manager | config:read, reviews:read, issues:manage, analytics:read | All 6 departments |
| `department_head` | Department Head | config:read, reviews:read, issues:manage | `["assigned_department"]` |
| `analyst` | Review Analyst | config:read, reviews:read, analytics:read | `[]` |

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
- `errors` (JSON list of strings).

Run statuses: `"running"`, `"completed"`, `"failed"`.

### `raw_reviews`

Stores original provider-shaped payloads for audit and reprocessing.

Important fields:
- `source_code` FK → `review_sources`;
- `external_review_id`;
- `ingestion_run_id` FK → `ingestion_runs`;
- `raw_payload` (JSON);
- `payload_hash` (SHA-256 hex of sorted JSON);
- `ingested_at` (UTC).

The unique key is `(source_code, external_review_id)` so repeated imports update existing rows rather than duplicating source records.

## Normalized Reviews

### `normalized_reviews`

Canonical review record used by analysis, dashboards, and issue linking.

Important fields:
- `raw_review_id`: one-to-one link to preserved raw payload.
- `source_code` and `external_review_id`: stable source identity, unique together.
- `reviewer_name`: public display name.
- `review_date`, `rating`, `language`, `title`, `body`: core review content.
- `content_hash`: SHA-256 of canonical body/title/rating/language for content dedupe.
- `is_content_duplicate` and `duplicate_of_review_id`: content duplicate flagging (first by ID = canonical).
- `normalized_payload` (JSON): canonical source-specific metadata (connector key, provider fields, visibility signals).
- `updated_at` (UTC).

Computed properties (not stored, derived at access time):
- `display_body`, `display_title`, `display_reviewer_name`, `display_external_review_id`: PII-redacted versions.
- `has_display_redactions`: whether any display field contains PII.
- `redacted_display_fields`: list of field names with redacted content.
- `source_name`, `is_verified_channel`: convenience accessors to the source relationship.

Relationship to `ReviewAnalysis` (one-to-one) and `IssueReviewLink` (one-to-many).

## Review Analysis

### `review_analyses`

Stores the latest active NLP/scoring output for each normalized review. One-to-one with `normalized_reviews`.

Important fields:
- `review_id`: FK → `normalized_reviews` (unique).
- `sentiment_label` (`positive`/`mixed`/`negative`), `sentiment_score` (-1.0 to 1.0), `sentiment_confidence`;
- `department_code` FK → `departments`;
- `department_confidence`, `department_model_name`;
- `reputation_risk_score` (0-100), `reputation_risk_label` (`low`/`medium`/`high`/`critical`);
- `embedding` (JSON list of floats, typically 384-dim from MiniLM);
- `embedding_model_name`, `embedding_generated_at`;
- `analysis_version` (`"analysis-v3"`);
- `explanation_factors` (JSON): transparent breakdowns including:
  - `sentiment`: strategy, model details, token count;
  - `department`: top prediction, confidence, ranked predictions;
  - `reputation_risk`: weights, threshold thresholds, operational explanations;
  - `model`: all model names and versions used;
  - `signals`: urgency terms matched, duplicate flags.
- `analyzed_at` (UTC);
- `is_active`: always `True` (V1 stores latest only).

V1 stores the latest active analysis per review rather than a full analysis history. Reanalysis updates this row.

## Detected Issues

### `detected_issues`

LLM-discovered operational issues from grouped negative/mixed reviews.

Important fields:
- `title`: canonical issue label (e.g. "Air conditioning not cooling rooms"), up to 255 chars.
- `description`: LLM-generated 1-3 sentence operational summary citing concrete specifics (rooms, floors, counts). Null for emerging candidates.
- `department_code` FK → `departments`;
- `status`: `"active"`, `"emerging"`, `"resolved"`, or `"recurred"`;
- `priority`: `"low"`, `"medium"`, `"high"`, or `"urgent"` (derived from risk score);
- `reputation_risk_score`: max risk score among linked reviews;
- `recurrence_count`: number of linked evidence reviews;
- `first_seen_at`, `last_seen_at`: UTC timestamps from review dates;
- `resolved_at`, `recurred_at`: lifecycle timestamps;
- `assignee_name`: optional assigned handler;
- `cluster_key` (unique): hash-based stable identifier for idempotent rebuilds;
- `cluster_centroid` (JSON): averaged embedding of linked reviews;
- `embedding_model_name`: which embedding model produced the centroid;
- `title_generated_by`: LLM provider (`"gemini"` or `"stub"`);
- `title_generation_model`: model ID (`"gemini-2.5-flash"` or `"stub-deterministic"`);
- `title_confidence`, `title_quality_score`;
- `keywords` (JSON list): extracted top frequency terms from evidence;
- `merged_from_id`: tracks issue merging for dedup;
- `created_at`, `updated_at` (UTC).

Status rules:
- ≥2 supporting reviews → `"active"`;
- 1 supporting review → `"emerging"` (surface via `/issues/emerging`, not the main list);
- `"resolved"` on user action;
- `"recurred"` when a previously resolved issue appears in a new detection run.

### `issue_review_links`

Many-to-many join between `detected_issues` and `normalized_reviews` with similarity metadata.

Important fields:
- `issue_id` FK and `review_id` FK: unique together;
- `similarity_score`: always 1.0 (direct evidence);
- `linked_at` (UTC);
- `is_triggering_evidence`: whether the review is within the 30-day recurrence window;
- `evidence_snippet`: the specific quote or problem specifics from the review (up to 500 chars).

Convenience properties (via `NormalizedReview` relationship):
- `review_source_code`, `review_source_name`: platform attribution;
- `review_external_id`, `review_reviewer_name`: redacted display values;
- `review_date`, `review_rating`, `review_body`: review content for detail sheet;
- `review_url`: original platform URL for real crawled reviews only (null for synthetic).

### `issue_events`

Append-only issue event history.

Tracked event types:
- `"created"`: issue detected by pipeline;
- `"resolved"`: issue marked resolved;
- `"priority_changed"`;
- `"assignee_changed"`.

Each event stores: `event_type`, `actor`, `old_value`, `new_value`, `note`, `created_at`.

## Model Metadata

Model metadata is stored with analysis outputs, not only in code:

- `model_name` identifies the analyzer or classifier (e.g. `"huggingface-transformers-sentiment-analysis"`, `"huggingface-transformers-zero-shot-classification"`, `"local-sentence-transformer-review-embeddings"`).
- `model_version` identifies the active model artifact (e.g. commit hash, pipeline name_or_path).
- `analysis_version` identifies the analysis contract (`"analysis-v3"`).
- `analyzed_at` records when the output was generated.
- `explanation_factors` stores transparent feature contributions and routing notes.

For issue detection, `title_generated_by` and `title_generation_model` record the LLM provider. `embedding_model_name` on `detected_issues` tracks which embedding pipeline produced the cluster centroid.

Staff-facing review responses hide model metadata from normal UI views while keeping it available in persisted records for technical audit.

## Data Flow Summary

1. A connector creates an `ingestion_runs` row.
2. Raw source data is upserted into `raw_reviews`.
3. Canonical data is upserted into `normalized_reviews`.
4. Content duplicates are flagged by normalized content hash.
5. `analyze_and_persist_review` creates or updates `review_analyses` with sentiment, department classification, embedding, and reputation risk.
6. Dashboard endpoints read normalized records plus active analysis for KPI aggregates.
7. Issue detection (triggered on demand) reads negative/mixed reviews, extracts problems via LLM, consolidates into canonical types, and creates `detected_issues` with `issue_review_links`.
8. Issue lifecycle events are recorded in `issue_events`.
9. Detection rebuilds preserve resolved/assignee state via `cluster_key` matching.
10. Emerging candidates (single-review) are excluded from the active issue list but available via `/issues/emerging`.

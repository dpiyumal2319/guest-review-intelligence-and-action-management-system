# Implementation Documentation: Guest Review Intelligence & Action Management System

## 1. System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Docker Compose (local) / Docker Compose (prod)                    │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  web          │    │  api          │    │  postgres            │  │
│  │  Next.js 15   │────│  FastAPI      │────│  PostgreSQL 16       │  │
│  │  React 18     │    │  Python 3.12  │    │  Port 5432/5433      │  │
│  │  Port 3000    │    │  Port 8000    │    │                      │  │
│  └──────────────┘    └──────┬─────────┘    └──────────────────────┘  │
│                              │                                        │
│                    ┌─────────▼─────────┐                             │
│                    │  Hugging Face     │                             │
│                    │  Transformers     │                             │
│                    │  (NLP pipeline)   │                             │
│                    └───────────────────┘                             │
└────────────────────────────────────────────────────────────────────┘
```

**Runtime components** (how the system runs):
- **postgres** — PostgreSQL 16 (alpine). Two instances: default (5432) and test (5433).
- **api** — FastAPI backend with Pydantic v2, SQLAlchemy 2.0, Alembic migrations. Loads Hugging Face transformers for NLP at startup.
- **web** — Next.js 15 standalone build with React 18, Tailwind CSS v4, shadcn/ui.

**Build-time only** (outside product Docker):
- **Ollama** (local) — generates synthetic fixture datasets via `connector_fixture_generator.py`. Not a runtime dependency.

### Startup sequence

`app/__init__.py` loads `apps/api/.env` via `python-dotenv` (with `override=False`, so real env vars take precedence) before any module reads `os.environ`. This means `GEMINI_API_KEY`, `LLM_PROVIDER`, `DATABASE_URL` can be set in a `.env` file without manual exporting. If `dotenv` is missing, startup silently continues.

_Port mappings: 3000 (web), 8000 (api), 5432 (postgres), 5433 (postgres_test)._

---

## 2. Database Schema (SQLAlchemy / PostgreSQL)

Ten tables across three migration versions (`cc291a0f3582` — initial schema, `daa1b3c587f2` — issue keywords/quality/merged, `e4f2a7c91b08` — issue description):

| Table | Purpose | Key Columns |
|---|---|---|
| `review_sources` | Platforms (Google, Booking, TripAdvisor) | `code` PK, `connector_key`, `is_verified_channel`, `source_metadata` JSON |
| `departments` | Hotel departments (FO, HK, FB, Eng, Mgmt, GR) | `code` PK, `risk_weight` (8-18), `service_level_hours`, `sort_order` |
| `demo_roles` | Role-based access (admin, ops mgr, dept head, analyst) | `code` PK, `permissions` JSON, `department_scope` JSON |
| `ingestion_runs` | Connector import history | `status`, `records_*` counters, `errors` JSON |
| `raw_reviews` | Original platform payloads (immutable audit trail) | `payload_hash` (SHA-256), `raw_payload` JSON, unique on `(source_code, external_review_id)` |
| `normalized_reviews` | Canonical review record | `body`, `rating`, `review_date`, `content_hash`, `display_*` computed via redaction, `is_content_duplicate`, `duplicate_of_review_id` |
| `review_analyses` | One-to-one with normalized_reviews | `sentiment_*`, `department_code`, `department_confidence`, `embedding` JSON (384-dim), `embedding_model_name`, `reputation_risk_score`/`label`, `analysis_version`, `explanation_factors` JSON |
| `detected_issues` | Operational issues from LLM pipeline | `title`, `description`, `department_code`, `status` (active/emerging/resolved/recurred), `priority`, `reputation_risk_score`, `recurrence_count`, `cluster_key` (unique), `cluster_centroid` JSON, `embedding_model_name`, `title_generated_by`/`title_generation_model`/`title_confidence`, `keywords` JSON, `title_quality_score`, `merged_from_id`, full lifecycle timestamps |
| `issue_review_links` | Many-to-many join with similarity metadata | `similarity_score`, `is_triggering_evidence`, `evidence_snippet`. Exposes `review_source_code`, `review_source_name`, `review_external_id`, `review_reviewer_name`, `review_date`, `review_rating`, `review_body`, `review_url` via relationship properties |
| `issue_events` | Audit trail | `event_type` (created/resolved/priority_changed/assignee_changed), `actor`, `old_value`, `new_value`, `note` |

### Data flow through the schema

```
raw_payload (JSON from connector)
  └── RawReview (immutable, payload_hash ensures idempotency)
        └── NormalizedReview (canonical fields, content_hash for dedup)
              ├── ReviewAnalysis (NLP results: sentiment, dept, embedding, risk score)
              └── IssueReviewLink ── DetectedIssue (LLM-derived operational issues)
                                      └── IssueEvent (lifecycle audit trail)
```

---

## 3. Ingestion Pipeline

**Entry point:** `POST /ingestion/connectors/{connector_key}` or `app/ingestion.py::run_mock_connector_by_key`

### Connector architecture

Each platform has a `MockConnector` dataclass (defined in `connectors/base.py`) with:
- `connector_key` — unique identifier
- `source_code` — FK to `review_sources`
- `records` — tuple of raw payload dicts
- `normalize` — callable that transforms raw → normalized shape

Three registered connectors (`connectors/registry.py`):
- `google_business_profile` — GBP-shaped raw payload (`name`, `reviewId`, `reviewer.displayName`, `starRating` as ONE–FIVE, `comment`, `createTime`, optional `reviewReply`)
- `booking_com` — Booking.com-shaped raw payload (`guest_review_id`, `reservation_id`, `guest_name`, `score` out of 10, `review_title`, `review_text`, `stay_date`, `reviewer_nationality`)
- `tripadvisor` — TripAdvisor-shaped raw payload (`id`, `location_id`, `url`, `title`, `text`, `rating` 1-5, `published_date`, `user_info.username`, `subratings`)

Each connector has a `normalize()` function that maps its platform-specific payload to the standard `{source_code, external_review_id, reviewer_name, review_date, rating, language, title, body, normalized_payload}` shape. `normalized_payload` preserves original platform fields (`provider_has_reply`, `provider_url`, `provider_helpful_votes`, etc.) for visibility scoring and UI display.

Raw connector payloads have only 2 sample records each (minimum for fixture validation). Real data comes from fixture files loaded via `load_connector_fixture_records()`.

### Ingestion flow (`ingestion.py::upsert_ingested_review`)

```
raw_payload → stable_payload_hash() → SHA-256 of sorted JSON

──→ RawReview upsert (by source_code + external_review_id):
    - If new: create RawReview, flush
    - If exists with same hash: update ingestion_run_id, preserve record
    - If exists with different hash: update payload + hash

──→ NormalizedReview upsert:
    - canonical_review_values() extracts: rating, body, review_date, language, etc.
    - normalized_content_hash() computes SHA-256 of canonical text/rating/language
    - If new: create NormalizedReview → trigger analyze_and_persist_review()
    - If payload changed: update → re-run analysis
    - If unchanged: skip

──→ Content duplicate detection:
    - refresh_content_duplicate_group() marks all reviews with same content_hash
    - First by ID = canonical; others = duplicates with duplicate_of_review_id set
```

### Direct payload ingestion (`ingestion.py::run_payload_ingestion`)

An alternative ingestion path that accepts raw payload dicts directly (not through a connector). Used by `run_seed_ingestion()` and the `demo_pipeline.py` script. Validates that all payloads match the expected `source_code`.

### Seed ingestion (`ingestion.py::run_seed_ingestion`)

8 hardcoded seed reviews (`seed_reviews.py`) for Google Business Profile, used as a minimal bootstrap review set. Wraps `run_payload_ingestion()` with 8 seed reviews covering: slow check-in, breakfast queue, AC problems (2 variants), bathroom cleanliness, noise, mold. Ratings: 1.0–5.0, all GBP-shaped.

### Fixture ingestion

- Payloads from `data/generated-fixtures/connectors-{dolphin,llama}/` — up to 1000 reviews per platform
- Or real crawled data from `data/real-reviews/connectors/`
- Generated by `connector_fixture_generator.py` using local Ollama with 16 concrete scenario types

---

## 4. NLP Analysis Pipeline

Triggered automatically during ingestion (via `analysis.py::analyze_and_persist_review`) or on demand via `POST /analysis/reanalyze`.

### 4a. Sentiment Analysis (`sentiment.py`)

| Aspect | Detail |
|---|---|
| **Model** | `nlptown/bert-base-multilingual-uncased-sentiment` (Hugging Face pipeline, `local_files_only=True`) |
| **Strategy** | Text classification pipeline → 1-5 star rating → mapped to label |
| **Label mapping** | 1-2 → `negative`, 3 → `mixed`, 4-5 → `positive` |
| **Score mapping** | 1 → -1.0, 2 → -0.5, 3 → 0.0, 4 → 0.5, 5 → 1.0 |
| **Version** | `analysis-v3` |
| **Fallback** | None — raises `AnalysisRuntimeUnavailableError` if model unavailable or text empty |

### 4b. Department Classification (`ml/department_classifier.py`)

| Aspect | Detail |
|---|---|
| **Model** | `facebook/bart-large-mnli` (zero-shot classification pipeline, `local_files_only=True`) |
| **Labels** | 6 departments with descriptive candidate strings (e.g. `"engineering maintenance repair air conditioning plumbing facility defects"`) |
| **Strategy** | Zero-shot against candidate labels, `multi_label=False`, single best label selected |
| **Batch** | Up to 64 texts at once via `classify_batch()` |
| **Fallback** | Returns `guest_relations` with 0.3 confidence if model unavailable |
| **Sentence-level** | Each sentence in a review is independently classified; results stored in `explanation_factors.department.predictions[]` |

### 4c. Semantic Similarity (`semantic_similarity.py`)

Three-tier embedding strategy with automatic fallback. The `LocalSemanticSimilarityAnalyzer` wraps all three:

| Aspect | Detail |
|---|---|
| **Primary model** | `sentence-transformers/all-MiniLM-L6-v2` — 384-dim embeddings |
| **Fallback 1** | TF-IDF cosine similarity (scikit-learn `TfidfVectorizer`, ngram 1-2) |
| **Fallback 2** | Token overlap with Jaccard similarity: `|A∩B| / sqrt(|A|·|B|)` |
| **Similarity threshold** | 0.78 (sentence transformer), 0.30 (TF-IDF), 0.30 (token overlap) |
| **Clustering** | Connected components (BFS) from pairwise similarity graph |
| **Centroid** | L2-normalized average of member embeddings, computed via `compute_centroid()` |
| **Centroid similarity** | Dot product: `centroid_similarity(c, v) = dot(c, v)` clamped to [-1, 1] |
| **Model metadata** | `SimilarityRuntimeMetadata` tracks strategy name, model name, version, and fallback reason. `SimilarityComputation` wraps metadata + similarities dict |
| **Embedding for analysis** | `EmbeddingResult` dataclass holds `embeddings` (list of float lists), `model_name`, `model_version`, `strategy`, `fallback_note`. Falls back to TF-IDF dense array, then empty list |
| **Sentence splitting** | Regex `[.!?]+[)"'\]\s]+` splits review text; minimum 3 words per sentence |

### 4d. Reputation Risk Scoring (`analysis.py::score_reputation_risk`)

Composite score (0-100), calculated from:

| Factor | Max Points | Description |
|---|---|---|
| Rating | 30 | `(5 - rating) / 4 * 30` — low ratings add risk |
| Sentiment | 25 | `-sentiment_score * 25` — negative sentiment adds risk |
| Department weight | 16 | From `departments.risk_weight` (engineering=16, management=18) |
| Recency | 5 | ≤7 days = 5, ≤30 days = 2, older = 0 |
| Urgency terms | 15 | 5 points per matched term (max 3 terms) |
| Duplicate signal | 5 | If review is cross-posted |
| Platform visibility | 8 | Helpful votes + public URL + unreplied status |

**Risk labels:** 0-29 → low, 30-49 → medium, 50-74 → high, 75-100 → critical

### 4e. Per-sentence analysis

Each review is split into sentences; each sentence gets a department classification and embedding, stored as part of the `explanation_factors` JSON on `ReviewAnalysis`.

### 4f. Error Handling

All three NLP modules (`sentiment`, `department_classifier`, `semantic_similarity`) use `AnalysisRuntimeUnavailableError(component, detail)` for unrecoverable failures (missing model artifacts, empty text). The analysis pipeline catches these at the endpoint level and returns HTTP 503. Semantic similarity and department classification degrade gracefully (return fallback results); sentiment analysis does not — it raises immediately if unavailable.

---

## 5. Issue Detection Pipeline (`issue_detection.py`)

An LLM-driven batch pipeline that rebuilds the entire issue set from negative/mixed reviews. Three passes:

### Pass A — Extraction

**Input:** Batch of 8 reviews (default `ISSUE_LLM_BATCH_SIZE`) → **Output:** structured problem mentions

```
Candidate reviews (sentiment = negative or mixed, up to 1000, default `ISSUE_MAX_REVIEWS`)
  → LLM prompt: extract {summary, department_code, specifics} per problem
  → Each review can produce 0-N problems
  → summary = 5-9 word normalized label (e.g. "AC not cooling the room")
  → specifics = concrete facts (room/floor/item/amount/time) from the review
```

### Detection trigger

Issue detection is triggered via `POST /issues/detect?force=true` or `npm run api:detect`. The `trigger_detection.py` script tries the local API first (`httpx POST localhost:8000`), and if the API is unavailable, falls back to in-process execution with `SessionLocal() + detect_issues()`.

### Pass B — Consolidation

**Input:** All problem summaries → **Output:** canonical issue type mapping

```
Unique summary labels → LLM discovers taxonomy (25-70 types)
  → Each label assigned to best-matching type index (or -1 = unique incident)
  → Department decided by majority extraction vote
  → Keeps severe incidents (pest, theft, safety) as their own type
```

### Pass C — Assembly

**Input:** Canonical types with grouped evidence reviews → **Output:** `DetectedIssue` records

```
Per canonical type:
  - Compute risk (max of linked reviews)
  - Compute centroid embedding (majority-dimension averaged)
  - Generate cluster_key (hash of department + title for idempotent rebuild)
  - If ≥2 supporting reviews → status = "active" (with LLM description)
  - If 1 supporting review → status = "emerging" (no description, precomputed candidate)
  - Create IssueReviewLink per evidence review
  - Create IssueEvent("created")
```

### State preservation on rebuild

The old issue set is deleted and recreated from scratch (`_replace_issue_set`), but manual state is preserved:
- If a rebuilt issue's `cluster_key` matches a previously resolved issue → status restored to "resolved"
- If a rebuilt issue's `cluster_key` matches a previously `recurred` issue → status set to current (active/emerging) since the issue is happening again
- `assignee_name`, `resolved_at`, `recurred_at` are preserved across rebuilds

### Triggering evidence determination

`_is_triggering_evidence(review)` returns `True` if `review.review_date >= now - 30 days` (`RECURRENCE_WINDOW_DAYS = 30`). This is stored per-link to distinguish fresh evidence from historical reviews that support the same issue.

### Emerging candidates

Single-review issues surfaced via `GET /issues/emerging`. Defaults to high-risk only (`EMERGING_HIGH_RISK_THRESHOLD = 50`), capped at 50. The representative review snippet is shown in lieu of an LLM description. The response includes `total_high_risk` and `total_emerging` counts for pagination context.

---

## 6. LLM Client Architecture (`llm_client.py`)

**Provider pattern** — provider selected at runtime by `LLM_PROVIDER` env var.

### Gemini provider (default)

| Aspect | Detail |
|---|---|
| **Model** | `gemini-2.5-flash` (configurable via `LLM_MODEL`) |
| **Auth** | `GEMINI_API_KEY` or `GOOGLE_API_KEY` |
| **Response type** | `application/json` enforced via `response_mime_type` |
| **Temperature** | 0.2 |
| **Max output** | 16384 tokens |
| **Thinking** | Disabled (thinking_budget=0) to keep cost predictable |
| **Retries** | Up to 4, exponential backoff, rate-limit aware |

### Stub provider (offline/deterministic)

Keyword-rule based for tests and environments without API keys. Each task (`extract`, `taxonomy`, `assign`, `describe`) returns deterministic JSON matching the real provider's schema.

---

## 7. REST API Endpoints (`main.py`)

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Health check |
| `/config` | GET | Reference data (sources, departments, roles) |
| `/ingestion/connectors/{key}` | POST | Trigger connector import |
| `/ingestion/runs` | GET | Recent ingestion runs |
| `/ingestion/source-status` | GET | Source status with latest run info |
| `/reviews` | GET | Paginated/filtered reviews |
| `/analysis/semantic-clusters` | GET | Semantic similarity clusters |
| `/analysis/reanalyze` | POST | Re-run NLP on all reviews |
| `/issues` | GET | Paginated/filtered active/resolved/recurred issues |
| `/issues/emerging` | GET | Single-review emerging candidates |
| `/issues/detect` | POST | Run LLM issue detection pipeline |
| `/issues/{id}` | GET | Issue detail with review links and event history |
| `/issues/{id}` | PATCH | Update assignee/priority |
| `/issues/{id}/resolve` | PATCH | Resolve issue |
| `/overview/kpis` | GET | Dashboard KPI aggregates |
| `/overview/action-analytics` | GET | Dashboard action metrics |

### Request schemas

- **`ConnectorImportRequest`**: optional `fixture_path` (string) for bypassing connector's embedded records with an external JSON file.
- **`IssueUpdateRequest`**: optional `assignee_name` and `priority` fields. Each change generates an `IssueEvent` audit trail entry.

### Common query parameters

Most endpoints accept filter params: `source_code`, `department_code`, `sentiment_label`, `reputation_risk`, `risk_group` (high_or_critical), `date_from`, `date_to`.

Issues endpoint accepts: `status`, `department_code`, `priority`, `assignee`, `min_risk`.

Reviews endpoint additionally accepts: `search` (full-text across body/title/name/id), `has_issues`, `order_by` (review_date or operational_priority).

---

## 8. Frontend Architecture

### Tech stack

| Layer | Technology |
|---|---|
| Framework | Next.js 15 (App Router) |
| UI Library | React 18 |
| Language | TypeScript 5 (strict) |
| Styling | Tailwind CSS v4 |
| Component library | shadcn/ui (base-nova style) |
| Charts | Recharts |
| Icons | lucide-react |
| Theme | next-themes (light/dark/system) |
| Drag & drop | @dnd-kit |
| Data table | @tanstack/react-table |
| Drawer | vaul |
| Build output | `output: "standalone"` for Docker |
| PostCSS | `@tailwindcss/postcss` plugin via `postcss.config.mjs` |
| shadcn config | `components.json`: style `base-nova`, RSC enabled, `baseColor: "neutral"`, CSS variables enabled, icon library `lucide` |
| Dockerfile | Multi-stage (`deps` → `builder` → `runner`), `node:20-alpine`, copies `.next/standalone` |

### Pages

#### `/dashboard` (Overview)
- **KPI cards**: active issues, high-risk issues, total reviews, avg risk score, untracked risk
- **Donut charts**: sentiment mix, risk level distribution
- **Bar charts**: department issues, priority distribution
- **Owner pressure**: grouped bar chart — active + high-risk issues per department
- **Platform risk**: horizontal bars with platform logos (Google, Booking, TripAdvisor)
- **Recent issues**: last 5 updated issues with status/risk badges
- **Drill-through**: every chart is clickable → navigates to /reviews or /issues with URL filters

#### `/reviews` (Reviews Table)
- Sortable, paginated table with columns: date, platform (with logo), rating, sentiment badge, risk badge, department, issue links, review title/body (truncated)
- Filter bar: search, dates, platform, department, sentiment, risk, has-issues, risk-group
- Display redaction: emails and phone numbers replaced with `[redacted email]` / `[redacted phone]`

#### `/issues` (Issues Management)
- **Active Issues tab**: table with issue title, department, status, priority, risk score, recurrence count, last seen, assignee
- **Emerging tab**: cards showing single-review candidates with representative snippets
- **Detail sheet**: slide-over panel with issue metadata, keywords, description, linked reviews (with evidence snippets + source attribution), event history
- **Resolve workflow**: button to mark issue resolved
- Filters: status, department, priority, min risk score

### Styling & theming

- **`globals.css`**: Tailwind v4 with `@import "tailwindcss"`, `@import "tw-animate-css"`, `@import "shadcn/tailwind.css"`.
- **Kingsbury brand palette**: Deep antique gold/bronze primary (`oklch(0.47 0.085 72)`) over warm charcoal + ivory neutrals. Dark mode inverts the palette. Platform brand colors for Google, Booking, TripAdvisor as CSS variables (`--platform-google`, `--platform-booking`, `--platform-tripadvisor`).
- **Animations**: `card-enter` (opacity + translateY) and `fade-in` keyframes, respects `prefers-reduced-motion: reduce`.
- **Theme toggling**: `ThemeProvider` wraps `next-themes` with `attribute="class"`, `defaultTheme="system"`, `enableSystem`, `disableTransitionOnChange`.
- **Fonts**: Inter (sans) via `next/font/google` with CSS variable `--font-inter`. JetBrains Mono (mono) via `--font-jetbrains`.

### Component hierarchy

```
RootLayout
  └── ThemeProvider (next-themes, attribute="class")
       └── AppProviders (DemoRoleProvider)
            └── SidebarProvider
                 ├── AppSidebar (Kingsbury logo, nav items, user dropdown)
                 ├── SiteHeader (role selector, department selector, theme toggle)
                 └── <Page Content>
                      ├── DashboardFilterBar (shared filter controls)
                      └── Page-specific content
```

### State management

- **DemoRoleProvider** (`use-demo-role.tsx`): React context for demo role/permission switching
- **useDashboardFilters**: URL search-param-based filter state
- **useCountUp**: animated number transitions for KPI cards
- **Platform meta** (`platform-meta.ts`): logo URLs and brand colors for Google, Booking, TripAdvisor

### API types (`lib/api-types.ts`)

TypeScript interfaces mirroring all Pydantic response models. Key types: `Review`, `ReviewAnalysis`, `DetectedIssue`, `IssueReviewLink`, `IssueEvent`, `OverviewKpi`, `OverviewActionAnalytics`, `DashboardDrillThrough`.

---

## 9. Fixture Generation (`connector_fixture_generator.py`)

**Input:** 16 scenario types (ac_not_cooling, slow_checkin, noise, breakfast_quality, housekeeping_dirty, plumbing, broken_fixture, wifi, billing_dispute, rude_staff, ac_smell, pest_in_food, bedbugs, theft, safety_alarm, dirty_pool) plus 5 positive templates  
**Model:** Local Ollama (`llama3.1` or configurable)  
**Output:** JSON arrays of platform-shaped payloads for Google, Booking.com, and TripAdvisor

Key rules:
- No precomputed analysis fields (NLP must compute fresh)
- Validates generated payloads are valid JSON per platform shape
- `DEFAULT_TOTAL_REVIEWS = 2000` per run
- Output goes to `data/generated-fixtures/connectors-{name}/`

---

## 10. Redaction System (`redaction.py`)

Two PII patterns are redacted from display fields:
- **Email addresses** → `[redacted email]` (pattern: `r"(?<![\w.%+-])[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}(?![\w.-])"`)
- **Phone numbers** → `[redacted phone]` (pattern: `r"(?<!\w)(?:\+?\d[\d\s().-]{6,}\d)(?!\w)"`)

The `redact_display_text()` function returns a `RedactedText(value, redacted, fields)` dataclass. Applied via `NormalizedReview.display_*` properties:
- `display_body`, `display_title`, `display_reviewer_name`, `display_external_review_id`
- `has_display_redactions` → bool whether any field was redacted
- `redacted_display_fields` → list of field names that contain PII (`["reviewer_name", "body", ...]`)

The `IssueReviewLink` model also exposes `review_body` via `display_body` (through its relationship to `NormalizedReview`), ensuring evidence snippets shown in the issue detail sheet are redacted too.

---

## 11. Testing

### API tests (`apps/api/tests/`)

| File | Contents |
|---|---|
| `test_smoke.py` | Basic route count, department label validation |
| `test_issue_detection.py` | Integration tests against PostgreSQL test DB using stub LLM |

Key issue detection test scenarios:
- Synonymous AC complaints → consolidate into 1 issue
- Pest incident → stays separate from AC issue (materially distinct)
- Single review → emerging status
- Resolved state → preserved across full rebuild

### CI/CD (`.github/workflows/pr-checks.yml`)

Runs on PR to `main`:
1. PostgreSQL test database (Docker service)
2. Node.js setup + `npm ci`
3. Web lint (`npm run lint`)
4. Web build (`npm run build`)
5. Python virtualenv + API tests

---

## 12. DevOps & Docker

### Local development (`docker-compose.yaml`)

```yaml
services:
  postgres:          # 16-alpine, port 5432
  postgres_test:     # 16-alpine, port 5433
  api:               # builds apps/api, port 8000
  web:               # builds apps/web, port 3000
```

### Production (`docker-compose.prod.yaml`)

Uses prebuilt images (`API_IMAGE`, `WEB_IMAGE`). Requires `POSTGRES_PASSWORD`.

### Data snapshots

A committed `pg_dump` snapshot at `data/db-snapshots/guest_reviews_20260609.sql.gz` for quick restore without running ingestion.

---

## 13. Bootstrap & Demo Workflow

1. `docker compose up -d postgres` — start database
2. `npm run api:migrate` — run Alembic migrations
3. `npm run api:seed` — insert reference config (sources, departments, roles)
4. `npm run api:demo` — run `demo_pipeline.py` which ingests 8 seed reviews via `run_seed_ingestion()` and runs issue detection
5. `docker compose up -d api web` — start full stack
6. Open `http://localhost:3000` — interactive dashboard

Alternative: `docker compose up -d` (starts everything, then migrate + seed inside containers).

For full fixture datasets: `npm run api:import:all` (wipes data, imports dolphin/llama/real fixtures, runs detection).

For fixture generation: `npm run api:generate:all` (generates dolphin + llama fixture sets via local Ollama) → `npm run api:import:all` (wipes data, imports all platforms, runs detection).

---

## 14. Key Design Decisions

| Decision | Rationale |
|---|---|
| **Batch issue rebuild** (not incremental) | Ensures consistency; manual state preserved via cluster_key |
| **Three-pass LLM pipeline** | Separates extraction, taxonomy discovery, and assembly → keeps each prompt focused and under token limits |
| **Stub LLM provider** | Enables deterministic testing and offline demo without API keys |
| **Three-tier embedding fallback** | sentence-transformers → TF-IDF → token overlap ensures semantic analysis never hard-fails |
| **Content-hash dedup** | Normalized content hash detects near-duplicate reviews across platforms |
| **Redaction at the model property layer** | PII redacted at display time (not storage) so raw data is preserved for analysis |
| **No queue/worker** | MVP scope; synchronous ingestion is adequate for prototype scale |
| **Recharts for charts** | Lightweight, composable, good React integration for dashboard use cases |

# Demo Script

## Goal

This script demonstrates the complete MVP path:

1. start the stack;
2. migrate and seed reference configuration;
3. explain source-policy boundaries;
4. generate or import connector-shaped review fixtures;
5. inspect reviews, search, redaction, and analysis outputs;
6. trigger LLM-driven issue detection;
7. review discovered issues and emerging candidates;
8. resolve an issue and inspect event history.

The script uses local/demo data only.

## Prerequisites

- Node.js 20 or newer.
- Python 3.12 or compatible Python 3.
- Docker and Docker Compose.
- API available at `http://localhost:8000`.
- Web available at `http://localhost:3000`.
- Required local Hugging Face model artifacts provisioned for the API runtime.

Optional shell helper:

```bash
API=http://localhost:8000
```

Recommended repo verification commands before the walkthrough:

```bash
npm run api:test
npm run lint:web
npm run build:web
```

## Source Policy Framing

Set expectations before clicking through the product:

- the MVP exposes only Google Business Profile, Booking.com, and Tripadvisor review platforms;
- connectors are official-shaped demo connectors, not live Kingsbury integrations;
- demo reviews may be generated outside the product with local Ollama and imported as connector-shaped fixture files;
- local Ollama is not called by the product runtime;
- the system does not delete, hide, suppress, or manipulate platform reviews.

Explain the reputation-risk problem:

- hotels generally cannot directly delete unfavorable reviews from major platforms;
- they can respond or request platform review only when content violates policy;
- the product helps detect risky and recurring operational problems early so the hotel can fix root causes before similar negative reviews keep appearing.

## 1. Start the Stack

```bash
docker compose up --build
```

Open:

- web: http://localhost:3000
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health

Expected health response:

```json
{"status":"ok","service":"api"}
```

## 2. Migrate and Seed Reference Data

In a second terminal:

```bash
npm run api:migrate
npm run api:seed
```

Confirm configuration:

```bash
curl "$API/config"
```

What to show:

- review sources are Google Business Profile, Booking.com, and Tripadvisor only;
- departments are seeded with risk weights and service levels;
- demo roles are visible (admin, operations_manager, department_head, analyst).

## 3. Generate Connector Fixtures

For a full demo dataset:

```bash
npm run api:generate:all
```

For a fast smoke dataset:

```bash
cd apps/api
.venv/bin/python scripts/generate_connector_fixtures.py \
  --total-reviews 9 \
  --output-dir /tmp/kingsbury-connector-fixtures
```

What to explain:

- fixture generation is outside the product boundary;
- generated files are provider-shaped platform payloads (GBP, Booking.com, TripAdvisor);
- generated fixtures intentionally contain repeated issue waves;
- fixtures must not contain precomputed sentiment, department, or Reputation Risk labels.

## 4. Import Review Data Through Connectors

Built-in connector records (minimal sample):

```bash
curl -X POST "$API/ingestion/connectors/google_business_profile"
curl -X POST "$API/ingestion/connectors/booking_com"
curl -X POST "$API/ingestion/connectors/tripadvisor"
```

Fixture-file import:

```bash
curl -X POST "$API/ingestion/connectors/google_business_profile" \
  -H "Content-Type: application/json" \
  -d '{"fixture_path":"apps/api/data/generated-fixtures/connectors-dolphin/google_business_profile.json"}'
```

Import all fixtures (wipes data first):

```bash
npm run api:import:all
```

Inspect run history:

```bash
curl "$API/ingestion/runs"
curl "$API/ingestion/source-status"
```

What to show:

- status;
- records seen/created/updated/skipped;
- duplicate flags;
- error counts;
- analysis runs immediately after successful review ingestion.

## 5. Inspect Reviews and Analysis

Default reviews (latest 25, one-year rolling date window):

```bash
curl "$API/reviews"
```

Filter examples:

```bash
curl "$API/reviews?sentiment_label=negative"
curl "$API/reviews?reputation_risk=high"
curl "$API/reviews?department_code=engineering"
curl "$API/reviews?search=check-in&department_code=front_office"
curl "$API/reviews?risk_group=high_or_critical"
curl "$API/reviews?has_issues=true"
```

What to show:

- normalized source platform fields;
- platform attribution (Google / Booking.com / TripAdvisor);
- display-safe review fields with email/phone redaction metadata;
- active analysis: sentiment label and score, department, Reputation Risk label and score;
- issue link badges when reviews are linked to detected issues.

In the web UI, open Reviews and:

- search for `check-in`;
- filter by platform, department, sentiment, or Reputation Risk;
- toggle the "has issues" filter.

## 6. Trigger Issue Detection

```bash
curl -X POST "$API/ingestion/connectors/google_business_profile" \
  -H "Content-Type: application/json" \
  -d '{"fixture_path":"apps/api/data/generated-fixtures/connectors-dolphin/google_business_profile.json"}'

curl -X POST "http://localhost:8000/issues/detect?force=true"
```

Or quickly with seed reviews:

```bash
npm run api:demo
```

What to explain:

- detection uses an LLM (Gemini by default, or `LLM_PROVIDER=stub` for offline);
- three passes: extract problems → consolidate taxonomy → assemble issues;
- issues with ≥2 supporting reviews become active; single-review issues are emerging candidates.

## 7. Review Discovered Issues

Active issues:

```bash
curl "$API/issues"
```

Filtered:

```bash
curl "$API/issues?status=active&department_code=engineering"
curl "$API/issues?priority=high"
curl "$API/issues?min_risk=50"
```

Emerging candidates (single-review, high-risk only by default):

```bash
curl "$API/issues/emerging"
curl "$API/issues/emerging?all=true"
```

Issue detail with linked reviews and event history:

```bash
curl "$API/issues/1"
```

What to show:

- issue title and LLM-generated description with concrete specifics;
- department, status, priority, risk score, recurrence count;
- keywords extracted from evidence;
- linked reviews with evidence snippets, platform attribution, and triggering-evidence flags;
- event history (created, priority_changed, etc.);
- state preservation across detection rebuilds (resolved issues stay resolved).

In the web UI, open Issues:

- switch between Active Issues and Emerging tabs;
- click an issue row to open the detail sheet with linked reviews and event history.

## 8. Manage Issue Lifecycle

Update issue assignee and priority:

```bash
curl -X PATCH "$API/issues/1" \
  -H "Content-Type: application/json" \
  -d '{"assignee_name": "Engineering Manager", "priority": "high"}'
```

Resolve an issue:

```bash
curl -X PATCH "$API/issues/1/resolve"
```

Verify the event was recorded:

```bash
curl "$API/issues/1"
```

What to show:

- issue events: `created`, `assignee_changed`, `priority_changed`, `resolved`;
- old/new values;
- notes and timestamps.

In the web UI, open an issue detail sheet and:

- click "Mark Resolved" to resolve it;
- observe the status change and event history update.

## 9. Overview KPIs and Dashboard

```bash
curl "$API/overview/kpis"
curl "$API/overview/action-analytics"
```

Filter examples:

```bash
curl "$API/overview/kpis?source_code=google_business_profile"
curl "$API/overview/kpis?department_code=engineering"
```

What to explain:

- KPIs are scoped to the three MVP review platforms;
- action analytics provide owner pressure, platform risk, action leakage, and recent issues;
- drill-through paths are included for UI navigation.

In the web UI, open Dashboard (Overview) and:

- apply date/platform/department/risk filters through the filter bar;
- observe KPI cards, donut charts (sentiment/risk), bar charts (department/priority);
- see owner pressure by department and platform risk spread;
- click charts to drill through to filtered Reviews/Issues views.

## 10. Semantic Clusters (Optional)

```bash
curl "$API/analysis/semantic-clusters"
curl "$API/analysis/semantic-clusters?similarity_threshold=0.30&min_cluster_size=2"
```

What to show:

- embedding strategy used (sentence-transformer, TF-IDF fallback, or token overlap);
- near-duplicate pairs and semantic clusters;
- cluster representative text, department, source mix, and average similarity.

## 11. Reanalysis

```bash
curl -X POST "$API/analysis/reanalyze"
curl -X POST "$API/analysis/reanalyze?source_code=google_business_profile"
```

What to show:

- `analyzed_count`;
- updated analysis metadata in persisted records;
- dashboard values remain filterable after reanalysis.

## Assessment Talking Points

- The source policy is explicit: only review-platform connectors are in the MVP.
- The same connector import can be shown through API routes or backend job commands.
- Demo fixture generation is outside the product runtime.
- Raw payloads are preserved for audit, while normalized reviews power dashboards and issue detection.
- NLP outputs are real model-backed outputs, not pre-baked fixture labels.
- Reputation Risk is the single user-facing risk metric.
- LLM-driven issue detection consolidates synonymous complaints across reviews into actionable issues.
- Emerging candidates provide early warning for single-review problems.
- Issue lifecycle records event history through creation, assignment, and resolution.
- The stack is reproducible with Docker Compose, migrations, seed data, and local model artifacts.

# Demo Script

## Goal

This script demonstrates the complete MVP path:

1. start the stack;
2. migrate and seed reference configuration;
3. explain source-policy boundaries and review-removal constraints;
4. generate or import connector-shaped review fixtures;
5. inspect reviews, search, redaction, and analysis outputs;
6. discover recurring Reputation Risk issues;
7. create action tickets manually;
8. update, resolve, and verify tickets.

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
- departments are seeded;
- issue categories are seeded;
- category-to-department mappings are visible;
- Reputation Risk thresholds and demo roles are visible.

## 3. Generate Connector Fixtures

For a full demo dataset:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py
```

For a fast smoke dataset:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 9 \
  --output-dir /tmp/kingsbury-connector-fixtures
```

What to explain:

- fixture generation is outside the product boundary;
- generated files are provider-shaped platform payloads;
- generated fixtures intentionally contain repeated issue waves;
- fixtures must not contain precomputed sentiment, category, department, or Reputation Risk labels.

## 4. Import Review Data Through Connectors

Built-in connector records:

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

Equivalent backend job commands:

```bash
cd apps/api
python3 -m app.jobs connector google_business_profile
python3 -m app.jobs connector booking_com
python3 -m app.jobs connector tripadvisor
python3 -m app.jobs connector google_business_profile --fixture-path data/generated-fixtures/connectors-dolphin/google_business_profile.json
```

Inspect run history:

```bash
curl "$API/ingestion/runs"
curl "$API/ingestion/source-status"
```

What to show:

- status;
- records seen/created/skipped;
- duplicate flags;
- row-level errors if any;
- analysis runs immediately after successful review ingestion.

## 5. Inspect Reviews and Analysis

Default reviews:

```bash
curl "$API/reviews"
```

Filter examples:

```bash
curl "$API/reviews?sentiment_label=negative"
curl "$API/reviews?reputation_risk=high"
curl "$API/reviews?issue_category_code=cleanliness"
curl "$API/reviews?department_code=housekeeping"
curl "$API/reviews?search=check-in&department_code=front_office"
```

What to show:

- normalized source platform fields;
- search works through the shared filter bar in the web UI and through the `search` API query parameter;
- display-safe review fields, including email/phone redaction metadata when applicable;
- active analysis;
- sentiment label and score;
- issue category predictions;
- Reputation Risk label and score;
- department ownership;
- operational explanation factors.

In the web UI, open Reviews and:

- search for `check-in`;
- filter by platform, department, category, or Reputation Risk;
- create a ticket manually from a high-risk review.

## 6. Overview KPIs

```bash
curl "$API/overview/kpis"
```

Filter examples:

```bash
curl "$API/overview/kpis?source_code=google_business_profile"
curl "$API/overview/kpis?issue_category_code=booking_checkin"
curl "$API/overview/kpis?department_code=front_office"
```

What to explain:

- KPIs are scoped to the three MVP review platforms;
- API returns dashboard-ready aggregates;
- Reputation Risk is the only risk/severity concept shown to staff.

In the web UI, open Overview and apply the same filters through the filter bar.

## 7. Discover Recurring Issues

Category/department recurrence summary:

```bash
curl "$API/issues/summary"
```

Semantic clusters:

```bash
curl "$API/analysis/semantic-clusters?similarity_threshold=0.30"
```

What to show:

- repeated issue categories by count;
- average and highest Reputation Risk;
- primary department;
- source platform mix;
- representative review IDs;
- semantic near-duplicate pairs and clusters where useful.

In the web UI, open Issues and show category/department rows. Create a ticket manually from a recurring issue group.

## 8. Create Tickets

### From a Single Review

Pick a review ID from `/reviews`, then:

```bash
curl -X POST "$API/reviews/1/tickets" \
  -H "Content-Type: application/json" \
  -d '{
    "department_code": "housekeeping",
    "priority": "high",
    "assignee_name": "Housekeeping Manager",
    "notes": "Investigate repeated cleanliness complaint."
  }'
```

### From a Recurring Issue Group

Pick a category/department pair from `/issues/summary`, then:

```bash
curl -X POST "$API/issues/groups/cleanliness/housekeeping/tickets" \
  -H "Content-Type: application/json" \
  -d '{
    "priority": "high",
    "notes": "Created from recurring cleanliness complaints."
  }'
```

### From a Semantic Cluster

Pick a cluster ID from `/analysis/semantic-clusters`, then:

```bash
curl -X POST "$API/analysis/semantic-clusters/semantic-1/tickets?similarity_threshold=0.30" \
  -H "Content-Type: application/json" \
  -d '{
    "priority": "urgent",
    "notes": "Created from semantically similar repeated complaints."
  }'
```

What to show:

- created ticket;
- source review IDs for recurring issue tickets;
- department ownership;
- initial `created` event;
- source reviews marked `ticket_created`;
- ticket priority defaulting from Reputation Risk when priority is omitted.

## 9. Update, Resolve, and Verify Tickets

List tickets:

```bash
curl "$API/tickets"
```

Get one ticket:

```bash
curl "$API/tickets/1"
```

Move to in progress:

```bash
curl -X PATCH "$API/tickets/1" \
  -H "Content-Type: application/json" \
  -d '{"status":"in_progress","notes":"Department manager accepted the ticket."}'
```

Resolve:

```bash
curl -X PATCH "$API/tickets/1" \
  -H "Content-Type: application/json" \
  -d '{"status":"resolved","notes":"Corrective action completed by the owning department."}'
```

Verify:

```bash
curl -X PATCH "$API/tickets/1" \
  -H "Content-Type: application/json" \
  -d '{"status":"verified","notes":"Management verified the resolution."}'
```

What to show:

- ticket status changes;
- `ticket_events` history;
- old/new values;
- notes and timestamps.

In the web UI, open Tickets and click a ticket row to show the event history sheet. Use the ticket detail controls to change status, priority, department, assignee, due date, and notes.

## 10. Reanalysis

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
- Raw payloads are preserved for audit, while normalized reviews power dashboards and tickets.
- NLP outputs are real model-backed outputs, not pre-baked fixture labels.
- Reputation Risk is the single user-facing risk metric.
- Recurring issue detection supports the claim that the hotel can act before patterns keep damaging future guest perception.
- Ticket workflow records event history through creation, updates, resolution, and verification.
- The stack is reproducible with Docker Compose, migrations, seed data, current repo verification commands, and local model artifacts.

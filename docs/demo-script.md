# Demo Script

## Goal

This script demonstrates the complete prototype path:

1. start the stack;
2. migrate and seed reference configuration;
3. import review data;
4. inspect analysis outputs;
5. discover recurring issues;
6. create action tickets;
7. update, resolve, and verify tickets;
8. run issue-classifier evaluation.

The script uses local/demo data only.

## Prerequisites

- Node.js 20 or newer.
- Python 3.12 or compatible Python 3.
- Docker and Docker Compose.
- API available at `http://localhost:8000`.
- Web available at `http://localhost:3000`.

Optional shell helper:

```bash
API=http://localhost:8000
```

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

- review sources include verified review, social listening, seed dataset, and Apify dataset import types;
- departments are seeded;
- issue categories are seeded;
- category-to-department mappings are visible;
- severity thresholds and demo roles are visible.

## 3. Import Demo Reviews

### Seed Dataset

```bash
curl -X POST "$API/ingestion/seed"
```

Expected behavior:

- first run creates seed reviews;
- repeated run skips already imported records;
- ingestion run counts are recorded.

### Verified Official-Shaped Mock Connectors

```bash
curl -X POST "$API/ingestion/connectors/google_business_profile"
curl -X POST "$API/ingestion/connectors/booking_com"
curl -X POST "$API/ingestion/connectors/tripadvisor"
```

What to explain:

- these are official-shaped mock connectors;
- they prove connector normalization without live platform credentials.

### Social Listening

```bash
curl -X POST "$API/ingestion/reddit"
```

What to explain:

- Reddit records are social listening, not verified guest reviews;
- they are excluded from default KPIs unless explicitly included.

### Inspect Run History

```bash
curl "$API/ingestion/runs"
curl "$API/ingestion/source-status"
```

What to show:

- status;
- records seen/created/skipped;
- duplicate flags;
- row-level errors if any.

## 4. Inspect Reviews and Analysis

Default reviews:

```bash
curl "$API/reviews"
```

Include social listening:

```bash
curl "$API/reviews?include_social_listening=true"
```

Filter examples:

```bash
curl "$API/reviews?sentiment_label=negative"
curl "$API/reviews?severity=high"
curl "$API/reviews?issue_category_code=cleanliness"
curl "$API/reviews?department_code=housekeeping"
curl "$API/reviews?search=check-in&department_code=front_office"
```

What to show:

- normalized source fields;
- display-safe review fields, including email/phone redaction metadata when applicable;
- active analysis;
- sentiment label and score;
- issue category predictions;
- severity label and score;
- department ownership;
- model metadata and explanation factors.

## 5. Overview KPIs and Source Rules

Default verified-review KPIs:

```bash
curl "$API/overview/kpis"
```

Explicitly include social listening:

```bash
curl "$API/overview/kpis?include_social_listening=true"
```

Filter examples:

```bash
curl "$API/overview/kpis?source_code=reddit_social_listening"
curl "$API/overview/kpis?issue_category_code=booking_checkin"
curl "$API/overview/kpis?department_code=front_office"
```

What to explain:

- default KPIs exclude social-listening records;
- source selection or inclusion flag makes social-listening records explicit;
- API returns dashboard-ready aggregates.

In the web UI, open Overview and apply the same filters through the filter bar.

## 6. Discover Recurring Issues

Category recurrence summary:

```bash
curl "$API/issues/summary"
```

Semantic clusters:

```bash
curl "$API/analysis/semantic-clusters?similarity_threshold=0.30"
```

What to show:

- repeated issue categories by count;
- average severity score;
- primary department;
- source mix;
- semantic near-duplicate pairs and clusters;
- representative review text and review IDs.

In the web UI, open Issues and show category rows plus semantic cluster cards.

## 7. Create Tickets

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

### From a Category Recurrence

Pick a category from `/issues/summary`, then:

```bash
curl -X POST "$API/issues/categories/cleanliness/tickets" \
  -H "Content-Type: application/json" \
  -d '{
    "priority": "high",
    "notes": "Created from recurring cleanliness complaints."
  }'
```

The API defaults department ownership to the dominant affected department unless `department_code` is provided.

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
- source reviews marked `ticket_created`.

## 8. Update, Resolve, and Verify Tickets

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

Add a resolution note:

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

In the web UI, open Tickets and click a ticket row to show the event history sheet.
Use the ticket detail controls to change status, priority, department, assignee, due date, and notes; the event history refreshes after saving.

## 8a. Offline Apify Import from the Web UI

Open Ingestion and use the Offline Apify import form.

Supported inputs:

- paste JSON or CSV export content and provide a matching file name;
- provide a server-accessible `.json` or `.csv` file path.

Malformed rows are recorded as import errors, and missing or unsupported input shows a failed import result without implying live Apify API access.

## 9. Run Offline Classifier Evaluation

Create a Python environment if needed:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Validate sample labels:

```bash
python -m app.ml.issue_classifier validate data/examples/issue_labels_sample.csv
```

Train and evaluate:

```bash
python -m app.ml.issue_classifier train-evaluate \
  data/examples/issue_labels_sample.csv \
  --model-output artifacts/ml/issue_classifier.pkl \
  --report-output reports/ml/issue_classifier_evaluation.json
```

What to show:

- dataset row count;
- train/test count;
- label counts;
- trained model macro F1;
- keyword baseline macro F1;
- per-class metrics;
- confusion matrix.

Explain that manual labels are research/evaluation infrastructure and not part of hotel operations.

## 10. Reanalysis After Model Change

After training or changing model settings:

```bash
curl -X POST "$API/analysis/reanalyze"
```

Optional:

```bash
curl -X POST "$API/analysis/reanalyze?source_type=verified_review"
curl -X POST "$API/analysis/reanalyze?source_code=google_business_profile"
```

What to show:

- `analyzed_count`;
- updated model metadata in review analysis;
- dashboard values remain filterable after reanalysis.

## Assessment Talking Points

- The source policy is explicit: mock official connectors are separate from social listening and Apify dataset import.
- Default KPIs protect verified-review analysis by excluding social listening.
- Raw payloads are preserved for audit, while normalized reviews power dashboards and tickets.
- NLP outputs are explainable through model metadata and explanation factors.
- Recurring issue detection works by category counts and semantic clusters.
- Ticket workflow records event history through creation, updates, resolution, and verification.
- The stack is reproducible with Docker Compose, migrations, seed data, and local evaluation scripts.

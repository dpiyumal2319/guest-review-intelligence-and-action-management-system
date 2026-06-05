# Guest Review Intelligence

Guest Review Intelligence is a local-first demo system for importing hotel review fixtures, running NLP analysis, and working through review, issue, and ticket management screens.

This README is the team handbook for running the system end to end.

## 1. What You Are Running

The system has three parts:

- PostgreSQL, always run in Docker
- FastAPI backend, run either locally or in Docker
- Next.js frontend, run either locally or in Docker

The default and recommended workflow is:

- run PostgreSQL in Docker
- run API locally
- run web locally
- ingest from the pregenerated pushed llama fixture files

The pregenerated fixture sets committed in this repo are:

- `apps/api/data/generated-fixtures/connectors`
  This is the pregenerated dolphin dataset.
- `apps/api/data/generated-fixtures/connectors-llama`
  This is the pregenerated llama dataset.

Important:

- the database is expected to be in Docker in all normal team workflows
- the llama fixture set is namespaced so it does not overwrite the dolphin fixture set
- use the fixture identity validator before imports if you change fixture files

## 2. Prerequisites

Install these on your machine:

- Docker and Docker Compose
- Python 3.12 or newer
- Node.js 20 or newer

Optional but useful:

- `psql`
- `curl`
- `jq`

## 3. Happy Path: Run with Docker DB and Local API/Web

### 3.1 Start PostgreSQL in Docker

From repo root:

```bash
docker compose up -d postgres
docker compose ps
```

Expected:

- the `postgres` service is `Up`
- port `5432` is exposed on localhost

### 3.2 Install API dependencies

From repo root:

```bash
npm run api:install
npm run api:install:nlp
```

This creates `apps/api/.venv`.

### 3.3 Run database migrations and seed reference config

From repo root:

```bash
npm run api:migrate
npm run api:seed
```

This seeds:

- review sources
- departments
- issue categories
- routing config
- demo roles

### 3.4 Start the API locally

From repo root:

```bash
cd apps/api
source .venv/bin/activate
python3 -m uvicorn app.main:app --reload
```

API endpoints:

- health: `http://localhost:8000/health`
- docs: `http://localhost:8000/docs`

### 3.5 Start the web app locally

In another terminal from repo root:

```bash
npm --prefix apps/web install
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 npm --prefix apps/web run dev
```

Web:

- `http://localhost:3000`

## 4. Happy Path: Ingest the Pregenerated Llama Fixture Files

This is the primary demo path for teammates.

### 4.1 Validate fixture identities before importing

From repo root:

```bash
python3 apps/api/scripts/validate_fixture_identity.py \
  apps/api/data/generated-fixtures/connectors \
  apps/api/data/generated-fixtures/connectors-llama
```

Expected:

```text
validated 2 fixture directories without identity collisions
```

### 4.2 Import the pregenerated llama files

From `apps/api`:

```bash
source .venv/bin/activate
python3 -m app.jobs connector google_business_profile --fixture-path ./data/generated-fixtures/connectors-llama/google_business_profile.json
python3 -m app.jobs connector booking_com --fixture-path ./data/generated-fixtures/connectors-llama/booking_com.json
python3 -m app.jobs connector tripadvisor --fixture-path ./data/generated-fixtures/connectors-llama/tripadvisor.json
```

Expected result:

- each command completes with `created` rows
- no `updated` rows on a fresh database

### 4.3 Verify the data loaded

From repo root:

```bash
psql 'postgresql://guest_reviews:guest_reviews@localhost:5432/guest_reviews' -c \
"SELECT source_code, count(*) FROM normalized_reviews GROUP BY source_code ORDER BY source_code;"
```

If you import only llama, expected counts are:

- `google_business_profile = 334`
- `booking_com = 333`
- `tripadvisor = 333`

Total:

- `1000` reviews

## 5. Optional: Load Both Dolphin and Llama for a 2,000 Review Database

If you want the larger combined demo dataset:

### 5.1 Reset demo data first

From `apps/api`:

```bash
source .venv/bin/activate
python3 scripts/wipe_demo_data.py
```

This wipes only demo operational data:

- ticket events
- tickets
- review analyses
- review predictions
- normalized reviews
- raw reviews
- ingestion runs

It does not wipe reference configuration.

### 5.2 Import dolphin fixtures

```bash
python3 -m app.jobs connector google_business_profile --fixture-path ./data/generated-fixtures/connectors/google_business_profile.json
python3 -m app.jobs connector booking_com --fixture-path ./data/generated-fixtures/connectors/booking_com.json
python3 -m app.jobs connector tripadvisor --fixture-path ./data/generated-fixtures/connectors/tripadvisor.json
```

### 5.3 Import llama fixtures

```bash
python3 -m app.jobs connector google_business_profile --fixture-path ./data/generated-fixtures/connectors-llama/google_business_profile.json
python3 -m app.jobs connector booking_com --fixture-path ./data/generated-fixtures/connectors-llama/booking_com.json
python3 -m app.jobs connector tripadvisor --fixture-path ./data/generated-fixtures/connectors-llama/tripadvisor.json
```

### 5.4 Verify final counts

```bash
psql 'postgresql://guest_reviews:guest_reviews@localhost:5432/guest_reviews' -c \
"SELECT source_code, count(*) FROM normalized_reviews GROUP BY source_code ORDER BY source_code;"
```

Expected counts:

- `google_business_profile = 668`
- `booking_com = 666`
- `tripadvisor = 666`

Total:

- `2000` reviews

## 6. How to Use the UI After Import

Open `http://localhost:3000`.

Main routes:

- `/dashboard`
- `/reviews`
- `/issues`
- `/tickets`

Recommended demo flow:

1. Open Dashboard and confirm total review count.
2. Open Reviews and verify records are paginated.
3. Create a ticket from a review.
4. Open Issues and create a recurring issue ticket.
5. Open Tickets and update status, priority, assignee, and notes.

Notes about current behavior:

- default date window is the last year already encoded in the UI defaults
- pagination and filtering on Reviews are server-side
- topbar role selectors and ticket sheet selectors show human labels, not raw system codes

## 7. Full Docker Run

If you want to run the full stack in Docker:

```bash
docker compose up --build
```

Then run schema and reference setup from repo root:

```bash
npm run api:migrate
npm run api:seed
```

Endpoints:

- web: `http://localhost:3000`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

Important:

- even in this mode, the happy-path data load is still importing the pushed pregenerated fixture files

## 8. Validation and Troubleshooting

### Validate fixture identity

Use this whenever fixture files change:

```bash
python3 apps/api/scripts/validate_fixture_identity.py \
  apps/api/data/generated-fixtures/connectors \
  apps/api/data/generated-fixtures/connectors-llama
```

If this fails, two fixture sets share the same `(source_code, external_review_id)` after connector normalization.

### Wipe only demo data

```bash
cd apps/api
source .venv/bin/activate
python3 scripts/wipe_demo_data.py
```

### Check database counts directly

```bash
psql 'postgresql://guest_reviews:guest_reviews@localhost:5432/guest_reviews' <<'SQL'
SELECT source_code, count(*) AS reviews
FROM normalized_reviews
GROUP BY source_code
ORDER BY source_code;
SQL
```

### Common failure modes

`0 created, N updated`

- you imported a fixture set that collides with existing external review IDs
- run the fixture validator
- if you intended a fresh demo, wipe demo data first

`failed` ingestion run with model/runtime errors

- API NLP dependencies or model artifacts are missing
- rerun:

```bash
npm run api:install
npm run api:install:nlp
```

### Sanity-check the codebase

From repo root:

```bash
npm run api:test
npm run lint:web
npm run build:web
```

## 9. Secondary Workflow: Generate New Review Fixtures with Ollama

This is not the main teammate workflow. Use this only when you intentionally want new generated review corpora.

Ollama is used only for fixture generation outside the product runtime.

### 9.1 Check Ollama

```bash
ollama list
```

Examples:

- `dolphin-llama3:latest`
- `llama3.1:latest`

### 9.2 Generate a new dolphin dataset

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 1000 \
  --model dolphin-llama3:latest \
  --seed 202607 \
  --output-dir /tmp/guest-review-fixtures-dolphin
```

### 9.3 Generate a new llama dataset with namespaced IDs

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 1000 \
  --model llama3.1:latest \
  --seed 202607 \
  --id-namespace llama \
  --output-dir /tmp/guest-review-fixtures-llama
```

### 9.4 Validate before importing

```bash
python3 apps/api/scripts/validate_fixture_identity.py \
  /tmp/guest-review-fixtures-dolphin \
  /tmp/guest-review-fixtures-llama
```

### 9.5 Import generated datasets

Use the same connector import commands shown earlier, replacing the fixture paths.

## 10. Canonical Supporting Docs

Use this README as the runbook. Use the docs below for architecture and deeper implementation details:

- `docs/README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/nlp-pipeline.md`
- `docs/evaluation-source-policy.md`
- `docs/demo-script.md`
- `docs/research/connector-fixture-generation.md`

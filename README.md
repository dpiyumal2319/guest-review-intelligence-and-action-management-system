# Guest Review Intelligence

Guest Review Intelligence is a local-first demo system for importing hotel review fixtures, running NLP analysis, and surfacing concrete department-owned operational Issues discovered from review content.

This README is the team runbook for bootstrapping, running, and validating the system end to end.

## 1. What You Are Running

The system has three parts:

- PostgreSQL, normally run in Docker
- FastAPI backend, run either locally or in Docker
- Next.js frontend, run either locally or in Docker

The recommended local workflow is:

- run PostgreSQL in Docker
- run API locally from `apps/api/.venv`
- run web locally from `apps/web`
- import review fixtures or run the small demo pipeline
- trigger Issue detection from the API or demo script

The current product model is:

- Raw/normalized reviews are imported from connector-shaped payloads.
- Review analysis stores sentiment, department, reputation risk, and embeddings.
- Detected Issues are concrete operational problems such as `AC not cooling` or `Bathroom mold`, owned by departments.
- Tickets and category-based issue taxonomies have been removed from the runtime workflow.

## 2. Prerequisites

Install these on your machine:

- Docker and Docker Compose
- Python 3.12 or newer
- Node.js 20 or newer

All setup, import, and verification commands are npm scripts — you don't need
`psql`, `curl`, or `jq` to follow this runbook.

NLP model artifacts are loaded with `local_files_only=True`. The
`npm run api:download-models` step (see §3.2) downloads everything to
`~/.cache/huggingface/` automatically.

## 3. Bootstrap: Docker DB with Local API/Web

### 3.1 Start PostgreSQL

From repo root:

```bash
docker compose up -d postgres
docker compose ps
```

Expected:

- the `postgres` service is `Up`
- port `5432` is exposed on localhost

### 3.2 Install dependencies

From repo root:

```bash
npm ci
npm run api:install
npm run api:install:nlp
npm run api:download-models
```

This creates `apps/api/.venv`, installs API/NLP Python packages, and downloads Hugging Face model artifacts into the local cache so the app can load them with `local_files_only=True`.

The download step requires a working internet connection and downloads ~2 GB of model weights on first run. Models are cached in `~/.cache/huggingface/` for reuse.

For the web app, use root workspace installs only. Do not run `npm install` inside `apps/web`, because a nested `apps/web/node_modules` can shadow the hoisted `next` package and break builds.

### 3.3 Run migrations and seed reference data

From repo root:

```bash
npm run api:migrate
npm run api:seed
```

This creates the clean issue-detection schema and seeds:

- review sources
- departments with risk weights
- demo roles

No Issues are pre-seeded. Issues are created by analysis and detection.

### 3.4 Start the API locally

From repo root:

```bash
npm run dev:api
```

API endpoints:

- health: `http://localhost:8000/health`
- docs: `http://localhost:8000/docs`

### 3.5 Start the web app locally

In another terminal from repo root:

```bash
npm run dev:web
```

Web:

- `http://localhost:3000`

## 4. Demo Data and Issue Detection

### 4.1 Small live demo pipeline

Use this when you want a fast end-to-end proof that raw reviews become detected Issues:

```bash
npm run api:demo
```

The script:

1. imports the small seed review batch as raw connector-shaped data;
2. runs analysis during ingestion;
3. verifies the embedding model is available;
4. triggers dynamic Issue detection.

Expected result:

- seed reviews are imported;
- detection reports created/linked Issues;
- the Issues page shows active concrete problems.

### 4.2 Pregenerated fixture datasets

The pregenerated fixture sets committed in this repo are:

- `apps/api/data/generated-fixtures/connectors-dolphin` (generated with `dolphin-llama3:latest`)
- `apps/api/data/generated-fixtures/connectors-llama` (generated with `llama3.1:latest`)

Validate fixture identities before importing both sets:

```bash
npm run api:validate-fixtures
```

Expected:

```text
validated 2 fixture directories without identity collisions
```

Import the llama fixture set:

```bash
npm run api:import:llama
```

Then trigger detection:

```bash
npm run api:detect
```

### 4.3 Load both fixture sets

If you want the larger combined demo dataset:

```bash
npm run api:import:all
```

This wipes any existing demo data, imports all six connector sets (dolphin + llama), and triggers issue detection.

## 5. Verify Data

```bash
npm run api:verify
```

Example output:

```
=== Reviews by source ===
  booking_com: 666
  google_business_profile: 668
  tripadvisor: 666

=== Issues by department/status ===
  engineering (active): 13
  food_beverage (active): 20
  front_office (active): 48
  guest_relations (active): 72
  housekeeping (active): 71
  management (active): 15

=== Evidence links: 1385 ===
```

## 6. Main UI Routes

Open `http://localhost:3000`.

Main routes:

- `/dashboard`
- `/reviews`
- `/issues`

Recommended demo flow:

1. Open Dashboard and review active/recurred/high-risk Issue KPIs.
2. Open Reviews and inspect department, reputation risk, and linked Issue badges.
3. Use the unlinked-review filter to find reviews not yet matched to Issues.
4. Open Issues and switch between Active Issues and Emerging candidates.
5. Filter Issues by department, status, priority, and risk.
6. Resolve an Issue manually, then import or detect matching evidence to demonstrate recurrence.

Notes about current behavior:

- Issues are created dynamically from semantically similar negative/mixed review sentences or a single critical review.
- Resolution is manual only.
- Recurrence is automatic when a new matching sentence arrives after resolution.
- The old `/tickets` workflow is intentionally removed.

## 7. Full Docker Run

If you want to run the full stack in Docker:

```bash
docker compose up --build
```

Then run schema and reference setup from repo root if the API container has not already done so:

```bash
npm run api:migrate
npm run api:seed
```

To trigger detection against a Docker container:

```bash
npm run api:detect
```

Endpoints:

- web: `http://localhost:3000`
- API health: `http://localhost:8000/health`
- API docs: `http://localhost:8000/docs`

## 8. Validation and Troubleshooting

### Run checks

From repo root:

```bash
npm run api:test
npm run lint:web
npm run build:web
```

`npm run api:test` bootstraps `apps/api/.venv` if needed and runs the API test suite. Issue-detection behavior tests require PostgreSQL and the local embedding model; otherwise they skip by design.

### Wipe only demo operational data

```bash
npm run api:wipe
```

This removes operational demo data such as detected Issues, issue events, issue-review links, analyses, reviews, raw reviews, and ingestion runs. It does not remove reference config.

### Common failure modes

`0 created, N updated` during fixture import

- you imported a fixture set that collides with existing external review IDs
- run the fixture validator
- wipe demo data first if you intended a fresh demo

`POST /issues/detect` returns `503`

- the embedding model is unavailable locally
- run `npm run api:download-models` to download all required models
- `npm run api:install:nlp` installs only the Python packages, not the model weights

API ingestion fails with model/runtime errors

- the sentiment or department classification model is not cached
- run `npm run api:download-models` to download all required models
- rerun dependency installation if packages are missing:

```bash
npm run api:install
npm run api:install:nlp
npm run api:download-models
```

## 9. Secondary Workflow: Generate New Review Fixtures with Ollama

This is not the main teammate workflow. Use it only when you intentionally want new generated review corpora.

Ollama is used only for fixture generation outside the product runtime.

### 9.1 Check Ollama

```bash
ollama list
```

Examples:

- `dolphin-llama3:latest`
- `llama3.1:latest`

### 9.2 Generate a new dolphin dataset

When `--output-dir` is omitted, the script creates
`apps/api/data/generated-fixtures/connectors-<model>-<timestamp>` automatically:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 1000 \
  --model dolphin-llama3:latest \
  --seed 202607
```

### 9.3 Generate a new llama dataset with namespaced IDs

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 1000 \
  --model llama3.1:latest \
  --seed 202607 \
  --id-namespace llama
```

To write to a specific location (e.g. outside the repo):

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

Use `npm run api:import:dolphin` and `npm run api:import:llama`, or point the
helper script directly at your new directory:

```bash
sh apps/api/scripts/import_fixture_set.sh apps/api/data/generated-fixtures/connectors-mynewset-20260705-143022
```

## 10. Canonical Supporting Docs

Use this README as the runbook. Use the docs below for architecture and deeper implementation details:

- `docs/README.md`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/nlp-pipeline.md`
- `docs/evaluation-source-policy.md`
- `docs/demo-script.md`
- `docs/research/connector-fixture-generation.md`

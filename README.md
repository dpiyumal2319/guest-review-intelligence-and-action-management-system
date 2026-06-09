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
- Review analysis stores sentiment, department, reputation risk, and embeddings (local Hugging Face models).
- **Issue detection is LLM-driven**: it reads negative/mixed reviews, extracts the concrete problems,
  and dynamically consolidates them into deduplicated, department-owned Issues such as
  `Air conditioning not cooling rooms` or `Cockroach in breakfast food`. Each Issue carries an
  evidence-grounded description. Issues with a single supporting review are surfaced as **emerging**
  candidates. See `apps/api/app/issue_detection.py`.
- The Issue LLM is provider-agnostic (`apps/api/app/llm_client.py`): **Gemini 2.5 Flash** by default,
  with a deterministic offline **stub** provider for tests / no-key runs.
- Review fixtures are generated locally with **Ollama** (the specificity of the generated reviews is
  what makes the Issues specific — see §9).
- Tickets and category-based issue taxonomies have been removed from the runtime workflow.

## 2. Prerequisites

Install these on your machine:

- Docker and Docker Compose
- Python 3.12 or newer
- Node.js 20 or newer
- [Ollama](https://ollama.com) with a chat model pulled (`ollama pull llama3.1`) — only needed to
  **generate** review fixtures (§9), not to run the app against the committed fixtures.

All setup, import, and verification commands are npm scripts — you don't need
`psql`, `curl`, or `jq` to follow this runbook.

NLP model artifacts (sentiment, department, embeddings) are loaded with `local_files_only=True`. The
`npm run api:download-models` step (see §3.2) downloads everything to `~/.cache/huggingface/`
automatically. These run on CPU during ingestion.

### LLM provider for Issue detection

Issue detection calls an LLM. Configure it in `apps/api/.env` (see `apps/api/.env.example`):

- `GEMINI_API_KEY=...` — uses **Gemini 2.5 Flash** (default; ~$0.25 per full detection run over
  ~1000 reviews). Get a key at <https://aistudio.google.com/apikey>.
- `LLM_PROVIDER=stub` — deterministic offline provider, no network/key. Lower quality (used by tests
  and for plumbing checks); fine to smoke-test the pipeline without a key.

If unset, the app uses Gemini when `GEMINI_API_KEY` is present, otherwise the stub.

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
3. triggers LLM Issue detection (set `GEMINI_API_KEY`, or run with `LLM_PROVIDER=stub` offline).

Expected result:

- seed reviews are imported;
- detection reports created/linked Issues;
- the Issues page shows active concrete problems.

### 4.2 Pregenerated fixture datasets

Two fixture sets are committed, each 1000 reviews across three connectors, with non-colliding ID
namespaces so both can be imported together:

- `apps/api/data/generated-fixtures/connectors-dolphin`
- `apps/api/data/generated-fixtures/connectors-llama`

Both are generated from a **specific-incident scenario library** (room/floor/item/amount/time), so the
reviews contain concrete details (`AC dead in room 412 for two nights`, `cockroach in the breakfast
pancake`) — that specificity is what lets detection produce pinpointed Issues. To regenerate them, see §9.

Validate fixture identities before importing both sets:

```bash
npm run api:validate-fixtures
```

Expected:

```text
validated 2 fixture directories without identity collisions
```

### 4.3 Load both fixture sets and detect

```bash
npm run api:import:all
```

This wipes existing demo data, imports both synthetic sets **and the real crawled reviews** (§4.4), then
triggers Issue detection. Detection needs an LLM provider configured (§2): `GEMINI_API_KEY` for real
quality, or `LLM_PROVIDER=stub` for an offline plumbing run. To import one set or detect on its own:

```bash
npm run api:import:dolphin   # or api:import:llama / api:import:real
npm run api:detect
```

> **Teammates: don't re-ingest.** A full ingestion runs local ML over ~5k reviews and bills a Gemini
> detection pass. If you only need the demo data, **restore the committed DB snapshot instead** (§4.5).

### 4.4 Real reviews (Google Places + TripAdvisor)

Real crawled reviews live in `apps/api/data/real-reviews/` and are ingested through the existing
`google_business_profile` and `tripadvisor` connectors — no new connector or subsystem. A one-off
transform cleans and reshapes them:

```bash
npm run api:transform:real   # clean + build connector fixtures (run once after dropping new crawl files)
npm run api:import:real       # ingest via the existing connectors
```

`api:transform:real` (`apps/api/scripts/transform_real_reviews.py`):

- **Cleans the Google Places file in place**, dropping owner-reply-only and non-English records (the raw
  crawl files are not needed afterwards). All cleaned text reviews stay in the raw file for reference.
- Ingests only the **low (≤3★) Google Places reviews** (`GP_FIXTURE_MAX_STARS`). The 4–5★ positives only
  add dashboard sentiment bulk — already provided by the synthetic fixtures — while each one costs a full
  local-ML ingestion pass (~6s on a 6 GB GPU). TripAdvisor is already filtered to 1–3★. (Positives also
  never reach Gemini regardless: Issue detection only sends **negative/mixed** reviews to the LLM.)
- Re-stamps every real review into the newest date window (just above the synthetic fixtures), so the real
  reviews surface at the top of detection's candidate cap and the dashboards — highlighting them without
  any UI change.
- Writes connector fixtures to `apps/api/data/real-reviews/connectors/{google_business_profile,tripadvisor}.json`
  (≈939 reviews: ~255 GP + 684 TripAdvisor).

`api:import:all` already runs `api:import:real` as part of the full rebuild; run the two commands above
directly only when you add or refresh the raw crawl files. The full run raises `ISSUE_MAX_REVIEWS`
(default `2500`) so the real reviews are processed alongside the synthetic ones rather than evicting them.

### 4.5 Restore the demo database from a snapshot (no re-ingestion)

A versioned, gzipped `pg_dump` of the fully-ingested database is committed under
`apps/api/data/db-snapshots/`. Restoring it gives you the exact demo data — reviews, analyses, and
detected Issues — **without re-ingesting or spending any Gemini credits**:

```bash
docker compose up -d postgres        # ensure the DB is running (§3.1)
npm run api:db:restore               # restores the newest snapshot in db-snapshots/
# or: npm run api:db:restore apps/api/data/db-snapshots/guest_reviews_YYYYMMDD.sql.gz
```

To produce a fresh snapshot after a full ingestion:

```bash
npm run api:db:dump                  # writes apps/api/data/db-snapshots/guest_reviews_<date>.sql.gz
```

The dump uses `--clean --if-exists`, so a restore is idempotent on a non-empty database.

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
  engineering (active): 8
  food_beverage (active): 5
  front_office (active): 6
  guest_relations (active): 4
  housekeeping (active): 9
  management (active): 3

=== Evidence links: 1500+ ===
```

Issue counts are now small (tens, not hundreds): detection consolidates synonymous complaints into one
Issue each, so the same problem no longer fragments. Exact numbers depend on the fixtures and the LLM.

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

- Issues are created by LLM extraction + dynamic consolidation over negative/mixed reviews. Detection
  is a full rebuild; manual state (resolved/assignee) is preserved across runs by the issue's stable key.
- Issues with a single supporting review appear as **emerging** candidates, not active Issues.
- Emerging candidates are precomputed during detection and served instantly (no realtime ML on page load).
- Resolution is manual only.
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

`npm run api:test` bootstraps `apps/api/.venv`, targets a dedicated test database, migrates it, seeds reference data, and runs the API test suite there. It does not clear the main demo/application database.

For local DB-backed tests, start the dedicated test Postgres service first:

```bash
npm run api:test-db:up
npm run api:test:docker
```

The test database runs at `localhost:5433` and is isolated from the main app database on `localhost:5432`.

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

- no LLM provider is configured for Issue detection
- set `GEMINI_API_KEY` in `apps/api/.env`, or run with `LLM_PROVIDER=stub` for an offline run
- with `LLM_PROVIDER=gemini` but no key, the provider reports unavailable (hence the 503)

API ingestion fails with model/runtime errors

- the sentiment or department classification model is not cached
- run `npm run api:download-models` to download all required models
- rerun dependency installation if packages are missing:

```bash
npm run api:install
npm run api:install:nlp
npm run api:download-models
```

## 9. Generate Review Fixtures with Ollama

Fixture generation runs a **local** Ollama model (free, offline) outside the product runtime. The
generator is driven by a specific-incident scenario library in
`apps/api/app/connector_fixture_generator.py` — each generated review is about a concrete incident
(room/floor/item/amount/time), which is what makes detected Issues specific and pinpointed. The local
model just phrases the incident naturally; the facts come from the scenario, so even a small model
produces specific reviews.

> Generating 2000 reviews calls the model once per review, so a full run takes a while (tens of
> minutes). It is free. Detection afterwards needs an LLM provider (§2).

### 9.1 Prerequisites

```bash
ollama pull llama3.1     # or any chat model; pass it via --model
ollama list              # confirm it is available
```

### 9.2 Regenerate both committed sets (recommended)

This overwrites `connectors-dolphin` and `connectors-llama` in place, each with 1000 reviews and its
own ID namespace, then validates there are no ID collisions:

```bash
npm run api:generate:all
```

Or generate one set at a time:

```bash
npm run api:generate:dolphin
npm run api:generate:llama
```

Both default to `--model llama3.1:latest` with different seeds so the two sets differ. Edit the
`api:generate:*` scripts in `package.json` to change the model, review count, or seed.

### 9.3 Custom runs

Call the generator directly for ad-hoc datasets. With `--output-dir` omitted it writes to
`apps/api/data/generated-fixtures/connectors-<model>-<timestamp>`:

```bash
cd apps/api && .venv/bin/python scripts/generate_connector_fixtures.py \
  --total-reviews 500 \
  --model llama3.1:latest \
  --id-namespace experiment \
  --output-dir data/generated-fixtures/connectors-experiment
```

Then validate and import:

```bash
.venv/bin/python scripts/validate_fixture_identity.py \
  data/generated-fixtures/connectors-dolphin \
  data/generated-fixtures/connectors-llama
sh scripts/import_fixture_set.sh data/generated-fixtures/connectors-experiment
```

### 9.4 Tune Issue prompts cheaply

Before a full detection run, dry-run the extract + consolidate passes on a small sample (no DB writes,
prints the resulting Issues + descriptions):

```bash
cd apps/api && .venv/bin/python scripts/test_issue_subset.py --topic "air condition" --limit 30
```

### 9.5 Full refresh end to end

```bash
npm run api:generate:all      # regenerate fixtures (Ollama; slow, free)
npm run api:import:all         # wipe + import + detect (needs GEMINI_API_KEY)
npm run api:verify             # review/issue counts
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

# Architecture

## System Purpose

Guest Review Intelligence is an academic prototype decision-support system for hotel review intelligence and action management. It uses The Kingsbury PLC as the case-study property while keeping the code and data model generic enough for hotel review workflows.

The system ingests simulated and prepared multi-source feedback, normalizes source payloads, runs local NLP analysis, exposes dashboard aggregations, detects repeated issues, and tracks corrective action through department-owned tickets.

It is not a production SaaS product. It does not use live Kingsbury credentials, production scraping, or paid LLM APIs.

## Runtime Components

The runtime has three primary services:

- **Web**: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, and Recharts. It serves the operational dashboard pages.
- **API**: FastAPI, Pydantic schemas, SQLAlchemy, Alembic, and local Python NLP modules. It owns ingestion, normalization, analysis, aggregation, and ticket workflows.
- **Database**: PostgreSQL in Docker Compose, with relational normalized records and JSON payload storage.

The initial architecture intentionally excludes Redis, Celery, Kafka, scheduled workers, and separate connector microservices. Connector and NLP logic live in backend modules rather than route handlers so they can later move to workers if processing volume requires it.

## Web Application

The web app lives in `apps/web`.

Primary pages:

- **Overview**: KPI and chart view for review volume, rating, sentiment, severity, departments, categories, and action statuses.
- **Reviews**: normalized review table with shared filters and analysis fields.
- **Issues**: category recurrence summary and semantic issue clusters.
- **Tickets**: corrective-action ticket list and ticket detail history.
- **Ingestion**: connector trigger and ingestion run/status view.

The web app calls the REST API directly using `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`. TypeScript API shapes are maintained in `apps/web/src/lib/api-types.ts`.

Dashboard filters are shared through `apps/web/src/hooks/use-dashboard-filters.ts`. Views support the relevant subset of date range, source, sentiment, issue category, department, severity, action status, and social-listening inclusion filters.

## API Application

The API app lives in `apps/api`.

Main route groups:

- `GET /health`: service health.
- `GET /config`: seeded reference data for sources, departments, categories, mappings, thresholds, and demo roles.
- `POST /ingestion/seed`: fallback seed dataset import.
- `POST /ingestion/connectors/{connector_key}`: official-shaped mock connector import.
- `POST /ingestion/apify-dataset`: offline Apify JSON/CSV dataset import.
- `POST /ingestion/reddit`: Reddit social-listening import.
- `GET /ingestion/runs` and `GET /ingestion/source-status`: ingestion audit/status.
- `GET /reviews`: normalized reviews with active analysis.
- `GET /overview/kpis`: dashboard-friendly KPI aggregate response.
- `GET /issues/summary`: category recurrence summary.
- `GET /analysis/semantic-clusters`: near-duplicate pairs and semantic clusters.
- `POST /analysis/reanalyze`: re-run analysis for imported reviews.
- Ticket endpoints under `/reviews/{review_id}/tickets`, `/issues/categories/{category_code}/tickets`, `/analysis/semantic-clusters/{cluster_id}/tickets`, and `/tickets`.

FastAPI-generated OpenAPI documentation is available at `/docs` when the API is running.

## Database and Migrations

The database schema is owned by SQLAlchemy models in `apps/api/app/models.py` and Alembic migrations in `apps/api/migrations/versions`.

The schema separates:

- source configuration from imported data;
- raw provider payloads from normalized reviews;
- latest active review analysis from normalized review summary columns;
- action ticket state from ticket event history;
- operational workflow data from offline ML evaluation data.

Run migrations with:

```bash
npm run api:migrate
```

Seed repeatable reference data with:

```bash
npm run api:seed
```

## Connector Design

Connectors are backend-owned modules, not separate services.

Verified official-shaped mock connectors live in `apps/api/app/connectors` and are registered in `apps/api/app/connectors/registry.py`. They mimic expected provider payload shapes for Google Business Profile, Booking.com, and Tripadvisor without claiming live official platform access.

All ingestion paths use shared ingestion services:

- create or update an `ingestion_runs` audit record;
- preserve raw source payloads;
- normalize into the canonical review schema;
- deduplicate by source and external review ID;
- flag content-hash duplicates;
- run analysis immediately after create/update;
- commit counts and row-level errors.

Reddit and Apify are intentionally separate paths because they have different source policy meanings.

## NLP Design

The NLP layer is local and reproducible:

- sentiment prefers a local transformer pipeline when a local model artifact is available and otherwise uses a deterministic local lexicon/rating fallback;
- issue-category classification uses a trained TF-IDF + Logistic Regression artifact when present, with keyword baseline fallback;
- severity is transparent and weighted from rating, sentiment, category, urgency terms, recurrence, and duplicate signals;
- semantic similarity uses local TF-IDF cosine similarity, with token similarity fallback if scikit-learn is unavailable;
- analysis stores model name, model version, analysis version, confidence, timestamp, and explanation factors.

No paid LLM API is required for core classification.

## Docker Runtime

Local source-build runtime:

```bash
docker compose up --build
```

Production-style image runtime:

```bash
POSTGRES_PASSWORD=change-me \
API_IMAGE=your-dockerhub-user/guest-review-intelligence-api:latest \
WEB_IMAGE=your-dockerhub-user/guest-review-intelligence-web:latest \
docker compose -f docker-compose.prod.yaml up
```

The Docker stack contains web, API, and PostgreSQL. Image names are environment-configurable so Docker Hub ownership is not hardcoded.

## Design Boundaries

In scope:

- manual/batch ingestion;
- provider-shaped mock official connectors;
- prepared public dataset imports;
- social-listening import separation;
- local NLP and transparent scoring;
- dashboard aggregations and filtering;
- department-owned ticket lifecycle.

Out of scope:

- live hotel-system integrations;
- production credentials;
- production scraping or bypassing platform controls;
- automated public guest replies;
- production auth, SSO, notifications, SLA automation, or CRM replacement;
- real-time ingestion infrastructure;
- required transformer fine-tuning.

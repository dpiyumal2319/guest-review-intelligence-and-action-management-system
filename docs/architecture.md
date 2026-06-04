# Architecture

## System Purpose

Guest Review Intelligence is an academic prototype decision-support system for hotel review intelligence and action management. It uses The Kingsbury PLC as the case-study property while keeping the code and data model generic enough for hotel review workflows.

The MVP ingests connector-shaped review payloads from Google Business Profile, Booking.com, and Tripadvisor, normalizes source payloads, runs local NLP analysis, exposes operational dashboard views, detects recurring issues, and tracks corrective action through department-owned tickets.

It is not a production SaaS product. It does not use live Kingsbury credentials, production scraping, Apify, Reddit/social listening, paid LLM APIs, or local LLMs in the product runtime.

## Runtime Components

The runtime has three primary services:

- **Web**: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, and Recharts. It serves the hotel staff dashboard.
- **API**: FastAPI, Pydantic schemas, SQLAlchemy, Alembic, and local Python NLP modules. It owns connector ingestion, normalization, analysis, aggregation, and ticket workflows.
- **Database**: PostgreSQL in Docker Compose, with relational normalized records and JSON payload storage.

The architecture intentionally excludes Redis, Celery, Kafka, scheduled workers, and separate connector microservices. Connector and NLP logic live in backend modules rather than route handlers so they can later move to workers if processing volume requires it.

## Web Application

The web app lives in `apps/web`.

Primary pages:

- **Overview**: KPI and chart view for review volume, rating, sentiment, Reputation Risk, departments, categories, and action statuses.
- **Reviews**: normalized review list with search, filters, analysis fields, and manual ticket creation.
- **Issues**: recurring issue groups by category and department, with Reputation Risk and source mix.
- **Tickets**: corrective-action ticket list, ticket detail editing, and event history.

The staff web app intentionally does not expose ingestion as a primary page. Connector runs are available through backend API/CLI paths for demo setup and admin use.

The web app calls the REST API directly using `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`. TypeScript API shapes are maintained in `apps/web/src/lib/api-types.ts`.

Dashboard filters are shared through `apps/web/src/hooks/use-dashboard-filters.ts`. Views support the relevant subset of date range, source platform, sentiment, issue category, department, Reputation Risk, action status, and text search filters.

## API Application

The API app lives in `apps/api`.

Main route groups:

- `GET /health`: service health.
- `GET /config`: seeded reference data for review platforms, departments, categories, mappings, Reputation Risk thresholds, and demo roles.
- `POST /ingestion/connectors/{connector_key}`: review-platform connector import, optionally from a local fixture path.
- `GET /ingestion/runs` and `GET /ingestion/source-status`: connector audit/status.
- `GET /reviews`: normalized reviews with active analysis.
- `GET /overview/kpis`: dashboard-friendly KPI aggregate response.
- `GET /issues/summary`: recurring issue summary by category and department.
- `GET /analysis/semantic-clusters`: near-duplicate pairs and semantic clusters for review records.
- `POST /analysis/reanalyze`: re-run analysis for imported reviews.
- Ticket endpoints under `/reviews/{review_id}/tickets`, `/issues/groups/{category_code}/{department_code}/tickets`, `/analysis/semantic-clusters/{cluster_id}/tickets`, and `/tickets`.

FastAPI-generated OpenAPI documentation is available at `/docs` when the API is running.

## Database and Migrations

The database schema is owned by SQLAlchemy models in `apps/api/app/models.py` and Alembic migrations in `apps/api/migrations/versions`.

The schema separates:

- review-platform configuration from imported data;
- raw provider payloads from normalized reviews;
- latest active review analysis from normalized review summary columns;
- action ticket state from ticket event history;
- product runtime data from offline demo fixture generation.

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

Review-platform connectors live in `apps/api/app/connectors` and are registered in `apps/api/app/connectors/registry.py`. They mimic expected provider payload shapes for Google Business Profile, Booking.com, and Tripadvisor without claiming live official platform access.

Connector runs:

- create or update an `ingestion_runs` audit record;
- preserve raw source payloads;
- normalize into the canonical review schema;
- deduplicate by source platform and external review ID;
- flag content-hash duplicates;
- run analysis immediately after create/update;
- commit counts and errors.

Generated demo reviews are produced outside the product boundary with local Ollama and saved as connector-shaped fixture files. Those files enter the system only through the normal connector ingestion path.

## NLP Design

The NLP layer is local and reproducible:

- sentiment uses the required Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` text-classification pipeline with the product label mapping `1-2 -> negative`, `3 -> mixed`, `4-5 -> positive`;
- issue-category classification uses the required Hugging Face `facebook/bart-large-mnli` zero-shot-classification pipeline against the seeded hotel taxonomy;
- missing required sentiment/category model artifacts fail clearly instead of silently falling back;
- Reputation Risk is transparent and weighted from rating, sentiment, category, urgency terms, recurrence, duplicate signals, recency, and platform visibility/engagement metadata where available;
- semantic similarity attempts local sentence-transformer embeddings and falls back to TF-IDF/token overlap for the optional clustering feature;
- analysis stores model name, model version, analysis version, confidence, timestamp, and explanation factors for technical audit.

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

- manual/batch review-platform connector ingestion;
- provider-shaped connector fixtures for demo data;
- local Hugging Face/community NLP;
- Reputation Risk scoring;
- dashboard aggregations and filtering;
- recurring issue discovery;
- manual review-to-ticket and issue-to-ticket workflows;
- department-owned ticket lifecycle.

Out of scope:

- live hotel-system integrations;
- production credentials;
- production scraping or bypassing platform controls;
- Apify as a product connector/source;
- Reddit or social listening in the MVP;
- seed dataset, CSV import, or dataset-import UI;
- manual labelling or classifier training as a product/demo workflow;
- local Ollama in product runtime;
- automatic public guest replies;
- production auth, SSO, notifications, SLA automation, or CRM replacement;
- real-time ingestion infrastructure;
- required transformer fine-tuning.

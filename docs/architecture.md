# Architecture

## System Purpose

Guest Review Intelligence is an academic prototype decision-support system for hotel review intelligence and action management. It uses The Kingsbury PLC as the case-study property while keeping the code and data model generic enough for hotel review workflows.

The MVP ingests connector-shaped review payloads from Google Business Profile, Booking.com, and Tripadvisor, normalizes source payloads, runs local NLP analysis, exposes operational dashboard views, triggers LLM-driven issue detection against negative reviews, and tracks issue lifecycle through department-owned issue records.

It is not a production SaaS product. It does not use live Kingsbury credentials, production scraping, Apify, Reddit/social listening, or local LLMs in the product runtime. Issue detection can use Google Gemini (configurable, offline stub available).

## Runtime Components

The runtime has three primary services:

- **Web**: Next.js 15, React 18, TypeScript 5, Tailwind CSS v4, shadcn/ui (base-nova), lucide-react, and Recharts. It serves the hotel staff dashboard.
- **API**: FastAPI, Pydantic v2, SQLAlchemy 2.0, Alembic, and local Python NLP modules (Hugging Face transformers). It owns connector ingestion, normalization, analysis, aggregation, LLM-driven issue detection, and issue lifecycle workflows.
- **Database**: PostgreSQL 16 (alpine) in Docker Compose, with relational normalized records, JSONB payload storage, and full audit trails.

The architecture intentionally excludes Redis, Celery, Kafka, scheduled workers, and separate connector microservices. Connector and NLP logic live in backend modules rather than route handlers so they can later move to workers if processing volume requires it.

## Web Application

The web app lives in `apps/web`.

Primary pages:

- **Dashboard** (`/dashboard`): KPI cards, donut charts (sentiment mix, risk distribution), bar charts (department issues, priority distribution), owner pressure, platform risk spread, recent issues. All charts are clickable drill-throughs to filtered Reviews or Issues views.
- **Reviews** (`/reviews`): normalized review table with search, platform/date/sentiment/risk/department filters, display redaction, issue link badges.
- **Issues** (`/issues`): Active Issues table with department/status/priority/risk filters and an Emerging tab for single-review early-warning candidates. Click a row for detail sheet with linked reviews, evidence snippets, and event history.

There is no separate Tickets page — the issue model replaces the ticket workflow. An empty `ingestion/` directory exists for future use.

The web app calls the REST API directly using `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`. TypeScript API shapes are maintained in `apps/web/src/lib/api-types.ts`.

Dashboard filters are shared through `apps/web/src/hooks/use-dashboard-filters.ts`. Views support date range, source platform, sentiment, department, Reputation Risk, risk group (high_or_critical), has-issues, and text search filters.

### Styling and Theming

`apps/web/src/app/globals.css` defines the Kingsbury brand palette: deep antique gold/bronze primary over warm charcoal + ivory neutrals, tuned for WCAG AA contrast, with full dark mode support. Platform brand colors (Google, Booking, TripAdvisor) are defined as CSS variables. Theme toggling uses `next-themes` with `attribute="class"`, `defaultTheme="system"`.

### Role Simulation

`apps/web/src/hooks/use-demo-role.tsx` provides a `DemoRoleProvider` context that simulates four demo roles (admin, operations_manager, department_head, analyst) with permissions and department scopes. The active role is persisted to `localStorage`.

## API Application

The API app lives in `apps/api`. Environment configuration is loaded from `apps/api/.env` via `python-dotenv` at package init (`app/__init__.py`).

Main route groups:

- `GET /health`: service health.
- `GET /config`: seeded reference data for review sources, departments, and demo roles.
- `POST /ingestion/connectors/{connector_key}`: review-platform connector import, optionally from a local fixture path.
- `GET /ingestion/runs` and `GET /ingestion/source-status`: connector audit/status.
- `GET /reviews`: paginated/filtered normalized reviews with analysis and issue links.
- `GET /overview/kpis`: dashboard KPI aggregates (sentiment/risk mix, department counts, priorities).
- `GET /overview/action-analytics`: dashboard action metrics (active/high-risk/recurred issues, owner pressure, platform risk, action leakage, recent issues).
- `GET /issues`: paginated/filtered issues (status, department, priority, assignee, min risk).
- `GET /issues/emerging`: single-review emerging candidates ranked by risk.
- `POST /issues/detect`: trigger LLM-driven issue detection pipeline (Gemini or stub).
- `GET /issues/{issue_id}`: issue detail with review links and event history.
- `PATCH /issues/{issue_id}`: update issue assignee/priority.
- `PATCH /issues/{issue_id}/resolve`: resolve an issue (sets status = resolved, records event).
- `GET /analysis/semantic-clusters`: near-duplicate pairs and semantic clusters.
- `POST /analysis/reanalyze`: re-run local NLP analysis for imported reviews.

FastAPI-generated OpenAPI documentation is available at `/docs` when the API is running.

## Database and Migrations

The database schema is owned by SQLAlchemy models in `apps/api/app/models.py` and Alembic migrations in `apps/api/migrations/versions`. Three migrations exist: initial schema creation, issue keywords/quality/merged fields, and issue description.

The schema separates:
- review-source configuration from imported data;
- raw provider payloads from normalized reviews;
- review analysis from normalized review records;
- detected issues from issue review links and issue event history;
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

Each connector has a `MockConnector` dataclass with embedded sample payloads and a `normalize()` function that maps platform-specific JSON to the canonical review shape.

Connector runs:
- create or update an `ingestion_runs` audit record;
- preserve raw source payloads;
- normalize into the canonical review schema;
- deduplicate by source platform and external review ID;
- flag content-hash duplicates;
- run NLP analysis immediately after create/update;
- commit counts and errors.

Generated demo reviews are produced outside the product boundary with local Ollama and saved as connector-shaped fixture files. Those files enter the system only through the normal connector ingestion path.

## NLP and Issue Detection Design

The NLP layer has two parts:

**Local NLP** (automatic per-review):
- Sentiment: Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` pipeline with label mapping `1-2 -> negative`, `3 -> mixed`, `4-5 -> positive`.
- Department classification: Hugging Face `facebook/bart-large-mnli` zero-shot pipeline against 6 department labels. Falls back to `guest_relations` if unavailable.
- Semantic similarity: `sentence-transformers/all-MiniLM-L6-v2` embeddings with TF-IDF and token overlap fallbacks.
- Reputation Risk: transparent weighted scoring from rating, sentiment, department weight, recency, urgency terms, duplicate signals, and platform visibility.
- All analyses store model name, version, confidence, timestamp, and explanation factors.

**LLM Issue Detection** (on-demand batch rebuild):
- Provider-agnostic client (`app/llm_client.py`) with Gemini 2.5 Flash as default and a deterministic offline stub for tests.
- Three-pass pipeline: extraction (problems per review), consolidation (canonical taxonomy), assembly (DetectedIssue records).
- Emerging candidates (single-review) are precomputed but not surfaced as active issues.
- State preservation: resolved/assignee state survives rebuilds via stable `cluster_key`.

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

The Docker stack contains web, API, and PostgreSQL (plus a separate test database). Image names are environment-configurable.

## Design Boundaries

In scope:
- manual/batch review-platform connector ingestion;
- provider-shaped connector fixtures for demo data;
- local Hugging Face/community NLP;
- Reputation Risk scoring;
- LLM-driven issue detection (Gemini configurable, stub offline);
- dashboard aggregations and filtering with drill-through;
- recurring issue discovery via semantic clustering and LLM consolidation;
- issue lifecycle management (active → resolved, with assignee/priority updates);
- emerging issue candidates for early warning.

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

# Guest Review Intelligence Context

## Project Summary

This repo contains an academic prototype decision-support system for hotel guest review intelligence and action management, using The Kingsbury PLC as the case-study property. The MVP ingests connector-shaped hotel review payloads, normalizes them, analyzes them with local Hugging Face/community NLP models, surfaces Reputation Risk and recurring operational issues, and tracks corrective action through department-owned tickets.

The project is a polished university prototype, not a production SaaS platform. It does not use live Kingsbury platform credentials and does not claim live official API access.

## Domain Language

- **Review platform**: A hotel review channel represented in the MVP. Current platforms are Google Business Profile, Booking.com, and Tripadvisor.
- **Connector**: A backend provider module that imports provider-shaped review payloads into the shared ingestion pipeline. Connectors are API-triggerable and individually runnable as backend jobs.
- **Connector fixture**: A local provider-shaped JSON file generated outside the product boundary for demo data. Fixtures are not a product source and must not contain precomputed analysis labels.
- **Raw review**: The original source payload stored for audit and reprocessing.
- **Normalized review**: The canonical review record used by analysis, dashboard views, and ticket workflows.
- **Review analysis**: The latest active NLP and scoring output for a review, including sentiment, issue categories, Reputation Risk, department mapping, duplicate signals, model metadata, confidence, and explanation factors.
- **Reputation Risk**: The single user-facing risk metric. It combines guest-perception damage and likelihood of repeated future complaints.
- **Issue category**: An operational review topic such as cleanliness, room condition, food and beverage, service delay, staff behavior, noise/events, pricing/value, booking/check-in, amenities/facilities, positive general, or other/uncategorized.
- **Recurring issue**: A repeated operational issue detected by category/department counts and, where useful, semantic clustering.
- **Action ticket**: A department-owned corrective-action item created manually from either a single review or a recurring issue group.
- **Review action status**: The status of a review as an input record: new, reviewed, ticket_created, or ignored.
- **Ticket status**: The operational workflow status of an action ticket: open, in_progress, blocked, resolved, or verified.

## Architectural Decisions Already Finalized

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, and Recharts.
- Backend: FastAPI, Python, REST, OpenAPI, Pydantic schemas, SQLAlchemy, Alembic.
- Database: PostgreSQL with relational normalized records and JSONB raw payload storage.
- Repo shape: monorepo-style `apps/web` and `apps/api`, without a monorepo framework initially.
- Docker: `docker-compose.yaml` for local build contexts and `docker-compose.prod.yaml` for Docker Hub images.
- Runtime: web, API, and PostgreSQL only; no Redis, worker, scheduler, Kafka, or connector microservices in the MVP.
- Sources: the product exposes only Google Business Profile, Booking.com, and Tripadvisor review platforms.
- Demo data: generated outside the product with local Ollama and imported through connector-shaped fixture files.
- NLP: Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` for sentiment and `facebook/bart-large-mnli` for zero-shot issue categorization. Missing required models fail clearly.
- Ingestion: manual/batch connector import with idempotent upsert, not real-time streaming.
- Source policy: no live Kingsbury credentials, no production scraping, no bypassing platform controls, and no false claim of official access.
- Product boundary: Apify, Reddit/social listening, seed datasets, CSV imports, manual labelling, and classifier training are not part of the MVP product or demo path.

## Issue Tracker

The current parent PRD is GitHub issue #61. Implementation issues are #62 through #70. Earlier PRDs #1 and #41 are closed as superseded.

Use the label vocabulary in `docs/agents/triage-labels.md`.

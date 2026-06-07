# Guest Review Intelligence Context

## Project Summary

This repo contains an academic prototype decision-support system for hotel guest review intelligence and action management, using The Kingsbury PLC as the case-study property. The MVP ingests connector-shaped hotel review payloads, normalizes them, analyzes them with local Hugging Face/community NLP models, surfaces Reputation Risk, dynamically discovers concrete operational Issues from review content, and tracks corrective action through department-owned Issues.

The project is a polished university prototype, not a production SaaS platform. It does not use live Kingsbury platform credentials and does not claim live official API access.

## Domain Language

- **Review platform**: A hotel review channel represented in the MVP. Current platforms are Google Business Profile, Booking.com, and Tripadvisor.
- **Connector**: A backend provider module that imports provider-shaped review payloads into the shared ingestion pipeline. Connectors are API-triggerable and individually runnable as backend jobs.
- **Connector fixture**: A local provider-shaped JSON file generated outside the product boundary for demo data. Fixtures are not a product source and must not contain precomputed analysis labels.
- **Raw review**: The original source payload stored for audit and reprocessing.
- **Normalized review**: The canonical review record used by analysis and dashboard views. Contains only normalized source data (title, body, rating, date, source, language). Analysis outputs live on ReviewAnalysis, not denormalized onto this record.
- **Review analysis**: The latest active NLP and scoring output for a review, including sentiment, department classification, Reputation Risk, sentence-level embeddings, duplicate signals, model metadata, confidence, and explanation factors.
- **Reputation Risk**: The single user-facing risk metric. It combines guest-perception damage and likelihood of repeated future complaints. Scored 0-100 with labels low/medium/high/critical.
- **Issue**: A concrete operational problem dynamically discovered from guest review content (e.g., "AC not cooling", "delayed check-in"). An Issue is the actionable unit: it has a department, status, priority, assignee, linked evidence reviews, lifecycle event history, and a human-readable title generated when the cluster crosses the detection threshold. Issues are created automatically when ≥2 semantically similar negative/mixed reviews in the same department appear within 30 days, or when a single review has reputation risk ≥75.
- **Issue lifecycle**: The status workflow of an Issue: emerging (computed-only pre-threshold candidate) → active (above threshold, needs action) → resolved (manually marked resolved) → recurred (auto-detected when a new matching review appears after resolution).
- **Issue event**: An audit trail entry recording lifecycle changes for an Issue (created, linked_review, resolved, recurred, title_generated, etc.). System-generated events use actor "system"; manual events use a free-text actor.
- **Issue review link**: A many-to-many join record linking a review to an Issue, with similarity score, linked timestamp, whether it was triggering evidence, and an optional evidence snippet from the matched sentence.
- **Sentence-level matching**: The process of splitting a review into sentences, classifying each sentence's department, embedding each sentence, and matching each sentence independently against existing Issue cluster centroids. One review can link to multiple Issues across departments.
- **Cluster centroid**: A JSON array of floats (384-dimensional embedding) stored on each Issue, computed from linked review embeddings. Used for incremental matching of new reviews against existing Issues.
- **Department**: The operational team responsible for an issue. Current departments: housekeeping, front_office, food_beverage, engineering, management, guest_relations. Each department has a risk_weight contributing to Reputation Risk scoring.

## Architectural Decisions Already Finalized

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, and Recharts.
- Backend: FastAPI, Python, REST, OpenAPI, Pydantic schemas, SQLAlchemy, Alembic.
- Database: PostgreSQL with relational normalized records and JSONB raw payload storage.
- Repo shape: monorepo-style `apps/web` and `apps/api`, without a monorepo framework initially.
- Docker: `docker-compose.yaml` for local build contexts and `docker-compose.prod.yaml` for Docker Hub images.
- Runtime: web, API, and PostgreSQL only; no Redis, worker, scheduler, Kafka, or connector microservices in the MVP.
- Sources: the product exposes only Google Business Profile, Booking.com, and Tripadvisor review platforms.
- Demo data: generated outside the product with local Ollama and imported through connector-shaped fixture files.
- NLP: Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` for sentiment, `facebook/bart-large-mnli` for zero-shot department classification, `sentence-transformers/all-MiniLM-L6-v2` for review/sentence embeddings and clustering, and `google/flan-t5-base` for Issue title generation. Missing models degrade gracefully (fallback paths) except embedding model blocks issue detection with a clear error.
- Ingestion: manual/batch connector import with idempotent upsert, not real-time streaming.
- Source policy: no live Kingsbury credentials, no production scraping, no bypassing platform controls, and no false claim of official access.
- Product boundary: Apify, Reddit/social listening, seed datasets, CSV imports, manual labelling, and classifier training are not part of the MVP product or demo path.

## Issue Tracker

The current parent PRD is GitHub issue #90. Earlier PRDs #1, #41, and #61 are closed or superseded.

Use the label vocabulary in `docs/agents/triage-labels.md`.

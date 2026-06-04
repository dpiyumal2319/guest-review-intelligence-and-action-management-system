# Guest Review Intelligence Context

## Project Summary

This repo contains an academic prototype decision-support system for hotel guest review intelligence and action management, using The Kingsbury PLC as the case-study property. The system ingests simulated and prepared multi-source guest feedback, normalizes it, analyzes it with NLP, surfaces operational insights, and tracks corrective action through department-owned tickets.

The project is a polished university prototype, not a production SaaS platform.

## Domain Language

- **Verified review source**: A review platform treated as an official guest-review channel in the prototype, represented by an official-shaped mock connector. Current examples are Google Business Profile, Booking.com, and Tripadvisor.
- **Social listening source**: A public discussion source that may mention the hotel but is not a verified guest-review channel. Reddit belongs here and must be excluded from default verified-review KPIs.
- **Dataset import source**: A prepared research/demo dataset import, such as an exported Apify JSON or CSV file. This is not the production connector layer.
- **Connector**: A backend provider module that imports source-shaped data into the shared ingestion pipeline. Connectors are API-triggerable and individually runnable as backend jobs.
- **Raw review**: The original source payload stored for audit and reprocessing.
- **Normalized review**: The canonical review record used by analysis, dashboard views, and ticket workflows.
- **Review analysis**: The latest active NLP and scoring output for a review, including sentiment, issue categories, Reputation Risk, department mapping, duplicate flags, model metadata, confidence, and explanation factors.
- **Issue category**: An operational review topic such as cleanliness, room condition, food and beverage, service delay, staff behavior, noise/events, pricing/value, booking/check-in, amenities/facilities, positive general, or other/uncategorized.
- **Recurring issue**: A repeated operational issue detected first by category counts and, where available, semantic clustering.
- **Action ticket**: A department-owned corrective-action item created from either a single review or a recurring issue group.
- **Review action status**: The status of a review as an input record: new, reviewed, ticket_created, or ignored.
- **Ticket status**: The operational workflow status of an action ticket: open, in_progress, blocked, resolved, or verified.
- **Manual labelling**: Offline research/evaluation work used to create ground truth for the issue-category classifier. It is not part of hotel staff operations.

## Architectural Decisions Already Finalized

- Frontend: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, lucide-react, and Recharts.
- Backend: FastAPI, Python, REST, OpenAPI, Pydantic schemas, SQLAlchemy, Alembic.
- Database: PostgreSQL with relational normalized records and JSONB raw payload storage.
- Repo shape: monorepo-style `apps/web` and `apps/api`, without a monorepo framework initially.
- Docker: `docker-compose.yaml` for local build contexts and `docker-compose.prod.yaml` for Docker Hub images.
- Runtime: web, API, and PostgreSQL only at first; add Redis/worker only if performance forces it.
- NLP: required classical ML issue-category classifier; pre-trained local transformer models for sentiment and semantic similarity; transformer fine-tuning is a stretch goal.
- Ingestion: manual/batch import with idempotent upsert, not real-time streaming.
- Source policy: no live Kingsbury credentials, no production scraping, no bypassing platform controls, and no false claim of official access.

## Issue Tracker

The parent PRD is GitHub issue #1. Implementation slices are GitHub issues #2 through #17.

Use the label vocabulary in `docs/agents/triage-labels.md`.

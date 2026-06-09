# Intelligent Multi-Source Guest Review Intelligence and Action Management System for The Kingsbury PLC

This project proposes a prototype decision-support system for The Kingsbury PLC to collect guest feedback from authorised review channels, analyse it using NLP techniques, identify recurring operational issues via LLM-driven detection, and support management action through dashboards and issue tracking. Guest feedback is distributed across platforms such as Google Business Profile, Booking.com, and Tripadvisor; this fragmentation makes it difficult for management to identify repeated service issues, prioritise operational improvements, and track corrective actions. The project aims to transform multi-source guest feedback into structured operational insights and department-level issue resolution.

The proposed solution is a **multi-source review ingestion, analysis, and action-management platform**. The system is designed around authorised review-source integration rather than public web scraping. For the prototype, official business-account access is simulated using mock API connectors shaped according to expected platform data structures. Google Business Profile, Booking.com, and Tripadvisor are treated as verified review sources.

## Scope Covered

The prototype includes an authorised review-ingestion layer with mock connectors for Google Business Profile, Booking.com, and Tripadvisor. All collected feedback is normalised into a unified review model containing source platform, review ID, rating, review text, timestamp, language, and content hash. The NLP component performs sentiment classification, department classification (zero-shot), Reputation Risk scoring, and embedding generation. A separate LLM-driven issue detection pipeline (Gemini or offline stub) extracts problems from negative/mixed reviews, consolidates them into canonical issue types, and assembles detected issues with evidence-grounded descriptions.

The management dashboard presents sentiment distribution, risk level distribution, department-wise issue load, priority distribution, owner pressure, platform risk spread, and recent issue summaries. The issue lifecycle workflow allows detected issues to be reviewed, assigned, prioritised, and resolved with full event history. Single-review emerging candidates provide early warning signals. **The prototype does not include live Kingsbury credentials**, production hotel-system integration, web scraping, automated public replies, full CRM functionality, or revenue/pricing prediction.

## Technical Architecture

The prototype is implemented as a web-based system using React 18 / Next.js 15 for the frontend, FastAPI (Python 3.12) for backend services, PostgreSQL 16 for data storage, and a Python-based NLP pipeline using Hugging Face transformers. LLM-driven issue detection uses Google Gemini 2.5 Flash with a deterministic offline stub for testing. Docker Compose is used for reproducible deployment during demonstration.

Key technical components:
- **Frontend**: TypeScript 5, Tailwind CSS v4, shadcn/ui (base-nova), Recharts, lucide-react, next-themes, @tanstack/react-table, @dnd-kit
- **Backend**: Pydantic v2, SQLAlchemy 2.0, Alembic migrations
- **NLP**: `nlptown/bert-base-multilingual-uncased-sentiment` (sentiment), `facebook/bart-large-mnli` (zero-shot dept classification), `sentence-transformers/all-MiniLM-L6-v2` (embeddings)
- **Issue Detection**: LLM client with Gemini provider (default) and stub provider (offline)
- **Delivery**: 3 Docker services (web, api, postgres + test database)

## Deliverables

The main deliverables are the review-ingestion prototype, unified dataset, NLP analysis pipeline, LLM-driven issue detection, management dashboard, issue lifecycle workflow, evaluation results, and final project documentation. The prototype is considered successful if it can import simulated multi-source reviews, normalise them, run NLP analysis, detect recurring issues via LLM consolidation, classify Reputation Risk and department ownership, visualise insights, and demonstrate a complete review-to-resolution workflow.

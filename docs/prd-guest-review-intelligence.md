# PRD: Guest Review Intelligence and Action Management System

## Problem Statement

The Kingsbury PLC needs a prototype decision-support system that turns fragmented guest feedback into structured operational insight and department-level action. Guest feedback is spread across review platforms, making it difficult for management to identify repeated service issues, prioritize improvements, and track whether corrective action was taken.

The project must prove the core functional requirement: ingest multi-source feedback, normalize it, classify review intelligence with NLP, detect recurring issues via LLM, and convert findings into tracked issue records. It is an academic prototype, not a production SaaS system.

## Solution

Build a web-based review intelligence and action-management prototype for a hotel case study. The system will ingest simulated official review-source data, normalize all records into a canonical review model, run local NLP analysis, trigger LLM-driven issue detection against negative reviews, expose dashboard insights, and support issue lifecycle tracking.

The product will use a Next.js dashboard with shadcn/ui, a FastAPI backend, PostgreSQL, local open-source NLP models, Gemini (offline stub fallback) for issue detection, and Docker Compose for local and production-style demo deployment. Official platform integrations will be represented by mock connectors shaped like expected provider payloads.

## User Stories

1. As a hotel general manager, I want to see overall guest sentiment across review sources, so that I can understand the current guest experience quickly.
2. As a hotel general manager, I want to see recurring issues, so that I can prioritize operational improvements.
3. As a hotel general manager, I want to see high Reputation Risk reviews, so that urgent guest experience problems are not missed.
4. As a hotel general manager, I want to see department-wise issue load, so that I can identify where operational pressure is concentrated.
5. As a hotel general manager, I want detected issues to be automatically grouped from reviews, so that patterns are surfaced without manual triage.
6. As a hotel general manager, I want to resolve detected issues, so that corrective action is tracked.
7. As a department manager, I want to see issues assigned to my department, so that I know what operational action is expected.
8. As a department manager, I want to update issue priority and assignee, so that management can track ownership.
9. As a department manager, I want issue event history recorded, so that the response taken is auditable.
10. As a manager, I want resolved issues to survive detection rebuilds, so that completed work is not lost.
11. As a front-office manager, I want booking and check-in complaints mapped to the correct department, so that ownership is clear.
12. As a housekeeping manager, I want cleanliness and room-condition complaints surfaced separately, so that root causes are easier to discuss.
13. As an F&B manager, I want food and beverage complaints grouped together, so that service and menu issues can be reviewed.
14. As an operations manager, I want noise and events complaints visible, so that event-related guest impact can be monitored.
15. As an administrator, I want to trigger connector imports manually, so that I can demonstrate ingestion on demand.
16. As an administrator, I want each connector to be runnable as an individual backend job, so that imports can be tested independently.
17. As an administrator, I want ingestion runs recorded with counts and errors, so that import behavior is auditable.
18. As an administrator, I want source definitions stored in the system, so that verified review sources are clearly distinguished.
19. As an evaluator, I want raw provider payloads stored separately from normalized reviews, so that transformations can be audited.
20. As an evaluator, I want normalized reviews to have source, external ID, rating, text, timestamp, and language, so that analysis is consistent.
21. As an evaluator, I want deterministic deduplication by source and external review ID, so that repeated imports do not create duplicate records.
22. As an evaluator, I want content-hash duplicate detection, so that repeated text can be identified even when IDs differ.
23. As an evaluator, I want semantic near-duplicate detection, so that similar repeated complaints can be flagged.
24. As an evaluator, I want near duplicates flagged rather than automatically merged, so that the prototype remains transparent.
25. As an NLP evaluator, I want zero-shot department classification, so that reviews are routed to the correct operational department.
26. As an NLP evaluator, I want pre-trained local transformer models for sentiment and semantic similarity, so that the system uses modern NLP without paid APIs for classification.
27. As an NLP evaluator, I want LLM-driven issue detection to extract concrete problems and consolidate them into canonical issue types, so that recurring patterns are discovered.
28. As an NLP evaluator, I want an offline stub fallback for issue detection, so that the pipeline works without paid API keys for testing.
29. As an NLP evaluator, I want model names and versions stored with analysis results, so that outputs are reproducible.
30. As an NLP evaluator, I want confidence scores and explanation factors stored, so that classifications can be audited.
31. As a dashboard user, I want an Overview page, so that I can scan review volume, sentiment, Reputation Risk, and trends.
32. As a dashboard user, I want a Reviews page, so that I can search and filter individual normalized reviews.
33. As a dashboard user, I want an Issues page, so that I can inspect detected issues and emerging candidates.
34. As a dashboard user, I want filters for date range, source, sentiment, department, Reputation Risk, and risk group, so that I can narrow analysis.
35. As a developer, I want a service layer shared by API routes and CLI jobs, so that connector and NLP logic can later move to a worker without rewrite.
36. As a developer, I want a REST API with OpenAPI documentation, so that the frontend and backend contracts are easy to inspect.
37. As a developer, I want Pydantic schemas as the backend contract source of truth, so that request and response shapes are explicit.
38. As a developer, I want PostgreSQL with relational tables and JSONB raw payload storage, so that both analytics and auditability are supported.
39. As a developer, I want Alembic migrations and seed commands, so that schema and reference data are reproducible.
40. As a developer, I want demo review data loaded through import flows, so that the ingestion pipeline is demonstrated honestly.
41. As a developer, I want Docker Compose for local build contexts, so that the stack can be tested from source.
42. As a developer, I want a production-style Docker Compose file using Docker Hub image variables, so that demo deployment can use published images.
43. As a developer, I want no Redis or worker initially, so that the prototype stays simple.
44. As a developer, I want the code structured so a worker can be added later if performance requires it, so that the design does not block scaling.
45. As a privacy-conscious stakeholder, I want the review model to avoid private guest identifiers, so that the prototype minimizes personal data.
46. As a privacy-conscious stakeholder, I want public reviewer display names treated cautiously, so that unnecessary identity storage is avoided.
47. As a privacy-conscious stakeholder, I want email and phone-like text redacted before display, so that sensitive details are not exposed.
48. As a project assessor, I want clear source-policy documentation, so that mock official connectors are not confused with live integrations.
49. As a project assessor, I want a demo script, so that the complete import-to-action workflow can be evaluated consistently.
50. As a project assessor, I want the system branded as a Kingsbury case study but coded generically for hotels, so that the design is realistic and reusable.

## Implementation Decisions

- The project is an academic prototype decision-support system, not a production SaaS platform.
- The repo will use a simple monorepo-style structure with separate web and API applications.
- The frontend will use Next.js 15, React 18, TypeScript 5, Tailwind CSS v4, shadcn/ui (base-nova), and lucide-react.
- The shadcn `dashboard-01` block will be installed using the default CLI command to bootstrap layout and sidebar dependencies, then sample dashboard content will be removed.
- The frontend will avoid preserving shadcn block mock business data. Real pages will be Overview, Reviews, and Issues.
- Recharts will be used for dashboard charts.
- The backend will use FastAPI (Python 3.12). Spring Boot is out of the architecture.
- The backend API will be REST with FastAPI-generated OpenAPI documentation.
- Pydantic v2 schemas are the backend API contract source of truth. OpenAPI TypeScript code generation is not required initially.
- PostgreSQL 16 is the primary database. Raw provider payloads will be preserved in JSONB while normalized records use relational tables.
- SQLAlchemy 2.0 will be used for persistence and Alembic for migrations.
- Reference data will be seeded separately from demo review imports.
- Core database concepts include review sources, raw reviews, normalized reviews, review analysis, departments, demo roles, detected issues, issue-review links, issue events, and ingestion runs.
- Connectors are backend-owned provider modules, not separate services in the initial prototype.
- Connectors must be both API-triggerable and individually runnable as backend jobs.
- Connector logic must live in reusable services/modules rather than route handlers.
- Initial connector keys are `google_business_profile`, `booking_com`, and `tripadvisor`.
- Google Business Profile, Booking.com, and Tripadvisor are treated as verified review sources through official-shaped mock connectors.
- The source policy must explicitly avoid scraping, bypassing platform controls, or claiming live Kingsbury platform credentials.
- Ingestion is manual or batch-triggered with idempotent upsert, not real-time streaming.
- Deterministic deduplication uses source plus external review ID.
- Content-hash deduplication stores a SHA-256 normalized text hash.
- Semantic near-duplicate detection uses local sentence embeddings and cosine similarity with two fallback tiers.
- Near duplicates are flagged for review; they are not automatically deleted or merged.
- The NLP core uses local open-source models for classification.
- Sentiment: `nlptown/bert-base-multilingual-uncased-sentiment`.
- Department classification: `facebook/bart-large-mnli` zero-shot against 6 department labels.
- Semantic embeddings: `sentence-transformers/all-MiniLM-L6-v2` with TF-IDF and token-overlap fallbacks.
- Department mapping is classification-based (zero-shot inference), not rule-based.
- Reputation Risk scoring is transparent and weighted, using rating, sentiment, department weight, urgency keywords, recency, duplicate signals, and platform visibility.
- Reputation Risk labels map weighted scores into low, medium, high, and critical.
- Department classification emits one primary department per review.
- Reviews are automatically analyzed after ingestion.
- A reanalysis command or endpoint must exist so model changes can be applied to existing reviews.
- Review analysis stores model metadata, confidence scores, analyzed timestamp, analysis version, and explanation factors.
- V1 stores the latest active analysis per review rather than full historical analysis versions.
- Manual labelling is research/evaluation infrastructure only. It is not part of hotel operations.
- English-first analysis is in scope. Non-English reviews can be detected but full multilingual NLP is out of scope.
- Issue detection is LLM-driven: extracts problems from negative/mixed reviews, consolidates into canonical types, assembles DetectedIssue records.
- The LLM client supports Gemini 2.5 Flash (default) and a deterministic offline stub for tests.
- Issues carry cluster keys for idempotent rebuild and state preservation.
- Single-review issues are precomputed as emerging candidates (surfaced separately from active issues).
- Issue lifecycle records events: created, priority_changed, assignee_changed, resolved.
- Review action status is implicit from issue linkage, not a separate field.
- Issues are department-owned by default, with optional individual assignee.
- Demo authentication is role simulation (DemoRoleProvider context), not production auth.
- Roles are admin, operations_manager, department_head, and analyst.
- Configuration is minimal and data-backed: review sources, departments, and demo roles.
- The initial Docker stack contains web, API, and PostgreSQL (plus test database).
- Redis and worker services are excluded initially but may be added if performance requires background processing.
- Final deployment files are `docker-compose.yaml` for local build contexts and `docker-compose.prod.yaml` for Docker Hub images.
- Docker Hub image names are configurable using environment variables rather than hardcoded account names.
- Environment variables are explicit and no secrets or live platform tokens are committed.
- Kingsbury is the case-study context in docs and demo data, but core code and data model remain generic for hotel review intelligence.

## Testing Decisions

- Tests should focus on externally observable behavior, not implementation details.
- Keep tests minimal and concentrated around backend pipeline and workflow correctness.
- Connector normalization tests should prove that provider-shaped payloads become canonical review records.
- Idempotent import tests should prove repeated connector runs do not duplicate reviews.
- Deduplication tests should cover external ID dedupe and normalized hash matching.
- Reputation Risk scoring tests should verify transparent score calculation and label thresholds.
- Issue detection integration tests should verify: synonymous complaints consolidate, distinct incidents stay separate, single reviews become emerging, resolved state survives rebuild.
- API smoke tests should verify core route groups are callable and return expected shapes.
- Frontend tests should remain lightweight. Manual demo walkthrough is acceptable for most UI verification.
- End-to-end demo testing should cover import, analysis, issue detection, issue review, and resolution.

## Out of Scope

- Live Kingsbury credentials.
- Production hotel PMS, CRM, or reservation-system integration.
- Public web scraping as the production ingestion method.
- Apify as a product ingestion connector or source.
- Reddit or social listening as a product source.
- Bypassing platform controls or claiming unauthorized official API access.
- Automated public replies to guests.
- Full CRM functionality.
- Revenue or pricing prediction.
- Full production authentication, SSO, password recovery, and audit-grade RBAC.
- Notifications, SLA automation, approval workflows, and attachments.
- Real-time streaming ingestion with Kafka, webhooks, or schedulers.
- GraphQL.
- Required transformer fine-tuning.
- Paid LLM APIs as core classification infrastructure (classification is local; issue detection LLM is configurable).
- Full multilingual analysis.
- Separate connector microservices in the prototype.
- Redis, Celery, or worker services unless performance forces them later.
- A full annotation product for hotel staff.
- Seed datasets, CSV imports, or manual-labelling UI as a product feature.

# PRD: Guest Review Intelligence and Action Management System

## Problem Statement

The Kingsbury PLC needs a prototype decision-support system that turns fragmented guest feedback into structured operational insight and department-level action. Guest feedback is spread across review platforms and public discussions, making it difficult for management to identify repeated service issues, prioritize improvements, and track whether corrective action was taken.

The project must prove the core functional requirement: ingest multi-source feedback, normalize it, classify review intelligence with NLP, detect duplicates and recurring issues, and convert important findings into action tickets. It is an academic prototype, not a production SaaS system.

## Solution

Build a web-based review intelligence and action-management prototype for a hotel case study. The system will ingest simulated official review-source data, import prepared public datasets, normalize all records into a canonical review model, run NLP analysis, expose dashboard insights, and support a review-to-ticket workflow.

The product will use a Next.js dashboard with shadcn/ui, a FastAPI backend, PostgreSQL, local open-source NLP models, and Docker Compose for local and production-style demo deployment. Official platform integrations will be represented by mock connectors shaped like expected provider payloads. Apify-collected data may be used as a one-time research dataset import, but Apify is not the production connector layer.

## User Stories

1. As a hotel general manager, I want to see overall guest sentiment across review sources, so that I can understand the current guest experience quickly.
2. As a hotel general manager, I want to see recurring issue categories, so that I can prioritize operational improvements.
3. As a hotel general manager, I want to see high-severity reviews, so that urgent guest experience problems are not missed.
4. As a hotel general manager, I want to see department-wise issue load, so that I can identify where operational pressure is concentrated.
5. As a hotel general manager, I want to convert an important review into an action ticket, so that the issue is assigned and tracked.
6. As a hotel general manager, I want to create a ticket from a recurring issue group, so that repeated complaints are handled as an operational pattern.
7. As a department manager, I want to see tickets assigned to my department, so that I know what corrective action is expected.
8. As a department manager, I want to update ticket status, so that management can track progress.
9. As a department manager, I want to add resolution notes, so that the response taken is recorded.
10. As a manager, I want resolved tickets to be verified, so that work is not considered complete before review.
11. As a front-office manager, I want booking and check-in complaints mapped to the correct department, so that ownership is clear.
12. As a housekeeping manager, I want cleanliness and room-condition complaints surfaced separately, so that root causes are easier to discuss.
13. As an F&B manager, I want food and beverage complaints grouped together, so that service and menu issues can be reviewed.
14. As an operations manager, I want noise and events complaints visible, so that event-related guest impact can be monitored.
15. As an administrator, I want to trigger connector imports manually, so that I can demonstrate ingestion on demand.
16. As an administrator, I want each connector to be runnable as an individual backend job, so that imports can be tested independently.
17. As an administrator, I want ingestion runs recorded with counts and errors, so that import behavior is auditable.
18. As an administrator, I want source definitions stored in the system, so that verified review sources and social listening sources are clearly distinguished.
19. As an administrator, I want Apify exports imported from files, so that research datasets can be loaded without putting scraping credentials inside the app.
20. As an evaluator, I want raw provider payloads stored separately from normalized reviews, so that transformations can be audited.
21. As an evaluator, I want normalized reviews to have source, external ID, rating, text, timestamp, type, and action status, so that analysis is consistent.
22. As an evaluator, I want deterministic deduplication by source and external review ID, so that repeated imports do not create duplicate records.
23. As an evaluator, I want content-hash duplicate detection, so that repeated text can be identified even when IDs differ.
24. As an evaluator, I want semantic near-duplicate detection, so that similar repeated complaints can be flagged.
25. As an evaluator, I want near duplicates flagged rather than automatically merged, so that the prototype remains transparent.
26. As an NLP evaluator, I want a trained issue-category classifier, so that the project proves a trained review intelligence component.
27. As an NLP evaluator, I want a classical ML issue-category model as the required trained model, so that the project can be completed within the available time.
28. As an NLP evaluator, I want pre-trained local transformer models for sentiment and semantic similarity, so that the system uses modern NLP without paid LLM APIs.
29. As an NLP evaluator, I want transformer fine-tuning treated as a stretch goal, so that the core delivery is not blocked by training complexity.
30. As an NLP evaluator, I want model names and versions stored with analysis results, so that outputs are reproducible.
31. As an NLP evaluator, I want confidence scores and explanation factors stored, so that classifications can be defended.
32. As a researcher, I want to manually label only a subset of reviews offline, so that ground truth exists for training and evaluation.
33. As a researcher, I want manual labelling kept outside the hotel workflow, so that the operational product remains automatic.
34. As a researcher, I want labelled data imported from CSV, so that model training is reproducible.
35. As a researcher, I want macro F1 reported for issue-category classification, so that imbalanced categories are evaluated honestly.
36. As a researcher, I want a baseline comparison against rules or simple classical methods, so that model value can be explained.
37. As a dashboard user, I want an Overview page, so that I can scan review volume, sentiment, severity, and trends.
38. As a dashboard user, I want a Reviews page, so that I can search and filter individual normalized reviews.
39. As a dashboard user, I want an Issues page, so that I can inspect recurring issue categories and clusters.
40. As a dashboard user, I want a Tickets page, so that I can manage corrective actions.
41. As a dashboard user, I want an Ingestion page, so that I can trigger imports and inspect connector run history.
42. As a dashboard user, I want filters for date range, source, sentiment, issue category, department, severity, and action status, so that I can narrow analysis.
43. As a dashboard user, I want Reddit separated as social listening, so that public discussions do not distort verified review KPIs.
44. As a dashboard user, I want Reddit mentions still eligible for tickets, so that relevant public issues can be acted on when appropriate.
45. As a developer, I want a service layer shared by API routes and CLI jobs, so that connector and NLP logic can later move to a worker without rewrite.
46. As a developer, I want a REST API with OpenAPI documentation, so that the frontend and backend contracts are easy to inspect.
47. As a developer, I want Pydantic schemas as the backend contract source of truth, so that request and response shapes are explicit.
48. As a developer, I want PostgreSQL with relational tables and JSONB raw payload storage, so that both analytics and auditability are supported.
49. As a developer, I want Alembic migrations and seed commands, so that schema and reference data are reproducible.
50. As a developer, I want demo review data loaded through import flows, so that the ingestion pipeline is demonstrated honestly.
51. As a developer, I want Docker Compose for local build contexts, so that the stack can be tested from source.
52. As a developer, I want a production-style Docker Compose file using Docker Hub image variables, so that demo deployment can use published images.
53. As a developer, I want no Redis or worker initially, so that the prototype stays simple.
54. As a developer, I want the code structured so a worker can be added later if performance requires it, so that the design does not block scaling.
55. As a privacy-conscious stakeholder, I want the review model to avoid private guest identifiers, so that the prototype minimizes personal data.
56. As a privacy-conscious stakeholder, I want public reviewer display names treated cautiously, so that unnecessary identity storage is avoided.
57. As a privacy-conscious stakeholder, I want email and phone-like text redaction considered before display, so that sensitive details are not exposed.
58. As a project assessor, I want clear source-policy documentation, so that mock official connectors, social listening, and Apify dataset import are not confused.
59. As a project assessor, I want a demo script, so that the complete import-to-action workflow can be evaluated consistently.
60. As a project assessor, I want the system branded as a Kingsbury case study but coded generically for hotels, so that the design is realistic and reusable.

## Implementation Decisions

- The project is an academic prototype decision-support system, not a production SaaS platform.
- The repo will use a simple monorepo-style structure with separate web and API applications.
- The frontend will use Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, and lucide-react.
- The shadcn `dashboard-01` block will be installed using the default CLI command to bootstrap layout and sidebar dependencies, then sample dashboard content will be removed.
- The frontend will avoid preserving shadcn block mock business data. Real pages will be Overview, Reviews, Issues, Tickets, and Ingestion.
- Recharts will be used for dashboard charts.
- The backend will use FastAPI and Python. Spring Boot is out of the architecture.
- The backend API will be REST with FastAPI-generated OpenAPI documentation.
- Pydantic schemas are the backend API contract source of truth. OpenAPI TypeScript code generation is not required initially.
- PostgreSQL is the primary database. Raw provider payloads will be preserved in JSONB while normalized records use relational tables.
- SQLAlchemy will be used for persistence and Alembic for migrations.
- Reference data will be seeded separately from demo review imports.
- Core database concepts include review sources, raw reviews, normalized reviews, review analysis, issue categories, departments, action tickets, ticket events, ingestion runs, and model versions or model runs.
- Connectors are backend-owned provider modules, not separate services in the initial prototype.
- Connectors must be both API-triggerable and individually runnable as backend jobs.
- Connector logic must live in reusable services/modules rather than route handlers.
- Initial connector IDs are `google_business_profile_mock`, `booking_com_mock`, `tripadvisor_mock`, `reddit_social_mock`, `fallback_seed`, and `apify_dataset_import`.
- Google Business Profile, Booking.com, and Tripadvisor are treated as verified review sources through official-shaped mock connectors.
- Reddit is treated as social listening, not a verified review source.
- Apify is allowed for one-time dataset preparation, but not as the app's production connector layer.
- Apify imports are file-based imports from exported JSON or CSV, not live Apify API integrations.
- The source policy must explicitly avoid scraping, bypassing platform controls, or claiming live Kingsbury platform credentials.
- Ingestion is manual or batch-triggered with idempotent upsert, not real-time streaming.
- Deterministic deduplication uses source plus external review ID.
- Content-hash deduplication stores a normalized text hash.
- Semantic near-duplicate detection uses local sentence embeddings and cosine similarity.
- Near duplicates are flagged for review or explanation; they are not automatically deleted or merged.
- The NLP core uses local open-source models and a required trained classical issue-category classifier.
- Required trained model: classical ML issue-category classifier, likely TF-IDF plus Logistic Regression or Linear SVM.
- Required transformer usage: pre-trained local transformer model for sentiment and `all-MiniLM-L6-v2`-style embeddings for semantic similarity.
- Transformer fine-tuning for issue categories is a stretch goal only.
- Department mapping is rule or table based from issue category to department.
- Severity scoring is transparent and weighted, using rating, sentiment, issue category, urgency keywords, and duplicate or recurrence frequency.
- Severity labels map weighted scores into low, medium, high, and critical.
- Issue categories are multi-label in the data model, even if the first trained model emits one primary category.
- Initial taxonomy includes service delay, room condition, cleanliness, food and beverage, noise/events, pricing/value, staff behavior, booking/check-in, amenities/facilities, positive general, and other/uncategorized.
- Reviews are automatically analyzed after ingestion.
- A reanalysis command or endpoint must exist so model changes can be applied to existing reviews.
- Review analysis stores model metadata, confidence scores, analyzed timestamp, analysis version, and explanation factors.
- V1 stores the latest active analysis per review rather than full historical analysis versions.
- Manual labelling is research/evaluation infrastructure only. It is not part of hotel operations.
- Labelled data is used to train and evaluate the issue-category classifier.
- Operational use automatically classifies ingested reviews without hotel staff labelling them.
- Dataset targets are 500-1,500 imported records and 300-600 manually labelled records.
- English-first analysis is in scope. Non-English reviews can be detected and flagged but full multilingual NLP is out of scope.
- Recurring issue detection is category-count based first, with semantic clusters as an enhancement using the same embedding infrastructure.
- Tickets can be created from individual reviews or recurring issue groups.
- Review action status is separate from ticket workflow status.
- Review action statuses are new, reviewed, ticket_created, and ignored.
- Ticket statuses are open, in_progress, blocked, resolved, and verified.
- Tickets are department-owned by default, with optional individual assignee.
- Ticket event history records status, priority, assignment, and note changes.
- Demo authentication is simple seeded users or role simulation, not production auth.
- Roles are admin, manager, and department user.
- Configuration is minimal and data-backed: taxonomy, department mapping, severity thresholds, source enabled flags, and duplicate threshold.
- The initial Docker stack contains web, API, and PostgreSQL.
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
- Deduplication tests should cover external ID dedupe, normalized hash matching, and semantic near-duplicate flagging where practical.
- Severity scoring tests should verify transparent score calculation and label thresholds.
- NLP evaluation scripts should produce issue-category metrics, especially macro F1.
- Ticket workflow tests should verify valid lifecycle transitions and event logging.
- API smoke tests should verify core route groups are callable and return expected shapes.
- Frontend tests should remain lightweight. Manual demo walkthrough is acceptable for most UI verification.
- End-to-end demo testing should cover import, analysis, recurring issue identification, ticket creation, ticket update, resolution, and verification.

## Out of Scope

- Live Kingsbury credentials.
- Production hotel PMS, CRM, or reservation-system integration.
- Public web scraping as the production ingestion method.
- Bypassing platform controls or claiming unauthorized official API access.
- Automated public replies to guests.
- Full CRM functionality.
- Revenue or pricing prediction.
- Full production authentication, SSO, password recovery, and audit-grade RBAC.
- Notifications, SLA automation, approval workflows, and attachments.
- Real-time streaming ingestion with Kafka, webhooks, or schedulers.
- GraphQL.
- Required transformer fine-tuning.
- Paid LLM APIs as core classification infrastructure.
- Full multilingual analysis.
- Separate connector microservices in the prototype.
- Redis, Celery, or worker services unless performance forces them later.
- A full annotation product for hotel staff.

## Further Notes

- The PRD should be published as a GitHub issue with the `ready-for-agent` label once GitHub CLI authentication is fixed.
- The current GitHub CLI token is invalid, so this file is the canonical PRD draft until it can be published.
- `docs/init.md` was only bootstrap material and can be removed after durable architecture, data model, NLP, evaluation, source-policy, and demo-script docs are created.

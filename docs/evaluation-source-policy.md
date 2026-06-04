# Evaluation and Source Policy

## Purpose

This document defines how the prototype should be evaluated and how each data source should be described. It keeps the MVP focused on hotel review platforms while documenting the boundary between provider-shaped connectors and live production access.

## MVP Review Sources

The MVP product and staff-facing API expose only hotel review platforms.

Configured sources:

- Google Business Profile;
- Booking.com;
- Tripadvisor.

Current implementation mapping:

- PRD `google_business_profile_mock` -> source and connector key `google_business_profile`;
- PRD `booking_com_mock` -> source and connector key `booking_com`;
- PRD `tripadvisor_mock` -> source and connector key `tripadvisor`.

Source-policy boundary:

- These are official-shaped mock connectors.
- They do not use live Kingsbury credentials.
- They do not claim actual official platform API access.
- They are suitable for demonstrating provider-shaped ingestion, normalization, idempotency, analysis, and dashboard behavior.

The staff-facing source and filter path should not expose seed datasets, Apify imports, CSV imports, Reddit, social listening, or source-type options.

## Prohibited Claims and Behaviors

Do not claim:

- live Kingsbury platform credentials are used;
- production official API integrations exist;
- Apify is the production ingestion connector;
- public scraping is part of the production workflow;
- non-platform records are verified guest reviews.

Do not implement:

- credential bypass;
- scraping that violates platform controls;
- automated public guest replies;
- hidden enrichment using paid LLM APIs without documenting model/version/source;
- ingestion paths that do not preserve source identity and audit metadata.

## Dashboard Evaluation

Evaluate dashboard behavior through these questions:

- Do Overview KPIs use only Google Business Profile, Booking.com, and Tripadvisor review records?
- Do Reviews, Issues, Tickets, and Overview use consistent platform source-code filters?
- Do API responses return dashboard-ready aggregates rather than forcing the frontend to reconstruct complex data?
- Can a manager identify high-severity reviews, recurring categories, semantic clusters, and department load?

Relevant endpoints:

```text
GET /overview/kpis
GET /reviews
GET /issues/summary
GET /analysis/semantic-clusters
GET /tickets
```

## Ingestion Evaluation

Evaluate ingestion behavior through:

- repeatable connector runs;
- `records_created`, `records_updated`, `records_skipped`, and `records_duplicate_flagged` counts;
- raw payload preservation;
- normalized review creation;
- automatic analysis after ingestion;
- run status and error reporting.

Relevant endpoints:

```text
POST /ingestion/connectors/{connector_key}
GET /ingestion/runs
GET /ingestion/source-status
```

## NLP Evaluation

Issue-category classifier evaluation is offline and research-scoped.

Expected evidence:

- labelled CSV validation;
- train/test split details;
- label distribution;
- macro F1 for the trained classifier;
- macro F1 for keyword baseline;
- per-class metrics;
- confusion matrix.

Commands:

```bash
cd apps/api
python -m app.ml.issue_classifier validate data/examples/issue_labels_sample.csv
python -m app.ml.issue_classifier train-evaluate \
  data/examples/issue_labels_sample.csv \
  --model-output artifacts/ml/issue_classifier.pkl \
  --report-output reports/ml/issue_classifier_evaluation.json
```

Manual labelling is not a hotel staff workflow. It is only used to create research ground truth.

## Ticket Workflow Evaluation

Evaluate action management through:

- creating a ticket from a single review;
- creating a ticket from a recurring issue category;
- creating a ticket from a semantic cluster;
- verifying department ownership;
- updating status through `open`, `in_progress`, `blocked`, `resolved`, and `verified` as relevant;
- checking `ticket_events` for lifecycle history;
- checking source review `action_status = ticket_created`.

Relevant endpoints:

```text
POST /reviews/{review_id}/tickets
POST /issues/categories/{category_code}/tickets
POST /analysis/semantic-clusters/{cluster_id}/tickets
GET /tickets
GET /tickets/{ticket_id}
PATCH /tickets/{ticket_id}
```

Backend job commands use the same services as the API routes:

```bash
cd apps/api
python -m app.jobs connector google_business_profile
python -m app.jobs connector booking_com
python -m app.jobs connector tripadvisor
```

## Privacy and Data Handling

The prototype minimizes sensitive data:

- stores public reviewer display names only when provided by the source payload;
- does not require email, phone, loyalty, payment, or reservation identifiers for reviews;
- keeps raw platform payloads for audit, so connector fixtures should avoid private personal data;
- redacts email-like and phone-like text in review API display fields while preserving raw payloads and normalized source fields for audit;
- treats assignee email on tickets as optional prototype workflow metadata.

## Assessment Checklist

- Staff-facing source configuration exposes only the three MVP review platforms.
- Metrics are scoped to Google Business Profile, Booking.com, and Tripadvisor records.
- Raw and normalized records can be audited.
- Analysis outputs store model metadata and explanation factors.
- Evaluation report compares trained classifier against baseline.
- Ticket workflow records event history.
- Demo can be repeated from a clean database.

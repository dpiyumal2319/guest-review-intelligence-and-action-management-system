# Evaluation and Source Policy

## Purpose

This document defines how the prototype should be evaluated and how each data source should be described. It prevents assessors, users, and future agents from confusing mock official connectors, social listening, and prepared dataset imports.

## Source Types

### Verified Review Sources

Verified review sources represent official guest-review channels in the prototype.

Current examples:

- Google Business Profile;
- Booking.com;
- Tripadvisor.

Current implementation mapping:

- PRD `google_business_profile_mock` -> source and connector key `google_business_profile`;
- PRD `booking_com_mock` -> source and connector key `booking_com`;
- PRD `tripadvisor_mock` -> source and connector key `tripadvisor`.

Important boundary:

- These are official-shaped mock connectors.
- They do not use live Kingsbury credentials.
- They do not claim actual official platform API access.
- They are suitable for demonstrating provider-shaped ingestion, normalization, idempotency, analysis, and dashboard behavior.

Default dashboard KPIs include verified review sources and exclude social listening.

### Seed Dataset

The seed dataset is controlled demo data for repeatable local demonstrations. It is useful for onboarding, smoke testing, and assessor walkthroughs.

It should be described as a fallback seed dataset, not live production feedback.

Current implementation mapping:

- PRD `fallback_seed` -> source `kingsbury_seed_dataset`, connector key `seed_dataset`, API route `/ingestion/seed`, and backend job `python -m app.jobs seed`.

### Social Listening

Reddit is treated as social listening.

Current implementation mapping:

- PRD `reddit_social_mock` -> source `reddit_social_listening`, API route `/ingestion/reddit`, and backend job `python -m app.jobs reddit`.

Important boundary:

- Social-listening records are public mentions, not verified guest-review records.
- They are excluded from default verified-review KPIs.
- They can be included explicitly through source filters or `include_social_listening=true`.
- They may still be eligible for operational review and tickets when relevant.

### Apify Dataset Import

Apify is supported only as an offline dataset preparation path.

Current implementation mapping:

- PRD `apify_dataset_import` -> source and connector key `apify_dataset_import`, API route `/ingestion/apify-dataset`, and backend job `python -m app.jobs apify`.

Important boundary:

- The app imports exported JSON or CSV files.
- The app does not call the Apify API as a production connector.
- The app does not scrape live websites.
- Dataset metadata such as actor name, export date, platform, and source URL is preserved for audit.

Use this path for research/demo datasets where the export was prepared outside the app.

## Prohibited Claims and Behaviors

Do not claim:

- live Kingsbury platform credentials are used;
- production official API integrations exist;
- Apify is the production ingestion connector;
- public scraping is part of the production workflow;
- social-listening records are verified guest reviews.

Do not implement:

- credential bypass;
- scraping that violates platform controls;
- automated public guest replies;
- hidden enrichment using paid LLM APIs without documenting model/version/source;
- ingestion paths that do not preserve source identity and audit metadata.

## Dashboard Evaluation

Evaluate dashboard behavior through these questions:

- Do Overview KPIs exclude social-listening records by default?
- Does selecting social listening or `include_social_listening=true` include those records explicitly?
- Do Reviews, Issues, Tickets, and Overview use consistent filters?
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
POST /ingestion/seed
POST /ingestion/connectors/{connector_key}
POST /ingestion/reddit
POST /ingestion/apify-dataset
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
python -m app.jobs seed
python -m app.jobs connector google_business_profile
python -m app.jobs connector booking_com
python -m app.jobs connector tripadvisor
python -m app.jobs reddit
python -m app.jobs apify --file-path data/imports/apify/export.json
```

## Privacy and Data Handling

The prototype minimizes sensitive data:

- stores public reviewer display names only when provided by the source payload;
- does not require email, phone, loyalty, payment, or reservation identifiers for reviews;
- keeps raw payloads for audit, so demo/import data should avoid private personal data;
- redacts email-like and phone-like text in review API display fields while preserving raw payloads and normalized source fields for audit;
- treats assignee email on tickets as optional prototype workflow metadata.

If real public datasets are used for assessment, redact private details before import.

## Assessment Checklist

- Source types are visibly distinct in configuration and docs.
- Default metrics do not mix social listening with verified review KPIs.
- Raw and normalized records can be audited.
- Analysis outputs store model metadata and explanation factors.
- Evaluation report compares trained classifier against baseline.
- Ticket workflow records event history.
- Demo can be repeated from a clean database.

# Evaluation and Source Policy

## Purpose

This document defines how the MVP should be evaluated and how data sources should be described. It keeps the product focused on hotel review platforms while documenting the boundary between provider-shaped demo connectors and live production access.

## MVP Review Sources

The product and staff-facing API expose only hotel review platforms:

- Google Business Profile;
- Booking.com;
- Tripadvisor.

Current implementation mapping:

- source and connector key `google_business_profile`;
- source and connector key `booking_com`;
- source and connector key `tripadvisor`.

Source-policy boundary:

- These are official-shaped connectors backed by local fixture/demo payloads.
- They do not use live Kingsbury credentials.
- They do not claim actual official platform API access.
- They are suitable for demonstrating provider-shaped ingestion, normalization, idempotency, analysis, and dashboard behavior.

The staff-facing source and filter path must not expose seed datasets, Apify imports, CSV imports, Reddit, social listening, synthetic/fake/mock labels, or source-type options.

## Demo Data Boundary

Demo review data is generated outside the product using local Ollama and saved as connector-shaped JSON fixtures.

Allowed:

- local fixture generation with `dolphin-llama3:latest`;
- provider-shaped Google Business Profile, Booking.com, and Tripadvisor JSON files;
- importing fixture files through the normal connector ingestion path;
- preserving raw fixture payloads for audit.

Not allowed in the product runtime:

- calling Ollama;
- Apify as a connector/source;
- Reddit/social listening;
- CSV import UX;
- manual labelling or classifier training as a demo workflow;
- precomputed sentiment, category, department, or Reputation Risk labels in connector fixtures.

## Reputation-Risk Problem Framing

Hotels generally cannot directly delete unfavorable guest reviews from major platforms. They can respond publicly or request platform review when content violates platform policy. The product therefore focuses on detecting risky feedback and recurring operational causes early so the hotel can fix its own service issues before similar negative reviews keep appearing.

Platform support for this framing:

- Google Business Profile allows businesses to report reviews for removal, but only policy-violating reviews are eligible; disagreement or dislike is not enough.
- Booking.com allows accommodations to request review assessment, but Booking.com decides whether content violates policy and accommodations must not manipulate guest reviews.
- Tripadvisor allows owners to report reviews and respond publicly; disagreement alone is not a removal reason.

## Prohibited Claims and Behaviors

Do not claim:

- live Kingsbury platform credentials are used;
- production official API integrations exist;
- Apify is a product ingestion connector;
- public scraping is part of the product workflow;
- non-platform records are verified guest reviews;
- the system deletes, hides, suppresses, or manipulates platform reviews.

Do not implement:

- credential bypass;
- scraping that violates platform controls;
- automated public guest replies;
- paid LLM APIs as hidden enrichment;
- ingestion paths that bypass source identity and audit metadata.

## Dashboard Evaluation

Evaluate dashboard behavior through these questions:

- Do Overview KPIs use only Google Business Profile, Booking.com, and Tripadvisor review records?
- Do Reviews, Issues, Tickets, and Overview use consistent platform source-code filters?
- Does the UI use one user-facing metric, Reputation Risk?
- Can a manager identify high Reputation Risk reviews, recurring categories, and department load?
- Can a manager manually convert a risky review or recurring issue into an action ticket?

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
- optional connector fixture file import;
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

Backend job commands use the same services as the API routes:

```bash
cd apps/api
python3 -m app.jobs connector google_business_profile
python3 -m app.jobs connector booking_com
python3 -m app.jobs connector tripadvisor
python3 -m app.jobs connector google_business_profile --fixture-path data/generated-fixtures/connectors/google_business_profile.json
```

## NLP Evaluation

Core NLP proof is product runtime behavior, not a mocked label workflow.

Check that:

- sentiment requires `nlptown/bert-base-multilingual-uncased-sentiment`;
- issue categorization requires `facebook/bart-large-mnli`;
- missing required models fail clearly;
- persisted analyses include model metadata and explanation factors;
- staff-facing responses show operational explanations without requiring model internals.

## Ticket Workflow Evaluation

Evaluate action management through:

- creating a ticket from a single review;
- creating a ticket from a recurring issue group;
- creating a ticket from a semantic cluster where useful;
- verifying department ownership;
- updating status through `open`, `in_progress`, `blocked`, `resolved`, and `verified` as relevant;
- checking `ticket_events` for lifecycle history;
- checking source review `action_status = ticket_created`.

Relevant endpoints:

```text
POST /reviews/{review_id}/tickets
POST /issues/groups/{category_code}/{department_code}/tickets
POST /analysis/semantic-clusters/{cluster_id}/tickets
GET /tickets
GET /tickets/{ticket_id}
PATCH /tickets/{ticket_id}
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
- Analysis uses required local model artifacts and stores model metadata.
- The UI uses Reputation Risk as the only risk/severity concept.
- Ticket workflow records event history.
- Demo can be repeated from a clean database.

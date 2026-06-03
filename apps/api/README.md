# API

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --reload
```

Health: http://localhost:8000/health

Docs: http://localhost:8000/docs

## Run tests

Install dependencies once, then run the API tests from the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cd ../..
npm run api:test
```

## Offline Apify dataset import

Apify is supported only as an offline research/demo dataset preparation source. The API does not connect to Apify, scrape live sites, or represent Apify as a production connector.

Trigger a JSON or CSV export import with a server-local file path:

```bash
curl -X POST http://localhost:8000/ingestion/apify-dataset \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "data/imports/apify/export.json",
    "actor_name": "apify/google-maps-reviews-scraper",
    "export_date": "2026-05-20T09:00:00+00:00",
    "platform": "google",
    "source_url": "https://example.test/hotel"
  }'
```

The importer stores the original row payload, normalized review, ingestion run counts, row-level validation errors, and dataset metadata such as actor name, export date, platform, and source URL under the `apify_dataset_import` source.

## Individual ingestion jobs

Each configured import source can be run outside the web UI with the same ingestion services used by the API routes:

```bash
cd apps/api
python3 -m app.jobs seed
python3 -m app.jobs connector google_business_profile
python3 -m app.jobs connector booking_com
python3 -m app.jobs connector tripadvisor
python3 -m app.jobs reddit
python3 -m app.jobs apify --file-path data/imports/apify/export.json
```

For pasted or scripted offline Apify content:

```bash
python3 -m app.jobs apify \
  --content '[{"reviewId":"demo-001","stars":5,"reviewText":"Excellent stay."}]' \
  --file-name apify-export.json
```

## Automatic review analysis

Every ingestion path runs local analysis after a normalized review is created or updated. Sentiment analysis first attempts a local transformer pipeline when the optional `transformers` runtime and a local model artifact are available; otherwise it falls back to `local-deterministic-review-analysis` version `2026.07.demo-fallback`.

The analyzer persists the latest active `review_analyses` row per review and synchronizes the review summary columns for API compatibility. Stored explanation metadata records which sentiment path ran, the active model name/version, confidence, analysis version, and any fallback note. Severity is transparent and weighted from rating, sentiment, issue category, urgency terms, recurrence counts, and duplicate signals when those fields are present.

## Run with Docker

```bash
docker build -t guest-review-intelligence-api .
docker run --rm -p 8000:8000 guest-review-intelligence-api
```

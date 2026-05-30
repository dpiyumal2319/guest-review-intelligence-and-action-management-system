# API

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Health: http://localhost:8000/health

Docs: http://localhost:8000/docs

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
python -m app.jobs seed
python -m app.jobs connector google_business_profile
python -m app.jobs connector booking_com
python -m app.jobs connector tripadvisor
python -m app.jobs reddit
python -m app.jobs apify --file-path data/imports/apify/export.json
```

For pasted or scripted offline Apify content:

```bash
python -m app.jobs apify \
  --content '[{"reviewId":"demo-001","stars":5,"reviewText":"Excellent stay."}]' \
  --file-name apify-export.json
```

## Automatic review analysis

Every ingestion path runs local analysis after a normalized review is created or updated. The current demo-safe analyzer is `local-deterministic-review-analysis` version `2026.07.demo-fallback`: a deterministic lexicon and rules fallback used because transformer sentiment dependencies are not installed in this prototype environment.

The analyzer persists the latest active `review_analyses` row per review and synchronizes the review summary columns for API compatibility. Severity is transparent and weighted from rating, sentiment, issue category, urgency terms, recurrence counts, and duplicate signals when those fields are present.

## Run with Docker

```bash
docker build -t guest-review-intelligence-api .
docker run --rm -p 8000:8000 guest-review-intelligence-api
```

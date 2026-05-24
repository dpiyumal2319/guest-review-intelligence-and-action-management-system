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

## Run with Docker

```bash
docker build -t guest-review-intelligence-api .
docker run --rm -p 8000:8000 guest-review-intelligence-api
```

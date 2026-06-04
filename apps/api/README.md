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

Run the API tests from the repository root:

```bash
npm run api:test
```

The test command creates `apps/api/.venv` when needed and installs `requirements.txt` if `pytest` is missing. To install dependencies explicitly without running tests:

```bash
npm run api:install
```

To install the local transformer NLP runtime into the same venv:

```bash
npm run api:install:nlp
```

If the system Python has `venv` but not `ensurepip`, the test runner bootstraps `pip` into the project venv before installing requirements.

## Individual ingestion jobs

Each configured review-platform connector can be run outside the web UI with the same ingestion service used by the API route:

```bash
cd apps/api
python3 -m app.jobs connector google_business_profile
python3 -m app.jobs connector booking_com
python3 -m app.jobs connector tripadvisor
python3 -m app.jobs connector google_business_profile --fixture-path data/generated-fixtures/connectors/google_business_profile.json
```

The same connector endpoint also accepts an optional JSON body with `fixture_path` to import a local provider-shaped fixture file through the normal connector ingestion path.

## Automatic review analysis

Every ingestion path runs local analysis after a normalized review is created or updated. Sentiment analysis requires the Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` text-classification pipeline, and issue-category analysis requires the Hugging Face `facebook/bart-large-mnli` zero-shot-classification pipeline against the seeded hotel taxonomy.

Semantic similarity first attempts a local `sentence-transformers` model, defaulting to `sentence-transformers/all-MiniLM-L6-v2`, and then falls back to TF-IDF cosine similarity if local model artifacts are unavailable.

Install the transformer runtime on Python 3.12, matching the API Docker image:

```bash
cd apps/api
python3 -m pip install -r requirements-nlp.txt
```

The runtime uses `local_files_only=True`, so demos remain offline-safe after model artifacts are provisioned. To use the transformer paths, pre-download or mount the configured Hugging Face model caches for:

```text
SENTIMENT_TRANSFORMER_MODEL_ID=nlptown/bert-base-multilingual-uncased-sentiment
ISSUE_CATEGORY_MODEL_ID=facebook/bart-large-mnli
SEMANTIC_SIMILARITY_MODEL_ID=sentence-transformers/all-MiniLM-L6-v2
```

The runtime uses `local_files_only=True`, so these model artifacts must be pre-provisioned or mounted into the environment. If either required review-analysis model is missing, ingestion and reanalysis fail clearly instead of falling back to rules.

The analyzer persists the latest active `review_analyses` row per review and synchronizes the review summary columns for API compatibility. Stored explanation metadata records the active model names and versions, confidence, analysis version, and scoring factors for technical audit. Staff-facing review responses omit that model metadata in normal operation.

## Run with Docker

```bash
docker build -t guest-review-intelligence-api .
docker run --rm -p 8000:8000 guest-review-intelligence-api
```

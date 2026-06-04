# Guest Review Intelligence

## Project documentation

Durable assessor and agent documentation lives in [`docs/README.md`](docs/README.md). Start there for architecture, data model, NLP pipeline, evaluation/source policy, and the demo script.

## Run the full local stack

```bash
docker compose up --build
```

Web: http://localhost:3000

API health: http://localhost:8000/health

API docs: http://localhost:8000/docs

## Configure API persistence

The API uses PostgreSQL through SQLAlchemy and Alembic. With the Compose database
running, create the schema and load repeatable reference data:

```bash
npm run api:migrate
npm run api:seed
```

Seeded configuration is exposed at http://localhost:8000/config.

Review-platform connectors can be triggered through the API:

```bash
curl -X POST http://localhost:8000/ingestion/connectors/google_business_profile
curl -X POST http://localhost:8000/ingestion/connectors/booking_com
curl -X POST http://localhost:8000/ingestion/connectors/tripadvisor
```

Imported normalized reviews are exposed at http://localhost:8000/reviews, and
recent ingestion runs are exposed at http://localhost:8000/ingestion/runs.

## Run the web app only

Use Node.js 20 or newer.

```bash
npm --prefix apps/web install
npm --prefix apps/web run dev
```

Web: http://localhost:3000

## Run the API only

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m alembic upgrade head
python3 -m app.seed
python3 -m uvicorn app.main:app --reload
```

API health: http://localhost:8000/health

API docs: http://localhost:8000/docs

## Run backend tests locally

Install the API dependencies first, then run the backend test suite from the
repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cd ../..
npm run api:test
```

## Run production-style Compose

```bash
POSTGRES_PASSWORD=change-me \
API_IMAGE=your-dockerhub-user/guest-review-intelligence-api:latest \
WEB_IMAGE=your-dockerhub-user/guest-review-intelligence-web:latest \
docker compose -f docker-compose.prod.yaml up
```

# Guest Review Intelligence

## Run the full local stack

```bash
docker compose up --build
```

Web: http://localhost:3000

API health: http://localhost:8000/health

API docs: http://localhost:8000/docs

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
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API health: http://localhost:8000/health

API docs: http://localhost:8000/docs

## Run production-style Compose

```bash
POSTGRES_PASSWORD=change-me \
API_IMAGE=your-dockerhub-user/guest-review-intelligence-api:latest \
WEB_IMAGE=your-dockerhub-user/guest-review-intelligence-web:latest \
docker compose -f docker-compose.prod.yaml up
```

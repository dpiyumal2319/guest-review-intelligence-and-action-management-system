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

## Run with Docker

```bash
docker build -t guest-review-intelligence-api .
docker run --rm -p 8000:8000 guest-review-intelligence-api
```

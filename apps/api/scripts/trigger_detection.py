"""Trigger issue detection. Tries the local API first, falls back to in-process."""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import httpx
    r = httpx.post("http://localhost:8000/issues/detect?force=true", timeout=600)
    r.raise_for_status()
    data = r.json()
    print(f"API detection: Created {data['created']}, Updated {data['updated']}, Linked {data['linked']}")
    if data.get("issues"):
        print(f"First issue: {data['issues'][0]['title']}")
except Exception:
    print("API not available, running detection in-process ...")
    from app.database import SessionLocal
    from app.issue_detection import detect_issues
    from app.llm_client import get_llm_client

    client = get_llm_client()
    if not client.is_available():
        print("ERROR: No LLM provider configured. Set GEMINI_API_KEY or LLM_PROVIDER=stub.")
        sys.exit(1)

    with SessionLocal() as session:
        result = detect_issues(session, force=True)
        print(
            f"In-process detection ({client.provider_name}): Created {result['created']}, "
            f"Emerging {result.get('emerging', 0)}, Linked {result['linked']}"
        )

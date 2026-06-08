"""Guest review intelligence API package."""

# Load apps/api/.env (if present) before any module reads os.environ, so configuration like
# GEMINI_API_KEY / LLM_PROVIDER / DATABASE_URL works without manually exporting variables.
# Real environment variables already set take precedence (override=False).
try:
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except Exception:  # noqa: BLE001 - dotenv is optional; never block startup on it
    pass

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.connector_fixture_generator import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

"""Demo pipeline: import seed reviews, run analysis, and trigger issue detection."""

from app.database import SessionLocal
from app.ingestion import run_seed_ingestion
from app.issue_detection import detect_issues
from app.semantic_similarity import get_semantic_similarity_analyzer


def main() -> None:
    with SessionLocal() as session:
        print("Importing demo reviews...")
        run = run_seed_ingestion(session)
        print(f"Import: {run.status}, Created: {run.records_created}")

        print("Checking embedding model...")
        runtime = get_semantic_similarity_analyzer()
        if not runtime.is_available():
            print("WARNING: Embedding model not available. Detection requires embeddings.")
            return

        print("Running issue detection...")
        result = detect_issues(session, force=True)
        print(f"Detection: Created {result['created']}, Updated {result['updated']}, Linked {result['linked']}")


if __name__ == "__main__":
    main()

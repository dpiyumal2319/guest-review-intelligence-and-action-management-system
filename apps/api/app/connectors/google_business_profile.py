from typing import Any

from app.connectors.base import MockConnector


GOOGLE_BUSINESS_PROFILE_PAYLOADS: tuple[dict[str, Any], ...] = (
    {
        "name": "accounts/1029384756/locations/8945123001/reviews/gbp-review-001",
        "reviewId": "gbp-review-001",
        "reviewer": {
            "displayName": "Maya Fernando",
            "profilePhotoUrl": "https://lh3.googleusercontent.com/a/mock-maya",
            "isAnonymous": False,
        },
        "starRating": "FOUR",
        "comment": "The lobby team handled our late arrival well, but the room air conditioning took hours to cool.",
        "createTime": "2026-05-16T15:42:00+05:30",
        "updateTime": "2026-05-16T15:42:00+05:30",
        "reviewReply": {
            "comment": "Thank you for the note. Engineering has been asked to inspect the unit.",
            "updateTime": "2026-05-17T09:15:00+05:30",
        },
    },
    {
        "name": "accounts/1029384756/locations/8945123001/reviews/gbp-review-002",
        "reviewId": "gbp-review-002",
        "reviewer": {
            "displayName": "Nuwan Perera",
            "profilePhotoUrl": "https://lh3.googleusercontent.com/a/mock-nuwan",
            "isAnonymous": False,
        },
        "starRating": "TWO",
        "comment": "Check-in queue was very slow and our prepaid booking was not visible at the desk.",
        "createTime": "2026-05-18T20:05:00+05:30",
        "updateTime": "2026-05-18T20:05:00+05:30",
    },
)


STAR_RATINGS = {
    "ONE": 1.0,
    "TWO": 2.0,
    "THREE": 3.0,
    "FOUR": 4.0,
    "FIVE": 5.0,
}


def normalize_google_business_profile(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_code": "google_business_profile",
        "external_review_id": payload["reviewId"],
        "reviewer_name": payload.get("reviewer", {}).get("displayName"),
        "review_date": payload.get("createTime"),
        "rating": STAR_RATINGS.get(payload.get("starRating")),
        "language": "en",
        "title": None,
        "body": payload["comment"],
        "normalized_payload": {
            "connector_key": "google_business_profile",
            "provider": "Google Business Profile",
            "provider_payload_shape": "businessprofile.googleapis.com account location review",
            "verified_review_source": True,
            "mock_official_shaped_connector": True,
            "provider_review_name": payload["name"],
            "provider_updated_at": payload.get("updateTime"),
            "provider_has_reply": "reviewReply" in payload,
        },
    }


connector = MockConnector(
    connector_key="google_business_profile",
    source_code="google_business_profile",
    provider_name="Google Business Profile",
    payload_shape="businessprofile.googleapis.com account location review",
    records=GOOGLE_BUSINESS_PROFILE_PAYLOADS,
    normalize=normalize_google_business_profile,
)


def main() -> None:
    from app.database import SessionLocal
    from app.ingestion import run_mock_connector_by_key

    with SessionLocal() as session:
        run = run_mock_connector_by_key(session, connector.connector_key)
        print(f"{run.connector_key} {run.status}: {run.records_created} created, {run.records_updated} updated, {run.records_skipped} skipped")


if __name__ == "__main__":
    main()

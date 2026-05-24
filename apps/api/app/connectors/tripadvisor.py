from typing import Any

from app.connectors.base import MockConnector


TRIPADVISOR_PAYLOADS: tuple[dict[str, Any], ...] = (
    {
        "id": "tripadvisor-review-001",
        "location_id": "the-kingsbury-colombo-demo",
        "url": "https://www.tripadvisor.com/ShowUserReviews-g293962-d301921-r001-The_Kingsbury_Colombo.html",
        "rating": 3,
        "published_date": "2026-05-14T18:25:00+05:30",
        "travel_date": "2026-05",
        "title": "Beautiful hotel but noisy event night",
        "text": "The rooms and lobby were impressive, but music from a private event carried late into the night.",
        "user": {
            "username": "HariniW",
            "user_location": {"name": "Kandy, Sri Lanka"},
            "contributions": 42,
        },
        "subratings": {
            "service": 4,
            "value": 3,
            "sleep_quality": 2,
            "cleanliness": 4,
        },
        "management_response": {
            "text": "We are reviewing event sound controls with our operations team.",
            "published_date": "2026-05-15T12:10:00+05:30",
        },
        "mock_analysis": {
            "sentiment_label": "mixed",
            "sentiment_score": -0.280,
            "issue_category_code": "noise_events",
            "severity": "medium",
            "department_code": "guest_relations",
        },
    },
    {
        "id": "tripadvisor-review-002",
        "location_id": "the-kingsbury-colombo-demo",
        "url": "https://www.tripadvisor.com/ShowUserReviews-g293962-d301921-r002-The_Kingsbury_Colombo.html",
        "rating": 2,
        "published_date": "2026-05-20T09:40:00+05:30",
        "travel_date": "2026-05",
        "title": "Maintenance issues in the bathroom",
        "text": "The shower drained slowly and the bathroom fittings felt worn. The front desk apologized but the issue remained.",
        "user": {
            "username": "TravelWithRavi",
            "user_location": {"name": "Dubai, United Arab Emirates"},
            "contributions": 18,
        },
        "subratings": {
            "service": 3,
            "value": 2,
            "sleep_quality": 3,
            "cleanliness": 3,
        },
        "mock_analysis": {
            "sentiment_label": "negative",
            "sentiment_score": -0.680,
            "issue_category_code": "room_condition",
            "severity": "high",
            "department_code": "engineering",
        },
    },
)


def normalize_tripadvisor(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload["mock_analysis"]
    return {
        "source_code": "tripadvisor",
        "external_review_id": payload["id"],
        "reviewer_name": payload.get("user", {}).get("username"),
        "review_date": payload.get("published_date"),
        "rating": float(payload["rating"]),
        "language": "en",
        "title": payload.get("title"),
        "body": payload["text"],
        "sentiment_label": analysis["sentiment_label"],
        "sentiment_score": analysis["sentiment_score"],
        "issue_category_code": analysis["issue_category_code"],
        "severity": analysis["severity"],
        "department_code": analysis["department_code"],
        "normalized_payload": {
            "connector_key": "tripadvisor",
            "provider": "Tripadvisor",
            "provider_payload_shape": "content API location review with subratings",
            "verified_review_source": True,
            "mock_official_shaped_connector": True,
            "provider_location_id": payload["location_id"],
            "provider_url": payload["url"],
            "provider_travel_date": payload.get("travel_date"),
            "provider_has_management_response": "management_response" in payload,
            "provider_subratings": payload.get("subratings", {}),
        },
    }


connector = MockConnector(
    connector_key="tripadvisor",
    source_code="tripadvisor",
    provider_name="Tripadvisor",
    payload_shape="content API location review with subratings",
    records=TRIPADVISOR_PAYLOADS,
    normalize=normalize_tripadvisor,
)


def main() -> None:
    from app.database import SessionLocal
    from app.ingestion import run_mock_connector_by_key

    with SessionLocal() as session:
        run = run_mock_connector_by_key(session, connector.connector_key)
        print(f"{run.connector_key} {run.status}: {run.records_created} created, {run.records_updated} updated, {run.records_skipped} skipped")


if __name__ == "__main__":
    main()

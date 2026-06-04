from typing import Any

from app.connectors.base import MockConnector


BOOKING_COM_PAYLOADS: tuple[dict[str, Any], ...] = (
    {
        "guest_review_id": "booking-review-001",
        "hotel_id": "kingsbury-colombo-demo",
        "reservation_id": "booking-res-71022",
        "reviewer": {
            "name": "Aisha Khan",
            "country_code": "PK",
            "stayed_room_name": "Premium Ocean View Room",
        },
        "scores": {
            "overall": 8.0,
            "cleanliness": 7.5,
            "comfort": 8.0,
            "facilities": 7.0,
            "staff": 9.0,
            "value_for_money": 7.0,
        },
        "content": {
            "headline": "Great staff, breakfast rush needs work",
            "positive": "Staff were warm and the ocean view was excellent.",
            "negative": "Breakfast queues were long and several buffet items were not replenished quickly.",
            "language_code": "en",
        },
        "created_at": "2026-05-12T10:18:00+05:30",
        "updated_at": "2026-05-13T08:00:00+05:30",
        "review_status": "published",
        "mock_analysis": {
            "sentiment_label": "mixed",
            "sentiment_score": -0.180,
            "issue_category_code": "food_beverage",
            "reputation_risk": "medium",
            "department_code": "food_beverage",
        },
    },
    {
        "guest_review_id": "booking-review-002",
        "hotel_id": "kingsbury-colombo-demo",
        "reservation_id": "booking-res-71084",
        "reviewer": {
            "name": "Sophie Martin",
            "country_code": "FR",
            "stayed_room_name": "Executive Room",
        },
        "scores": {
            "overall": 9.0,
            "cleanliness": 9.0,
            "comfort": 9.0,
            "facilities": 8.5,
            "staff": 9.5,
            "value_for_money": 8.0,
        },
        "content": {
            "headline": "Comfortable stay close to the seafront",
            "positive": "The team was attentive, housekeeping was consistent, and the location worked perfectly.",
            "negative": "",
            "language_code": "en",
        },
        "created_at": "2026-05-19T11:30:00+05:30",
        "updated_at": "2026-05-19T11:30:00+05:30",
        "review_status": "published",
        "mock_analysis": {
            "sentiment_label": "positive",
            "sentiment_score": 0.720,
            "issue_category_code": "positive_general",
            "reputation_risk": "low",
            "department_code": "guest_relations",
        },
    },
)


def normalize_booking_com(payload: dict[str, Any]) -> dict[str, Any]:
    analysis = payload["mock_analysis"]
    content = payload["content"]
    body_parts = [content.get("positive", ""), content.get("negative", "")]
    return {
        "source_code": "booking_com",
        "external_review_id": payload["guest_review_id"],
        "reviewer_name": payload.get("reviewer", {}).get("name"),
        "review_date": payload.get("created_at"),
        "rating": round(float(payload["scores"]["overall"]) / 2, 2),
        "language": content.get("language_code", "en"),
        "title": content.get("headline"),
        "body": " ".join(part for part in body_parts if part).strip(),
        "sentiment_label": analysis["sentiment_label"],
        "sentiment_score": analysis["sentiment_score"],
        "issue_category_code": analysis["issue_category_code"],
        "reputation_risk": analysis["reputation_risk"],
        "department_code": analysis["department_code"],
        "normalized_payload": {
            "connector_key": "booking_com",
            "provider": "Booking.com",
            "provider_payload_shape": "connectivity guest review with reservation and score breakdown",
            "verified_review_source": True,
            "mock_official_shaped_connector": True,
            "provider_hotel_id": payload["hotel_id"],
            "provider_reservation_id": payload["reservation_id"],
            "provider_review_status": payload["review_status"],
            "provider_updated_at": payload.get("updated_at"),
            "provider_scores": payload["scores"],
        },
    }


connector = MockConnector(
    connector_key="booking_com",
    source_code="booking_com",
    provider_name="Booking.com",
    payload_shape="connectivity guest review with reservation and score breakdown",
    records=BOOKING_COM_PAYLOADS,
    normalize=normalize_booking_com,
)


def main() -> None:
    from app.database import SessionLocal
    from app.ingestion import run_mock_connector_by_key

    with SessionLocal() as session:
        run = run_mock_connector_by_key(session, connector.connector_key)
        print(f"{run.connector_key} {run.status}: {run.records_created} created, {run.records_updated} updated, {run.records_skipped} skipped")


if __name__ == "__main__":
    main()

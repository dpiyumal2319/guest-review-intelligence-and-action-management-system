from pathlib import Path
from datetime import UTC, datetime
import json

import pytest

from app.connector_fixture_generator import (
    ANALYSIS_FIELD_NAMES,
    DEFAULT_MODEL,
    PLATFORMS,
    contains_analysis_fields,
    generate_connector_fixtures,
    parse_review_draft,
    platform_counts,
)
from app.ml.issue_classifier import KeywordBaselineClassifier, train_and_evaluate, validate_labelled_csv


FIXTURES = Path(__file__).parent / "fixtures"


def long_review(category_code: str, variant: str) -> str:
    return (
        f"This synthetic hotel review is for {category_code} and describes a realistic guest stay with enough "
        f"context for classifier training. During a two night visit, the guest noticed specific details about "
        f"arrival, room expectations, staff follow up, and the overall service flow. The main issue stayed focused "
        f"on {category_code}, while the writing still sounded like a normal traveller explaining what happened. "
        f"The review includes concrete observations, a clear sentiment, and a distinct wording variant {variant}."
    )


def test_labelled_csv_validates_against_seeded_taxonomy() -> None:
    result = validate_labelled_csv(FIXTURES / "issue_labels_valid.csv")

    assert result.is_valid
    assert len(result.rows) == 8
    assert {row.issue_category_code for row in result.rows} == {
        "booking_checkin",
        "cleanliness",
        "food_beverage",
        "positive_general",
    }


def test_labelled_csv_rejects_unknown_taxonomy_label(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad-labels.csv"
    csv_path.write_text(
        "text,issue_category_code\n"
        "\"The room was not clean.\",cleanliness\n"
        "\"This label should fail.\",made_up_category\n",
        encoding="utf-8",
    )

    result = validate_labelled_csv(csv_path)

    assert not result.is_valid
    assert "made_up_category" in result.errors[0]


def test_keyword_baseline_predicts_simple_issue_category() -> None:
    predictions = KeywordBaselineClassifier().predict(
        ["The bathroom was dirty.", "The booking and check-in process was delayed."]
    )

    assert predictions == ["cleanliness", "booking_checkin"]


def test_train_and_evaluate_writes_model_and_report(tmp_path: Path) -> None:
    pytest.importorskip("sklearn")
    model_path = tmp_path / "issue_classifier.pkl"
    report_path = tmp_path / "issue_classifier_report.json"

    report = train_and_evaluate(
        FIXTURES / "issue_labels_valid.csv",
        model_output_path=model_path,
        report_output_path=report_path,
        test_size=0.5,
    )

    assert model_path.exists()
    assert report_path.exists()
    assert report["model"]["type"] == "tfidf_logistic_regression"
    assert report["baseline"]["type"] == "keyword_rules"
    assert "macro_f1" in report["model"]
    assert "confusion_matrix" in report["model"]


def test_connector_review_parser_accepts_fenced_json() -> None:
    draft = parse_review_draft(
        """
        ```json
        {"title":"Slow arrival", "text":"The check-in queue was slow and our booking could not be found for almost an hour after we arrived from a late flight.", "rating":2}
        ```
        """,
        fallback_rating=3,
    )

    assert draft.title == "Slow arrival"
    assert draft.rating == 2
    assert "check-in queue" in draft.text


def test_platform_counts_split_reviews_across_three_sources() -> None:
    counts = platform_counts(2000)

    assert set(counts) == set(PLATFORMS)
    assert sum(counts.values()) == 2000
    assert max(counts.values()) - min(counts.values()) <= 1


def test_connector_fixture_generation_writes_provider_shapes_without_analysis(tmp_path: Path) -> None:
    prompts: list[str] = []

    def fake_requester(prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps(
            {
                "title": f"Fixture title {len(prompts)}",
                "text": f"Repeated issue wave fixture review {len(prompts)} with natural hotel feedback.",
                "rating": 2 if len(prompts) % 2 else 5,
            }
        )

    result = generate_connector_fixtures(
        output_dir=tmp_path / "fixtures",
        total_reviews=9,
        request_text=fake_requester,
        seed=42,
    )

    assert result.model == DEFAULT_MODEL
    assert result.counts == {
        "google_business_profile": 3,
        "booking_com": 3,
        "tripadvisor": 3,
    }
    assert len(prompts) == 9
    assert all("dolphin" not in prompt.lower() for prompt in prompts)

    google = json.loads(result.files["google_business_profile"].read_text(encoding="utf-8"))
    booking = json.loads(result.files["booking_com"].read_text(encoding="utf-8"))
    tripadvisor = json.loads(result.files["tripadvisor"].read_text(encoding="utf-8"))
    manifest = json.loads(result.files["manifest"].read_text(encoding="utf-8"))

    assert google[0]["reviewId"].startswith("gbp-review-")
    assert google[0]["name"].endswith(google[0]["reviewId"])
    assert google[0]["starRating"] in {"ONE", "TWO", "THREE", "FOUR", "FIVE"}
    assert "comment" in google[0]
    assert "likeCount" in google[0]

    assert booking[0]["guest_review_id"].startswith("booking-review-")
    assert booking[0]["reservation_id"].startswith("booking-res-")
    assert booking[0]["scores"]["overall"] >= 1
    assert "positive" in booking[0]["content"]
    assert "helpful_votes" in booking[0]

    assert tripadvisor[0]["id"].startswith("tripadvisor-review-")
    assert "subratings" in tripadvisor[0]
    assert "helpful_votes" in tripadvisor[0]["user"]
    assert "text" in tripadvisor[0]

    assert manifest["model"] == "dolphin-llama3:latest"
    assert manifest["total_reviews"] == 9
    assert manifest["date_window_start"] == "2025-06-05T00:00:00+00:00"
    assert manifest["date_window_end"] == "2026-06-05T23:59:59+00:00"
    fixture_dates = [
        datetime.fromisoformat(payload["createTime"].replace("Z", "+00:00"))
        for payload in google
    ] + [
        datetime.fromisoformat(payload["created_at"])
        for payload in booking
    ] + [
        datetime.fromisoformat(payload["published_date"])
        for payload in tripadvisor
    ]
    assert min(fixture_dates) == datetime(2025, 6, 5, 0, 0, tzinfo=UTC)
    assert max(fixture_dates) == datetime(2026, 6, 5, 23, 59, 59, tzinfo=UTC)
    for payloads in (google, booking, tripadvisor):
        assert not contains_analysis_fields(payloads)
        serialized = json.dumps(payloads)
        for field_name in ANALYSIS_FIELD_NAMES:
            assert field_name not in serialized


def test_connector_fixture_generation_can_namespace_provider_ids(tmp_path: Path) -> None:
    def fake_requester(prompt: str) -> str:
        return json.dumps(
            {
                "title": "Namespaced fixture",
                "text": "A realistic hotel review for checking namespaced fixture identities.",
                "rating": 3,
            }
        )

    result = generate_connector_fixtures(
        output_dir=tmp_path / "fixtures",
        total_reviews=3,
        request_text=fake_requester,
        id_namespace="llama",
        seed=42,
    )

    google = json.loads(result.files["google_business_profile"].read_text(encoding="utf-8"))
    booking = json.loads(result.files["booking_com"].read_text(encoding="utf-8"))
    tripadvisor = json.loads(result.files["tripadvisor"].read_text(encoding="utf-8"))
    manifest = json.loads(result.files["manifest"].read_text(encoding="utf-8"))

    assert google[0]["reviewId"].startswith("llama-gbp-review-")
    assert google[0]["name"].endswith(google[0]["reviewId"])
    assert booking[0]["guest_review_id"].startswith("llama-booking-review-")
    assert tripadvisor[0]["id"].startswith("llama-tripadvisor-review-")
    assert manifest["id_namespace"] == "llama"

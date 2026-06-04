from pathlib import Path
import json

import pytest

from app.ml.label_draft_generator import (
    build_dataset_manifest,
    generate_label_drafts,
    parse_generated_rows,
)
from app.ml.issue_classifier import KeywordBaselineClassifier, train_and_evaluate, validate_labelled_csv
from app.seed_data import ISSUE_CATEGORIES


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


def test_qwen_response_parser_accepts_fenced_json() -> None:
    rows = parse_generated_rows(
        """
        ```json
        {"rows":[{"text":"The check-in queue was slow and our booking could not be found for almost an hour after we arrived from a late flight. The lobby was busy, but nobody explained what was happening or offered water while families waited with luggage. Once the room was finally located, the key cards failed twice and we had to return to the desk again. The staff apologized, yet the arrival felt disorganized and stressful.", "rating":2}]}
        ```
        """,
        category_code="booking_checkin",
    )

    assert len(rows) == 1
    assert rows[0].issue_category_code == "booking_checkin"
    assert rows[0].rating == 2
    assert "check-in queue" in rows[0].text


def test_qwen_response_parser_accepts_shorter_reviews_when_rating_is_valid() -> None:
    rows = parse_generated_rows(
        '{"rows":[{"text":"The check-in queue was slow, frustrating, and poorly managed.", "rating":2}]}',
        category_code="booking_checkin",
    )

    assert len(rows) == 1
    assert rows[0].rating == 2


def test_ollama_draft_generation_writes_valid_random_category_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "ollama_issue_labels_synthetic.csv"
    prompts: list[str] = []

    def fake_requester(prompt: str) -> str:
        prompts.append(prompt)
        category_line = next(line for line in prompt.splitlines() if line.startswith("Category code:"))
        category_code = category_line.split(":", 1)[1].strip()
        return json.dumps({"text": long_review(category_code, str(len(prompts))), "rating": 2})

    result = generate_label_drafts(
        output_path=output_path,
        total_rows=5,
        request_text=fake_requester,
    )
    validation = validate_labelled_csv(output_path)

    assert validation.is_valid
    assert len(result.rows) == 5
    assert len(prompts) == 5
    assert sum(result.label_counts.values()) == 5
    assert result.rows[0].review_id.startswith("synthetic-")
    assert result.rows[0].source_code == "ollama_synthetic_evaluation"
    assert result.rows[0].notes == "ollama-generated synthetic evaluation label"
    assert output_path.read_text(encoding="utf-8").splitlines()[0] == (
        "review_id,text,issue_category_code,source_code,rating,notes"
    )


def test_ollama_draft_generation_discards_invalid_and_duplicate_outputs(tmp_path: Path) -> None:
    output_path = tmp_path / "ollama_issue_labels_total.csv"
    responses = iter(
        [
            "not json",
            json.dumps({"text": "", "rating": 3}),
            json.dumps({"text": "Duplicate but otherwise usable review.", "rating": 3}),
            json.dumps({"text": "Duplicate but otherwise usable review.", "rating": 3}),
            json.dumps({"text": "A distinct usable review after bad output.", "rating": 4}),
        ]
    )

    def fake_requester(prompt: str) -> str:
        return next(responses)

    result = generate_label_drafts(
        output_path=output_path,
        total_rows=2,
        request_text=fake_requester,
    )

    assert len(result.rows) == 2
    assert result.duplicate_count == 1


def test_qwen_manifest_records_hash_counts_and_review_status(tmp_path: Path) -> None:
    csv_path = tmp_path / "reviewed.csv"
    csv_path.write_text(
        "review_id,text,issue_category_code,source_code,rating,notes\n"
        f"reviewed-001,\"{long_review('cleanliness', 'manifest-one')}\",cleanliness,ollama_synthetic_evaluation,2,synthetic evaluation\n"
        f"reviewed-002,\"{long_review('positive_general', 'manifest-two')}\",positive_general,ollama_synthetic_evaluation,5,synthetic evaluation\n",
        encoding="utf-8",
    )

    manifest = build_dataset_manifest(csv_path=csv_path, human_reviewed=False)

    assert manifest["human_reviewed"] is False
    assert manifest["row_count"] == 2
    assert manifest["label_counts"] == {"cleanliness": 1, "positive_general": 1}
    assert len(manifest["csv_sha256"]) == 64
    assert manifest["validation"]["is_valid"] is True

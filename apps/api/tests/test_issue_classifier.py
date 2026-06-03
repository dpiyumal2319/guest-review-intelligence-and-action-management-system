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
        {"rows":[{"text":"The check-in queue was slow and our booking could not be found for almost an hour.", "rating":2}]}
        ```
        """,
        category_code="booking_checkin",
    )

    assert len(rows) == 1
    assert rows[0].issue_category_code == "booking_checkin"
    assert rows[0].rating == 2
    assert "check-in queue" in rows[0].text


def test_qwen_draft_generation_writes_valid_deduped_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "qwen_issue_labels_draft.csv"

    def fake_requester(prompt: str) -> str:
        category_line = next(line for line in prompt.splitlines() if line.startswith("Category code:"))
        category_code = category_line.split(":", 1)[1].strip()
        rows = [
            {
                "text": f"Guest review for {category_code} with a clearly described hotel experience number one.",
                "rating": 2,
            },
            {
                "text": f"Guest review for {category_code} with a clearly described hotel experience number one.",
                "rating": 2,
            },
            {
                "text": f"Guest review for {category_code} with a clearly described hotel experience number two.",
                "rating": 3,
            },
        ]
        return json.dumps({"rows": rows})

    result = generate_label_drafts(
        output_path=output_path,
        rows_per_category=2,
        batch_size=2,
        request_text=fake_requester,
    )
    validation = validate_labelled_csv(output_path)

    assert validation.is_valid
    assert len(result.rows) == len(ISSUE_CATEGORIES) * 2
    assert result.duplicate_count >= len(ISSUE_CATEGORIES)
    assert result.label_counts == {category["code"]: 2 for category in ISSUE_CATEGORIES}
    assert result.rows[0].review_id.startswith("qwen-cleanliness-")
    assert output_path.read_text(encoding="utf-8").splitlines()[0] == (
        "review_id,text,issue_category_code,source_code,rating,notes"
    )


def test_qwen_manifest_records_hash_counts_and_review_status(tmp_path: Path) -> None:
    csv_path = tmp_path / "reviewed.csv"
    csv_path.write_text(
        "review_id,text,issue_category_code,source_code,rating,notes\n"
        "reviewed-001,\"The bathroom was dirty and the towels smelled damp.\",cleanliness,qwen_synthetic_draft,2,human reviewed\n"
        "reviewed-002,\"The staff were friendly and the stay was excellent.\",positive_general,qwen_synthetic_draft,5,human reviewed\n",
        encoding="utf-8",
    )

    manifest = build_dataset_manifest(csv_path=csv_path, human_reviewed=True)

    assert manifest["human_reviewed"] is True
    assert manifest["row_count"] == 2
    assert manifest["label_counts"] == {"cleanliness": 1, "positive_general": 1}
    assert len(manifest["csv_sha256"]) == 64
    assert manifest["validation"]["is_valid"] is True

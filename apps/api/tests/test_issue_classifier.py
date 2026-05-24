from pathlib import Path

import pytest

from app.ml.issue_classifier import KeywordBaselineClassifier, train_and_evaluate, validate_labelled_csv


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

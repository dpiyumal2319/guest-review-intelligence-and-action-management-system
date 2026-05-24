from __future__ import annotations

import argparse
import csv
import json
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.seed_data import ISSUE_CATEGORIES


REQUIRED_LABEL_COLUMNS = ("text", "issue_category_code")
OPTIONAL_LABEL_COLUMNS = ("review_id", "source_code", "rating", "notes")


@dataclass(frozen=True)
class LabelledReview:
    row_number: int
    text: str
    issue_category_code: str
    review_id: str | None = None


@dataclass(frozen=True)
class ValidationResult:
    rows: list[LabelledReview]
    errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


class KeywordBaselineClassifier:
    """Deterministic baseline used for comparison with the trained model."""

    KEYWORDS: dict[str, tuple[str, ...]] = {
        "cleanliness": ("dirty", "clean", "dust", "stain", "smell", "linen", "bathroom", "hygiene"),
        "room_condition": ("air conditioning", "ac", "hot water", "maintenance", "broken", "leak", "room"),
        "food_beverage": ("breakfast", "food", "buffet", "restaurant", "bar", "dinner", "meal", "coffee"),
        "service_delay": ("slow", "delay", "wait", "queue", "late", "response", "took"),
        "staff_behavior": ("staff", "rude", "helpful", "friendly", "manager", "receptionist", "attitude"),
        "noise_events": ("noise", "music", "event", "party", "loud", "sleep", "crowd"),
        "pricing_value": ("price", "expensive", "value", "worth", "billing", "charge", "rate"),
        "booking_checkin": ("booking", "reservation", "check-in", "check in", "checkout", "deposit", "payment"),
        "amenities_facilities": ("pool", "gym", "spa", "wifi", "wi-fi", "parking", "lift", "elevator"),
        "positive_general": ("excellent", "great", "perfect", "amazing", "wonderful", "recommend", "beautiful"),
    }

    def __init__(self, fallback_label: str = "other_uncategorized") -> None:
        self.fallback_label = fallback_label

    def predict(self, texts: list[str]) -> list[str]:
        predictions: list[str] = []
        for text in texts:
            normalized = text.lower()
            label = self.fallback_label
            best_score = 0
            for category_code, keywords in self.KEYWORDS.items():
                score = sum(1 for keyword in keywords if keyword in normalized)
                if score > best_score:
                    label = category_code
                    best_score = score
            predictions.append(label)
        return predictions


def taxonomy_codes() -> set[str]:
    return {category["code"] for category in ISSUE_CATEGORIES}


def validate_labelled_csv(path: Path) -> ValidationResult:
    errors: list[str] = []
    rows: list[LabelledReview] = []
    allowed_labels = taxonomy_codes()

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = [column for column in REQUIRED_LABEL_COLUMNS if column not in fieldnames]
        if missing_columns:
            return ValidationResult(
                rows=[],
                errors=[f"Missing required column(s): {', '.join(missing_columns)}."],
            )

        for row_number, row in enumerate(reader, start=2):
            text = (row.get("text") or "").strip()
            label = (row.get("issue_category_code") or "").strip()
            review_id = (row.get("review_id") or "").strip() or None

            if not text:
                errors.append(f"Row {row_number}: text is required.")
            if not label:
                errors.append(f"Row {row_number}: issue_category_code is required.")
            elif label not in allowed_labels:
                errors.append(
                    f"Row {row_number}: issue_category_code '{label}' is not in the seeded issue taxonomy."
                )

            if text and label in allowed_labels:
                rows.append(
                    LabelledReview(
                        row_number=row_number,
                        text=text,
                        issue_category_code=label,
                        review_id=review_id,
                    )
                )

    if not rows and not errors:
        errors.append("CSV contains no labelled review rows.")

    return ValidationResult(rows=rows, errors=errors)


def validate_or_raise(path: Path) -> list[LabelledReview]:
    result = validate_labelled_csv(path)
    if not result.is_valid:
        raise ValueError("\n".join(result.errors))
    return result.rows


def train_issue_classifier(rows: list[LabelledReview]) -> Any:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    if len({row.issue_category_code for row in rows}) < 2:
        raise ValueError("Training requires at least two issue categories.")

    return Pipeline(
        steps=[
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1, sublinear_tf=True)),
            (
                "classifier",
                LogisticRegression(
                    class_weight="balanced",
                    max_iter=1000,
                    random_state=42,
                ),
            ),
        ]
    ).fit([row.text for row in rows], [row.issue_category_code for row in rows])


def split_labelled_rows(
    rows: list[LabelledReview],
    test_size: float,
    random_state: int,
) -> tuple[list[LabelledReview], list[LabelledReview]]:
    from sklearn.model_selection import train_test_split

    labels = [row.issue_category_code for row in rows]
    label_counts = {label: labels.count(label) for label in set(labels)}
    stratify = labels if min(label_counts.values()) >= 2 and len(label_counts) > 1 else None

    train_rows, test_rows = train_test_split(
        rows,
        test_size=test_size,
        random_state=random_state,
        stratify=stratify,
    )
    return list(train_rows), list(test_rows)


def evaluate_predictions(
    y_true: list[str],
    y_pred: list[str],
    labels: list[str],
) -> dict[str, Any]:
    from sklearn.metrics import classification_report, confusion_matrix, f1_score

    present_labels = [label for label in labels if label in set(y_true) | set(y_pred)]
    return {
        "macro_f1": f1_score(y_true, y_pred, labels=present_labels, average="macro", zero_division=0),
        "per_class": classification_report(
            y_true,
            y_pred,
            labels=present_labels,
            output_dict=True,
            zero_division=0,
        ),
        "confusion_matrix": {
            "labels": present_labels,
            "matrix": confusion_matrix(y_true, y_pred, labels=present_labels).tolist(),
        },
    }


def train_and_evaluate(
    csv_path: Path,
    *,
    model_output_path: Path | None = None,
    report_output_path: Path | None = None,
    test_size: float = 0.3,
    random_state: int = 42,
) -> dict[str, Any]:
    rows = validate_or_raise(csv_path)
    if len(rows) < 4:
        raise ValueError("Training/evaluation requires at least four labelled rows.")

    train_rows, test_rows = split_labelled_rows(rows, test_size=test_size, random_state=random_state)
    model = train_issue_classifier(train_rows)
    baseline = KeywordBaselineClassifier()

    y_true = [row.issue_category_code for row in test_rows]
    labels = sorted(taxonomy_codes())
    model_predictions = list(model.predict([row.text for row in test_rows]))
    baseline_predictions = baseline.predict([row.text for row in test_rows])

    report = {
        "dataset": {
            "csv_path": str(csv_path),
            "row_count": len(rows),
            "train_count": len(train_rows),
            "test_count": len(test_rows),
            "label_counts": {
                label: sum(1 for row in rows if row.issue_category_code == label)
                for label in sorted({row.issue_category_code for row in rows})
            },
        },
        "model": {
            "type": "tfidf_logistic_regression",
            **evaluate_predictions(y_true, model_predictions, labels),
        },
        "baseline": {
            "type": "keyword_rules",
            **evaluate_predictions(y_true, baseline_predictions, labels),
        },
    }

    if model_output_path is not None:
        model_output_path.parent.mkdir(parents=True, exist_ok=True)
        with model_output_path.open("wb") as model_file:
            pickle.dump(model, model_file)

    if report_output_path is not None:
        report_output_path.parent.mkdir(parents=True, exist_ok=True)
        report_output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate, train, and evaluate the offline issue-category classifier."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a manually labelled CSV against the taxonomy.",
    )
    validate_parser.add_argument("csv_path", type=Path)

    train_parser = subparsers.add_parser(
        "train-evaluate",
        help="Train the classifier and produce an evaluation report.",
    )
    train_parser.add_argument("csv_path", type=Path)
    train_parser.add_argument("--model-output", type=Path, default=Path("artifacts/ml/issue_classifier.pkl"))
    train_parser.add_argument("--report-output", type=Path, default=Path("reports/ml/issue_classifier_evaluation.json"))
    train_parser.add_argument("--test-size", type=float, default=0.3)
    train_parser.add_argument("--random-state", type=int, default=42)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        result = validate_labelled_csv(args.csv_path)
        if result.is_valid:
            print(f"Valid labelled CSV: {len(result.rows)} rows.")
            return 0
        for error in result.errors:
            print(error)
        return 1

    if args.command == "train-evaluate":
        report = train_and_evaluate(
            args.csv_path,
            model_output_path=args.model_output,
            report_output_path=args.report_output,
            test_size=args.test_size,
            random_state=args.random_state,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

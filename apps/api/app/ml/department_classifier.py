from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os

from app.analysis_runtime import AnalysisRuntimeUnavailableError

DEPARTMENT_LABELS = [
    "housekeeping room cleanliness bathroom cleaning linen hygiene",
    "front office reception check-in check-out booking reservations arrival",
    "food beverage restaurant dining breakfast bar room service cuisine",
    "engineering maintenance repair air conditioning plumbing facility defects",
    "management pricing value strategy policy hotel administration",
    "guest relations service recovery follow-up complaint handling staff courtesy",
]

DEPARTMENT_LABEL_TO_CODE: dict[str, str] = {
    "housekeeping room cleanliness bathroom cleaning linen hygiene": "housekeeping",
    "front office reception check-in check-out booking reservations arrival": "front_office",
    "food beverage restaurant dining breakfast bar room service cuisine": "food_beverage",
    "engineering maintenance repair air conditioning plumbing facility defects": "engineering",
    "management pricing value strategy policy hotel administration": "management",
    "guest relations service recovery follow-up complaint handling staff courtesy": "guest_relations",
}

DEFAULT_DEPARTMENT_MODEL_ID = "facebook/bart-large-mnli"
DEPARTMENT_MODEL_NAME = "huggingface-transformers-zero-shot-classification"


@dataclass(frozen=True)
class DepartmentPredictionResult:
    department_code: str
    confidence: float
    rank: int
    model_name: str
    model_version: str


class DepartmentClassifierRuntime:
    def __init__(self) -> None:
        self.model_id = os.getenv("ISSUE_CATEGORY_MODEL_ID", DEFAULT_DEPARTMENT_MODEL_ID)
        self.model_revision = os.getenv("ISSUE_CATEGORY_MODEL_REVISION")
        self.model_name = DEPARTMENT_MODEL_NAME
        try:
            self.pipeline = _load_transformer_pipeline(
                model_id=self.model_id,
                revision=self.model_revision,
            )
        except Exception as exc:
            self.pipeline = None
            self._unavailable_reason = f"{type(exc).__name__}: {exc}"
        if self.pipeline is not None:
            self.model_version = self.model_revision or _pipeline_version(self.pipeline) or self.model_id
        else:
            self.model_version = "unavailable"
        self._candidate_labels = DEPARTMENT_LABELS

    @property
    def is_available(self) -> bool:
        return self.pipeline is not None

    def classify(self, text: str, *, top_k: int = 1) -> list[DepartmentPredictionResult]:
        if not text.strip():
            raise AnalysisRuntimeUnavailableError(
                "department-classifier",
                "Review text is empty, so the department model cannot run.",
            )
        if self.pipeline is None:
            return [
                DepartmentPredictionResult(
                    department_code="guest_relations",
                    confidence=0.3,
                    rank=1,
                    model_name=DEPARTMENT_MODEL_NAME,
                    model_version="unavailable",
                )
            ]

        result = self.pipeline(
            text,
            candidate_labels=self._candidate_labels,
            multi_label=False,
            truncation=True,
        )
        labels = list(result.get("labels", []))
        scores = list(result.get("scores", []))
        predictions: list[DepartmentPredictionResult] = []
        for label, score in zip(labels, scores, strict=False):
            confidence = round(float(score), 3)
            if len(predictions) >= top_k:
                break
            department_code = DEPARTMENT_LABEL_TO_CODE.get(str(label).strip(), "guest_relations")
            predictions.append(
                DepartmentPredictionResult(
                    department_code=department_code,
                    confidence=confidence,
                    rank=len(predictions) + 1,
                    model_name=self.model_name,
                    model_version=self.model_version,
                )
            )
        if not predictions:
            predictions.append(
                DepartmentPredictionResult(
                    department_code="guest_relations",
                    confidence=0.3,
                    rank=1,
                    model_name=DEPARTMENT_MODEL_NAME,
                    model_version="unavailable",
                )
            )
        return predictions

    def classify_batch(self, texts: list[str]) -> list[list[DepartmentPredictionResult]]:
        return [self.classify(text) for text in texts]


def _load_transformer_pipeline(*, model_id: str, revision: str | None):
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline

    tokenizer = AutoTokenizer.from_pretrained(
        model_id,
        revision=revision,
        local_files_only=True,
    )
    model = AutoModelForSequenceClassification.from_pretrained(
        model_id,
        revision=revision,
        local_files_only=True,
    )
    return pipeline(
        "zero-shot-classification",
        model=model,
        tokenizer=tokenizer,
    )


def _pipeline_version(pipeline_obj) -> str | None:
    model = getattr(pipeline_obj, "model", None)
    config = getattr(model, "config", None)
    for attribute in ("_commit_hash", "name_or_path", "_name_or_path"):
        value = getattr(config, attribute, None) if config is not None else None
        if value:
            return str(value)
    return None


@lru_cache(maxsize=1)
def get_department_classifier() -> DepartmentClassifierRuntime:
    return DepartmentClassifierRuntime()

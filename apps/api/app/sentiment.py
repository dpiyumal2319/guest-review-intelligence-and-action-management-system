from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
import re

from app.analysis_runtime import AnalysisRuntimeUnavailableError


ANALYSIS_VERSION = "analysis-v2"
DEFAULT_SENTIMENT_MODEL_ID = "nlptown/bert-base-multilingual-uncased-sentiment"
SENTIMENT_MODEL_NAME = "huggingface-transformers-sentiment-analysis"
STAR_TO_SENTIMENT = {
    1: ("negative", -1.0),
    2: ("negative", -0.5),
    3: ("mixed", 0.0),
    4: ("positive", 0.5),
    5: ("positive", 1.0),
}


@dataclass(frozen=True)
class SentimentAnalysisResult:
    sentiment_label: str
    sentiment_score: float
    sentiment_confidence: float
    model_name: str
    model_version: str
    analysis_version: str
    explanation_factors: dict
    fallback_note: str | None


class LocalTransformerSentimentAnalyzer:
    def __init__(self) -> None:
        self.model_id = os.getenv("SENTIMENT_TRANSFORMER_MODEL_ID", DEFAULT_SENTIMENT_MODEL_ID)
        self.model_revision = os.getenv("SENTIMENT_TRANSFORMER_MODEL_REVISION")
        try:
            self._pipeline = _load_transformer_pipeline(
                model_id=self.model_id,
                revision=self.model_revision,
            )
        except Exception as exc:  # pragma: no cover - covered through monkeypatched tests
            raise AnalysisRuntimeUnavailableError(
                "sentiment",
                (
                    "Install `transformers`, provision the "
                    f"`{self.model_id}` artifact locally, and keep Hugging Face local files enabled. "
                    f"Original error: {type(exc).__name__}: {exc}"
                ),
            ) from exc

    def analyze(self, text: str, tokens: set[str], rating: float | None) -> SentimentAnalysisResult:
        if not text.strip():
            raise AnalysisRuntimeUnavailableError("sentiment", "Review text is empty, so the sentiment model cannot run.")

        prediction = self._pipeline(text, truncation=True)[0]
        raw_label = str(prediction.get("label", "")).strip()
        raw_score = round(float(prediction.get("score", 0.5)), 3)
        star_rating = _transformer_stars(raw_label)
        sentiment_label, sentiment_score = STAR_TO_SENTIMENT[star_rating]
        model_version = self.model_revision or _pipeline_version(self._pipeline) or self.model_id
        return SentimentAnalysisResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            sentiment_confidence=raw_score,
            model_name=SENTIMENT_MODEL_NAME,
            model_version=model_version,
            analysis_version=ANALYSIS_VERSION,
            explanation_factors={
                "strategy": "huggingface_text_classification_pipeline",
                "transformer_label": raw_label,
                "transformer_score": raw_score,
                "star_rating": star_rating,
                "model_id": self.model_id,
                "model_revision": self.model_revision or model_version,
                "rating": None if rating is None else float(rating),
                "tokens_seen": len(tokens),
            },
            fallback_note=None,
        )


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
        "sentiment-analysis",
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


def _transformer_stars(raw_label: str) -> int:
    match = re.search(r"([1-5])", raw_label)
    if match is None:
        raise AnalysisRuntimeUnavailableError(
            "sentiment",
            f"Unexpected label `{raw_label}` from `{DEFAULT_SENTIMENT_MODEL_ID}`.",
        )
    return int(match.group(1))


@lru_cache(maxsize=1)
def get_sentiment_analyzer() -> LocalTransformerSentimentAnalyzer:
    return LocalTransformerSentimentAnalyzer()

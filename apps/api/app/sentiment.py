from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os


ANALYSIS_VERSION = "analysis-v2"
DEFAULT_SENTIMENT_MODEL_ID = "distilbert/distilbert-base-uncased-finetuned-sst-2-english"
FALLBACK_MODEL_NAME = "local-deterministic-review-analysis"
FALLBACK_MODEL_VERSION = "2026.07.demo-fallback"

POSITIVE_TERMS = {
    "amazing",
    "attentive",
    "comfortable",
    "excellent",
    "friendly",
    "good",
    "great",
    "helpful",
    "memorable",
    "perfect",
    "quickly",
    "warm",
}
NEGATIVE_TERMS = {
    "apologized",
    "broken",
    "dirty",
    "difficult",
    "delayed",
    "drained",
    "issue",
    "late",
    "long",
    "loud",
    "maintenance",
    "noise",
    "not",
    "problem",
    "queue",
    "slow",
    "stretched",
    "took",
    "worn",
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


class DeterministicSentimentAnalyzer:
    def analyze(self, tokens: set[str], rating: float | None) -> SentimentAnalysisResult:
        positive_matches = sorted(tokens & POSITIVE_TERMS)
        negative_matches = sorted(tokens & NEGATIVE_TERMS)
        lexical_score = (len(positive_matches) - len(negative_matches)) / max(
            len(positive_matches) + len(negative_matches),
            3,
        )
        rating_score = 0.0 if rating is None else max(min((float(rating) - 3.0) / 2.0, 1.0), -1.0)
        combined = (0.62 * lexical_score) + (0.38 * rating_score)
        combined = round(max(min(combined, 1.0), -1.0), 3)
        label = _label_from_score(combined)
        confidence = round(
            min(0.95, 0.55 + abs(combined) * 0.4 + min(len(positive_matches) + len(negative_matches), 4) * 0.04),
            3,
        )
        fallback_note = (
            "Deterministic local lexicon/rule fallback used because local transformer sentiment dependencies "
            "or model artifacts are unavailable in this environment."
        )
        return SentimentAnalysisResult(
            sentiment_label=label,
            sentiment_score=combined,
            sentiment_confidence=confidence,
            model_name=FALLBACK_MODEL_NAME,
            model_version=FALLBACK_MODEL_VERSION,
            analysis_version=ANALYSIS_VERSION,
            explanation_factors={
                "strategy": "deterministic_fallback",
                "rating_score": round(rating_score, 3),
                "lexical_score": round(lexical_score, 3),
                "positive_terms": positive_matches,
                "negative_terms": negative_matches,
            },
            fallback_note=fallback_note,
        )


class LocalTransformerSentimentAnalyzer:
    def __init__(self) -> None:
        self.model_id = os.getenv("SENTIMENT_TRANSFORMER_MODEL_ID", DEFAULT_SENTIMENT_MODEL_ID)
        self.model_revision = os.getenv("SENTIMENT_TRANSFORMER_MODEL_REVISION")
        self._fallback = DeterministicSentimentAnalyzer()
        self._pipeline = None
        self._unavailable_reason: str | None = None
        try:
            self._pipeline = _load_transformer_pipeline(
                model_id=self.model_id,
                revision=self.model_revision,
            )
        except Exception as exc:  # pragma: no cover - covered through monkeypatched tests
            self._unavailable_reason = f"{type(exc).__name__}: {exc}"

    def analyze(self, text: str, tokens: set[str], rating: float | None) -> SentimentAnalysisResult:
        if not text.strip():
            return self._fallback.analyze(tokens, rating)
        if self._pipeline is None:
            fallback_result = self._fallback.analyze(tokens, rating)
            return SentimentAnalysisResult(
                sentiment_label=fallback_result.sentiment_label,
                sentiment_score=fallback_result.sentiment_score,
                sentiment_confidence=fallback_result.sentiment_confidence,
                model_name=fallback_result.model_name,
                model_version=fallback_result.model_version,
                analysis_version=fallback_result.analysis_version,
                explanation_factors=fallback_result.explanation_factors,
                fallback_note=self.fallback_note or fallback_result.fallback_note,
            )

        prediction = self._pipeline(text, truncation=True)[0]
        raw_label = str(prediction.get("label", "")).strip()
        raw_score = float(prediction.get("score", 0.5))
        sentiment_score = _transformer_score(raw_label, raw_score)
        sentiment_label = _label_from_score(sentiment_score)
        model_version = self.model_revision or _pipeline_version(self._pipeline) or self.model_id
        return SentimentAnalysisResult(
            sentiment_label=sentiment_label,
            sentiment_score=sentiment_score,
            sentiment_confidence=round(raw_score, 3),
            model_name="local-transformer-sentiment-analysis",
            model_version=model_version,
            analysis_version=ANALYSIS_VERSION,
            explanation_factors={
                "strategy": "local_transformer_pipeline",
                "transformer_label": raw_label,
                "transformer_score": round(raw_score, 3),
                "model_id": self.model_id,
                "model_revision": self.model_revision or model_version,
            },
            fallback_note=None,
        )

    @property
    def fallback_note(self) -> str | None:
        if self._unavailable_reason is None:
            return None
        return (
            "Deterministic local lexicon/rule fallback used because the local transformer sentiment runtime "
            f"was unavailable: {self._unavailable_reason}"
        )


def _load_transformer_pipeline(*, model_id: str, revision: str | None):
    from transformers import pipeline

    return pipeline(
        "sentiment-analysis",
        model=model_id,
        revision=revision,
        local_files_only=True,
    )


def _pipeline_version(pipeline_obj) -> str | None:
    model = getattr(pipeline_obj, "model", None)
    config = getattr(model, "config", None)
    for attribute in ("_commit_hash", "name_or_path", "_name_or_path"):
        value = getattr(config, attribute, None) if config is not None else None
        if value:
            return str(value)
    return None


def _transformer_score(raw_label: str, raw_score: float) -> float:
    normalized_label = raw_label.upper()
    centered_score = max(0.0, min(1.0, (raw_score - 0.5) * 2.0))
    if normalized_label in {"POSITIVE", "LABEL_1"}:
        return round(centered_score, 3)
    if normalized_label in {"NEGATIVE", "LABEL_0"}:
        return round(-centered_score, 3)
    return 0.0


def _label_from_score(score: float) -> str:
    if score >= 0.25:
        return "positive"
    if score <= -0.20:
        return "negative"
    return "mixed"


@lru_cache(maxsize=1)
def get_sentiment_analyzer() -> LocalTransformerSentimentAnalyzer:
    return LocalTransformerSentimentAnalyzer()

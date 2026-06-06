from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ml.department_classifier import DepartmentPredictionResult, get_department_classifier
from app.models import Department, NormalizedReview, ReviewAnalysis
from app.sentiment import ANALYSIS_VERSION, get_sentiment_analyzer
from app.semantic_similarity import (
    EmbeddingResult,
    get_semantic_similarity_analyzer,
    split_sentences,
)


URGENCY_TERMS = {
    "angry",
    "broken",
    "dangerous",
    "dirty",
    "hygiene",
    "immediately",
    "late at night",
    "manager",
    "refund",
    "unsafe",
    "urgent",
}


@dataclass(frozen=True)
class SentenceAnalysis:
    sentence: str
    department_code: str
    department_confidence: float
    embedding: list[float] | None


@dataclass(frozen=True)
class AnalysisResult:
    sentiment_label: str
    sentiment_score: float
    sentiment_confidence: float
    department_code: str
    department_confidence: float
    department_model_name: str
    department_model_version: str
    reputation_risk_score: int
    reputation_risk_label: str
    explanation_factors: dict
    embedding: list[float] | None
    embedding_model_name: str | None
    sentence_analyses: list[SentenceAnalysis]


def analyze_and_persist_review(
    session: Session,
    review: NormalizedReview,
    *,
    analyzed_at: datetime | None = None,
) -> ReviewAnalysis:
    analyzed_at = analyzed_at or datetime.now(UTC)
    result = analyze_review(session, review, analyzed_at)
    embedding_result = _embed_review_text(review)
    embedding = embedding_result.embeddings[0] if embedding_result.embeddings else None

    values = {
        "sentiment_label": result.sentiment_label,
        "sentiment_score": result.sentiment_score,
        "sentiment_confidence": result.sentiment_confidence,
        "department_code": result.department_code,
        "department_confidence": result.department_confidence,
        "department_model_name": result.department_model_name,
        "reputation_risk_score": result.reputation_risk_score,
        "reputation_risk_label": result.reputation_risk_label,
        "embedding": embedding,
        "embedding_model_name": embedding_result.model_name or None,
        "embedding_generated_at": analyzed_at if embedding is not None else None,
        "analysis_version": ANALYSIS_VERSION,
        "explanation_factors": result.explanation_factors,
        "analyzed_at": analyzed_at,
        "is_active": True,
    }

    analysis = review.analysis
    if analysis is None:
        analysis = ReviewAnalysis(review_id=review.id, **values)
        session.add(analysis)
        session.flush()
    else:
        for field, value in values.items():
            setattr(analysis, field, value)
        session.flush()

    review.updated_at = analyzed_at
    return analysis


def analyze_review(
    session: Session,
    review: NormalizedReview,
    analyzed_at: datetime,
) -> AnalysisResult:
    text = " ".join(part for part in [review.title, review.body] if part)
    tokens = tokenize(text)

    sentiment_result = get_sentiment_analyzer().analyze(text, tokens, review.rating)

    department_predictions = classify_department(text)
    department_code = department_predictions[0].department_code if department_predictions else "guest_relations"
    department_confidence = department_predictions[0].confidence if department_predictions else 0.3

    department_risk_weight = _get_department_risk_weight(session, department_code)

    urgency_score, urgency_matches = urgency_factor(text)
    duplicate_signal = bool(
        review.normalized_payload.get("duplicate_signal")
        or review.normalized_payload.get("duplicate_review_ids")
    )

    reputation_risk_score, reputation_risk_label, reputation_risk_factors = score_reputation_risk(
        rating=review.rating,
        sentiment_score=sentiment_result.sentiment_score,
        department_risk_weight=department_risk_weight,
        review_date=review.review_date,
        analyzed_at=analyzed_at,
        urgency_score=urgency_score,
        duplicate_signal=duplicate_signal,
        normalized_payload=review.normalized_payload,
    )

    sentences = split_sentences(text)
    sentence_analyses: list[SentenceAnalysis] = []
    if sentences:
        dept_classifier = get_department_classifier()
        embedding_runtime = get_semantic_similarity_analyzer()
        sentence_embeddings = embedding_runtime.embed_batch(sentences) if embedding_runtime.is_available() else EmbeddingResult()
        for i, sentence in enumerate(sentences):
            sent_dept = dept_classifier.classify(sentence)
            sent_emb = sentence_embeddings.embeddings[i] if i < len(sentence_embeddings.embeddings) else None
            sentence_analyses.append(
                SentenceAnalysis(
                    sentence=sentence,
                    department_code=sent_dept[0].department_code if sent_dept else department_code,
                    department_confidence=sent_dept[0].confidence if sent_dept else 0.0,
                    embedding=sent_emb,
                )
            )

    explanation_factors = {
        "sentiment": sentiment_result.explanation_factors,
        "department": {
            "department_code": department_code,
            "department_confidence": department_confidence,
            "predictions": [
                {
                    "department_code": pred.department_code,
                    "confidence": pred.confidence,
                    "rank": pred.rank,
                }
                for pred in department_predictions
            ],
        },
        "reputation_risk": reputation_risk_factors,
        "model": {
            "sentiment_model_name": sentiment_result.model_name,
            "sentiment_model_version": sentiment_result.model_version,
            "analysis_version": ANALYSIS_VERSION,
            "sentiment_confidence": sentiment_result.sentiment_confidence,
            "sentiment_strategy": sentiment_result.explanation_factors["strategy"],
            "fallback_note": sentiment_result.fallback_note,
            "department_model_name": department_predictions[0].model_name if department_predictions else "unavailable",
            "department_model_version": department_predictions[0].model_version if department_predictions else "unavailable",
        },
        "signals": {
            "urgency_terms": urgency_matches,
            "duplicate_signal": duplicate_signal,
        },
    }

    return AnalysisResult(
        sentiment_label=sentiment_result.sentiment_label,
        sentiment_score=sentiment_result.sentiment_score,
        sentiment_confidence=sentiment_result.sentiment_confidence,
        department_code=department_code,
        department_confidence=department_confidence,
        department_model_name=department_predictions[0].model_name if department_predictions else "unavailable",
        department_model_version=department_predictions[0].model_version if department_predictions else "unavailable",
        reputation_risk_score=reputation_risk_score,
        reputation_risk_label=reputation_risk_label,
        explanation_factors=explanation_factors,
        embedding=None,
        embedding_model_name=None,
        sentence_analyses=sentence_analyses,
    )


def classify_department(text: str) -> list[DepartmentPredictionResult]:
    classifier = get_department_classifier()
    return classifier.classify(text, top_k=1)


def _embed_review_text(review: NormalizedReview) -> EmbeddingResult:
    runtime = get_semantic_similarity_analyzer()
    text = " ".join(part for part in [review.title, review.body] if part).strip()
    if not text:
        return EmbeddingResult()
    return runtime.embed_batch([text])


def reanalyze_reviews(
    session: Session,
    *,
    source_code: str | None = None,
    analyzed_at: datetime | None = None,
) -> int:
    analyzed_at = analyzed_at or datetime.now(UTC)
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.analysis),
            selectinload(NormalizedReview.source),
        )
    )
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)

    reviews = list(session.scalars(query.order_by(NormalizedReview.id)))
    for review in reviews:
        analyze_and_persist_review(session, review, analyzed_at=analyzed_at)
    session.commit()
    return len(reviews)


def score_reputation_risk(
    *,
    rating: float | None,
    sentiment_score: float,
    department_risk_weight: int,
    review_date: datetime | None,
    analyzed_at: datetime,
    urgency_score: int,
    duplicate_signal: bool,
    normalized_payload: dict | None = None,
) -> tuple[int, str, dict]:
    rating_points = 0 if rating is None else round(max(0.0, (5.0 - float(rating)) / 4.0) * 30)
    sentiment_points = round(max(0.0, -sentiment_score) * 25)
    department_points = department_risk_weight
    recency_points = recency_factor(review_date, analyzed_at)
    duplicate_points = 5 if duplicate_signal else 0
    visibility_points, visibility_signals = visibility_factor(normalized_payload or {})
    total = int(
        min(
            100,
            rating_points
            + sentiment_points
            + department_points
            + recency_points
            + urgency_score
            + duplicate_points
            + visibility_points,
        )
    )
    if total >= 75:
        label = "critical"
    elif total >= 50:
        label = "high"
    elif total >= 30:
        label = "medium"
    else:
        label = "low"
    return (
        total,
        label,
        {
            "score": total,
            "label": label,
            "weights": {
                "rating": rating_points,
                "sentiment": sentiment_points,
                "department": department_points,
                "recency": recency_points,
                "urgency_terms": urgency_score,
                "duplicate_signal": duplicate_points,
                "platform_visibility": visibility_points,
            },
            "operational_explanations": reputation_risk_explanations(
                rating_points=rating_points,
                sentiment_points=sentiment_points,
                department_points=department_points,
                recency_points=recency_points,
                visibility_signals=visibility_signals,
            ),
            "thresholds": {"low": "0-29", "medium": "30-49", "high": "50-74", "critical": "75-100"},
        },
    )


def recency_factor(review_date: datetime | None, analyzed_at: datetime) -> int:
    if review_date is None:
        return 0
    if review_date.tzinfo is None and analyzed_at.tzinfo is not None:
        review_date = review_date.replace(tzinfo=analyzed_at.tzinfo)
    if analyzed_at.tzinfo is None and review_date.tzinfo is not None:
        analyzed_at = analyzed_at.replace(tzinfo=review_date.tzinfo)
    age_days = max(0, (analyzed_at - review_date).days)
    if age_days <= 7:
        return 5
    if age_days <= 30:
        return 2
    return 0


def visibility_factor(normalized_payload: dict) -> tuple[int, list[str]]:
    signals: list[str] = []
    points = 0
    helpful_votes = first_numeric_payload_value(
        normalized_payload,
        "helpful_votes",
        "provider_helpful_votes",
        "provider_helpful_vote_count",
        "helpful_count",
    )
    if helpful_votes is not None and helpful_votes > 0:
        signals.append("helpful_vote_visibility")
        points += min(5, int(helpful_votes))
    if normalized_payload.get("provider_url"):
        signals.append("public_review_url")
        points += 2
    if (
        normalized_payload.get("provider_has_reply") is False
        or normalized_payload.get("provider_has_management_response") is False
    ):
        signals.append("unreplied_public_review")
        points += 2
    return min(8, points), signals


def first_numeric_payload_value(normalized_payload: dict, *keys: str) -> float | None:
    for key in keys:
        value = normalized_payload.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def reputation_risk_explanations(
    *,
    rating_points: int,
    sentiment_points: int,
    department_points: int,
    recency_points: int,
    visibility_signals: list[str],
) -> list[str]:
    explanations: list[str] = []
    if rating_points >= 15:
        explanations.append("low rating")
    if sentiment_points >= 10:
        explanations.append("negative sentiment")
    if department_points >= 14:
        explanations.append("high-impact department")
    if recency_points:
        explanations.append("recent review")
    if visibility_signals:
        explanations.append("visible platform engagement")
    return explanations


def urgency_factor(text: str) -> tuple[int, list[str]]:
    normalized = text.lower()
    matches = sorted(term for term in URGENCY_TERMS if term in normalized)
    return min(15, len(matches) * 5), matches


def _get_department_risk_weight(session: Session, department_code: str) -> int:
    dept = session.get(Department, department_code)
    if dept is not None:
        return dept.risk_weight
    return 12


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z][a-z-]+", lowered))
    phrases = {phrase for phrase in URGENCY_TERMS if " " in phrase and phrase in lowered}
    return words | phrases

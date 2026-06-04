from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.ml.issue_classifier import IssueCategoryPredictionResult, get_issue_category_classifier
from app.models import CategoryDepartmentMapping, NormalizedReview, ReviewAnalysis, ReviewIssueCategoryPrediction
from app.sentiment import ANALYSIS_VERSION, get_sentiment_analyzer


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
CATEGORY_REPUTATION_RISK_WEIGHT = {
    "cleanliness": 18,
    "booking_checkin": 16,
    "room_condition": 15,
    "staff_behavior": 14,
    "noise_events": 13,
    "service_delay": 12,
    "food_beverage": 11,
    "amenities_facilities": 10,
    "pricing_value": 9,
    "other_uncategorized": 6,
    "positive_general": 0,
}


@dataclass(frozen=True)
class AnalysisResult:
    sentiment_label: str
    sentiment_score: float
    sentiment_confidence: float
    issue_category_code: str
    issue_category_predictions: list[IssueCategoryPredictionResult]
    reputation_risk_score: int
    reputation_risk_label: str
    department_code: str
    explanation_factors: dict


def analyze_and_persist_review(session: Session, review: NormalizedReview, analyzed_at: datetime | None = None) -> ReviewAnalysis:
    analyzed_at = analyzed_at or datetime.now(UTC)
    result = analyze_review(session, review, analyzed_at)
    values = {
        "sentiment_label": result.sentiment_label,
        "sentiment_score": result.sentiment_score,
        "sentiment_confidence": result.sentiment_confidence,
        "issue_category_code": result.issue_category_code,
        "reputation_risk_score": result.reputation_risk_score,
        "reputation_risk_label": result.reputation_risk_label,
        "department_code": result.department_code,
        "model_name": result.explanation_factors["model"]["sentiment_model_name"],
        "model_version": result.explanation_factors["model"]["sentiment_model_version"],
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
        analysis.issue_category_predictions.clear()
        session.flush()

    analysis.issue_category_predictions = [
        ReviewIssueCategoryPrediction(
            category_code=prediction.category_code,
            confidence=prediction.confidence,
            rank=prediction.rank,
            is_primary=prediction.rank == 1,
            department_code=primary_department_for_category(session, prediction.category_code),
            model_name=prediction.model_name,
            model_version=prediction.model_version,
            analyzed_at=analyzed_at,
        )
        for prediction in result.issue_category_predictions
    ]

    review.sentiment_label = result.sentiment_label
    review.sentiment_score = result.sentiment_score
    review.issue_category_code = result.issue_category_code
    review.reputation_risk = result.reputation_risk_label
    review.department_code = result.department_code
    review.updated_at = analyzed_at
    return analysis


def analyze_review(session: Session, review: NormalizedReview, analyzed_at: datetime) -> AnalysisResult:
    text = " ".join(part for part in [review.title, review.body] if part)
    tokens = tokenize(text)
    sentiment_result = get_sentiment_analyzer().analyze(text, tokens, review.rating)
    issue_category_predictions, category_factors = classify_issue_categories(text)
    issue_category_code = issue_category_predictions[0].category_code
    department_code = primary_department_for_category(session, issue_category_code)
    urgency_score, urgency_matches = urgency_factor(text)
    recurrence_count = recurrence_count_7d(session, review, issue_category_code, analyzed_at)
    duplicate_signal = bool(review.normalized_payload.get("duplicate_signal") or review.normalized_payload.get("duplicate_review_ids"))
    reputation_risk_score, reputation_risk_label, reputation_risk_factors = score_reputation_risk(
        rating=review.rating,
        sentiment_score=sentiment_result.sentiment_score,
        issue_category_code=issue_category_code,
        review_date=review.review_date,
        analyzed_at=analyzed_at,
        urgency_score=urgency_score,
        recurrence_count=recurrence_count,
        duplicate_signal=duplicate_signal,
        normalized_payload=review.normalized_payload,
    )
    explanation_factors = {
        "sentiment": sentiment_result.explanation_factors,
        "issue_category": category_factors,
        "reputation_risk": reputation_risk_factors,
        "department": {
            "department_code": department_code,
            "mapping_source": "category_department_mappings.primary",
        },
        "model": {
            "sentiment_model_name": sentiment_result.model_name,
            "sentiment_model_version": sentiment_result.model_version,
            "analysis_version": ANALYSIS_VERSION,
            "sentiment_confidence": sentiment_result.sentiment_confidence,
            "sentiment_strategy": sentiment_result.explanation_factors["strategy"],
            "fallback_note": sentiment_result.fallback_note,
            "issue_classifier_model": issue_category_predictions[0].model_name,
            "issue_classifier_version": issue_category_predictions[0].model_version,
        },
        "signals": {
            "urgency_terms": urgency_matches,
            "recurrence_count_7d": recurrence_count,
            "duplicate_signal": duplicate_signal,
        },
    }
    return AnalysisResult(
        sentiment_label=sentiment_result.sentiment_label,
        sentiment_score=sentiment_result.sentiment_score,
        sentiment_confidence=sentiment_result.sentiment_confidence,
        issue_category_code=issue_category_code,
        issue_category_predictions=issue_category_predictions,
        reputation_risk_score=reputation_risk_score,
        reputation_risk_label=reputation_risk_label,
        department_code=department_code,
        explanation_factors=explanation_factors,
    )


def classify_issue_categories(text: str) -> tuple[list[IssueCategoryPredictionResult], dict]:
    classifier = get_issue_category_classifier()
    predictions = classifier.predict_ranked(text, top_k=3)
    return predictions, {
        "predictions": [
            {
                "category_code": prediction.category_code,
                "confidence": prediction.confidence,
                "rank": prediction.rank,
                "model_name": prediction.model_name,
                "model_version": prediction.model_version,
            }
            for prediction in predictions
        ],
        "mapping_source": "huggingface_zero_shot_classification",
    }


def reanalyze_reviews(
    session: Session,
    *,
    source_code: str | None = None,
    source_type: str | None = None,
    analyzed_at: datetime | None = None,
) -> int:
    analyzed_at = analyzed_at or datetime.now(UTC)
    query = (
        select(NormalizedReview)
        .join(NormalizedReview.source)
        .options(
            selectinload(NormalizedReview.analysis).selectinload(ReviewAnalysis.issue_category_predictions),
            selectinload(NormalizedReview.source),
        )
    )
    if source_code is not None:
        query = query.where(NormalizedReview.source_code == source_code)
    if source_type is not None:
        query = query.where(NormalizedReview.source.has(source_type=source_type))

    reviews = list(session.scalars(query.order_by(NormalizedReview.id)))
    for review in reviews:
        analyze_and_persist_review(session, review, analyzed_at)
    session.commit()
    return len(reviews)


def score_reputation_risk(
    *,
    rating: float | None,
    sentiment_score: float,
    issue_category_code: str,
    review_date: datetime | None,
    analyzed_at: datetime,
    urgency_score: int,
    recurrence_count: int,
    duplicate_signal: bool,
    normalized_payload: dict | None = None,
) -> tuple[int, str, dict]:
    rating_points = 0 if rating is None else round(max(0.0, (5.0 - float(rating)) / 4.0) * 30)
    sentiment_points = round(max(0.0, -sentiment_score) * 25)
    category_points = CATEGORY_REPUTATION_RISK_WEIGHT.get(issue_category_code, 6)
    recency_points = recency_factor(review_date, analyzed_at)
    recurrence_points = min(10, max(0, recurrence_count - 1) * 3)
    duplicate_points = 5 if duplicate_signal else 0
    visibility_points, visibility_signals = visibility_factor(normalized_payload or {})
    total = int(min(
        100,
        rating_points
        + sentiment_points
        + category_points
        + recency_points
        + urgency_score
        + recurrence_points
        + duplicate_points
        + visibility_points,
    ))
    if total >= 75:
        label = "critical"
    elif total >= 50:
        label = "high"
    elif total >= 30:
        label = "medium"
    else:
        label = "low"
    return total, label, {
        "score": total,
        "label": label,
        "weights": {
            "rating": rating_points,
            "sentiment": sentiment_points,
            "issue_category": category_points,
            "recency": recency_points,
            "urgency_terms": urgency_score,
            "recurrence": recurrence_points,
            "duplicate_signal": duplicate_points,
            "platform_visibility": visibility_points,
        },
        "operational_explanations": reputation_risk_explanations(
            rating_points=rating_points,
            sentiment_points=sentiment_points,
            category_points=category_points,
            recency_points=recency_points,
            recurrence_points=recurrence_points,
            visibility_signals=visibility_signals,
        ),
        "thresholds": {"low": "0-29", "medium": "30-49", "high": "50-74", "critical": "75-100"},
    }


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
    if normalized_payload.get("provider_has_reply") is False or normalized_payload.get("provider_has_management_response") is False:
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
    category_points: int,
    recency_points: int,
    recurrence_points: int,
    visibility_signals: list[str],
) -> list[str]:
    explanations: list[str] = []
    if rating_points >= 15:
        explanations.append("low rating")
    if sentiment_points >= 10:
        explanations.append("negative sentiment")
    if category_points >= 14:
        explanations.append("high-impact issue category")
    if recency_points:
        explanations.append("recent review")
    if recurrence_points:
        explanations.append("recent recurrence")
    if visibility_signals:
        explanations.append("visible platform engagement")
    return explanations


def urgency_factor(text: str) -> tuple[int, list[str]]:
    normalized = text.lower()
    matches = sorted(term for term in URGENCY_TERMS if term in normalized)
    return min(15, len(matches) * 5), matches


def recurrence_count_7d(
    session: Session,
    review: NormalizedReview,
    issue_category_code: str,
    analyzed_at: datetime,
) -> int:
    if review.review_date is None:
        return 1
    window_start = review.review_date - timedelta(days=7)
    window_end = review.review_date + timedelta(days=7)
    count = session.scalar(
        select(func.count(NormalizedReview.id))
        .where(NormalizedReview.id != review.id)
        .where(NormalizedReview.issue_category_code == issue_category_code)
        .where(NormalizedReview.review_date.is_not(None))
        .where(NormalizedReview.review_date >= window_start)
        .where(NormalizedReview.review_date <= window_end)
    )
    return (count or 0) + 1


def primary_department_for_category(session: Session, issue_category_code: str) -> str:
    mapping = session.scalar(
        select(CategoryDepartmentMapping)
        .where(CategoryDepartmentMapping.category_code == issue_category_code)
        .where(CategoryDepartmentMapping.is_primary.is_(True))
        .limit(1)
    )
    if mapping is None:
        return "guest_relations"
    return mapping.department_code


def tokenize(text: str) -> set[str]:
    lowered = text.lower()
    words = set(re.findall(r"[a-z][a-z-]+", lowered))
    phrases = {phrase for phrase in URGENCY_TERMS if " " in phrase and phrase in lowered}
    return words | phrases

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CategoryDepartmentMapping, NormalizedReview, ReviewAnalysis


ANALYSIS_VERSION = "analysis-v1"
MODEL_NAME = "local-deterministic-review-analysis"
MODEL_VERSION = "2026.07.demo-fallback"

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
CATEGORY_RULES = {
    "cleanliness": {"bathroom", "clean", "cleaned", "dirty", "floor", "hygiene", "linen", "sink"},
    "room_condition": {
        "air",
        "conditioning",
        "cool",
        "drained",
        "fittings",
        "maintenance",
        "plumbing",
        "room",
        "shower",
        "worn",
    },
    "food_beverage": {"bar", "breakfast", "buffet", "dining", "food", "restaurant", "room service"},
    "service_delay": {"delay", "delayed", "hours", "long", "queue", "quickly", "slow", "stretched", "took"},
    "staff_behavior": {"attitude", "courtesy", "helpful", "professional", "rude", "staff", "team"},
    "noise_events": {"audible", "banquet", "event", "late at night", "music", "noise", "noisy", "sleep"},
    "pricing_value": {"billing", "expensive", "overpriced", "price", "value"},
    "booking_checkin": {"arrival", "booking", "check-in", "checkout", "desk", "prepaid", "reservation"},
    "amenities_facilities": {"gym", "lift", "parking", "pool", "spa", "wi-fi", "wifi"},
}
CATEGORY_SEVERITY_WEIGHT = {
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
    severity_score: int
    severity_label: str
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
        "severity_score": result.severity_score,
        "severity_label": result.severity_label,
        "department_code": result.department_code,
        "model_name": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "analysis_version": ANALYSIS_VERSION,
        "explanation_factors": result.explanation_factors,
        "analyzed_at": analyzed_at,
        "is_active": True,
    }

    analysis = review.analysis
    if analysis is None:
        analysis = ReviewAnalysis(review_id=review.id, **values)
        session.add(analysis)
    else:
        for field, value in values.items():
            setattr(analysis, field, value)

    review.sentiment_label = result.sentiment_label
    review.sentiment_score = result.sentiment_score
    review.issue_category_code = result.issue_category_code
    review.severity = result.severity_label
    review.department_code = result.department_code
    review.updated_at = analyzed_at
    return analysis


def analyze_review(session: Session, review: NormalizedReview, analyzed_at: datetime) -> AnalysisResult:
    text = " ".join(part for part in [review.title, review.body] if part)
    tokens = tokenize(text)
    sentiment_label, sentiment_score, sentiment_confidence, sentiment_factors = score_sentiment(tokens, review.rating)
    issue_category_code, category_factors = classify_issue_category(tokens, sentiment_label)
    department_code = primary_department_for_category(session, issue_category_code)
    urgency_score, urgency_matches = urgency_factor(text)
    recurrence_count = recurrence_count_7d(session, review, issue_category_code, analyzed_at)
    duplicate_signal = bool(review.normalized_payload.get("duplicate_signal") or review.normalized_payload.get("duplicate_review_ids"))
    severity_score, severity_label, severity_factors = score_severity(
        rating=review.rating,
        sentiment_score=sentiment_score,
        issue_category_code=issue_category_code,
        urgency_score=urgency_score,
        recurrence_count=recurrence_count,
        duplicate_signal=duplicate_signal,
    )
    explanation_factors = {
        "sentiment": sentiment_factors,
        "issue_category": category_factors,
        "severity": severity_factors,
        "department": {
            "department_code": department_code,
            "mapping_source": "category_department_mappings.primary",
        },
        "model": {
            "model_name": MODEL_NAME,
            "model_version": MODEL_VERSION,
            "analysis_version": ANALYSIS_VERSION,
            "fallback_note": (
                "Deterministic local lexicon/rule fallback used for demo-safe analysis because transformer "
                "sentiment dependencies are not installed in this prototype environment."
            ),
        },
        "signals": {
            "urgency_terms": urgency_matches,
            "recurrence_count_7d": recurrence_count,
            "duplicate_signal": duplicate_signal,
        },
    }
    return AnalysisResult(
        sentiment_label=sentiment_label,
        sentiment_score=sentiment_score,
        sentiment_confidence=sentiment_confidence,
        issue_category_code=issue_category_code,
        severity_score=severity_score,
        severity_label=severity_label,
        department_code=department_code,
        explanation_factors=explanation_factors,
    )


def score_sentiment(tokens: set[str], rating: float | None) -> tuple[str, float, float, dict]:
    positive_matches = sorted(tokens & POSITIVE_TERMS)
    negative_matches = sorted(tokens & NEGATIVE_TERMS)
    lexical_score = (len(positive_matches) - len(negative_matches)) / max(
        len(positive_matches) + len(negative_matches),
        3,
    )
    rating_score = 0.0 if rating is None else max(min((float(rating) - 3.0) / 2.0, 1.0), -1.0)
    combined = (0.62 * lexical_score) + (0.38 * rating_score)
    combined = round(max(min(combined, 1.0), -1.0), 3)
    if combined >= 0.25:
        label = "positive"
    elif combined <= -0.20:
        label = "negative"
    else:
        label = "mixed"
    confidence = round(min(0.95, 0.55 + abs(combined) * 0.4 + min(len(positive_matches) + len(negative_matches), 4) * 0.04), 3)
    return label, combined, confidence, {
        "rating_score": round(rating_score, 3),
        "lexical_score": round(lexical_score, 3),
        "positive_terms": positive_matches,
        "negative_terms": negative_matches,
    }


def classify_issue_category(tokens: set[str], sentiment_label: str) -> tuple[str, dict]:
    scores = {
        category: len({term for term in terms if term in tokens})
        for category, terms in CATEGORY_RULES.items()
    }
    category, score = max(scores.items(), key=lambda item: (item[1], CATEGORY_SEVERITY_WEIGHT.get(item[0], 0)))
    if sentiment_label == "positive" and score <= 2:
        category = "positive_general"
        score = 0
    if score == 0:
        category = "positive_general" if sentiment_label == "positive" else "other_uncategorized"
    return category, {
        "rule_scores": scores,
        "selected_category": category,
        "mapping_source": "local_keyword_rules",
    }


def score_severity(
    *,
    rating: float | None,
    sentiment_score: float,
    issue_category_code: str,
    urgency_score: int,
    recurrence_count: int,
    duplicate_signal: bool,
) -> tuple[int, str, dict]:
    rating_points = 0 if rating is None else round(max(0.0, (5.0 - float(rating)) / 4.0) * 30)
    sentiment_points = round(max(0.0, -sentiment_score) * 25)
    category_points = CATEGORY_SEVERITY_WEIGHT.get(issue_category_code, 6)
    recurrence_points = min(10, max(0, recurrence_count - 1) * 3)
    duplicate_points = 5 if duplicate_signal else 0
    total = int(min(100, rating_points + sentiment_points + category_points + urgency_score + recurrence_points + duplicate_points))
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
            "urgency_terms": urgency_score,
            "recurrence": recurrence_points,
            "duplicate_signal": duplicate_points,
        },
        "thresholds": {"low": "0-29", "medium": "30-49", "high": "50-74", "critical": "75-100"},
    }


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
    phrases = {phrase for phrase in {term for terms in CATEGORY_RULES.values() for term in terms} | URGENCY_TERMS if " " in phrase and phrase in lowered}
    return words | phrases

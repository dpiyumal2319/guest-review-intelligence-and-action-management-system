from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import hashlib
import math
import os
import re

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import (
    DetectedIssue,
    Department,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    ReviewAnalysis,
)
from app.semantic_similarity import (
    centroid_similarity,
    compute_centroid,
    get_semantic_similarity_analyzer,
    split_sentences,
)
from app.ml.department_classifier import get_department_classifier

SIMILARITY_THRESHOLD = 0.75
RECURRENCE_WINDOW_DAYS = 30
MIN_EVIDENCE_FOR_PROMOTION = 2
SINGLE_CRITICAL_RISK_THRESHOLD = 75

DEDUP_CENTROID_SIMILARITY = 0.92
DEDUP_TITLE_OVERLAP_THRESHOLD = 0.70

_DEPARTMENT_DISPLAY_NAMES: dict[str, str] = {
    "housekeeping": "Housekeeping & Room Cleanliness",
    "front_office": "Front Office & Reception",
    "food_beverage": "Food & Beverage",
    "engineering": "Engineering & Maintenance",
    "management": "Hotel Management & Policy",
    "guest_relations": "Guest Relations & Service",
}

_GENERIC_TITLE_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^(issue|problem|complaint|concern|matter|topic)(\s|$)",
        r"^(guest|customer|client)\s+(issue|problem|complaint|concern)",
        r"^(room|hotel|property|facility)\s+(issue|problem)",
        r"^(staff|service)\s+(issue|problem|complaint)",
        r"^(general|various|multiple|several)\s+(issue|problem)",
        r"^\w+\s+\w+$",
        r"^(about|regarding|concerning)\s+",
    ]
]


def detect_issues(
    session: Session,
    *,
    force: bool = False,
) -> dict:
    created = 0
    updated = 0
    linked = 0
    merged = 0

    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] = {}

    existing_issues = list(session.scalars(select(DetectedIssue)))

    unlinked_reviews = _get_unlinked_reviews(session, force=force)

    for review in unlinked_reviews:
        linked_count = _match_review_against_issues(session, review, existing_issues, _sentence_vector_cache)
        linked += linked_count

    session.flush()

    singletons = _get_unlinked_negative_reviews(session)

    emerging_clusters = _find_emerging_clusters(session, singletons, _sentence_vector_cache)

    new_issue_ids: list[int] = []
    for cluster in emerging_clusters:
        issue = _promote_cluster(session, cluster, _sentence_vector_cache)
        if issue is not None:
            created += 1
            existing_issues.append(issue)
            new_issue_ids.append(issue.id)

    session.flush()

    if created > 0:
        merged = _deduplicate_issues(session, new_issue_ids)

    for issue in existing_issues:
        if issue.status == "active":
            _update_issue_from_links(session, issue, _sentence_vector_cache)
            updated += 1

    session.commit()
    return {"created": created, "updated": updated, "linked": linked, "merged": merged}


def _get_unlinked_reviews(session: Session, *, force: bool = False) -> list[NormalizedReview]:
    if force:
        return list(session.scalars(
            select(NormalizedReview)
            .where(NormalizedReview.analysis.has(ReviewAnalysis.embedding.is_not(None)))
            .order_by(NormalizedReview.id)
        ))

    linked_review_ids = set(
        session.scalars(select(IssueReviewLink.review_id))
    )

    return list(session.scalars(
        select(NormalizedReview)
        .where(
            and_(
                NormalizedReview.analysis.has(ReviewAnalysis.embedding.is_not(None)),
                NormalizedReview.id.notin_(linked_review_ids) if linked_review_ids else True,
            )
        )
        .order_by(NormalizedReview.id)
    ))


def _get_unlinked_negative_reviews(session: Session) -> list[NormalizedReview]:
    linked_ids = set(session.scalars(select(IssueReviewLink.review_id)))
    return list(session.scalars(
        select(NormalizedReview).where(
            and_(
                NormalizedReview.analysis.has(
                    and_(
                        ReviewAnalysis.embedding.is_not(None),
                        ReviewAnalysis.sentiment_label.in_(["negative", "mixed"]),
                    )
                ),
                NormalizedReview.id.notin_(linked_ids) if linked_ids else True,
            )
        ).order_by(NormalizedReview.review_date.desc(), NormalizedReview.id)
    ))


def _build_sentence_vectors(
    review: NormalizedReview,
    cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> list[tuple[str, str, list[float]]]:
    if cache is not None and review.id in cache:
        return cache[review.id]
    text = review.body or ""
    sentences = split_sentences(text)
    if not sentences:
        result: list[tuple[str, str, list[float]]] = []
        if cache is not None:
            cache[review.id] = result
        return result

    dept_classifier = get_department_classifier()
    embedding_runtime = get_semantic_similarity_analyzer()

    dept_results = dept_classifier.classify_batch(sentences)
    sentence_depts = [r[0].department_code for r in dept_results] if dept_results else []

    sentence_embeddings: list[list[float]] = []
    if embedding_runtime.is_available():
        emb_result = embedding_runtime.embed_batch(sentences)
        sentence_embeddings = emb_result.embeddings
        if len(sentence_embeddings) < len(sentences):
            sentence_embeddings = []
    else:
        sentence_embeddings = []

    results: list[tuple[str, str, list[float]]] = []
    for i, sentence in enumerate(sentences):
        dept = sentence_depts[i] if i < len(sentence_depts) else "guest_relations"
        emb = sentence_embeddings[i] if i < len(sentence_embeddings) else []
        if emb:
            results.append((sentence, dept, emb))
    if cache is not None:
        cache[review.id] = results
    return results


def _match_review_against_issues(
    session: Session,
    review: NormalizedReview,
    issues: list[DetectedIssue],
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> int:
    linked_count = 0

    sentence_vectors = _build_sentence_vectors(review, _sentence_vector_cache)
    if not sentence_vectors:
        return 0

    now = datetime.now(UTC)
    matched_issue_ids: set[int] = set()

    for sentence_text, sentence_dept, sentence_emb in sentence_vectors:
        for issue in issues:
            if issue.id in matched_issue_ids:
                continue
            if issue.department_code != sentence_dept:
                continue

            similarity = centroid_similarity(issue.cluster_centroid, sentence_emb)
            if similarity < SIMILARITY_THRESHOLD:
                continue

            existing_link = session.scalar(
                select(IssueReviewLink).where(
                    and_(
                        IssueReviewLink.issue_id == issue.id,
                        IssueReviewLink.review_id == review.id,
                    )
                )
            )
            if existing_link is not None:
                matched_issue_ids.add(issue.id)
                continue

            is_triggering = _is_triggering_evidence(review)

            link = IssueReviewLink(
                issue_id=issue.id,
                review_id=review.id,
                similarity_score=round(similarity, 4),
                linked_at=now,
                is_triggering_evidence=is_triggering,
                evidence_snippet=sentence_text[:500],
            )
            session.add(link)
            matched_issue_ids.add(issue.id)
            linked_count += 1

            session.add(
                IssueEvent(
                    issue_id=issue.id,
                    event_type="linked_review",
                    actor="system",
                    old_value=None,
                    new_value=str(review.id),
                    note=f"Review #{review.id} sentence matched with similarity {similarity:.3f}",
                    created_at=now,
                )
            )

            if is_triggering:
                _recompute_issue_centroid(session, issue)
                issue.recurrence_count = _count_triggering_reviews(session, issue)
                issue.last_seen_at = now
                if review.analysis is not None:
                    issue.reputation_risk_score = max(
                        issue.reputation_risk_score,
                        review.analysis.reputation_risk_score,
                    )

            was_resolved = issue.status == "resolved"
            if was_resolved and is_triggering:
                issue.status = "recurred"
                issue.recurred_at = now
                session.add(
                    IssueEvent(
                        issue_id=issue.id,
                        event_type="recurred",
                        actor="system",
                        old_value="resolved",
                        new_value="recurred",
                        note=f"Reopened due to new matching review #{review.id}",
                        created_at=now,
                    )
                )

    return linked_count


def _is_triggering_evidence(review: NormalizedReview) -> bool:
    if review.review_date is None:
        return False
    window_start = datetime.now(UTC) - timedelta(days=RECURRENCE_WINDOW_DAYS)
    if review.review_date < window_start:
        return False
    return True


def _extract_evidence_snippet(body: str) -> str | None:
    if not body:
        return None
    return body[:500] if len(body) > 500 else body


def _find_emerging_clusters(
    session: Session,
    singletons: list[NormalizedReview],
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> list[dict]:
    groups_by_dept: dict[str, list[NormalizedReview]] = {}
    for review in singletons:
        sentence_depts = {
            sentence_dept
            for _sentence, sentence_dept, _embedding in _build_sentence_vectors(review, _sentence_vector_cache)
        }
        for dept in sentence_depts:
            groups_by_dept.setdefault(dept, []).append(review)

    clusters: list[dict] = []

    for dept, reviews in groups_by_dept.items():
        visited: set[int] = set()
        for i in range(len(reviews)):
            if reviews[i].id in visited:
                continue

            component: list[NormalizedReview] = [reviews[i]]
            visited.add(reviews[i].id)

            a_vectors = _build_sentence_vectors(reviews[i], _sentence_vector_cache)

            for j in range(i + 1, len(reviews)):
                if reviews[j].id in visited:
                    continue

                b_vectors = _build_sentence_vectors(reviews[j], _sentence_vector_cache)

                max_sim = _max_sentence_pair_similarity(a_vectors, b_vectors, department_code=dept)

                if max_sim >= SIMILARITY_THRESHOLD:
                    component.append(reviews[j])
                    visited.add(reviews[j].id)

            if len(component) >= MIN_EVIDENCE_FOR_PROMOTION:
                clusters.append({
                    "department_code": dept,
                    "reviews": component,
                })
            elif len(component) == 1 and component[0].analysis is not None:
                risk = component[0].analysis.reputation_risk_score
                if risk >= SINGLE_CRITICAL_RISK_THRESHOLD:
                    clusters.append({
                        "department_code": dept,
                        "reviews": component,
                    })

    return clusters


def _max_sentence_pair_similarity(
    a_vectors: list[tuple[str, str, list[float]]],
    b_vectors: list[tuple[str, str, list[float]]],
    *,
    department_code: str | None = None,
) -> float:
    if not a_vectors or not b_vectors:
        return 0.0
    best = 0.0
    for _, a_dept, a_emb in a_vectors:
        if department_code is not None and a_dept != department_code:
            continue
        for _, b_dept, b_emb in b_vectors:
            if department_code is not None and b_dept != department_code:
                continue
            if department_code is None and a_dept != b_dept:
                continue
            sim = centroid_similarity(a_emb, b_emb)
            if sim > best:
                best = sim
    return best


def _promote_cluster(
    session: Session,
    cluster: dict,
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> DetectedIssue | None:
    reviews: list[NormalizedReview] = cluster["reviews"]
    if not reviews:
        return None

    department_code = cluster["department_code"]
    now = datetime.now(UTC)

    centroid_vectors: list[list[float]] = []
    evidence_sentences: list[str] = []
    for review in reviews:
        sentence_vectors = _build_sentence_vectors(review, _sentence_vector_cache)
        for _sentence, s_dept, s_emb in sentence_vectors:
            if s_dept == department_code:
                centroid_vectors.append(s_emb)
                evidence_sentences.append(_sentence)

    if not centroid_vectors:
        return None

    centroid = compute_centroid(centroid_vectors)

    review_ids = sorted(r.id for r in reviews)
    cluster_key = _build_cluster_key(department_code, review_ids)

    existing = session.scalar(
        select(DetectedIssue).where(DetectedIssue.cluster_key == cluster_key)
    )
    if existing is not None:
        return None

    embedding_runtime = get_semantic_similarity_analyzer()
    embedding_model_name = embedding_runtime.metadata().embedding_model_name or "unknown"

    risk_scores = [
        r.analysis.reputation_risk_score
        for r in reviews
        if r.analysis is not None
    ]
    max_risk = max(risk_scores) if risk_scores else 0

    department_name: str = _DEPARTMENT_DISPLAY_NAMES.get(department_code, department_code) or department_code
    title = _generate_operational_title(evidence_sentences, department_name)
    quality_score = _score_title_quality(title, evidence_sentences)
    keywords = _extract_keywords(evidence_sentences, department_code)
    generator_info = _get_title_generator_info()

    issue = DetectedIssue(
        title=title,
        department_code=department_code,
        status="active",
        priority=_priority_from_risk(max_risk),
        reputation_risk_score=max_risk,
        recurrence_count=len(reviews),
        first_seen_at=min(r.review_date or now for r in reviews),
        last_seen_at=now,
        assignee_name=None,
        cluster_key=cluster_key,
        cluster_centroid=centroid,
        embedding_model_name=embedding_model_name,
        title_generated_by=generator_info[0],
        title_generation_model=generator_info[1],
        title_confidence=generator_info[2],
        keywords=keywords,
        title_quality_score=quality_score,
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    session.flush()

    note = f"Issue created from {len(reviews)} reviews in {department_code}"
    if len(reviews) == 1:
        note = f"Issue created from single critical review in {department_code} (risk >= {SINGLE_CRITICAL_RISK_THRESHOLD})"

    session.add(
        IssueEvent(
            issue_id=issue.id,
            event_type="created",
            actor="system",
            old_value=None,
            new_value="active",
            note=note,
            created_at=now,
        )
    )

    for review in reviews:
        similarity = 0.0
        sentence_vectors = _build_sentence_vectors(review, _sentence_vector_cache)
        best_sim = 0.0
        best_sentence = None
        for st, s_dept, s_emb in sentence_vectors:
            if s_dept == department_code:
                sim = centroid_similarity(centroid, s_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_sentence = st
        if best_sim == 0.0 and review.analysis is not None and review.analysis.embedding is not None:
            best_sim = centroid_similarity(centroid, review.analysis.embedding)
            best_sentence = review.body[:500]
        similarity = best_sim

        evidence = best_sentence[:500] if best_sentence else _extract_evidence_snippet(review.body)

        link = IssueReviewLink(
            issue_id=issue.id,
            review_id=review.id,
            similarity_score=round(similarity, 4),
            linked_at=now,
            is_triggering_evidence=True,
            evidence_snippet=evidence,
        )
        session.add(link)

        session.add(
            IssueEvent(
                issue_id=issue.id,
                event_type="linked_review",
                actor="system",
                old_value=None,
                new_value=str(review.id),
                note=f"Review #{review.id} linked as founding evidence",
                created_at=now,
            )
        )

    session.add(
        IssueEvent(
            issue_id=issue.id,
            event_type="title_generated",
            actor="system",
            old_value=None,
            new_value=title,
            note=f"Title generated by {generator_info[0]} (quality: {quality_score:.2f})",
            created_at=now,
        )
    )

    return issue


def _generate_operational_title(
    evidence_sentences: list[str],
    department_name: str,
) -> str:
    unique_sentences: list[str] = []
    seen: set[str] = set()
    for s in evidence_sentences:
        key = s.strip().lower()
        if key and key not in seen:
            unique_sentences.append(s.strip())
            seen.add(key)

    if not unique_sentences:
        return "Guest-reported operational issue"

    generator_info = _get_title_generator_info()

    if generator_info[0] == "flan-t5":
        try:
            result = _flan_t5_operational_title(unique_sentences, department_name)
            if result and len(result.split()) >= 3:
                return result[:200]
        except Exception:
            pass

    return _extractive_title(unique_sentences)


def _flan_t5_operational_title(
    sentences: list[str],
    department_name: str,
) -> str:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_id = "google/flan-t5-base"
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_id, local_files_only=True)

    complaint_list = "\n".join(f"  - {s[:200]}" for s in sentences[:5])

    prompt = f"""Task: Write a short operational issue title from hotel guest complaints.

Example 1
Complaints:
  - AC not cooling, room was very hot
Issue title: AC not cooling

Example 2
Complaints:
  - bathroom had black mold in shower, drain was clogged
Issue title: Bathroom shower mold and clogged drain

Example 3
Complaints:
  - waited 45 minutes for check-in, front desk understaffed
Issue title: Check-in wait times exceeding 45 minutes

Example 4
Complaints:
  - room service delivered cold food after 90 minute wait
Issue title: Room service delivering cold meals after long wait

Example 5
Complaints:
  - breakfast buffet items not refilled, staff unprepared for peak
Issue title: Breakfast buffet not replenished during peak hours

Example 6
Complaints:
  - loud music from event kept us awake until 2am
Issue title: Noise disturbance from event on lower floors

Now do this:
Complaints:
{complaint_list}
Issue title:"""
    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=768)
    outputs = model.generate(
        **inputs,
        max_new_tokens=20,
        do_sample=False,
        num_beams=3,
        no_repeat_ngram_size=2,
        early_stopping=True,
    )
    title = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    title = _clean_title(title)

    if not title or len(title.split()) < 3:
        return _extractive_title(sentences)

    if _is_generic_title(title):
        return _extractive_title(sentences)

    return title[:200]


def _clean_title(title: str) -> str:
    title = title.strip().strip('"').strip("'")
    prefixes = [
        "title:", "issue:", "problem:", "topic:", "the", "a ", "an ",
        "generate a", "here is", "this is", "complaints:", "complaint:",
    ]
    lower = title.lower()
    for prefix in prefixes:
        if lower.startswith(prefix):
            title = title[len(prefix):].strip()

    if title and title[0].islower():
        title = title[0].upper() + title[1:]

    return title.strip()


def _is_generic_title(title: str) -> bool:
    if len(title.split()) < 3:
        return True

    for pattern in _GENERIC_TITLE_PATTERNS:
        if pattern.search(title):
            return True

    generic_words = {"issue", "problem", "complaint", "concern", "feedback", "matter", "topic", "thing"}
    title_words = set(w.lower() for w in title.split())
    if len(title_words) <= 2 and title_words & generic_words:
        return True

    return False


def _score_title_quality(
    title: str,
    evidence_sentences: list[str],
) -> float:
    score = 0.5

    word_count = len(title.split())
    if 5 <= word_count <= 12:
        score += 0.15
    elif 13 <= word_count <= 16:
        score += 0.05

    if _is_generic_title(title):
        score -= 0.4

    evidence_words: set[str] = set()
    for s in evidence_sentences:
        for w in s.lower().split():
            if len(w) > 3:
                evidence_words.add(w.strip(".,;:!?\"'()[]"))
    title_lower = title.lower()
    matches = sum(1 for w in evidence_words if w in title_lower)
    if matches >= 3:
        score += 0.15
    elif matches >= 1:
        score += 0.05

    specificity_markers = [
        "broken", "failing", "slow", "delayed", "missing", "dirty",
        "cold", "hot", "noisy", "leaking", "clogged", "overflowing",
        "not working", "unavailable", "insufficient", "overcrowded",
        "waiting", "queue", "minutes", "hours", "degrees", "floors",
        "rooms", "restaurant", "buffet", "bathroom", "shower", "ac",
        "air condition", "check-in", "checkout", "billing", "reservation",
    ]
    if any(marker in title_lower for marker in specificity_markers):
        score += 0.10

    score = max(0.0, min(score, 1.0))
    return round(score, 4)


def _extractive_title(sentences: list[str]) -> str:
    unique: list[str] = []
    seen: set[str] = set()
    for s in sentences:
        key = s.strip().lower()
        if key and key not in seen:
            unique.append(s.strip())
            seen.add(key)

    if not unique:
        return "Guest-reported operational issue"

    key_phrases: list[tuple[str, int]] = []
    complaint_verbs = {
        "broken", "not working", "not cooling", "not cleaned", "dirty",
        "mold", "slow", "delayed", "cold", "hot", "noisy", "uncomfortable",
        "disappointed", "unsatisfied", "terrible", "poor", "awful",
        "failed", "failing", "leaking", "clogged", "overflowing",
        "missing", "unavailable", "damaged", "worn", "stained",
    }

    for sentence in unique:
        words = sentence.lower().split()
        for i in range(len(words)):
            for j in range(3, 10):
                if i + j > len(words):
                    break
                phrase = " ".join(words[i:i + j])
                weight = 0
                for verb in complaint_verbs:
                    if verb in phrase:
                        weight += 2
                if len(phrase) > 15 and not phrase.startswith(("the ", "a ", "an ", "i ", "we ", "my ")):
                    key_phrases.append((phrase, weight + j))

    if key_phrases:
        key_phrases.sort(key=lambda x: x[1], reverse=True)
        title = key_phrases[0][0]
        title = title.strip().strip(".,;:!?")
        if title and title[0].islower():
            title = title[0].upper() + title[1:]
        if len(title.split()) >= 3:
            return title[:200]

    for sentence in unique:
        words = sentence.split()
        if len(words) >= 5:
            trimmed = " ".join(words[:12])
            trimmed = trimmed.strip().strip(".,;:!?")
            if trimmed and trimmed[0].islower():
                trimmed = trimmed[0].upper() + trimmed[1:]
            return trimmed[:200]

    return unique[0][:200]


def _extract_keywords(
    evidence_sentences: list[str],
    department_code: str,
) -> list[str]:
    stop_words = {
        "the", "a", "an", "is", "was", "were", "are", "be", "been",
        "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "can", "shall", "to", "of",
        "in", "for", "on", "with", "at", "by", "from", "as", "into",
        "through", "during", "before", "after", "above", "below", "up",
        "down", "out", "off", "over", "under", "again", "further",
        "then", "once", "here", "there", "when", "where", "why", "how",
        "all", "both", "each", "few", "more", "most", "other", "some",
        "such", "no", "nor", "not", "only", "own", "same", "so", "than",
        "too", "very", "just", "because", "but", "and", "or", "if",
        "while", "about", "i", "me", "my", "myself", "we", "our",
        "ours", "you", "your", "he", "she", "it", "its", "they", "them",
        "this", "that", "these", "those", "which", "what",
    }

    dept_boost_terms: dict[str, set[str]] = {
        "housekeeping": {
            "bathroom", "shower", "toilet", "sink", "drain", "mold", "mildew",
            "clean", "cleaning", "dirty", "stain", "linen", "towel", "bed",
            "sheet", "pillow", "mattress", "floor", "carpet", "dust", "trash",
            "amenities", "soap", "shampoo", "toiletries", "housekeeping",
            "maid", "turn down",
        },
        "engineering": {
            "ac", "air condition", "cooling", "heating", "thermostat", "temperature",
            "hot", "cold", "plumbing", "leak", "water", "electrical", "power",
            "light", "bulb", "tv", "television", "wifi", "internet", "elevator",
            "lock", "key", "door", "window", "noise", "noisy", "soundproof",
            "repair", "maintenance", "broken", "fix", "facility",
        },
        "food_beverage": {
            "breakfast", "buffet", "restaurant", "dining", "meal", "food",
            "drink", "bar", "cocktail", "room service", "order", "menu",
            "coffee", "tea", "cuisine", "dish", "taste", "quality",
            "replenish", "refill", "cold food", "wait", "service",
        },
        "front_office": {
            "check-in", "checkin", "check-out", "checkout", "reception",
            "front desk", "queue", "wait", "waiting", "booking", "reservation",
            "bill", "billing", "charge", "charged", "payment", "refund",
            "deposit", "invoice", "key card", "concierge", "luggage", "bell",
        },
        "management": {
            "price", "pricing", "value", "cost", "expensive", "policy",
            "rule", "manager", "management", "communication", "response",
            "complaint", "resolution", "compensation", "refund", "credit",
        },
        "guest_relations": {
            "staff", "employee", "manager", "service", "attitude", "rude",
            "helpful", "friendly", "unfriendly", "polite", "courtesy",
            "hospitality", "welcome", "greeting", "guest", "customer",
            "experience", "satisfaction",
        },
    }

    all_text = " ".join(evidence_sentences).lower()
    words = re.findall(r"[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*", all_text)

    bigrams: list[str] = []
    for i in range(len(words) - 1):
        bigram = f"{words[i]} {words[i+1]}"
        bg_words = set(bigram.split())
        if bg_words - stop_words:
            bigrams.append(bigram)

    filtered_words = [w for w in words if w not in stop_words and len(w) > 2]

    word_freq: dict[str, int] = Counter()
    for w in filtered_words:
        word_freq[w] += 1
    for bg in bigrams:
        word_freq[bg] += 1

    boost_terms = dept_boost_terms.get(department_code, set())
    for term in boost_terms:
        if term in all_text:
            word_freq[term] += 3

    scored: list[tuple[str, int]] = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

    keywords: list[str] = []
    seen: set[str] = set()
    for kw, _freq in scored:
        if kw in seen:
            continue
        if len(kw) < 3:
            continue
        covered = False
        for existing in list(keywords):
            if kw in existing or existing in kw:
                covered = True
                break
        if not covered:
            keywords.append(kw)
            seen.add(kw)
        if len(keywords) >= 7:
            break

    return keywords


def _deduplicate_issues(
    session: Session,
    new_issue_ids: list[int],
) -> int:
    if not new_issue_ids:
        return 0

    now = datetime.now(UTC)
    new_issues = list(
        session.scalars(
            select(DetectedIssue).where(
                and_(
                    DetectedIssue.id.in_(new_issue_ids),
                    DetectedIssue.status == "active",
                )
            )
        )
    )
    if not new_issues:
        return 0

    all_active = list(
        session.scalars(
            select(DetectedIssue).where(DetectedIssue.status == "active")
        )
    )

    merged_count = 0
    to_delete_ids: set[int] = set()

    for i in range(len(new_issues)):
        issue_a = new_issues[i]
        if issue_a.id in to_delete_ids:
            continue

        for issue_b in all_active:
            if issue_b.id == issue_a.id:
                continue
            if issue_b.id in to_delete_ids:
                continue
            if issue_b.department_code != issue_a.department_code:
                continue

            centroid_sim = centroid_similarity(
                issue_a.cluster_centroid,
                issue_b.cluster_centroid,
            )

            title_sim = _word_overlap_similarity(issue_a.title, issue_b.title)

            should_merge = (
                centroid_sim >= DEDUP_CENTROID_SIMILARITY or
                (centroid_sim >= 0.85 and title_sim >= DEDUP_TITLE_OVERLAP_THRESHOLD)
            )

            if not should_merge:
                continue

            survivor, absorbed = _pick_survivor(issue_a, issue_b)

            if absorbed.id in to_delete_ids:
                continue

            _merge_issues(session, survivor, absorbed, now)
            merged_count += 1
            to_delete_ids.add(absorbed.id)

            if survivor == issue_a:
                for j in range(len(new_issues)):
                    if new_issues[j].id == absorbed.id:
                        new_issues[j] = survivor

    session.flush()
    return merged_count


def _word_overlap_similarity(title_a: str, title_b: str) -> float:
    words_a = set(re.findall(r"[a-zA-Z]+", title_a.lower()))
    words_b = set(re.findall(r"[a-zA-Z]+", title_b.lower()))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / min(len(words_a), len(words_b))


def _pick_survivor(
    issue_a: DetectedIssue,
    issue_b: DetectedIssue,
) -> tuple[DetectedIssue, DetectedIssue]:
    score_a = (
        (issue_a.title_quality_score or 0) * 3 +
        issue_a.recurrence_count * 0.5 +
        (len(issue_a.keywords or []) * 0.2)
    )
    score_b = (
        (issue_b.title_quality_score or 0) * 3 +
        issue_b.recurrence_count * 0.5 +
        (len(issue_b.keywords or []) * 0.2)
    )
    if score_a >= score_b:
        return (issue_a, issue_b)
    return (issue_b, issue_a)


def _merge_issues(
    session: Session,
    survivor: DetectedIssue,
    absorbed: DetectedIssue,
    now: datetime,
) -> None:
    links = session.scalars(
        select(IssueReviewLink).where(IssueReviewLink.issue_id == absorbed.id)
    ).all()

    for link in links:
        existing = session.scalar(
            select(IssueReviewLink).where(
                and_(
                    IssueReviewLink.issue_id == survivor.id,
                    IssueReviewLink.review_id == link.review_id,
                )
            )
        )
        if existing is not None:
            continue
        link.issue_id = survivor.id
        session.add(link)

    for event in session.scalars(
        select(IssueEvent).where(IssueEvent.issue_id == absorbed.id)
    ).all():
        event.issue_id = survivor.id
        session.add(event)

    session.add(
        IssueEvent(
            issue_id=survivor.id,
            event_type="merged",
            actor="system",
            old_value=str(absorbed.id),
            new_value=None,
            note=f"Merged duplicate issue #{absorbed.id} ({absorbed.title})",
            created_at=now,
        )
    )

    survivor.recurrence_count = _count_triggering_reviews(session, survivor)
    survivor.updated_at = now
    if absorbed.reputation_risk_score > survivor.reputation_risk_score:
        survivor.reputation_risk_score = absorbed.reputation_risk_score
        survivor.priority = _priority_from_risk(survivor.reputation_risk_score)
    if absorbed.first_seen_at < survivor.first_seen_at:
        survivor.first_seen_at = absorbed.first_seen_at
    if absorbed.last_seen_at > survivor.last_seen_at:
        survivor.last_seen_at = absorbed.last_seen_at

    if survivor.title_quality_score is not None and absorbed.title_quality_score is not None:
        if absorbed.title_quality_score > survivor.title_quality_score:
            survivor.title = absorbed.title
            survivor.title_quality_score = absorbed.title_quality_score
            survivor.title_generated_by = absorbed.title_generated_by
            survivor.title_generation_model = absorbed.title_generation_model
            survivor.title_confidence = absorbed.title_confidence

    merged_keywords: list[str] = list(dict.fromkeys(
        (survivor.keywords or []) + (absorbed.keywords or [])
    ))[:10]
    survivor.keywords = merged_keywords

    survivor.merged_from_id = absorbed.id

    session.delete(absorbed)


def _get_title_generator_info() -> tuple[str, str | None, float | None]:
    try:
        from transformers import AutoConfig
        model_id = "google/flan-t5-base"
        AutoConfig.from_pretrained(model_id, local_files_only=True)
        return ("flan-t5", model_id, None)
    except Exception:
        return ("extractive", None, None)


def _build_cluster_key(department_code: str, review_ids: list[int]) -> str:
    raw = f"{department_code}:{','.join(str(r) for r in sorted(review_ids))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _recompute_issue_centroid(
    session: Session,
    issue: DetectedIssue,
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> None:
    links = session.scalars(
        select(IssueReviewLink).where(IssueReviewLink.issue_id == issue.id)
    ).all()

    embeddings: list[list[float]] = []
    for link in links:
        review = session.get(NormalizedReview, link.review_id)
        if review is None:
            continue
        sentence_vectors = _build_sentence_vectors(review, _sentence_vector_cache)
        for _st, s_dept, s_emb in sentence_vectors:
            if s_dept == issue.department_code:
                embeddings.append(s_emb)

    if embeddings:
        issue.cluster_centroid = compute_centroid(embeddings)


def _count_triggering_reviews(session: Session, issue: DetectedIssue) -> int:
    return session.scalar(
        select(func.count(IssueReviewLink.id)).where(
            and_(
                IssueReviewLink.issue_id == issue.id,
                IssueReviewLink.is_triggering_evidence.is_(True),
            )
        )
    ) or 1


def _update_issue_from_links(
    session: Session,
    issue: DetectedIssue,
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] | None = None,
) -> None:
    _recompute_issue_centroid(session, issue, _sentence_vector_cache)
    issue.recurrence_count = _count_triggering_reviews(session, issue)
    issue.last_seen_at = datetime.now(UTC)
    links = session.scalars(
        select(IssueReviewLink).where(IssueReviewLink.issue_id == issue.id)
    ).all()
    if links:
        risks = []
        for link in links:
            review = session.get(NormalizedReview, link.review_id)
            if review is not None and review.analysis is not None:
                risks.append(review.analysis.reputation_risk_score)
        if risks:
            issue.reputation_risk_score = max(risks)
    issue.updated_at = datetime.now(UTC)


def resolve_issue(session: Session, issue_id: int) -> DetectedIssue | None:
    issue = session.get(DetectedIssue, issue_id)
    if issue is None:
        return None

    now = datetime.now(UTC)
    session.add(
        IssueEvent(
            issue_id=issue.id,
            event_type="status_changed",
            actor="system",
            old_value=issue.status,
            new_value="resolved",
            note="Issue manually resolved",
            created_at=now,
        )
    )
    session.add(
        IssueEvent(
            issue_id=issue.id,
            event_type="resolved",
            actor="system",
            old_value=issue.status,
            new_value="resolved",
            note="Issue resolved by user action",
            created_at=now,
        )
    )

    issue.status = "resolved"
    issue.resolved_at = now
    issue.updated_at = now
    session.commit()
    return issue


def _priority_from_risk(risk_score: int) -> str:
    if risk_score >= 75:
        return "urgent"
    if risk_score >= 50:
        return "high"
    if risk_score >= 30:
        return "medium"
    return "low"


def get_emerging_candidates(session: Session) -> list[dict]:
    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] = {}
    singletons = _get_unlinked_negative_reviews(session)

    groups_by_dept: dict[str, list[NormalizedReview]] = {}
    for review in singletons:
        sentence_depts = {
            sentence_dept
            for _sentence, sentence_dept, _embedding in _build_sentence_vectors(review, _sentence_vector_cache)
        }
        for dept in sentence_depts:
            groups_by_dept.setdefault(dept, []).append(review)

    candidates: list[dict] = []
    now = datetime.now(UTC)

    for dept, reviews in groups_by_dept.items():
        if len(reviews) < 2:
            continue

        visited: set[int] = set()
        for i in range(len(reviews)):
            if reviews[i].id in visited:
                continue

            component_reviews = [reviews[i]]
            visited.add(reviews[i].id)

            a_vectors = _build_sentence_vectors(reviews[i], _sentence_vector_cache)

            for j in range(i + 1, len(reviews)):
                if reviews[j].id in visited:
                    continue

                b_vectors = _build_sentence_vectors(reviews[j], _sentence_vector_cache)

                max_sim = _max_sentence_pair_similarity(a_vectors, b_vectors, department_code=dept)

                if max_sim >= SIMILARITY_THRESHOLD:
                    component_reviews.append(reviews[j])
                    visited.add(reviews[j].id)

            if len(component_reviews) >= 2:
                risks = [
                    r.analysis.reputation_risk_score
                    for r in component_reviews
                    if r.analysis is not None
                ]
                sims = []
                for a in range(len(component_reviews)):
                    for b in range(a + 1, len(component_reviews)):
                        a_vecs = _build_sentence_vectors(component_reviews[a], _sentence_vector_cache)
                        b_vecs = _build_sentence_vectors(component_reviews[b], _sentence_vector_cache)
                        s = _max_sentence_pair_similarity(a_vecs, b_vecs, department_code=dept)
                        if s > 0:
                            sims.append(s)

                candidates.append({
                    "department_code": dept,
                    "review_count": len(component_reviews),
                    "avg_similarity": round(sum(sims) / len(sims), 3) if sims else None,
                    "risk_scores": risks,
                    "representative_snippet": component_reviews[0].display_body[:240],
                    "review_ids": [r.id for r in component_reviews],
                    "first_seen_at": min(r.review_date or now for r in component_reviews),
                    "last_seen_at": max(r.review_date or now for r in component_reviews),
                })

    candidates.sort(key=lambda c: (c["review_count"], c.get("avg_similarity") or 0), reverse=True)
    return candidates

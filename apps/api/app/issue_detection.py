from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
import os

from sqlalchemy import and_, func, or_, select
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
    compute_centroid,
    centroid_similarity,
    get_semantic_similarity_analyzer,
    split_sentences,
)

SIMILARITY_THRESHOLD = 0.55
RECURRENCE_WINDOW_DAYS = 30
MIN_EVIDENCE_FOR_PROMOTION = 2
SINGLE_CRITICAL_RISK_THRESHOLD = 75
EMBEDDING_DIMS = 384


def detect_issues(
    session: Session,
    *,
    force: bool = False,
) -> dict:
    created = 0
    updated = 0
    linked = 0

    existing_issues = list(session.scalars(select(DetectedIssue)))

    unlinked_reviews = _get_unlinked_reviews(session, force=force)

    for review in unlinked_reviews:
        linked_count = _match_review_against_issues(session, review, existing_issues)
        linked += linked_count

    session.flush()

    singletons = _get_unlinked_negative_reviews(session)

    emerging_clusters = _find_emerging_clusters(session, singletons)

    for cluster in emerging_clusters:
        issue = _promote_cluster(session, cluster)
        if issue is not None:
            created += 1
            existing_issues.append(issue)

    session.flush()

    for issue in existing_issues:
        if issue.status in ("active", "recurred"):
            if _check_threshold_met(session, issue):
                if issue.status != "recurred":
                    _update_issue_from_links(session, issue)
                    updated += 1

    session.commit()
    return {"created": created, "updated": updated, "linked": linked}


def _get_unlinked_reviews(session: Session, *, force: bool = False) -> list[NormalizedReview]:
    if force:
        return list(session.scalars(
            select(NormalizedReview)
            .where(NormalizedReview.analysis.has(ReviewAnalysis.embedding.is_not(None)))
            .order_by(NormalizedReview.id)
        ))

    linked_review_ids = set(
        session.scalars(
            select(IssueReviewLink.review_id)
        )
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


def _match_review_against_issues(
    session: Session,
    review: NormalizedReview,
    issues: list[DetectedIssue],
) -> int:
    linked_count = 0
    if review.analysis is None or review.analysis.embedding is None:
        return 0

    review_embedding = review.analysis.embedding
    review_dept = review.analysis.department_code

    now = datetime.now(UTC)

    for issue in issues:
        if issue.status == "resolved":
            continue
        if issue.department_code != review_dept:
            continue

        similarity = centroid_similarity(issue.cluster_centroid, review_embedding)
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
            continue

        is_triggering = _is_triggering_evidence(session, review, issue)
        evidence = _extract_evidence_snippet(review.body)

        link = IssueReviewLink(
            issue_id=issue.id,
            review_id=review.id,
            similarity_score=round(similarity, 4),
            linked_at=now,
            is_triggering_evidence=is_triggering,
            evidence_snippet=evidence,
        )
        session.add(link)
        linked_count += 1

        session.add(
            IssueEvent(
                issue_id=issue.id,
                event_type="linked_review",
                actor="system",
                old_value=None,
                new_value=str(review.id),
                note=f"Review #{review.id} linked with similarity {similarity:.3f}",
                created_at=now,
            )
        )

        if is_triggering:
            _recompute_issue_centroid(session, issue)
            issue.recurrence_count = _count_triggering_reviews(session, issue)
            issue.last_seen_at = now
            issue.reputation_risk_score = max(
                issue.reputation_risk_score,
                review.analysis.reputation_risk_score,
            )

        if issue.status == "resolved":
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


def _is_triggering_evidence(
    session: Session,
    review: NormalizedReview,
    issue: DetectedIssue,
) -> bool:
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
) -> list[dict]:
    if len(singletons) < 2:
        return []

    groups_by_dept: dict[str, list[NormalizedReview]] = {}
    for review in singletons:
        if review.analysis is None or review.analysis.department_code is None:
            continue
        dept = review.analysis.department_code
        groups_by_dept.setdefault(dept, []).append(review)

    clusters: list[dict] = []

    for dept, reviews in groups_by_dept.items():
        if len(reviews) < 2:
            continue

        visited: set[int] = set()
        for i in range(len(reviews)):
            if reviews[i].id in visited:
                continue
            if reviews[i].analysis is None or reviews[i].analysis.embedding is None:
                continue

            component: list[NormalizedReview] = [reviews[i]]
            visited.add(reviews[i].id)

            for j in range(i + 1, len(reviews)):
                if reviews[j].id in visited:
                    continue
                if reviews[j].analysis is None or reviews[j].analysis.embedding is None:
                    continue

                sim = centroid_similarity(
                    reviews[i].analysis.embedding,
                    reviews[j].analysis.embedding,
                )
                if sim >= SIMILARITY_THRESHOLD:
                    component.append(reviews[j])
                    visited.add(reviews[j].id)

            if len(component) >= MIN_EVIDENCE_FOR_PROMOTION or (
                len(component) == 1
                and component[0].analysis is not None
                and component[0].analysis.reputation_risk_score >= SINGLE_CRITICAL_RISK_THRESHOLD
            ):
                pass

            if len(component) >= MIN_EVIDENCE_FOR_PROMOTION:
                clusters.append({
                    "department_code": dept,
                    "reviews": component,
                })

    return clusters


def _promote_cluster(session: Session, cluster: dict) -> DetectedIssue | None:
    reviews: list[NormalizedReview] = cluster["reviews"]
    if not reviews:
        return None

    department_code = cluster["department_code"]
    now = datetime.now(UTC)

    embeddings = [
        r.analysis.embedding
        for r in reviews
        if r.analysis is not None and r.analysis.embedding is not None
    ]
    if not embeddings:
        return None

    centroid = compute_centroid(embeddings)

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

    title = _generate_title(reviews)

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
        title_generated_by=_get_title_generator_info()[0],
        title_generation_model=_get_title_generator_info()[1],
        title_confidence=_get_title_generator_info()[2],
        created_at=now,
        updated_at=now,
    )
    session.add(issue)
    session.flush()

    session.add(
        IssueEvent(
            issue_id=issue.id,
            event_type="created",
            actor="system",
            old_value=None,
            new_value="active",
            note=f"Issue created from {len(reviews)} reviews in {department_code}",
            created_at=now,
        )
    )

    for review in reviews:
        similarity = 0.0
        if review.analysis is not None and review.analysis.embedding is not None:
            similarity = centroid_similarity(centroid, review.analysis.embedding)

        link = IssueReviewLink(
            issue_id=issue.id,
            review_id=review.id,
            similarity_score=round(similarity, 4),
            linked_at=now,
            is_triggering_evidence=True,
            evidence_snippet=_extract_evidence_snippet(review.body),
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
            note=f"Title generated by {_get_title_generator_info()[0]}",
            created_at=now,
        )
    )

    return issue


def _generate_title(reviews: list[NormalizedReview]) -> str:
    generator_info = _get_title_generator_info()
    generator_type = generator_info[0]

    sentences: list[str] = []
    for review in reviews[:5]:
        text = " ".join(part for part in [review.title, review.body] if part)
        parts = split_sentences(text)
        sentences.extend(parts[:3])

    if not sentences:
        return _fallback_title(reviews)

    if generator_type == "flan-t5":
        try:
            return _flan_t5_title(sentences[:5])
        except Exception:
            pass

    return _fallback_title(reviews)


def _fallback_title(reviews: list[NormalizedReview]) -> str:
    for review in reviews:
        if review.title:
            words = review.title.strip().split()
            if 3 <= len(words) <= 8:
                return review.title.strip()
    for review in reviews:
        if review.title:
            return review.title.strip()[:60]
    body = reviews[0].body if reviews else ""
    sentences = split_sentences(body)
    if sentences:
        return sentences[0][:80]
    return "Review issue"


def _flan_t5_title(sentences: list[str]) -> str:
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

    model_id = "google/flan-t5-base"
    tokenizer = AutoTokenizer.from_pretrained(model_id, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(model_id, local_files_only=True)

    prompt = "Generate a short title (3-6 words) for an operational issue based on these complaints:\n"
    for s in sentences[:5]:
        prompt += f"- {s[:200]}\n"

    inputs = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
    outputs = model.generate(
        **inputs,
        max_new_tokens=20,
        do_sample=False,
    )
    title = tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
    if not title or len(title.split()) < 2:
        return _fallback_title_from_sentences(sentences)
    return title[:100]


def _fallback_title_from_sentences(sentences: list[str]) -> str:
    if sentences:
        return sentences[0][:80]
    return "Review issue"


def _get_title_generator_info() -> tuple[str, str | None, float | None]:
    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, AutoConfig
        model_id = "google/flan-t5-base"
        config = AutoConfig.from_pretrained(model_id, local_files_only=True)
        return ("flan-t5", model_id, None)
    except Exception:
        return ("centroid-excerpt", None, None)


def _build_cluster_key(department_code: str, review_ids: list[int]) -> str:
    raw = f"{department_code}:{','.join(str(r) for r in sorted(review_ids))}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


def _recompute_issue_centroid(session: Session, issue: DetectedIssue) -> None:
    links = session.scalars(
        select(IssueReviewLink).where(IssueReviewLink.issue_id == issue.id)
    ).all()

    embeddings: list[list[float]] = []
    for link in links:
        review = session.get(NormalizedReview, link.review_id)
        if review is not None and review.analysis is not None and review.analysis.embedding is not None:
            embeddings.append(review.analysis.embedding)

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


def _check_threshold_met(session: Session, issue: DetectedIssue) -> bool:
    count = session.scalar(
        select(func.count(IssueReviewLink.id)).where(
            and_(
                IssueReviewLink.issue_id == issue.id,
                IssueReviewLink.is_triggering_evidence.is_(True),
            )
        )
    ) or 0
    return count >= MIN_EVIDENCE_FOR_PROMOTION


def _update_issue_from_links(session: Session, issue: DetectedIssue) -> None:
    _recompute_issue_centroid(session, issue)
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
    singletons = _get_unlinked_negative_reviews(session)

    groups_by_dept: dict[str, list[NormalizedReview]] = {}
    for review in singletons:
        if review.analysis is None or review.analysis.department_code is None:
            continue
        dept = review.analysis.department_code
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
            if reviews[i].analysis is None or reviews[i].analysis.embedding is None:
                continue

            component_reviews = [reviews[i]]
            visited.add(reviews[i].id)

            for j in range(i + 1, len(reviews)):
                if reviews[j].id in visited:
                    continue
                if reviews[j].analysis is None or reviews[j].analysis.embedding is None:
                    continue

                sim = centroid_similarity(
                    reviews[i].analysis.embedding,
                    reviews[j].analysis.embedding,
                )
                if sim >= SIMILARITY_THRESHOLD:
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
                        if (
                            component_reviews[a].analysis is not None
                            and component_reviews[b].analysis is not None
                            and component_reviews[a].analysis.embedding is not None
                            and component_reviews[b].analysis.embedding is not None
                        ):
                            s = centroid_similarity(
                                component_reviews[a].analysis.embedding,
                                component_reviews[b].analysis.embedding,
                            )
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

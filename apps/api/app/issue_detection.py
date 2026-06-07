from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from functools import lru_cache
import hashlib
import os

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

SIMILARITY_THRESHOLD = 0.78
RECURRENCE_WINDOW_DAYS = 30
MIN_EVIDENCE_FOR_PROMOTION = 2
SINGLE_CRITICAL_RISK_THRESHOLD = 75


def detect_issues(
    session: Session,
    *,
    force: bool = False,
) -> dict:
    created = 0
    updated = 0
    linked = 0

    _sentence_vector_cache: dict[int, list[tuple[str, str, list[float]]]] = {}

    existing_issues = list(session.scalars(select(DetectedIssue)))

    unlinked_reviews = _get_unlinked_reviews(session, force=force)

    for review in unlinked_reviews:
        linked_count = _match_review_against_issues(session, review, existing_issues, _sentence_vector_cache)
        linked += linked_count

    session.flush()

    singletons = _get_unlinked_negative_reviews(session)

    emerging_clusters = _find_emerging_clusters(session, singletons, _sentence_vector_cache)

    for cluster in emerging_clusters:
        issue = _promote_cluster(session, cluster, _sentence_vector_cache)
        if issue is not None:
            created += 1
            existing_issues.append(issue)

    session.flush()

    for issue in existing_issues:
        if issue.status == "active":
            _update_issue_from_links(session, issue, _sentence_vector_cache)
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
    for review in reviews:
        sentence_vectors = _build_sentence_vectors(review, _sentence_vector_cache)
        for _sentence, s_dept, s_emb in sentence_vectors:
            if s_dept == department_code:
                centroid_vectors.append(s_emb)

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
        from transformers import AutoConfig
        model_id = "google/flan-t5-base"
        AutoConfig.from_pretrained(model_id, local_files_only=True)
        return ("flan-t5", model_id, None)
    except Exception:
        return ("centroid-excerpt", None, None)


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

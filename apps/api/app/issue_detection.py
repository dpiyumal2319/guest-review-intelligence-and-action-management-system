"""LLM-driven issue detection.

Turns guest reviews into a clean, deduplicated set of actionable operational issues. The
pipeline is a deterministic batch rebuild with three LLM passes:

* Pass A - Extraction: read each negative/mixed review and pull out discrete, normalized
  problems ({summary, department_code, specifics}).
* Pass B - Consolidation: group synonymous problems into canonical issue types, while keeping
  severe or materially distinct incidents (pest/hygiene, billing fraud, safety) separate.
* Pass C - Assembly: for each canonical type, create one DetectedIssue grounded in its evidence
  reviews, with an LLM-written description that cites concrete specifics (which rooms/floors/
  items, how many guests, severity). Issues with a single supporting review are stored as
  ``status="emerging"`` (precomputed candidates) instead of ``active``.

The LLM is provided by :mod:`app.llm_client` (Gemini by default, deterministic stub offline).
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
import hashlib
import json
import os
import re

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.models import (
    DetectedIssue,
    IssueEvent,
    IssueReviewLink,
    NormalizedReview,
    ReviewAnalysis,
)
from app.semantic_similarity import compute_centroid
from app.llm_client import (
    TASK_CONSOLIDATE,
    TASK_DESCRIBE,
    TASK_EXTRACT,
    LLMClient,
    get_llm_client,
)

RECURRENCE_WINDOW_DAYS = 30
MIN_EVIDENCE_FOR_PROMOTION = 2  # >=2 supporting reviews -> active; 1 -> emerging

VALID_DEPARTMENTS = {
    "housekeeping",
    "front_office",
    "food_beverage",
    "engineering",
    "management",
    "guest_relations",
}
DEFAULT_DEPARTMENT = "guest_relations"

CONSOLIDATION_CHUNK_SIZE = 120


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# ============================================================================================
# Orchestration
# ============================================================================================
def detect_issues(session: Session, *, force: bool = False) -> dict:
    """Rebuild the issue set from current reviews. ``force`` is accepted for API/script
    compatibility; detection is always a full rebuild."""
    client = get_llm_client()
    if not client.is_available():
        raise RuntimeError(
            "LLM provider is not configured. Set GEMINI_API_KEY (or LLM_PROVIDER=stub)."
        )

    reviews = _candidate_reviews(session, limit=_env_int("ISSUE_MAX_REVIEWS", 1000))
    if not reviews:
        return {"created": 0, "updated": 0, "linked": 0, "merged": 0}

    review_by_id = {r.id: r for r in reviews}

    # Pass A - extract problems per review.
    mentions = _extract_problems(client, reviews)  # list of {review_id, summary, department_code, specifics}
    if not mentions:
        _replace_issue_set(session, [], client)
        return {"created": 0, "updated": 0, "linked": 0, "merged": 0}

    # Pass B - consolidate problem summaries into canonical issue types.
    summary_to_canonical = _consolidate_problems(client, mentions)

    # Group reviews under each canonical (department, title).
    groups: dict[tuple[str, str], dict] = {}
    for mention in mentions:
        key_summary = mention["summary"].strip().lower()
        canonical = summary_to_canonical.get(
            key_summary,
            (_normalize_department(mention["department_code"]), mention["summary"].strip()[:200]),
        )
        dept, title = canonical
        group = groups.setdefault((dept, title), {"review_ids": {}, "evidence": []})
        rid = mention["review_id"]
        if rid not in group["review_ids"]:
            group["review_ids"][rid] = mention.get("specifics") or mention["summary"]
        group["evidence"].append(mention.get("specifics") or mention["summary"])

    built = _build_issues(client, groups, review_by_id)

    created, emerging = _replace_issue_set(session, built, client)

    return {
        "created": created,
        "updated": 0,
        "linked": sum(len(b["reviews"]) for b in built),
        "merged": 0,
        "emerging": emerging,
    }


def _candidate_reviews(session: Session, *, limit: int) -> list[NormalizedReview]:
    """Negative/mixed reviews with a body, newest first, capped at ``limit``."""
    return list(
        session.scalars(
            select(NormalizedReview)
            .where(
                NormalizedReview.analysis.has(
                    ReviewAnalysis.sentiment_label.in_(["negative", "mixed"])
                )
            )
            .order_by(NormalizedReview.review_date.desc(), NormalizedReview.id.desc())
            .limit(limit)
        )
    )


# ============================================================================================
# Pass A - extraction
# ============================================================================================
_EXTRACT_SYSTEM = (
    "You are an operations analyst for a hotel. You read raw guest reviews and extract the "
    "concrete, actionable operational problems each one reports. You ALWAYS keep specific "
    "facts the guest mentioned (room number, floor, room type, item, amount, time, duration). "
    "You never invent facts that are not in the review."
)


def _extract_problems(client: LLMClient, reviews: list[NormalizedReview]) -> list[dict]:
    batch_size = _env_int("ISSUE_LLM_BATCH_SIZE", 8)
    mentions: list[dict] = []
    for start in range(0, len(reviews), batch_size):
        batch = reviews[start : start + batch_size]
        payload = [{"review_id": r.id, "text": _review_text(r)} for r in batch]
        prompt = _extract_prompt(payload)
        try:
            result = client.generate_json(
                system=_EXTRACT_SYSTEM, user=prompt, task=TASK_EXTRACT, payload=payload
            )
        except Exception:  # noqa: BLE001 - skip a failed batch rather than abort the run
            continue
        for entry in (result or {}).get("results", []):
            rid = entry.get("review_id")
            if rid is None:
                continue
            for problem in entry.get("problems", []) or []:
                summary = str(problem.get("summary", "")).strip()
                if not summary:
                    continue
                mentions.append(
                    {
                        "review_id": int(rid),
                        "summary": summary,
                        "department_code": _normalize_department(problem.get("department_code")),
                        "specifics": str(problem.get("specifics", "")).strip()[:500] or None,
                    }
                )
    return mentions


def _extract_prompt(payload: list[dict]) -> str:
    reviews_block = "\n".join(
        f'- review_id {item["review_id"]}: "{item["text"]}"' for item in payload
    )
    return (
        "Extract the operational problems from each hotel guest review below.\n\n"
        f"Departments (use the code): {', '.join(sorted(VALID_DEPARTMENTS))}.\n\n"
        "Rules:\n"
        "- One review may contain several distinct problems; list each separately.\n"
        "- If a review has no actionable complaint (purely positive), return an empty list.\n"
        "- `summary` = a short normalized problem label (5-9 words), e.g. 'AC not cooling the room'.\n"
        "- `specifics` = the concrete facts the guest gave (room/floor/item/amount/time). Empty if none.\n"
        "- Pick the single best department code for each problem.\n\n"
        "Return ONLY JSON of this shape:\n"
        '{"results":[{"review_id":123,"problems":[{"summary":"...","department_code":"engineering","specifics":"room 412, 4th floor, 2 nights"}]}]}\n\n'
        f"Reviews:\n{reviews_block}"
    )


# ============================================================================================
# Pass B - consolidation
# ============================================================================================
_CONSOLIDATE_SYSTEM = (
    "You group hotel complaint labels into canonical operational issue types. You MERGE labels "
    "that describe the same root problem (e.g. 'AC not cooling', 'air con takes forever', 'room "
    "stayed hot' -> one issue). You KEEP SEPARATE any severe or materially distinct incident "
    "(pest/hygiene like insects in food, theft or billing fraud, safety hazards) - never fold "
    "those into a generic bucket. Each canonical title is specific and actionable."
)


def _consolidate_problems(client: LLMClient, mentions: list[dict]) -> dict[tuple[str, str], tuple[str, str]]:
    # Unique summaries with a department vote. Extraction (full review context) is the most
    # reliable signal for department, so we keep these votes and let them decide the canonical
    # issue's department later - not the consolidation step, which only sees short labels.
    dept_votes: dict[str, Counter] = {}
    for m in mentions:
        dept_votes.setdefault(m["summary"].strip(), Counter())[m["department_code"]] += 1
    summary_dept = {summary.lower(): votes.most_common(1)[0][0] for summary, votes in dept_votes.items()}
    unique = [
        {"summary": summary, "department_code": votes.most_common(1)[0][0]}
        for summary, votes in dept_votes.items()
    ]

    canonical_types = _consolidate_in_chunks(client, unique)

    # Map each original summary (lowercased) -> (department, canonical_title). The department is
    # the majority extraction-vote across the type's members (falls back to the model's label).
    summary_to_canonical: dict[str, tuple[str, str]] = {}
    for ctype in canonical_types:
        title = str(ctype.get("canonical_title", "")).strip()[:200]
        if not title:
            continue
        members = [str(m).strip() for m in (ctype.get("member_summaries", []) or [])]
        member_votes = Counter(
            summary_dept[m.lower()] for m in members if m.lower() in summary_dept
        )
        dept = (
            member_votes.most_common(1)[0][0]
            if member_votes
            else _normalize_department(ctype.get("department_code"))
        )
        for member in members:
            summary_to_canonical[member.lower()] = (dept, title)

    # Any summary the model dropped becomes its own canonical type (no data loss).
    for item in unique:
        key = item["summary"].strip().lower()
        if key not in summary_to_canonical:
            summary_to_canonical[key] = (item["department_code"], item["summary"].strip()[:200])

    return summary_to_canonical


def _consolidate_in_chunks(client: LLMClient, unique: list[dict]) -> list[dict]:
    chunks = [
        unique[i : i + CONSOLIDATION_CHUNK_SIZE]
        for i in range(0, len(unique), CONSOLIDATION_CHUNK_SIZE)
    ] or [[]]
    collected: list[dict] = []
    for chunk in chunks:
        collected.extend(_consolidate_call(client, chunk))
    if len(chunks) > 1 and collected:
        # Second pass merges canonical titles produced across chunks.
        merge_input = [
            {"summary": c["canonical_title"], "department_code": _normalize_department(c.get("department_code"))}
            for c in collected
            if c.get("canonical_title")
        ]
        merged = _consolidate_call(client, merge_input)
        # Re-expand: map first-pass member summaries through the merged titles.
        title_to_merged: dict[str, dict] = {}
        for m in merged:
            for member in m.get("member_summaries", []) or []:
                title_to_merged[str(member).strip().lower()] = m
        remapped: dict[tuple[str, str], dict] = {}
        for c in collected:
            outer = title_to_merged.get(str(c.get("canonical_title", "")).strip().lower())
            if outer is None:
                target_title = c["canonical_title"]
                target_dept = _normalize_department(c.get("department_code"))
            else:
                target_title = outer["canonical_title"]
                target_dept = _normalize_department(outer.get("department_code"))
            bucket = remapped.setdefault((target_dept, target_title), {
                "canonical_title": target_title,
                "department_code": target_dept,
                "member_summaries": [],
            })
            bucket["member_summaries"].extend(c.get("member_summaries", []) or [])
        return list(remapped.values())
    return collected


def _consolidate_call(client: LLMClient, items: list[dict]) -> list[dict]:
    if not items:
        return []
    prompt = _consolidate_prompt(items)
    try:
        result = client.generate_json(
            system=_CONSOLIDATE_SYSTEM, user=prompt, task=TASK_CONSOLIDATE,
            payload=[i["summary"] for i in items],
        )
    except Exception:  # noqa: BLE001 - degrade to one-type-per-label rather than abort
        return [
            {"canonical_title": i["summary"][:200], "department_code": i["department_code"], "member_summaries": [i["summary"]]}
            for i in items
        ]
    return (result or {}).get("types", []) or []


def _consolidate_prompt(items: list[dict]) -> str:
    labels_block = "\n".join(f'- ({i["department_code"]}) {i["summary"]}' for i in items)
    return (
        "Group these hotel complaint labels into canonical operational issue types.\n\n"
        "Rules:\n"
        "- Merge labels describing the same root problem into ONE type.\n"
        "- Keep severe/distinct incidents (insects or hair in food, theft, billing fraud, safety) as their own type.\n"
        "- `canonical_title` = a specific, actionable issue title (e.g. 'Air conditioning fails to cool guest rooms').\n"
        "- `member_summaries` MUST list the exact input labels you assigned to that type.\n"
        "- Every input label must appear in exactly one type.\n\n"
        "Return ONLY JSON of this shape:\n"
        '{"types":[{"canonical_title":"...","department_code":"engineering","member_summaries":["label a","label b"]}]}\n\n'
        f"Labels:\n{labels_block}"
    )


# ============================================================================================
# Pass C - assembly
# ============================================================================================
_DESCRIBE_SYSTEM = (
    "You write a 1-3 sentence operational summary of a hotel issue for a manager. You ground it "
    "ONLY in the supplied evidence, citing concrete specifics (rooms, floors, items, amounts, "
    "counts). No fluff, no invented facts."
)


def _build_issues(client: LLMClient, groups: dict[tuple[str, str], dict], review_by_id: dict[int, NormalizedReview]) -> list[dict]:
    built: list[dict] = []
    for (dept, title), group in groups.items():
        review_ids = list(group["review_ids"].keys())
        reviews = [review_by_id[rid] for rid in review_ids if rid in review_by_id]
        if not reviews:
            continue
        evidence = [s for s in group["evidence"] if s][:12]
        description = _describe_issue(client, title, evidence, len(reviews))
        built.append({
            "department_code": dept,
            "title": title,
            "description": description,
            "reviews": reviews,
            "evidence_by_review": group["review_ids"],
            "keywords": _extract_keywords(evidence, dept),
        })
    return built


def _describe_issue(client: LLMClient, title: str, evidence: list[str], review_count: int) -> str | None:
    payload = {"title": title, "evidence": evidence, "review_count": review_count}
    prompt = (
        f"Issue: {title}\nGuest reports ({review_count} total):\n"
        + "\n".join(f"- {e}" for e in evidence)
        + "\n\nReturn ONLY JSON: {\"description\":\"...\"}"
    )
    try:
        result = client.generate_json(
            system=_DESCRIBE_SYSTEM, user=prompt, task=TASK_DESCRIBE, payload=payload
        )
        text = str((result or {}).get("description", "")).strip()
        return text or None
    except Exception:  # noqa: BLE001 - description is best-effort
        return None


def _replace_issue_set(session: Session, built: list[dict], client: LLMClient) -> tuple[int, int]:
    """Delete existing detected issues and recreate from ``built``, preserving manual state
    (resolved/assignee) keyed by cluster_key. Returns (active_created, emerging_created)."""
    now = datetime.now(UTC)

    # Snapshot manual state before wiping.
    snapshot: dict[str, dict] = {}
    for issue in session.scalars(select(DetectedIssue)):
        if issue.assignee_name or issue.status in ("resolved", "recurred"):
            snapshot[issue.cluster_key] = {
                "status": issue.status,
                "assignee_name": issue.assignee_name,
                "resolved_at": issue.resolved_at,
                "recurred_at": issue.recurred_at,
            }
        session.delete(issue)
    session.flush()

    active = 0
    emerging = 0
    for item in built:
        reviews = item["reviews"]
        cluster_key = _canonical_cluster_key(item["department_code"], item["title"])
        risk_scores = [r.analysis.reputation_risk_score for r in reviews if r.analysis is not None]
        max_risk = max(risk_scores) if risk_scores else 0
        centroid = compute_centroid(
            [r.analysis.embedding for r in reviews if r.analysis is not None and r.analysis.embedding]
        ) or []
        embedding_model_name = next(
            (r.analysis.embedding_model_name for r in reviews if r.analysis is not None and r.analysis.embedding_model_name),
            "none",
        )
        review_dates = [r.review_date for r in reviews if r.review_date is not None]
        status = "active" if len(reviews) >= MIN_EVIDENCE_FOR_PROMOTION else "emerging"

        issue = DetectedIssue(
            title=item["title"][:255],
            description=item["description"],
            department_code=item["department_code"],
            status=status,
            priority=_priority_from_risk(max_risk),
            reputation_risk_score=max_risk,
            recurrence_count=len(reviews),
            first_seen_at=min(review_dates) if review_dates else now,
            last_seen_at=max(review_dates) if review_dates else now,
            assignee_name=None,
            cluster_key=cluster_key,
            cluster_centroid=centroid,
            embedding_model_name=embedding_model_name or "none",
            title_generated_by=client.provider_name,
            title_generation_model=client.model_name,
            title_confidence=None,
            keywords=item["keywords"],
            title_quality_score=1.0,
            created_at=now,
            updated_at=now,
        )

        restored = snapshot.get(cluster_key)
        if restored is not None:
            issue.status = restored["status"] if restored["status"] != "recurred" else status
            issue.assignee_name = restored["assignee_name"]
            issue.resolved_at = restored["resolved_at"]
            issue.recurred_at = restored["recurred_at"]

        session.add(issue)
        session.flush()

        if issue.status == "emerging":
            emerging += 1
        else:
            active += 1

        session.add(
            IssueEvent(
                issue_id=issue.id,
                event_type="created",
                actor="system",
                old_value=None,
                new_value=issue.status,
                note=f"Issue built from {len(reviews)} review(s) via {client.provider_name}",
                created_at=now,
            )
        )

        for review in reviews:
            snippet = item["evidence_by_review"].get(review.id) or _review_text(review)[:500]
            session.add(
                IssueReviewLink(
                    issue_id=issue.id,
                    review_id=review.id,
                    similarity_score=1.0,
                    linked_at=now,
                    is_triggering_evidence=_is_triggering_evidence(review),
                    evidence_snippet=str(snippet)[:500],
                )
            )

    session.commit()
    return active, emerging


# ============================================================================================
# Emerging candidates (precomputed -> served from DB)
# ============================================================================================
def list_emerging_candidates(session: Session) -> list[dict]:
    """Return precomputed emerging issues shaped for IssueEmergingResponse."""
    issues = list(
        session.scalars(
            select(DetectedIssue)
            .where(DetectedIssue.status == "emerging")
            .order_by(DetectedIssue.reputation_risk_score.desc(), DetectedIssue.last_seen_at.desc())
        )
    )
    candidates: list[dict] = []
    for issue in issues:
        links = issue.review_links
        risk_scores = []
        review_ids = []
        snippet = issue.description or issue.title
        for link in links:
            review_ids.append(link.review_id)
            if link.review is not None and link.review.analysis is not None:
                risk_scores.append(link.review.analysis.reputation_risk_score)
            if link.evidence_snippet and snippet == issue.title:
                snippet = link.evidence_snippet
        candidates.append(
            {
                "department_code": issue.department_code,
                "review_count": issue.recurrence_count,
                "avg_similarity": None,
                "risk_scores": risk_scores,
                "representative_snippet": (snippet or issue.title)[:240],
                "review_ids": review_ids,
                "first_seen_at": issue.first_seen_at,
                "last_seen_at": issue.last_seen_at,
            }
        )
    return candidates


# ============================================================================================
# Issue lifecycle (unchanged behaviour)
# ============================================================================================
def resolve_issue(session: Session, issue_id: int) -> DetectedIssue | None:
    issue = session.get(DetectedIssue, issue_id)
    if issue is None:
        return None

    now = datetime.now(UTC)
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


# ============================================================================================
# Helpers
# ============================================================================================
def _review_text(review: NormalizedReview) -> str:
    body = (review.body or "").strip()
    title = (review.title or "").strip()
    text = f"{title}. {body}" if title and title.lower() not in body.lower() else body
    return re.sub(r"\s+", " ", text)[:600]


def _normalize_department(code: object) -> str:
    value = str(code or "").strip().lower()
    return value if value in VALID_DEPARTMENTS else DEFAULT_DEPARTMENT


def _is_triggering_evidence(review: NormalizedReview) -> bool:
    if review.review_date is None:
        return False
    return review.review_date >= datetime.now(UTC) - timedelta(days=RECURRENCE_WINDOW_DAYS)


def _priority_from_risk(risk_score: int) -> str:
    if risk_score >= 75:
        return "urgent"
    if risk_score >= 50:
        return "high"
    if risk_score >= 30:
        return "medium"
    return "low"


def _canonical_cluster_key(department_code: str, title: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{department_code}-{title}".lower()).strip("-")[:48]
    suffix = hashlib.sha1(f"{department_code}:{title.lower()}".encode()).hexdigest()[:10]
    return f"{base}-{suffix}"[:64]


_STOP_WORDS = {
    "the", "a", "an", "is", "was", "were", "are", "be", "to", "of", "in", "for", "on", "with",
    "at", "by", "from", "as", "and", "or", "but", "not", "no", "it", "this", "that", "guest",
    "room", "hotel", "stay", "had", "very", "too", "our", "we", "my", "i", "they", "them",
}


def _extract_keywords(evidence_sentences: list[str], department_code: str) -> list[str]:
    text = " ".join(evidence_sentences).lower()
    words = [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text) if len(w) > 2 and w not in _STOP_WORDS]
    freq: Counter = Counter(words)
    keywords: list[str] = []
    for word, _count in freq.most_common(20):
        if any(word in kw or kw in word for kw in keywords):
            continue
        keywords.append(word)
        if len(keywords) >= 7:
            break
    return keywords

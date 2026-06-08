"""Provider-agnostic JSON LLM client for the issue pipeline.

The issue detection pipeline asks an LLM to (a) extract normalized problems from each
review, (b) consolidate them into canonical issue types, and (c) write an evidence-grounded
description per issue. All three are JSON-in / JSON-out tasks, so this module exposes a single
``generate_json`` method.

Two providers ship today:

* ``gemini`` (default) - Google Gemini 2.5 Flash via the ``google-genai`` SDK. Cheap, remote.
* ``stub`` - a deterministic, offline, keyword-rule provider used when no API key is configured
  or ``LLM_PROVIDER=stub``. It lets tests and constrained environments run the full pipeline
  without network access. It is intentionally simple, not a quality substitute for Gemini.

The provider is selected from the environment so the rest of the app never imports an SDK
directly. To add Claude/Ollama later, implement another ``_Provider`` and register it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
import json
import os
import re
import time
from typing import Any


class LLMUnavailableError(RuntimeError):
    """Raised when no usable LLM provider is configured (e.g. missing API key)."""


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

# Task identifiers passed by the pipeline. Real providers ignore them; the stub uses them to
# decide what deterministic shape to return.
TASK_EXTRACT = "extract"
TASK_CONSOLIDATE = "consolidate"
TASK_TAXONOMY = "taxonomy"
TASK_ASSIGN = "assign"
TASK_DESCRIBE = "describe"


def _strip_code_fences(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _loads_lenient(text: str) -> Any:
    cleaned = _strip_code_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        starts = [i for i in (cleaned.find("{"), cleaned.find("[")) if i >= 0]
        ends = [i for i in (cleaned.rfind("}"), cleaned.rfind("]")) if i >= 0]
        if not starts or not ends:
            raise
        return json.loads(cleaned[min(starts) : max(ends) + 1])


# --------------------------------------------------------------------------------------------
# Gemini provider
# --------------------------------------------------------------------------------------------
class _GeminiProvider:
    name = "gemini"

    def __init__(self, *, api_key: str, model: str) -> None:
        from google import genai  # imported lazily so the dep is optional

        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def generate_json(self, *, system: str, user: str, max_retries: int = 4) -> Any:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system or None,
            response_mime_type="application/json",
            temperature=0.2,
            # Allow large structured responses (assignment/extraction batches) so JSON does not
            # truncate mid-array, which would fail parsing.
            max_output_tokens=16384,
            # Disable "thinking" - those tokens bill as output on 2.5 Flash. Extraction /
            # consolidation are structured tasks that don't need it, so keep cost predictable.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=user,
                    config=config,
                )
                return _loads_lenient(response.text or "")
            except Exception as exc:  # noqa: BLE001 - normalize SDK + parse errors into retries
                last_exc = exc
                if _is_rate_limit(exc):
                    time.sleep(min(2 ** attempt * 4, 60))
                else:
                    time.sleep(min(2 ** attempt, 8))
        raise LLMUnavailableError(f"Gemini request failed after {max_retries} attempts: {last_exc}")


def _is_rate_limit(exc: Exception) -> bool:
    text = f"{getattr(exc, 'code', '')} {getattr(exc, 'status', '')} {exc}".lower()
    return "429" in text or "resource_exhausted" in text or "rate" in text and "limit" in text


# --------------------------------------------------------------------------------------------
# Stub provider (deterministic, offline)
# --------------------------------------------------------------------------------------------
# Keyword -> (department_code, canonical_title). First match wins; order matters (specific first).
_STUB_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("cockroach", "insect", "roach", "bug in", "hair in", "mold", "mould"), "housekeeping", "Hygiene and pest incidents"),
    (("air condition", "air-condition", "air con", "aircon", "a/c", " ac ", "ac ", "cooling", "too hot", "not cool"), "engineering", "Air conditioning not cooling rooms"),
    (("wifi", "wi-fi", "internet", "network"), "engineering", "Unreliable in-room WiFi"),
    (("leak", "plumbing", "drain", "hot water", "shower", "toilet", "tap"), "engineering", "Plumbing and drainage faults"),
    (("noise", "noisy", "loud", "music", "bass", "thin wall"), "engineering", "Noise disturbance reaching rooms"),
    (("check-in", "checkin", "queue", "reception", "front desk", "wait to check"), "front_office", "Slow check-in at reception"),
    (("bill", "charge", "overcharge", "refund", "deposit", "invoice", "minibar"), "front_office", "Billing and overcharge disputes"),
    (("breakfast", "buffet", "restaurant", "dining", "food", "meal", "cold food", "room service"), "food_beverage", "Breakfast quality and replenishment"),
    (("dirty", "clean", "towel", "linen", "sheet", "dust", "bathroom"), "housekeeping", "Room cleanliness shortfalls"),
    (("rude", "unhelpful", "staff", "ignored", "attitude", "manager"), "guest_relations", "Unhelpful staff interactions"),
    (("price", "expensive", "value", "policy"), "management", "Pricing and value concerns"),
)


class _StubProvider:
    name = "stub"
    model = "stub-deterministic"

    def generate_json(self, *, system: str, user: str, task: str, payload: Any, max_retries: int = 0) -> Any:
        if task == TASK_EXTRACT:
            return self._extract(payload)
        if task == TASK_CONSOLIDATE:
            return self._consolidate(payload)
        if task == TASK_TAXONOMY:
            return self._taxonomy(payload)
        if task == TASK_ASSIGN:
            return self._assign(payload)
        if task == TASK_DESCRIBE:
            return self._describe(payload)
        return {}

    @staticmethod
    def _classify(text: str) -> tuple[str, str] | None:
        low = f" {text.lower()} "
        for keywords, dept, canonical in _STUB_RULES:
            if any(kw in low for kw in keywords):
                return dept, canonical
        return None

    def _extract(self, payload: Any) -> dict:
        results = []
        for item in payload or []:
            match = self._classify(str(item.get("text", "")))
            problems = []
            if match is not None:
                dept, canonical = match
                problems.append({
                    "summary": canonical,
                    "department_code": dept,
                    "specifics": str(item.get("text", ""))[:160],
                })
            results.append({"review_id": item.get("review_id"), "problems": problems})
        return {"results": results}

    def _consolidate(self, payload: Any) -> dict:
        groups: dict[tuple[str, str], list[str]] = {}
        for summary in payload or []:
            match = self._classify(summary) or ("guest_relations", summary[:60] or "General guest concern")
            groups.setdefault(match, []).append(summary)
        types_out = [
            {"canonical_title": canonical, "department_code": dept, "member_summaries": members}
            for (dept, canonical), members in groups.items()
        ]
        return {"types": types_out}

    def _taxonomy(self, payload: Any) -> dict:
        # payload = list of summary strings. Build the unique (dept, canonical) buckets.
        seen: dict[tuple[str, str], None] = {}
        for summary in payload or []:
            match = self._classify(summary) or ("guest_relations", str(summary)[:60] or "General guest concern")
            seen.setdefault((match[0], match[1]), None)
        return {"types": [{"canonical_title": title, "department_code": dept} for (dept, title) in seen]}

    def _assign(self, payload: Any) -> dict:
        # payload = {"summaries": [...], "taxonomy_titles": [...]}.
        summaries = (payload or {}).get("summaries", [])
        titles = (payload or {}).get("taxonomy_titles", [])
        index_by_title = {t: i for i, t in enumerate(titles)}
        assignments = []
        for i, summary in enumerate(summaries):
            match = self._classify(summary)
            t = index_by_title.get(match[1], -1) if match else -1
            assignments.append({"s": i, "t": t})
        return {"assignments": assignments}

    def _describe(self, payload: Any) -> dict:
        title = payload.get("title", "Issue")
        evidence = payload.get("evidence", []) or []
        count = payload.get("review_count", len(evidence))
        sample = evidence[0][:140] if evidence else ""
        desc = f"{count} guest review(s) describe: {title.lower()}."
        if sample:
            desc += f' For example: "{sample}".'
        return {"description": desc}


# --------------------------------------------------------------------------------------------
# Public client
# --------------------------------------------------------------------------------------------
@dataclass
class LLMClient:
    provider: Any
    provider_name: str
    model_name: str

    def is_available(self) -> bool:
        return self.provider is not None

    def generate_json(
        self,
        *,
        system: str,
        user: str,
        task: str = "",
        payload: Any = None,
    ) -> Any:
        if self.provider is None:
            raise LLMUnavailableError(
                "No LLM provider configured. Set GEMINI_API_KEY (LLM_PROVIDER=gemini) "
                "or LLM_PROVIDER=stub for offline runs."
            )
        if self.provider_name == "stub":
            return self.provider.generate_json(system=system, user=user, task=task, payload=payload)
        return self.provider.generate_json(system=system, user=user)


def _build_client() -> LLMClient:
    provider_name = os.getenv("LLM_PROVIDER", "").strip().lower()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

    # Default to gemini when a key exists; otherwise fall back to the offline stub.
    if not provider_name:
        provider_name = "gemini" if api_key else "stub"

    if provider_name == "stub":
        return LLMClient(provider=_StubProvider(), provider_name="stub", model_name="stub-deterministic")

    if provider_name == "gemini":
        if not api_key:
            # Configured for gemini but no key -> unavailable; endpoints surface a clear 503.
            return LLMClient(provider=None, provider_name="gemini", model_name=DEFAULT_GEMINI_MODEL)
        model = os.getenv("LLM_MODEL", DEFAULT_GEMINI_MODEL)
        try:
            provider = _GeminiProvider(api_key=api_key, model=model)
        except Exception:  # noqa: BLE001 - missing SDK / bad config -> unavailable
            return LLMClient(provider=None, provider_name="gemini", model_name=model)
        return LLMClient(provider=provider, provider_name="gemini", model_name=model)

    raise LLMUnavailableError(f"Unknown LLM_PROVIDER {provider_name!r}")


@lru_cache(maxsize=1)
def get_llm_client() -> LLMClient:
    return _build_client()


def reset_llm_client_cache() -> None:
    """Test helper: clear the cached client so env changes take effect."""
    get_llm_client.cache_clear()

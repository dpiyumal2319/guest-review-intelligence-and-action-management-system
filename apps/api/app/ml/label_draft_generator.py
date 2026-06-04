from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Callable, Iterable
from urllib import request

from app.ml.issue_classifier import validate_labelled_csv
from app.seed_data import ISSUE_CATEGORIES


CSV_COLUMNS = ("review_id", "text", "issue_category_code", "source_code", "rating", "notes")
DEFAULT_MODEL = "qwen2.5-coder:7b"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_ROWS_PER_CATEGORY = 40
DEFAULT_TOTAL_ROWS = 1000
DEFAULT_BATCH_SIZE = 10
DEFAULT_MAX_RETRIES = 3
DEFAULT_SOURCE_CODE = "qwen_synthetic_evaluation"
DEFAULT_NOTES = "qwen-generated synthetic evaluation label"
MIN_REVIEW_WORDS = 35
PROMPT_VERSION = "qwen-issue-label-synthetic-v2"


@dataclass(frozen=True)
class GeneratedLabelRow:
    review_id: str
    text: str
    issue_category_code: str
    source_code: str
    rating: int
    notes: str


@dataclass(frozen=True)
class DraftGenerationResult:
    output_path: Path
    rows: list[GeneratedLabelRow]
    label_counts: dict[str, int]
    validation_errors: list[str]
    duplicate_count: int


def taxonomy_codes() -> list[str]:
    return [category["code"] for category in ISSUE_CATEGORIES]


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def slug_for_category(category_code: str) -> str:
    return category_code.replace("_", "-")


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def preview_text(text: str, *, limit: int = 220) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def label_counts_for_total(total_rows: int) -> dict[str, int]:
    codes = taxonomy_codes()
    if total_rows < len(codes):
        raise ValueError(f"total_rows must be at least {len(codes)} so every category is represented.")
    base_count, remainder = divmod(total_rows, len(codes))
    return {
        code: base_count + (1 if index < remainder else 0)
        for index, code in enumerate(codes)
    }


def build_prompt(*, category_code: str, category_name: str, category_description: str, count: int) -> str:
    return (
        "Generate synthetic hotel guest review training examples for an academic issue-category classifier.\n"
        "Return JSON only, with this exact shape: "
        '{"rows":[{"text":"...", "rating": 1}]}\n'
        f"Category code: {category_code}\n"
        f"Category name: {category_name}\n"
        f"Category description: {category_description}\n"
        f"Number of rows: {count}\n"
        "Rules:\n"
        "- Each text must be a realistic English hotel guest review between 40 and 260 words.\n"
        "- Use 2 to 6 sentences per review, with natural detail rather than generic one-line complaints.\n"
        "- Randomize stay context: solo travel, couple, family, business trip, event, weekend, long stay, or transit.\n"
        "- Vary voice and structure: calm and specific, frustrated, balanced, highly positive, or disappointed.\n"
        "- Include concrete hotel details such as arrival time, room features, staff interactions, meals, noise sources, facilities, price expectations, or follow-up requests.\n"
        "- The main label must clearly match the requested category, but natural background context is allowed.\n"
        "- Vary wording, guest situation, severity, and rating.\n"
        "- Use ratings from 1 to 5.\n"
        "- Do not include names, phone numbers, emails, reservation IDs, or private identifiers.\n"
        "- Do not make every review the same length or template.\n"
        "- Do not include markdown, explanations, comments, or extra keys."
    )


def ollama_request(prompt: str, *, model: str = DEFAULT_MODEL, ollama_url: str = DEFAULT_OLLAMA_URL) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.8},
        }
    ).encode("utf-8")
    http_request = request.Request(
        ollama_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=120) as response:
        response_payload = json.loads(response.read().decode("utf-8"))
    return str(response_payload.get("response", ""))


def extract_json_payload(raw_response: str) -> object:
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start_candidates = [index for index in [cleaned.find("{"), cleaned.find("[")] if index >= 0]
        end_candidates = [index for index in [cleaned.rfind("}"), cleaned.rfind("]")] if index >= 0]
        if not start_candidates or not end_candidates:
            raise
        return json.loads(cleaned[min(start_candidates) : max(end_candidates) + 1])


def parse_generated_rows(
    raw_response: str,
    *,
    category_code: str,
    source_code: str = DEFAULT_SOURCE_CODE,
    notes: str = DEFAULT_NOTES,
) -> list[GeneratedLabelRow]:
    payload = extract_json_payload(raw_response)
    if isinstance(payload, dict):
        raw_rows = payload.get("rows") or payload.get("reviews") or payload.get("items")
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        raise ValueError("Ollama response did not contain a JSON row list.")

    rows: list[GeneratedLabelRow] = []
    for index, item in enumerate(raw_rows, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("review") or item.get("review_text") or "").strip()
        if word_count(text) < MIN_REVIEW_WORDS:
            continue
        try:
            rating = int(float(item.get("rating", 3)))
        except (TypeError, ValueError):
            continue
        if rating < 1 or rating > 5:
            continue
        rows.append(
            GeneratedLabelRow(
                review_id=f"pending-{category_code}-{index:03d}",
                text=text,
                issue_category_code=category_code,
                source_code=source_code,
                rating=rating,
                notes=notes,
            )
        )
    return rows


def count_raw_rows(raw_response: str) -> int:
    try:
        payload = extract_json_payload(raw_response)
    except json.JSONDecodeError:
        return 0
    if isinstance(payload, dict):
        raw_rows = payload.get("rows") or payload.get("reviews") or payload.get("items")
    else:
        raw_rows = payload
    return len(raw_rows) if isinstance(raw_rows, list) else 0


def dedupe_rows(rows: Iterable[GeneratedLabelRow]) -> tuple[list[GeneratedLabelRow], int]:
    seen_texts: set[str] = set()
    deduped: list[GeneratedLabelRow] = []
    duplicate_count = 0
    for row in rows:
        key = normalize_text(row.text)
        if key in seen_texts:
            duplicate_count += 1
            continue
        seen_texts.add(key)
        deduped.append(row)
    return deduped, duplicate_count


def assign_review_ids(rows: Iterable[GeneratedLabelRow]) -> list[GeneratedLabelRow]:
    counters = {code: 0 for code in taxonomy_codes()}
    assigned: list[GeneratedLabelRow] = []
    for row in rows:
        counters[row.issue_category_code] = counters.get(row.issue_category_code, 0) + 1
        assigned.append(
            GeneratedLabelRow(
                review_id=f"qwen-{slug_for_category(row.issue_category_code)}-{counters[row.issue_category_code]:03d}",
                text=row.text,
                issue_category_code=row.issue_category_code,
                source_code=row.source_code,
                rating=row.rating,
                notes=row.notes,
            )
        )
    return assigned


def write_labelled_csv(rows: Iterable[GeneratedLabelRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def generate_label_drafts(
    *,
    output_path: Path,
    rows_per_category: int = DEFAULT_ROWS_PER_CATEGORY,
    target_counts: dict[str, int] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_retries: int = DEFAULT_MAX_RETRIES,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    request_text: Callable[[str], str] | None = None,
    log: Callable[[str], None] | None = None,
) -> DraftGenerationResult:
    requester = request_text or (lambda prompt: ollama_request(prompt, model=model, ollama_url=ollama_url))
    all_rows: list[GeneratedLabelRow] = []
    duplicate_count = 0
    allowed_codes = set(taxonomy_codes())
    counts_by_category = target_counts or {code: rows_per_category for code in taxonomy_codes()}

    for category_index, category in enumerate(ISSUE_CATEGORIES, start=1):
        category_code = category["code"]
        category_target = counts_by_category[category_code]
        category_rows: list[GeneratedLabelRow] = []
        seen_for_category: set[str] = set()
        attempts = 0
        if log is not None:
            log(
                f"[{category_index}/{len(ISSUE_CATEGORIES)}] generating {category_target} "
                f"rows for {category_code}"
            )
        while len(category_rows) < category_target:
            attempts += 1
            target_for_batch = min(batch_size, category_target - len(category_rows))
            prompt = build_prompt(
                category_code=category_code,
                category_name=category["name"],
                category_description=category["description"],
                count=target_for_batch,
            )
            raw_response = requester(prompt)
            if log is not None:
                log(f'  raw qwen preview: "{preview_text(raw_response, limit=500)}"')
            raw_row_count = count_raw_rows(raw_response)
            try:
                parsed_rows = parse_generated_rows(raw_response, category_code=category_code)
            except (json.JSONDecodeError, ValueError) as error:
                if log is not None:
                    log(
                        f"  request {attempts}: discarded invalid qwen response "
                        f"({error.__class__.__name__}); total {len(category_rows)}/{category_target}"
                    )
                continue
            accepted_before_batch = len(category_rows)
            for row in parsed_rows:
                if row.issue_category_code not in allowed_codes:
                    continue
                normalized = normalize_text(row.text)
                if normalized in seen_for_category:
                    duplicate_count += 1
                    continue
                seen_for_category.add(normalized)
                category_rows.append(row)
                if log is not None:
                    log(
                        f'    accepted {category_code} #{len(category_rows)}: '
                        f'rating={row.rating}, words={word_count(row.text)}, '
                        f'text="{preview_text(row.text)}"'
                    )
                if len(category_rows) >= category_target:
                    break
            if log is not None:
                accepted = len(category_rows) - accepted_before_batch
                rejected = max(raw_row_count - len(parsed_rows), 0)
                log(
                    f"  request {attempts}: accepted {accepted} "
                    f"of {len(parsed_rows)} valid parsed rows; rejected {rejected} short/invalid rows; "
                    f"total {len(category_rows)}/{category_target}"
                )
        if log is not None:
            log(f"  completed {category_code}: {len(category_rows)} rows")
        all_rows.extend(category_rows)

    assigned_rows, cross_category_duplicates = dedupe_rows(assign_review_ids(all_rows))
    duplicate_count += cross_category_duplicates
    if log is not None:
        log(f"writing {len(assigned_rows)} rows to {output_path}")
    write_labelled_csv(assigned_rows, output_path)
    validation = validate_labelled_csv(output_path)
    label_counts = {
        code: sum(1 for row in assigned_rows if row.issue_category_code == code)
        for code in taxonomy_codes()
    }
    return DraftGenerationResult(
        output_path=output_path,
        rows=assigned_rows,
        label_counts=label_counts,
        validation_errors=validation.errors,
        duplicate_count=duplicate_count,
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_manifest(
    *,
    csv_path: Path,
    model: str = DEFAULT_MODEL,
    prompt_version: str = PROMPT_VERSION,
    human_reviewed: bool,
) -> dict:
    validation = validate_labelled_csv(csv_path)
    label_counts: dict[str, int] = {}
    if validation.is_valid:
        for row in validation.rows:
            label_counts[row.issue_category_code] = label_counts.get(row.issue_category_code, 0) + 1
    return {
        "csv_path": str(csv_path),
        "csv_sha256": sha256_file(csv_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "human_reviewed": human_reviewed,
        "model": model,
        "prompt_version": prompt_version,
        "row_count": len(validation.rows),
        "label_counts": dict(sorted(label_counts.items())),
        "validation": {
            "is_valid": validation.is_valid,
            "errors": validation.errors,
        },
    }


def write_dataset_manifest(manifest: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate or document Qwen-assisted issue-label datasets.")
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Generate synthetic labelled rows with local Ollama.")
    row_count_group = generate_parser.add_mutually_exclusive_group()
    row_count_group.add_argument("--rows-per-category", type=int, default=DEFAULT_ROWS_PER_CATEGORY)
    row_count_group.add_argument(
        "--total-rows",
        type=int,
        help=f"Generate a balanced dataset with this many total rows. Full synthetic target: {DEFAULT_TOTAL_ROWS}.",
    )
    generate_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    generate_parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Deprecated compatibility option; generation now continues until targets are filled.",
    )
    generate_parser.add_argument("--model", default=DEFAULT_MODEL)
    generate_parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    generate_parser.add_argument("--quiet", action="store_true", help="Suppress progress logs.")
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/api/data/labelled/qwen_issue_labels_draft.csv"),
    )

    manifest_parser = subparsers.add_parser("manifest", help="Write an evidence manifest for an approved CSV.")
    manifest_parser.add_argument("csv_path", type=Path)
    manifest_parser.add_argument("--model", default=DEFAULT_MODEL)
    manifest_parser.add_argument("--human-reviewed", action="store_true")
    manifest_parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/research/evidence/qwen_issue_labels_manifest.json"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv.insert(0, "generate")
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command

    if command == "generate":
        target_counts = label_counts_for_total(args.total_rows) if args.total_rows is not None else None
        result = generate_label_drafts(
            output_path=args.output,
            rows_per_category=args.rows_per_category,
            target_counts=target_counts,
            batch_size=args.batch_size,
            max_retries=args.max_retries,
            model=args.model,
            ollama_url=args.ollama_url,
            log=None if args.quiet else lambda message: print(message, flush=True),
        )
        print(
            json.dumps(
                {
                    "output_path": str(result.output_path),
                    "row_count": len(result.rows),
                    "label_counts": result.label_counts,
                    "duplicate_count": result.duplicate_count,
                    "validation_errors": result.validation_errors,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if not result.validation_errors else 1

    if command == "manifest":
        manifest = build_dataset_manifest(
            csv_path=args.csv_path,
            model=args.model,
            human_reviewed=args.human_reviewed,
        )
        write_dataset_manifest(manifest, args.output)
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0 if manifest["validation"]["is_valid"] else 1

    parser.error(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

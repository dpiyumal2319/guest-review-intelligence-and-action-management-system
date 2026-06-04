from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import random
import re
import sys
from typing import Callable, Iterable
from urllib import request

from app.ml.issue_classifier import validate_labelled_csv
from app.seed_data import ISSUE_CATEGORIES


CSV_COLUMNS = ("review_id", "text", "issue_category_code", "source_code", "rating", "notes")
DEFAULT_MODEL = "qwen2.5-coder:7b"
DOLPHIN_MODEL = "dolphin-llama3:latest"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_TOTAL_ROWS = 1000
DEFAULT_SOURCE_CODE = "ollama_synthetic_evaluation"
DEFAULT_NOTES = "ollama-generated synthetic evaluation label"
PROMPT_VERSION = "ollama-issue-label-synthetic-v3"


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


def preview_text(text: str, *, limit: int = 500) -> str:
    normalized = re.sub(r"\s+", " ", text.strip())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def build_prompt(*, category_code: str, category_name: str, category_description: str, model: str) -> str:
    tone_rule = (
        "Dolphin is allowed to produce blunt, angry, aggressive guest language when the rating is low, "
        "but do not include hate speech, threats, private identifiers, or explicit slurs.\n"
        if model == DOLPHIN_MODEL
        else ""
    )
    return (
        "Generate one synthetic hotel guest review for an academic issue-category classifier.\n"
        "Return JSON only, with this exact shape: "
        '{"text":"...", "rating": 1}\n'
        f"Category code: {category_code}\n"
        f"Category name: {category_name}\n"
        f"Category description: {category_description}\n"
        "Rules:\n"
        "- The review should usually be 40 to 260 words, but natural shorter reviews are fine.\n"
        "- Make the main issue clearly match the requested category.\n"
        "- Randomize stay context: solo, couple, family, business trip, weekend, long stay, event, or transit.\n"
        "- Vary tone, severity, wording, and rating.\n"
        "- Include concrete hotel details when useful.\n"
        f"{tone_rule}"
        "- Use a rating from 1 to 5.\n"
        "- Do not include names, phone numbers, emails, reservation IDs, or private identifiers.\n"
        "- Do not include markdown, explanations, comments, or extra keys."
    )


def ollama_request(prompt: str, *, model: str = DEFAULT_MODEL, ollama_url: str = DEFAULT_OLLAMA_URL) -> str:
    payload = json.dumps(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.95},
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
    if isinstance(payload, dict) and any(key in payload for key in ("text", "review", "review_text")):
        raw_rows = [payload]
    elif isinstance(payload, dict):
        raw_rows = payload.get("rows") or payload.get("reviews") or payload.get("items")
    else:
        raw_rows = payload
    if not isinstance(raw_rows, list):
        raise ValueError("Ollama response did not contain a JSON review object or row list.")

    rows: list[GeneratedLabelRow] = []
    for index, item in enumerate(raw_rows, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or item.get("review") or item.get("review_text") or "").strip()
        if not text:
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


def assign_review_ids(rows: Iterable[GeneratedLabelRow]) -> list[GeneratedLabelRow]:
    counters = {code: 0 for code in taxonomy_codes()}
    assigned: list[GeneratedLabelRow] = []
    for row in rows:
        counters[row.issue_category_code] = counters.get(row.issue_category_code, 0) + 1
        assigned.append(
            GeneratedLabelRow(
                review_id=f"synthetic-{slug_for_category(row.issue_category_code)}-{counters[row.issue_category_code]:03d}",
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
    total_rows: int = DEFAULT_TOTAL_ROWS,
    model: str = DEFAULT_MODEL,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    request_text: Callable[[str], str] | None = None,
    log: Callable[[str], None] | None = None,
    rng: random.Random | None = None,
) -> DraftGenerationResult:
    requester = request_text or (lambda prompt: ollama_request(prompt, model=model, ollama_url=ollama_url))
    randomizer = rng or random.Random()
    accepted_rows: list[GeneratedLabelRow] = []
    seen_texts: set[str] = set()
    duplicate_count = 0

    while len(accepted_rows) < total_rows:
        category = randomizer.choice(ISSUE_CATEGORIES)
        category_code = category["code"]
        prompt = build_prompt(
            category_code=category_code,
            category_name=category["name"],
            category_description=category["description"],
            model=model,
        )
        raw_response = requester(prompt)
        try:
            parsed_rows = parse_generated_rows(raw_response, category_code=category_code)
        except (json.JSONDecodeError, ValueError):
            if log is not None:
                log(f"discarded invalid model output; completed {len(accepted_rows)}/{total_rows}")
                log(f'model output: "{preview_text(raw_response)}"')
            continue

        accepted_this_call = False
        for row in parsed_rows:
            normalized = normalize_text(row.text)
            if normalized in seen_texts:
                duplicate_count += 1
                continue
            seen_texts.add(normalized)
            accepted_rows.append(row)
            accepted_this_call = True
            if log is not None:
                log(f"completed {len(accepted_rows)}/{total_rows} [{category_code}] rating={row.rating}")
                log(f'model output review: "{preview_text(row.text)}"')
            break

        if not accepted_this_call and log is not None:
            log(f"discarded invalid or duplicate model output; completed {len(accepted_rows)}/{total_rows}")
            log(f'model output: "{preview_text(raw_response)}"')

    assigned_rows = assign_review_ids(accepted_rows)
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
    parser = argparse.ArgumentParser(description="Generate or document Ollama-assisted issue-label datasets.")
    subparsers = parser.add_subparsers(dest="command")

    generate_parser = subparsers.add_parser("generate", help="Generate synthetic labelled rows with local Ollama.")
    generate_parser.add_argument("--total-rows", type=int, default=DEFAULT_TOTAL_ROWS)
    generate_parser.add_argument("--model", default=DEFAULT_MODEL)
    generate_parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    generate_parser.add_argument("--quiet", action="store_true", help="Suppress progress logs.")
    generate_parser.add_argument(
        "--output",
        type=Path,
        default=Path("apps/api/data/labelled/ollama_issue_labels_synthetic.csv"),
    )

    manifest_parser = subparsers.add_parser("manifest", help="Write an evidence manifest for a generated CSV.")
    manifest_parser.add_argument("csv_path", type=Path)
    manifest_parser.add_argument("--model", default=DEFAULT_MODEL)
    manifest_parser.add_argument("--human-reviewed", action="store_true")
    manifest_parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/research/evidence/ollama_issue_labels_manifest.json"),
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
        result = generate_label_drafts(
            output_path=args.output,
            total_rows=args.total_rows,
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

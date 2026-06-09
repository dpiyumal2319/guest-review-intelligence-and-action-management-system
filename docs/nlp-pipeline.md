# NLP Pipeline

## Scope

The NLP pipeline turns normalized review text and metadata into operational intelligence through two distinct subsystems:

**Local NLP** (runs automatically on every review at ingestion time):
- sentiment label, score, and confidence;
- department classification via zero-shot inference;
- Reputation Risk score and label;
- embedding generation for semantic similarity;
- explanation factors and model metadata.

**LLM Issue Detection** (triggered on demand via API or CLI):
- extracting normalized problems from negative/mixed reviews;
- consolidating synonymous problems into canonical issue types;
- assembling `DetectedIssue` records with evidence-grounded descriptions.

## Execution Points

Local NLP analysis runs automatically after connector ingestion when a normalized review is created or updated.

Manual reanalysis is available through:

```bash
curl -X POST http://localhost:8000/analysis/reanalyze
curl -X POST "http://localhost:8000/analysis/reanalyze?source_code=google_business_profile"
```

Reanalysis updates the active `review_analyses` row for each review.

Issue detection is triggered separately:

```bash
curl -X POST "http://localhost:8000/issues/detect?force=true"
```

Which runs a three-pass LLM pipeline (extract → consolidate → assemble) against negative/mixed reviews.

## Sentiment

Sentiment uses `apps/api/app/sentiment.py` with the Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` text-classification pipeline.

Runtime contract:
- the model artifact must be available locally (`local_files_only=True`);
- missing dependencies or artifacts fail clearly instead of returning a rules-based fallback.

Inputs:
- review title and body;
- optional numeric source rating.

Outputs:
- `sentiment_label`: `positive`, `mixed`, or `negative`;
- `sentiment_score`: bounded from `-1.0` to `1.0`;
- `sentiment_confidence`;
- explanation factors containing model strategy and label-mapping details.

The model output is mapped as `1-2 stars -> negative`, `3 stars -> mixed`, and `4-5 stars -> positive`.

## Department Classification

Department classification is implemented in `apps/api/app/ml/department_classifier.py`.

Runtime behavior:
- uses Hugging Face `facebook/bart-large-mnli`;
- runs zero-shot classification against 6 department candidate labels:
  - `"housekeeping room cleanliness bathroom cleaning linen hygiene"`
  - `"front office reception check-in check-out booking reservations arrival"`
  - `"food beverage restaurant dining breakfast bar room service cuisine"`
  - `"engineering maintenance repair air conditioning plumbing facility defects"`
  - `"management pricing value strategy policy hotel administration"`
  - `"guest relations service recovery follow-up complaint handling staff courtesy"`
- returns top-ranked department prediction per review;
- falls back to `guest_relations` with 0.3 confidence if the model runtime is unavailable.

Prediction metadata per result:
- `department_code` — the matched department;
- `confidence` — zero-shot classification confidence;
- `rank` — prediction rank;
- `model_name` — `"huggingface-transformers-zero-shot-classification"`;
- `model_version` — model revision or pipeline identifier.

Each sentence in a review receives its own independent department classification. Sentence-level and review-level predictions are stored in `explanation_factors.department`.

## Reputation Risk

Reputation Risk is the single user-facing risk metric. It combines likely guest-perception damage with operational urgency.

Inputs (from `analysis.py::score_reputation_risk`):
- numeric rating;
- sentiment score;
- department risk weight (from `departments.risk_weight`: front_office=12, housekeeping=14, food_beverage=12, engineering=16, guest_relations=12, management=18);
- review recency;
- urgency terms (12 keywords: angry, broken, dangerous, dirty, hygiene, immediately, late at night, manager, refund, unsafe, urgent);
- content duplicate signal;
- source/platform visibility signals (helpful votes, public reply status, review URL presence).

Weights:
- rating: up to 30 points — `(5 - rating) / 4 * 30`;
- negative sentiment: up to 25 points — `-sentiment_score * 25`;
- department weight: from `departments.risk_weight` (direct, unscaled);
- recency: ≤7 days = 5 points, ≤30 days = 2 points, older = 0;
- urgency terms: 5 points per matched term, max 15;
- duplicate signal: 5 points if detected;
- platform visibility: up to 8 points (helpful votes + public URL + unreplied status).

Total is capped at 100.

Labels:
- `low`: 0-29;
- `medium`: 30-49;
- `high`: 50-74;
- `critical`: 75-100.

The score, label, weights, visibility signals, thresholds, and operational explanations are stored in `explanation_factors.reputation_risk`.

## Department Mapping

Department ownership is determined by zero-shot classification at analysis time. The single most-confident department is stored as `department_code` on `ReviewAnalysis`. There is no separate category-to-department mapping table — classification maps directly to departments.

If no classifier result is available (model unloaded), the system routes to `guest_relations`.

## Duplicate Signals

The analysis pipeline includes duplicate detection:

- **Content duplicates**: flagged during ingestion by normalized content hash (`normalized_content_hash` in `ingestion.py`). Reviews sharing the same hash are linked via `normalized_reviews.duplicate_of_review_id`.
- **Semantic near-duplicates**: computed on demand through the `GET /analysis/semantic-clusters` endpoint. Near-duplicate pairs and clusters are built from pairwise embedding similarity, not merged automatically.

## Semantic Similarity

Semantic similarity lives in `apps/api/app/semantic_similarity.py`.

Endpoint:
```bash
curl "http://localhost:8000/analysis/semantic-clusters?similarity_threshold=0.30"
```

Default behavior:
- uses the current MVP review-platform records;
- uses `similarity_threshold = 0.78` (sentence-transformer);
- uses `min_cluster_size = 2`.

Implementation — three-tier fallback:
1. **Primary**: `sentence-transformers/all-MiniLM-L6-v2` — 384-dim normalized embeddings with cosine similarity;
2. **Fallback 1**: scikit-learn `TfidfVectorizer` (ngram 1-2) with cosine similarity (`TFIDF_FALLBACK_SIMILARITY_THRESHOLD = 0.30`);
3. **Fallback 2**: token overlap with Jaccard-style similarity (`|A∩B| / sqrt(|A|·|B|)`) at threshold 0.30.

Embeddings are also used by the issue detection pipeline to compute cluster centroids for `detected_issues.cluster_centroid`.

Connected components (BFS) over pairwise similarities above the threshold form clusters. Centroids are L2-normalized averages.

Response includes:
- embedding strategy used;
- embedding model name/version;
- fallback note;
- near-duplicate pairs;
- semantic clusters with representative review, department, source mix, review IDs, and average similarity.

Semantic clusters support recurring-issue discovery but do not delete or merge reviews.

## LLM-Driven Issue Detection

Issue detection is a separate pipeline in `apps/api/app/issue_detection.py` that uses an LLM (Gemini by default, deterministic stub for offline) via the provider-agnostic `llm_client.py`.

It does NOT require a paid LLM key — setting `LLM_PROVIDER=stub` runs the full pipeline offline with keyword-rule determinism (intended for tests and constrained environments). For real-world quality, set `LLM_PROVIDER=gemini` with `GEMINI_API_KEY`.

### Three-pass pipeline

**Pass A — Extraction**: Each negative/mixed review (batch of 8) is sent to the LLM to extract discrete problems as `{summary, department_code, specifics}`. Specifics capture concrete facts (room number, floor, item, amount, time).

**Pass B — Consolidation**: All extracted problem summaries are processed in two LLM steps:
1. Discover a taxonomy of canonical issue types from up to 800 frequent labels.
2. Assign each label to a taxonomy type by index (or `-1` for unique incidents).

Severe/distinct incidents (pest, theft, safety) are kept as their own type.

**Pass C — Assembly**: Each canonical type becomes a `DetectedIssue`:
- ≥2 supporting reviews → `status = "active"` (with LLM-written description citing concrete specifics);
- 1 supporting review → `status = "emerging"` (precomputed candidate, no description);
- `cluster_key` is hash-based for idempotent rebuild;
- centroid embedding from linked review embeddings;
- priority derived from max reputation risk score of linked reviews.

### State preservation

On rebuild, resolved/assigned state is preserved by `cluster_key` match. Manually resolved issues stay resolved; assignees survive detection rebuilds.

## Model Tracking Contract

Every persisted analysis must be explainable through stored metadata:
- `model_name` — analyzer/classifier identifier;
- `model_version` — artifact identifier;
- `analysis_version` — contract version (`"analysis-v3"`);
- `sentiment_confidence` / `department_confidence`;
- `analyzed_at` — UTC timestamp;
- `explanation_factors` — transparent feature contributions and routing notes.

For `DetectedIssue` records:
- `title_generated_by` — LLM provider name (`"gemini"` or `"stub"`);
- `title_generation_model` — model ID (`"gemini-2.5-flash"` or `"stub-deterministic"`);
- `embedding_model_name` — which embedding model generated the centroid;
- `cluster_key` — stable hash for rebuild consistency.

The staff UI shows operational explanations, not model internals. Technical audit data remains stored in the backend.

## Known Prototype Limits

- English-first analysis.
- Required local Hugging Face model artifacts must be provisioned before the demo.
- V1 stores only the latest active analysis per review.
- Semantic similarity is optional support for recurring issue discovery and may fall back to lighter local methods.
- Issue detection is a batch rebuild, not incremental — re-running replaces the full issue set.
- The system surfaces risks and recurring patterns; it does not delete, suppress, or manipulate platform reviews.

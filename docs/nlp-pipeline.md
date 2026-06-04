# NLP Pipeline

## Scope

The NLP pipeline turns normalized review text and metadata into operational intelligence:

- sentiment label, score, and confidence;
- issue-category predictions;
- Reputation Risk score and label;
- department ownership;
- duplicate, recency, visibility, and recurrence signals;
- semantic near-duplicate pairs and issue clusters;
- explanation factors and model metadata.

The pipeline is local and reproducible. It does not require paid LLM APIs and does not call Ollama at product runtime.

## Execution Points

Analysis runs automatically after connector ingestion when a normalized review is created or updated.

Manual reanalysis is available through:

```bash
curl -X POST http://localhost:8000/analysis/reanalyze
curl -X POST "http://localhost:8000/analysis/reanalyze?source_code=google_business_profile"
```

Reanalysis updates the latest active `review_analyses` row and synchronizes summary columns back onto `normalized_reviews`.

## Sentiment

Sentiment uses `apps/api/app/sentiment.py` with the Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` text-classification pipeline.

Runtime contract:

- the model artifact must be available locally;
- the runtime uses local Hugging Face loading;
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

## Issue-Category Classification

Operational issue classification is implemented in `apps/api/app/ml/issue_classifier.py`.

Runtime behavior:

- uses Hugging Face `facebook/bart-large-mnli`;
- runs zero-shot classification against the seeded hotel issue taxonomy;
- returns ranked issue-category predictions;
- fails clearly when the required model runtime is unavailable.

Prediction metadata:

- `category_code`;
- `confidence`;
- `rank`;
- `is_primary`;
- `department_code`;
- `model_name`;
- `model_version`;
- `analyzed_at`.

The top-ranked prediction becomes the primary issue category for the active analysis and normalized review summary.

## Reputation Risk

Reputation Risk is the single user-facing risk metric. It combines likely guest-perception damage with likelihood of repeated future complaints.

Inputs:

- numeric rating;
- sentiment score;
- issue category;
- review recency;
- urgency terms;
- recurrence count in a seven-day window around the review date;
- content duplicate signal;
- source/platform visibility or engagement metadata where available.

Weights:

- rating: up to 30 points;
- negative sentiment: up to 25 points;
- issue-category weight: category-specific;
- recency: up to 8 points;
- urgency terms: up to 15 points;
- recurrence: up to 10 points;
- duplicate signal: 5 points;
- visibility/engagement: up to 7 points.

Labels:

- `low`: 0-29;
- `medium`: 30-49;
- `high`: 50-74;
- `critical`: 75-100.

The score, label, weights, visibility signals, and operational explanations are stored in `explanation_factors`.

## Department Mapping

Department ownership is data-backed through `category_department_mappings`.

The active analysis uses the primary department mapping for the selected issue category. If no primary mapping exists, the runtime routes to `guest_relations`.

This keeps operational routing explainable and adjustable without rewriting classifier logic.

## Recurrence and Duplicate Signals

The analysis pipeline includes recurrence and duplicate signals:

- `recurrence_count_7d`: number of reviews in the same category within a seven-day window around the review date;
- `duplicate_signal`: true when normalized payload duplicate metadata indicates a repeated or near-duplicate review.

Content duplicates are flagged by normalized content hash during ingestion. Semantic near duplicates are computed through the semantic similarity endpoint rather than automatically merging records.

## Semantic Similarity

Semantic similarity lives in `apps/api/app/semantic_similarity.py`.

Endpoint:

```bash
curl "http://localhost:8000/analysis/semantic-clusters?similarity_threshold=0.30"
```

Default behavior:

- uses the current MVP review-platform records;
- uses `similarity_threshold = 0.78`;
- uses `min_cluster_size = 2`.

Implementation:

- local sentence-transformer embeddings with cosine similarity when a local model artifact is available;
- local TF-IDF vectors with cosine similarity through scikit-learn as the first fallback for this optional clustering feature;
- token/Jaccard-style fallback when scikit-learn is unavailable;
- connected components over pairwise similarities form clusters.

Response includes:

- embedding strategy used for the current response;
- embedding model name/version;
- fallback note for the optional semantic feature;
- near-duplicate pairs;
- semantic clusters with representative review, category, department, source mix, review IDs, and average similarity.

Semantic clusters support recurring-issue discovery and can be converted into action tickets. They do not delete or merge reviews.

## Model Tracking Contract

Every persisted analysis must be explainable through stored metadata:

- `model_name`;
- `model_version`;
- `analysis_version`;
- `confidence`;
- `analyzed_at`;
- `explanation_factors`.

The staff UI shows operational explanations, not model internals. Technical audit data remains stored in the backend.

## Known Prototype Limits

- English-first analysis.
- Required sentiment and issue-category model artifacts must be provisioned locally before the demo.
- V1 stores only the latest active analysis per review.
- Semantic similarity is optional support for recurring issue discovery and may fall back to lighter local methods.
- The system surfaces risks and recurring patterns; it does not delete, suppress, or manipulate platform reviews.

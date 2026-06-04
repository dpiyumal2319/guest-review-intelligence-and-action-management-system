# NLP Pipeline

## Scope

The NLP pipeline turns normalized review text and metadata into operational intelligence:

- sentiment label, score, and confidence;
- issue-category predictions;
- Reputation Risk score and label;
- department ownership;
- duplicate and recurrence signals;
- semantic near-duplicate pairs and issue clusters;
- explanation factors and model metadata.

The pipeline is local and reproducible. It does not require paid LLM APIs.

## Execution Points

Analysis runs automatically after ingestion when a normalized review is created or updated.

Manual reanalysis is available through:

```bash
curl -X POST http://localhost:8000/analysis/reanalyze
```

Optional filters:

- `source_code`;
- `source_type`.

Reanalysis updates the latest active `review_analyses` row and synchronizes summary columns back onto `normalized_reviews`.

## Sentiment

Current prototype sentiment uses `apps/api/app/sentiment.py` with the Hugging Face `nlptown/bert-base-multilingual-uncased-sentiment` text-classification pipeline. The runtime requires the local model artifact and fails clearly when it is unavailable.

Inputs:

- review title and body tokens;
- optional numeric rating.

Signals:

- local transformer prediction when available;
- positive lexical terms;
- negative lexical terms;
- Hugging Face label and confidence.

Outputs:

- `sentiment_label`: `positive`, `mixed`, or `negative`;
- `sentiment_score`: bounded from `-1.0` to `1.0`;
- `sentiment_confidence`;
- explanation factors containing the Hugging Face strategy and label-mapping details.

The model output is mapped as `1-2 stars -> negative`, `3 stars -> mixed`, and `4-5 stars -> positive`.

## Issue-Category Classification

Operational issue classification is implemented in `apps/api/app/ml/issue_classifier.py`.

Runtime behavior:

- If a trained artifact exists, the runtime loads a TF-IDF + Logistic Regression classifier.
- If no artifact exists, it falls back to `KeywordBaselineClassifier`.
- The analyzer stores ranked predictions in `review_issue_category_predictions`.

Default artifact path:

```text
apps/api/artifacts/ml/issue_classifier.pkl
```

Environment overrides:

```text
ISSUE_CLASSIFIER_MODEL_PATH
ISSUE_CLASSIFIER_MODEL_VERSION
```

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

## Training and Evaluation

Manual labelling is research/evaluation infrastructure only. It is not part of hotel staff operations.

CSV requirements:

- required columns: `text`, `issue_category_code`;
- optional columns: `review_id`, `source_code`, `rating`, `notes`.

Validate labelled data:

```bash
cd apps/api
python -m app.ml.issue_classifier validate data/examples/issue_labels_sample.csv
```

Train and evaluate:

```bash
cd apps/api
python -m app.ml.issue_classifier train-evaluate \
  data/examples/issue_labels_sample.csv \
  --model-output artifacts/ml/issue_classifier.pkl \
  --report-output reports/ml/issue_classifier_evaluation.json
```

Evaluation output includes:

- dataset row counts;
- train/test counts;
- label counts;
- trained model macro F1;
- keyword baseline macro F1;
- per-class classification report;
- confusion matrix.

Macro F1 is the headline metric because issue categories are expected to be imbalanced.

## Reputation Risk

Reputation Risk is transparent and deterministic.

Inputs:

- numeric rating;
- sentiment score;
- issue category;
- urgency terms;
- recurrence count in a seven-day window around the review date;
- duplicate signal.

Weights:

- rating: up to 30 points;
- negative sentiment: up to 25 points;
- issue-category weight: category-specific;
- urgency terms: up to 15 points;
- recurrence: up to 10 points;
- duplicate signal: 5 points.

Labels:

- `low`: 0-29;
- `medium`: 30-49;
- `high`: 50-74;
- `critical`: 75-100.

The score, label, weights, and thresholds are stored in `explanation_factors`.

## Department Mapping

Department ownership is data-backed through `category_department_mappings`.

The active analysis uses the primary department mapping for the selected issue category. If no primary mapping exists, the fallback is `guest_relations`.

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

- excludes social-listening records unless explicitly included;
- uses `similarity_threshold = 0.78`;
- uses `min_cluster_size = 2`.

Implementation:

- local sentence-transformer embeddings with cosine similarity when a local model artifact is available;
- local TF-IDF vectors with cosine similarity through scikit-learn as the first fallback;
- token/Jaccard-style fallback when scikit-learn is unavailable;
- connected components over pairwise similarities form clusters.

Response includes:

- embedding strategy used for the current response;
- embedding model name/version;
- fallback note;
- near-duplicate pairs;
- semantic clusters with representative review, category, department, source mix, review IDs, and average similarity.

Semantic clusters support recurring-issue discovery and can be converted into action tickets.

## Model Tracking Contract

Every persisted analysis must be explainable through stored metadata:

- `model_name`;
- `model_version`;
- `analysis_version`;
- `confidence`;
- `analyzed_at`;
- `explanation_factors`.

This allows assessors to understand whether an output came from the local transformer sentiment path, deterministic sentiment fallback, trained classifier artifact, keyword fallback, or semantic similarity fallback.

## Known Prototype Limits

- English-first analysis.
- Transformer sentiment is opportunistic and local-only: the runtime does not download model weights automatically and falls back deterministically when no local artifact is present.
- Sentence embeddings are opportunistic and local-only: the runtime uses a local sentence-transformer artifact when available and otherwise falls back to TF-IDF or token overlap.
- V1 stores only the latest active analysis per review.
- The classifier requires enough labelled examples across at least two categories to train.
- Semantic similarity flags and clusters records; it does not delete or merge reviews.

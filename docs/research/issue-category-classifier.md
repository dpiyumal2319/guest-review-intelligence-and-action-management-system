# Issue-Category Classifier Research Workflow

This workflow is for offline research and evaluation only. Synthetic Ollama labels are used as accepted prototype evaluation data for the issue-category classifier; they are not part of the hotel operational review, ticket, or department workflow.

## Labelled CSV Format

Create a UTF-8 CSV with these required columns:

- `text`: review text used as the classifier input.
- `issue_category_code`: one seeded issue taxonomy code.

Optional columns are preserved for traceability but are not used for training:

- `review_id`
- `source_code`
- `rating`
- `notes`

The `issue_category_code` value must match one of the seeded codes in `apps/api/app/seed_data.py`: `cleanliness`, `room_condition`, `food_beverage`, `service_delay`, `staff_behavior`, `noise_events`, `pricing_value`, `booking_checkin`, `amenities_facilities`, `positive_general`, or `other_uncategorized`.

See `apps/api/data/examples/issue_labels_sample.csv` for a small committed hand-written format example. Generated synthetic datasets should stay outside git under ignored generated-data paths such as `apps/api/data/labelled/`.

## Validate Labels

From `apps/api`:

```bash
python3 -m app.ml.issue_classifier validate data/examples/issue_labels_sample.csv
```

Validation checks required columns, non-empty text, and labels against the seeded issue taxonomy.

## Train And Evaluate

The required classifier is a classical scikit-learn pipeline:

- TF-IDF word and bigram features.
- Balanced logistic regression classifier.

It is compared with a deterministic keyword-rule baseline so the trained classifier has a simple reference point.

From `apps/api`:

```bash
python3 -m app.ml.issue_classifier train-evaluate data/examples/issue_labels_sample.csv \
  --model-output artifacts/ml/issue_classifier.pkl \
  --report-output reports/ml/issue_classifier_evaluation.json
```

The JSON report includes:

- dataset row counts and label counts.
- trained model macro F1.
- baseline macro F1.
- per-class precision/recall/F1.
- confusion matrix labels and matrix values.

Use a larger Ollama-generated synthetic dataset for meaningful prototype-scale results. The committed hand-written sample is intentionally tiny and exists only to document the format.

## Ollama Synthetic Dataset Workflow

The repository supports low-cost synthetic review generation with local Ollama models. Generated rows are accepted as synthetic evaluation labels, not human-labelled ground truth.

From the repository root, generate 1000 synthetic labels with Qwen:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py \
  --total-rows 1000 \
  --model qwen2.5-coder:7b
```

Generate the same volume with Dolphin for more aggressive negative-review wording:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py \
  --total-rows 1000 \
  --model dolphin-llama3:latest
```

The script makes one model request per review, randomly picks one seeded issue category before each request, and keeps going until the total target is reached. Logs show only the total completion count and accepted model output review:

```text
completed 17/1000 [cleanliness] rating=2
model output review: "The bathroom smelled damp when I walked in, and the sink had marks that looked like it had not been cleaned properly..."
```

Use `--quiet` to suppress progress logs when running in automation.

Default behavior:

- `--total-rows 1000` controls the only target count.
- The issue category is selected randomly for each accepted review.
- Calls local Ollama at `http://127.0.0.1:11434/api/generate`.
- Writes the generated CSV to ignored path `apps/api/data/labelled/ollama_issue_labels_synthetic.csv`.
- Uses IDs such as `synthetic-cleanliness-001`.
- Uses `source_code=ollama_synthetic_evaluation`.
- Uses `notes=ollama-generated synthetic evaluation label`.
- Prompts for realistic 40-260 word reviews with randomized stay context, tone, and detail.
- Keeps requesting from the local model until the total target count is reached.
- Discards invalid JSON, empty text rows, invalid ratings, and duplicate normalized text.

For a quick smoke test without creating the full dataset:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py \
  --total-rows 10 \
  --model qwen2.5-coder:7b \
  --output /tmp/ollama_issue_labels_smoke.csv
```

After full generation succeeds, validate the synthetic dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier validate data/labelled/ollama_issue_labels_synthetic.csv
```

Write an evidence manifest if you want to commit evidence without committing the generated CSV:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py manifest \
  apps/api/data/labelled/ollama_issue_labels_synthetic.csv \
  --model qwen2.5-coder:7b \
  --output docs/research/evidence/ollama_issue_labels_manifest.json
```

Train and evaluate from the synthetic dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier train-evaluate data/labelled/ollama_issue_labels_synthetic.csv \
  --model-output /tmp/ollama_issue_classifier.pkl \
  --report-output ../../docs/research/evidence/ollama_issue_classifier_evaluation.json
```

Commit the manifest and evaluation report so assessors can verify row counts, label distribution, validation status, model name, prompt version, CSV SHA256, and classifier metrics.

## Published Prototype Evaluation Evidence

- Labelled dataset artifact: `apps/api/data/examples/issue_labels_sample.csv` (8 labelled rows).
- Evaluation output artifact: `docs/research/evidence/issue_labels_sample_evaluation.json`.
- Regeneration command:

```bash
cd apps/api
python3 -m app.ml.issue_classifier train-evaluate \
  data/examples/issue_labels_sample.csv \
  --model-output /tmp/issue_classifier.pkl \
  --report-output /tmp/issue_labels_sample_evaluation.json
```

Current committed evidence (`random_state=42`, `test_size=0.3`) shows:

- trained model macro F1: `0.0`
- keyword baseline macro F1: `0.5`
- label counts: 1 row each for `amenities_facilities`, `booking_checkin`, `cleanliness`, `food_beverage`, `noise_events`, `positive_general`, `room_condition`, and `service_delay`.
- note on labels in confusion matrices: `staff_behavior` appears in the baseline confusion-matrix labels because the keyword baseline predicted it for one test sample, even though the 8-row labelled dataset itself contains no `staff_behavior` row.

### Dataset Scale Status vs PRD Target

The original PRD target of **300-600 manually labelled reviews** is impractical for the MVP. The project uses transparent Ollama-generated synthetic labels instead, with the evidence manifest explicitly recording `human_reviewed=false`.
The closure target for this MVP is a valid 1000-row synthetic dataset, committed manifest, and committed classifier evaluation report.

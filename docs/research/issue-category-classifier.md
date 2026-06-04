# Issue-Category Classifier Research Workflow

This workflow is for offline research and evaluation only. Synthetic Qwen labels are used as accepted prototype evaluation data for the issue-category classifier; they are not part of the hotel operational review, ticket, or department workflow.

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

See `apps/api/data/examples/issue_labels_sample.csv` for a small committed hand-written format example. The repository also includes `apps/api/data/examples/qwen_issue_labels_synthetic.csv`, a synthetic Qwen-generated dataset for reproducible classifier evaluation. Real guest-data exports should stay outside git under ignored generated-data paths such as `apps/api/data/labelled/`.

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

Use the larger Qwen synthetic dataset for meaningful prototype-scale results. The committed hand-written sample is intentionally tiny and exists only to document the format.

## Qwen Synthetic Dataset Workflow

The repository supports low-cost synthetic review generation with the local Ollama model `qwen2.5-coder:7b`. Generated rows are accepted as synthetic evaluation labels, not human-labelled ground truth.

From the repository root, generate the full 1000-row balanced synthetic dataset:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py --total-rows 1000 --batch-size 5
```

The script prints one progress block per issue category and one line per model request, for example:

```text
[1/11] generating 91 rows for cleanliness
  request 1: accepted 5 of 5 valid parsed rows; rejected 0 short/invalid rows; total 5/91
```

Use `--quiet` to suppress progress logs when running in automation.

Default behavior:

- `--total-rows 1000` distributes rows across the 11 seeded issue categories as 91 rows for the first 10 taxonomy categories and 90 rows for the last category.
- Calls local Ollama at `http://127.0.0.1:11434/api/generate`.
- Writes the generated CSV to ignored path `apps/api/data/labelled/qwen_issue_labels_draft.csv`.
- Uses IDs such as `qwen-cleanliness-001`.
- Uses `source_code=qwen_synthetic_evaluation`.
- Uses `notes=qwen-generated synthetic evaluation label`.
- Prompts for realistic 40-260 word reviews with randomized stay context, tone, and detail.
- Rejects generated rows shorter than 35 words, validates taxonomy labels, and removes duplicate normalized text before writing.
- Keeps requesting from the local model until each category reaches its target count.
- Discards invalid JSON, short rows, invalid ratings, and duplicate normalized text.
- Logs a raw Qwen response preview, accepted row previews, and rejected short/invalid row counts for each request.

For a quick smoke test without creating the full dataset:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py \
  --total-rows 22 \
  --batch-size 2 \
  --output /tmp/qwen_issue_labels_smoke.csv
```

After full generation succeeds, copy the generated synthetic dataset into the committed examples path:

```bash
cp apps/api/data/labelled/qwen_issue_labels_draft.csv \
  apps/api/data/examples/qwen_issue_labels_synthetic.csv
```

Validate the synthetic dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier validate data/examples/qwen_issue_labels_synthetic.csv
```

Write a committed evidence manifest:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py manifest \
  apps/api/data/examples/qwen_issue_labels_synthetic.csv \
  --output docs/research/evidence/qwen_issue_labels_manifest.json
```

Train and evaluate from the synthetic dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier train-evaluate data/examples/qwen_issue_labels_synthetic.csv \
  --model-output /tmp/qwen_issue_classifier.pkl \
  --report-output ../../docs/research/evidence/qwen_issue_classifier_evaluation.json
```

Commit the synthetic dataset, manifest, and evaluation report so assessors can reproduce row counts, label distribution, validation status, model name, prompt version, CSV SHA256, and classifier metrics.

## Published Prototype Evaluation Evidence

- Labelled dataset artifact: `apps/api/data/examples/issue_labels_sample.csv` (8 labelled rows).
- Evaluation output artifact: `docs/research/evidence/issue_labels_sample_evaluation.json`.
- Synthetic Qwen dataset artifact: `apps/api/data/examples/qwen_issue_labels_synthetic.csv`.
- Synthetic Qwen manifest: `docs/research/evidence/qwen_issue_labels_manifest.json` (`human_reviewed=false`).
- Synthetic Qwen evaluation output: `docs/research/evidence/qwen_issue_classifier_evaluation.json`.
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

Current synthetic Qwen evidence (`random_state=42`, `test_size=0.3`) shows:

- row count: `440`
- label counts: 40 rows each across all 11 issue categories.
- trained model macro F1: `0.7160959813133726`
- keyword baseline macro F1: `0.5391834626489358`
- validation status: valid CSV, no taxonomy errors.

### Dataset Scale Status vs PRD Target

The original PRD target of **300-600 manually labelled reviews** is impractical for the MVP. The project uses transparent Qwen-generated synthetic labels instead, with the evidence manifest explicitly recording `human_reviewed=false`.
The closure target for this MVP is a valid 1000-row synthetic dataset, committed manifest, and committed classifier evaluation report.

# Issue-Category Classifier Research Workflow

This workflow is for offline research and evaluation only. Manual labelling creates ground truth for the issue-category classifier; it is not part of the hotel operational review, ticket, or department workflow.

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

See `apps/api/data/examples/issue_labels_sample.csv` for a small committed hand-written format example. The repository also includes `apps/api/data/examples/qwen_issue_labels_synthetic.csv`, a synthetic Qwen-generated draft dataset for reproducible classifier evaluation. Real guest-data exports and human-reviewed working files should stay outside git under ignored generated-data paths such as `apps/api/data/labelled/`.

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

Use a larger human-reviewed labelled subset for meaningful results. The committed sample is intentionally tiny and exists only to document the format.

## Qwen-Assisted Dataset Draft Workflow

The repository supports low-cost draft generation with the local Ollama model `qwen2.5-coder:7b`. This is only a repetitive drafting aid. Generated rows are **not** considered human-labelled until a person reviews and approves them.

From the repository root, generate a balanced draft dataset:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py --rows-per-category 40
```

The script prints one progress block per issue category and one line per accepted batch, for example:

```text
[1/11] generating 40 rows for cleanliness
  batch 1/7: accepted 10 of 10 parsed rows; total 10/40
```

Use `--quiet` to suppress progress logs when running in automation.

Default behavior:

- Generates 40 rows for each of the 11 seeded issue categories, for 440 draft rows.
- Calls local Ollama at `http://127.0.0.1:11434/api/generate`.
- Writes the full draft CSV to ignored path `apps/api/data/labelled/qwen_issue_labels_draft.csv`.
- Uses IDs such as `qwen-cleanliness-001`.
- Uses `source_code=qwen_synthetic_draft`.
- Uses `notes=qwen-generated draft; requires human review`.
- Validates taxonomy labels and removes duplicate normalized text before writing.

For reproducible prototype evidence, copy the generated synthetic draft into the committed examples path after generation:

```bash
cp apps/api/data/labelled/qwen_issue_labels_draft.csv \
  apps/api/data/examples/qwen_issue_labels_synthetic.csv
```

This committed synthetic dataset is not a substitute for human-reviewed ground truth, but it allows the classifier training and evidence reports to be reproduced from the repository alone.

Human review step:

1. Open `apps/api/data/labelled/qwen_issue_labels_draft.csv`.
2. Remove weak, ambiguous, duplicated, or incorrectly labelled rows.
3. Save the approved file as `apps/api/data/labelled/qwen_issue_labels_reviewed.csv`.
4. Do not change the label taxonomy values.

Validate the reviewed dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier validate data/labelled/qwen_issue_labels_reviewed.csv
```

Write a committed evidence manifest for the ignored reviewed CSV:

```bash
python3 apps/api/scripts/generate_issue_label_drafts.py manifest \
  apps/api/data/labelled/qwen_issue_labels_reviewed.csv \
  --human-reviewed \
  --output docs/research/evidence/qwen_issue_labels_manifest.json
```

Train and evaluate from the reviewed dataset:

```bash
cd apps/api
python3 -m app.ml.issue_classifier train-evaluate data/labelled/qwen_issue_labels_reviewed.csv \
  --model-output /tmp/qwen_issue_classifier.pkl \
  --report-output ../../docs/research/evidence/qwen_issue_classifier_evaluation.json
```

The full reviewed CSV remains ignored. Commit the manifest and evaluation report so assessors can verify row counts, label distribution, validation status, model name, prompt version, and CSV SHA256 without storing real guest-data exports in Git.

## Published Prototype Evaluation Evidence

- Labelled dataset artifact: `apps/api/data/examples/issue_labels_sample.csv` (8 labelled rows).
- Evaluation output artifact: `docs/research/evidence/issue_labels_sample_evaluation.json`.
- Synthetic Qwen dataset artifact: `apps/api/data/examples/qwen_issue_labels_synthetic.csv` (440 generated rows; 40 per category).
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

The PRD target of **300-600 manually labelled reviews** is **not met** by the committed 8-row hand-written example alone.
The repository now includes a 440-row synthetic Qwen draft dataset to exercise the classifier at the target volume. The intended final closure path for manual ground truth remains: generate or start from the draft rows locally, human-review the ignored CSV, then commit the manifest and classifier evaluation evidence with `human_reviewed=true`.
Do not claim the target is met until `qwen_issue_labels_reviewed.csv` exists locally, validates successfully, and the committed evidence manifest records `human_reviewed=true`.

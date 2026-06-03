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

See `apps/api/data/examples/issue_labels_sample.csv` for a small committed example. Real labelled exports should stay outside git or under ignored generated-data paths.

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

Use a larger manually labelled subset for meaningful results. The committed sample is intentionally tiny and exists only to document the format.

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

### Dataset Scale Status vs PRD Target

The PRD target of **300-600 manually labelled reviews** is **not met** in the current repository evidence set.  
For this academic prototype milestone, the committed dataset is intentionally reduced to 8 labelled rows to prove the reproducible pipeline and reporting format.  
Meeting the full target remains pending additional human-provided labels.

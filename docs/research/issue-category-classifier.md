# Issue-Category Classifier Research Workflow

This workflow is offline research support only. It is not the main MVP demo-data path and is not part of the hotel staff product runtime.

## Labelled CSV Format

Use a UTF-8 CSV with these required columns:

- `text`: review text used as classifier input.
- `issue_category_code`: one seeded issue taxonomy code.

Optional columns are preserved for traceability but are not used for training:

- `review_id`
- `source_code`
- `rating`
- `notes`

See `apps/api/data/examples/issue_labels_sample.csv` for a small committed format example.

## Validate Labels

From `apps/api`:

```bash
python3 -m app.ml.issue_classifier validate data/examples/issue_labels_sample.csv
```

## Train And Evaluate

From `apps/api`:

```bash
python3 -m app.ml.issue_classifier train-evaluate data/examples/issue_labels_sample.csv \
  --model-output artifacts/ml/issue_classifier.pkl \
  --report-output reports/ml/issue_classifier_evaluation.json
```

The report compares the trained TF-IDF/logistic-regression classifier with the deterministic keyword-rule baseline.

## MVP Demo Data

Do not use labelled CSV generation as the main MVP path. Demo review data should come from connector-shaped platform fixtures generated with:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py
```

See `docs/research/connector-fixture-generation.md`.

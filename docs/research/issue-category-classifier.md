# Legacy Issue-Category Classifier Research Notes

This document is retained only as historical research context. It is not the MVP product path, not the demo-data path, and not required for the current walkthrough.

The current MVP uses:

- Hugging Face `facebook/bart-large-mnli` zero-shot classification against 6 department candidate labels (`apps/api/app/ml/department_classifier.py`) for department routing;
- LLM-driven issue detection via `apps/api/app/issue_detection.py` and `apps/api/app/llm_client.py` for building detected issues from negative/mixed reviews;
- connector-shaped review fixtures generated with `generate_connector_fixtures.py` for demo data.

Do not use labelled CSV generation, TF-IDF/logistic-regression training, or keyword-rule baselines as the main MVP proof. Those older workflows were part of the superseded PRDs #1 and #41.

For the current fixture generation workflow, see:
```bash
python3 apps/api/scripts/generate_connector_fixtures.py
```

Reference: `docs/research/connector-fixture-generation.md`.

# Legacy Issue-Category Classifier Research Notes

This document is retained only as historical research context. It is not the MVP product path, not the demo-data path, and not required for the current walkthrough.

The current MVP uses:

- Hugging Face `facebook/bart-large-mnli` zero-shot classification against the hotel issue taxonomy for product issue categorization;
- connector-shaped review fixtures generated with `apps/api/scripts/generate_connector_fixtures.py` for demo data.

Do not use labelled CSV generation, TF-IDF/logistic-regression training, or keyword-rule baselines as the main MVP proof. Those older workflows were part of the superseded PRDs #1 and #41.

For the current fixture generation workflow, see:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py
```

Reference: `docs/research/connector-fixture-generation.md`.

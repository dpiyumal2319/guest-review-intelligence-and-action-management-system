# Connector Fixture Generation

This workflow generates local demo review fixture files for the MVP review platforms:

- Google Business Profile
- Booking.com
- Tripadvisor

Generation uses local Ollama as a data-preparation tool only. The product runtime does not call Ollama.

## Generate Fixtures

From the repository root:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py
```

Default behavior:

- uses `dolphin-llama3:latest`;
- calls local Ollama at `http://127.0.0.1:11434/api/generate`;
- generates 2,000 reviews split across the three platforms;
- writes JSON files under `apps/api/data/generated-fixtures/connectors/`;
- writes a manifest with counts, files, model, and generation timestamp;
- keeps generated files out of git by default.

For a smoke run:

```bash
python3 apps/api/scripts/generate_connector_fixtures.py \
  --total-reviews 9 \
  --output-dir /tmp/kingsbury-connector-fixtures
```

## Fixture Boundary

Generated payloads are shaped like provider records and include realistic:

- IDs;
- timestamps;
- ratings;
- review text;
- optional titles;
- reviewer aliases or display metadata;
- platform engagement fields such as likes, helpful votes, replies, subratings, or photos.

The generator intentionally repeats scenario waves, such as slow check-in queues, bathroom maintenance, breakfast delays, event noise, air-conditioning delays, and housekeeping follow-up delays. These repeated waves support recurring issue detection after normal ingestion and analysis.

Generated fixture payloads must not include precomputed analysis fields:

- sentiment labels or scores;
- issue category labels;
- department labels;
- severity labels;
- reputation-risk labels;
- analysis objects.

The generator validates this recursively before writing each payload.

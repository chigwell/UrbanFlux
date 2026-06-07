# Backend

FastAPI service for syncing London Datastore CSV dataset metadata into SQLite, downloading CSV files, and serving paginated dashboard APIs.

## Development

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Sync examples

```bash
python -m app.scraper --mode api
python -m app.scraper --mode api --download --max-file-size-mb 100
python -m app.scraper --mode pages --max-pages 2
```

The downloader waits between files and retries transient HTTP failures, including `429 Too Many Requests`. Environment overrides:

```text
LONDON_DOWNLOAD_REQUEST_DELAY_SECONDS=1.5
LONDON_DOWNLOAD_RETRY_ATTEMPTS=6
LONDON_DOWNLOAD_RETRY_BACKOFF_SECONDS=3
LONDON_DOWNLOAD_MAX_RETRY_AFTER_SECONDS=180
```

## CSV transformation plans

Create reusable LLM-defined rules for assigning row date ranges and London boroughs later:

```bash
python -m scripts.plan_csv_transformations --limit 10
```

The planner processes downloaded CSV files that do not already have a successful plan. It sends dataset metadata, CSV metadata, headers, and first sample rows to the OpenAI-compatible LLM7 API.

Required environment:

```text
LLM7_TOKEN=...
```

Optional environment:

```text
LLM7_API_BASE_URL=https://api.llm7.io/v1
LLM7_MODEL=gpt-4o-mini
LLM7_REQUEST_TIMEOUT_SECONDS=90
```

Useful commands:

```bash
python -m scripts.plan_csv_transformations --csv-file-id 1
python -m scripts.plan_csv_transformations --retry-errors --limit 10
python -m scripts.plan_csv_transformations --csv-file-id 1 --dry-run
python -m scripts.run_csv_transformations --limit 10
```

The results are stored in `csv_transformation_plans` and exposed through:

```text
GET /api/transformation-plans
GET /api/csv-files/{csv_file_id}/transformation-plan
```

Apply a successful transformation plan to every row in that CSV:

```bash
python -m scripts.apply_csv_row_transformations --csv-file-id 1
```

Apply pending successful plans that do not already have row outputs:

```bash
python -m scripts.apply_csv_row_transformations --limit 10
```

Re-apply existing row outputs:

```bash
python -m scripts.apply_csv_row_transformations --retry --limit 10
```

The deterministic row outputs are stored in `csv_row_transformations` and exposed through:

```text
GET  /api/transformation-stats
GET  /api/csv-files/{csv_file_id}/row-transformations
GET  /api/csv-files/{csv_file_id}/row-transformations/stats
POST /api/csv-files/{csv_file_id}/row-transformations/apply
```

Use `scripts.run_csv_transformations` for the normal workflow. It creates missing LLM plans and immediately applies successful plans to rows, while skipping CSV files that already have successful plans and row outputs.

The dashboard can also start a background download job for all CSV files that are not already downloaded:

```text
POST /api/download-jobs/pending
GET  /api/download-jobs/active
POST /api/download-jobs/active/stop
```

### Borough boundaries

Load London borough boundary data from the official LSOA shapefile and expose it through the API:

```bash
python -m scripts.sync_london_borough_boundaries --url "https://data.london.gov.uk/download/20od9/2a5e50ac-c22e-4d68-89e2-85f1e0ff9057/LB_LSOA2021_shp.zip"
```

Alternative local file usage:

```bash
python -m scripts.sync_london_borough_boundaries --shape-path /path/to/LB_LSOA2021_shp.zip
```

The script writes borough boundaries into the `london_borough_boundaries` table.

API endpoint:

```text
GET /api/borough-boundaries

Quick verification after sync:

```bash
python3 - <<'PY'
import sqlite3, json
from pathlib import Path
path = Path('data/london_datastore.sqlite3')
conn = sqlite3.connect(path)
row = conn.execute("SELECT COUNT(*) FROM london_borough_boundaries").fetchone()
print("borough_rows", row[0])
sample = conn.execute(
    "SELECT borough_name, border_coordinates_json, source_file_name FROM london_borough_boundaries ORDER BY borough_name LIMIT 1"
).fetchone()
sample_name = sample[0]
sample_points = len(json.loads(sample[1])[0]) if sample and sample[1] else 0
print("sample", sample)
print("sample_name", sample_name)
print("sample_border_points", sample_points)
PY
```
```

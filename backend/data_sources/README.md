# London Mapped Data Package

This folder bootstraps the standalone London mapped data package from public Cloudflare R2.

```text
setup_london_mapped_data.py
```

The package resolves London boroughs from coordinates and returns mapped CSV data for the detected borough.

## Public Bundle

```text
https://pub-f20eb55e72ee41a5b80036ea8f6107bb.r2.dev/london_mapped_data_public_bundle.zip
```

The public zip is sanitized:

```text
No .env
No API tokens
No local /Users/... paths
No LLM keys
```

## Setup On VPS

From `backend/data_sources`:

```bash
python3 setup_london_mapped_data.py
```

This downloads the zip from R2, unpacks:

```text
london_mapped_data_package/
```

and runs a smoke test.

Then install the package:

```bash
cd london_mapped_data_package
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Force Re-download

```bash
python3 setup_london_mapped_data.py --force
```

Keep the downloaded zip after unpacking:

```bash
python3 setup_london_mapped_data.py --keep-zip
```

## Python API

Resolve borough only:

```python
from london_mapped_data import resolve_borough

borough = resolve_borough(51.5074, -0.1278)
```

Get mapped data:

```python
from london_mapped_data import get_borough_data

result = get_borough_data(
    lat=51.5074,
    lon=-0.1278,
    theme="planning_land",
    limit=50,
)
```

Lazy iteration for large result sets:

```python
from london_mapped_data import iter_borough_data

for row in iter_borough_data(51.5074, -0.1278, theme="housing", batch_size=1000):
    print(row)
```

Summary for cards/charts:

```python
from london_mapped_data import get_borough_summary

summary = get_borough_summary(51.5074, -0.1278)
```

## Supported Themes

```text
planning_land
housing
socioeconomic
health
environment
transport
safety
demographics
other
```

## Notes

- The runtime package is Python-only.
- It does not require FastAPI.
- It uses SQLite and Python stdlib.
- Coordinates must be WGS84 latitude/longitude.
- If coordinates are outside London borough boundaries, `resolve_borough(...)` returns `None`.
- `get_borough_data(..., limit=None)` may return a very large list. Prefer `iter_borough_data(...)` for production jobs.

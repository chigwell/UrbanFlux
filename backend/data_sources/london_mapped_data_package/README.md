# London Mapped Data Package

Standalone Python package for querying mapped London data by coordinates.

It accepts WGS84 coordinates (`lat`, `lon`), resolves the London borough using bundled borough boundaries, and returns mapped CSV rows from a compact SQLite data bundle.

## Build the compact data bundle locally

Run from this folder:

```bash
python3 -m london_mapped_data.export build-db \
  --source ../backend/data/london_datastore.sqlite3 \
  --out data/london_mapped_compact.sqlite3
```

Optional zip for VPS copy:

```bash
python3 -m london_mapped_data.export zip \
  --db data/london_mapped_compact.sqlite3 \
  --out dist/london_mapped_data_bundle.zip
```

Optional CSV export:

```bash
python3 -m london_mapped_data.export csv \
  --db data/london_mapped_compact.sqlite3 \
  --out dist/csv_export
```

## Deploy on VPS

```bash
unzip london_mapped_data_bundle.zip
cd london_mapped_data_package
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Use from Python

```python
from london_mapped_data import get_borough_data

result = get_borough_data(
    lat=51.5074,
    lon=-0.1278,
    theme="housing",
    limit=50,
)

print(result["borough"]["name"])
print(result["rows"][0])
```

For large result sets, prefer the lazy iterator:

```python
from london_mapped_data import iter_borough_data

for row in iter_borough_data(51.5074, -0.1278, theme="planning_land"):
    print(row)
```

## Public functions

- `resolve_borough(lat, lon, db_path=None)`
- `get_borough_data(lat, lon, theme=None, include_partial=True, limit=None, offset=0, db_path=None)`
- `iter_borough_data(lat, lon, theme=None, include_partial=True, batch_size=1000, db_path=None)`
- `get_borough_summary(lat, lon, db_path=None, top_datasets_limit=30)`

## Themes

- `planning_land`
- `housing`
- `socioeconomic`
- `health`
- `environment`
- `transport`
- `safety`
- `demographics`
- `other`

The theme is a heuristic label based on dataset/resource metadata. It is intended for visualization and approximate redevelopment impact analysis.

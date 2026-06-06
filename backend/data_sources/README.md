# London Mapped Data

This module provides London borough mapped data by coordinates.

The first call automatically downloads and unpacks the public data bundle from Cloudflare R2:

```text
https://pub-f20eb55e72ee41a5b80036ea8f6107bb.r2.dev/london_mapped_data_public_bundle.zip
```

The bundle is sanitized: it does not contain `.env`, API tokens, LLM keys, or local `/Users/...` paths.

## Quick Test

From the UrbanFlux repo root:

```bash
python3 backend/data_sources/test.py
```

The first run downloads about `336MB` and unpacks about `3.1GB`.

## Use In Python

```python
from backend.data_sources import get_borough_data, get_borough_summary, resolve_borough

lat = 51.5074
lon = -0.1278

borough = resolve_borough(lat, lon)
summary = get_borough_summary(lat, lon)
housing = get_borough_data(lat, lon, theme="housing", limit=10)
```

For large result sets, use the iterator:

```python
from backend.data_sources import iter_borough_data

for row in iter_borough_data(51.5074, -0.1278, theme="planning_land"):
    print(row)
```

## Available Themes

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

## Manual Download

Usually this is not needed because imports auto-download the package. To do it manually:

```bash
cd backend/data_sources
python3 setup_london_mapped_data.py
```

Force re-download:

```bash
python3 setup_london_mapped_data.py --force
```

## Notes

- Coordinates must be WGS84 latitude/longitude.
- If a point is outside London borough boundaries, `resolve_borough(...)` returns `None`.
- `get_borough_data(..., limit=None)` can return a very large list; prefer `iter_borough_data(...)` for production.

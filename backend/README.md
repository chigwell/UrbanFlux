# Backend (FastAPI)

FastAPI backend for UrbanFlux CityTwin.

Production API URL: `https://api.urbanflux.london/`

## API Surface

- `GET /` -> `{"message": "UrbanFlux backend is running"}`
- `GET /hello` -> `{"message": "Hello World"}`
- `POST /population` accepts a GeoJSON `Polygon`, `MultiPolygon`, or `Feature` and returns `approximate_population`, `lsoa_count`, `area_km2`, and `note`.
- `POST /impact` accepts the selected GeoJSON polygon plus replanning slider params and returns deterministic London-data-first impact metrics, optionally refined by Nemotron when explicitly enabled.
- `GET /borough-data-test` resolves a lat/lon to the mapped London borough data package and returns theme summaries, top datasets, and latest-row previews.

OpenAPI is available at `/openapi.json`, Swagger UI at `/docs`, and ReDoc at `/redoc`.

## Run Locally

### 1) Install dependencies

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Start the API

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 3) Run tests

```bash
pytest tests
```

CI runs the same backend test suite on Python 3.12.

## Nemotron Behavior

`/impact` always computes deterministic London-data-first metrics first. The Nemotron adapter is isolated in `nemotron_adapter.py` and falls back to those deterministic metrics when `FAL_KEY` is absent, `fal_client` is not installed, the call times out, or the model output is not valid metric JSON.

`fal-client` and `python-dotenv` are intentionally not part of `requirements.txt` in this refactor. Enabling live Nemotron in production should be a separate dependency/deploy migration.

`nemotron.py` is a legacy manual script for recommendation-style experiments. It is not imported by the FastAPI server.

## Backend Layout

- `main.py` - FastAPI routes and public import surface.
- `schemas.py` - Pydantic request/response models.
- `population.py` - GeoJSON parsing, LSOA loading, selected-area population, and area calculations.
- `impact.py` - deterministic London-data-first impact metrics and source/basis helpers.
- `borough_context.py` - trusted borough row selection and Nemotron prompt context.
- `nemotron_adapter.py` - optional Nemotron call, JSON parsing, timeout fallback, and source allow-list validation.
- `borough_data.py` / `utils.py` - mapped London data package endpoint helpers.

## GitHub Actions Deploy (VPS)

Workflow file: `.github/workflows/deploy.yml`

Push to `main` uploads `backend/` to:

```text
/opt/urbanflux/backend
```

The workflow installs Python dependencies on the VPS, ensures the mapped London data package exists, and restarts the `systemd` service.

### Required GitHub secrets

- `VPS_HOST`
- `VPS_USER`
- `VPS_SSH_PRIVATE_KEY`
- `VPS_SSH_PORT`
- `VPS_SERVICE_NAME`
- `FAL_KEY` only if a future migration enables live Nemotron dependencies

Current expected values:

- `VPS_HOST=161.97.187.158`
- `VPS_USER=deploy`
- `VPS_SSH_PORT=22`
- `VPS_SERVICE_NAME=urbanflux-backend`

### VPS service

Expected `systemd` service file:

```text
/etc/systemd/system/urbanflux-backend.service
```

Expected service command:

```bash
/opt/urbanflux/backend/.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
```

Check status:

```bash
sudo systemctl status urbanflux-backend --no-pager
```

Check local VPS endpoints:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/hello
curl -i http://127.0.0.1:8000/openapi.json
```

Check public API endpoints:

```bash
curl -i https://api.urbanflux.london/
curl -i https://api.urbanflux.london/hello
curl -i https://api.urbanflux.london/openapi.json
```

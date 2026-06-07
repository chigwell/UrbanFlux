# Backend (FastAPI)

FastAPI backend for UrbanFlux CityTwin.

Production API URL: `https://api.urbanflux.london/`

> [!WARNING]
> The hosted backend at `https://api.urbanflux.london/` was turned off after the hackathon. Run this backend locally if you need API functionality.

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

Backend CI is disabled because the hosted backend was turned off after the hackathon.

## Nemotron Behavior

`/impact` always computes deterministic London-data-first metrics first. If `fal_client` is available and `FAL_KEY` is set, the API attempts a Nemotron refinement and falls back to deterministic metrics when the call times out or returns invalid metric JSON.

The standard backend install works without live Nemotron credentials. To run live Nemotron refinement, install the provider client package used by `nemotron_adapter.py` and set `FAL_KEY` in the backend environment.

`nemotron.py` is a standalone recommendation script. It is not imported by the FastAPI server.

Optional second LLM fallback:

- `FALLBACK_LLM_PROVIDER_URL` - OpenAI-compatible base URL or full chat completions URL. If a base URL is provided, `/chat/completions` is appended.
- `FALLBACK_LLM_PROVIDER_TOKEN` - bearer token for the fallback provider.
- `FALLBACK_LLM_PROVIDER_MODEL` - optional model name. Defaults to the configured Nemotron model name.
- `IMPACT_LLM_TIMEOUT_S` - optional total LLM refinement timeout in seconds. Defaults to 20.

The `/impact` path tries FAL/OpenRouter first, then this fallback provider, then deterministic London-data-first metrics.

## Backend Layout

- `main.py` - FastAPI routes and public import surface.
- `schemas.py` - Pydantic request/response models.
- `population.py` - GeoJSON parsing, LSOA loading, selected-area population, and area calculations.
- `impact.py` - deterministic London-data-first impact metrics and source/basis helpers.
- `borough_context.py` - trusted borough row selection and Nemotron prompt context.
- `nemotron_adapter.py` - optional Nemotron call, JSON parsing, timeout fallback, and source allow-list validation.
- `borough_data.py` / `utils.py` - mapped London data package endpoint helpers.

## GitHub Actions Deploy

Workflow file: `.github/workflows/deploy.yml`

The current workflow deploys only the frontend. Backend VPS deployment is disabled because the hosted backend was turned off after the hackathon.

### Local service

Example `systemd` service file:

```text
/etc/systemd/system/urbanflux-backend.service
```

Example service command:

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

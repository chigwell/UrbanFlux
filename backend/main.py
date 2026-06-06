from __future__ import annotations

import json
import os
import sys
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import shape
from shapely.ops import unary_union

_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from borough_data import build_borough_data_test_response

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

tags_metadata = [
    {
        "name": "status",
        "description": "Service status and connectivity checks.",
    },
    {
        "name": "population",
        "description": "Approximate population calculations for selected GeoJSON areas.",
    },
    {
        "name": "impact",
        "description": "Illustrative replanning impact calculations for selected areas and UI parameters.",
    },
    {
        "name": "borough-data",
        "description": "Test endpoints for mapped London borough datasets by coordinates.",
    },
]

app = FastAPI(
    title="UrbanFlux API",
    summary="FastAPI backend for UrbanFlux CityTwin.",
    description=(
        "UrbanFlux backend API for service checks, selected-area population estimates, "
        "and replanning impact calculations. OpenAPI is available at `/openapi.json`, "
        "Swagger UI at `/docs`, and ReDoc at `/redoc`."
    ),
    version="0.1.0",
    contact={
        "name": "UrbanFlux Team",
        "url": "https://urbanflux.london/",
    },
    openapi_tags=tags_metadata,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# LSOA data loader  (cached – downloaded once per process lifetime)
# ---------------------------------------------------------------------------

# Pre-built LSOA GeoJSON with population joined.
# Source: ONS LSOA Dec-2021 boundaries (BSC simplified) + Census 2021 TS001.
# Fallback: we reconstruct from the two raw sources on first call.
# ---------------------------------------------------------------------------
# LSOA data loader  (cached – loaded once per process lifetime)
# ---------------------------------------------------------------------------

_LSOA_BOUNDARIES_PATH = "london-lsoa-boundaries.geojson"
_POPULATION_JSON_PATH = "london-lsoa-population.json"

# Fallback remote URL if local boundaries file is absent.
# Paginated: ArcGIS caps at 2000 features per request.
_ARCGIS_BASE_URL = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BSC_V4/"
    "FeatureServer/0/query"
)
_LONDON_BBOX = "-0.5103751,51.2867602,0.3340155,51.6918741"


def _fetch_arcgis_features() -> list[dict]:
    """Paginate through ArcGIS to fetch all London LSOA boundary features."""
    import urllib.parse
    all_features: list[dict] = []
    offset = 0
    page_size = 2000
    while True:
        params = urllib.parse.urlencode({
            "geometry": _LONDON_BBOX,
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": "LSOA21CD",
            "returnGeometry": "true",
            "f": "geojson",
            "resultRecordCount": page_size,
            "resultOffset": offset,
        })
        url = f"{_ARCGIS_BASE_URL}?{params}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                page = json.loads(resp.read())
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch LSOA boundaries from ArcGIS: {exc}") from exc
        features = page.get("features", [])
        all_features.extend(features)
        if not page.get("exceededTransferLimit") or len(features) == 0:
            break
        offset += page_size
    return all_features


@lru_cache(maxsize=1)
def _load_lsoa_features() -> list[dict]:
    """
    Load LSOA boundary + population into a list of dicts:
        {"geometry": shapely_geom, "code": "E01xxxxxx", "population": int}

    Priority:
    1. data_sources package (Eugene's work – imported if available)
    2. Local london-lsoa-boundaries.geojson + london-lsoa-population.json
    3. Remote ArcGIS fetch (slow first call; cached thereafter)
    """

    # Hook for Eugene's data_sources package
    try:
        from data_sources import get_lsoa_features  # type: ignore
        return get_lsoa_features()
    except (ImportError, AttributeError):
        pass

    # --- load population lookup -----------------------------------------------
    try:
        with open(_POPULATION_JSON_PATH) as fh:
            pop_lookup: dict[str, int] = json.load(fh)
    except FileNotFoundError:
        pop_lookup = {}

    # --- load boundaries (local file preferred, ArcGIS fallback) --------------
    if os.path.exists(_LSOA_BOUNDARIES_PATH):
        with open(_LSOA_BOUNDARIES_PATH) as fh:
            gj = json.load(fh)
        raw_features = gj.get("features", [])
    else:
        raw_features = _fetch_arcgis_features()

    features = []
    for feat in raw_features:
        code = feat["properties"].get("LSOA21CD", "")
        population = pop_lookup.get(code, 0)
        try:
            geom = shape(feat["geometry"])
        except Exception:
            continue
        features.append({"geometry": geom, "code": code, "population": population})

    return features


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class GeoJSONPolygon(BaseModel):
    """A GeoJSON Polygon or MultiPolygon Feature or raw geometry."""
    type: str = Field(
        ...,
        description="GeoJSON object type. Use `Polygon`, `MultiPolygon`, or `Feature`.",
        examples=["Polygon"],
    )
    coordinates: Any | None = Field(
        default=None,
        description="GeoJSON coordinates for a raw Polygon or MultiPolygon geometry.",
    )
    geometry: Any | None = Field(
        default=None,
        description="GeoJSON geometry object when `type` is `Feature`.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-0.1312, 51.5069],
                            [-0.1198, 51.5075],
                            [-0.1158, 51.5015],
                            [-0.1268, 51.4987],
                            [-0.1355, 51.5018],
                            [-0.1312, 51.5069],
                        ]
                    ],
                }
            ]
        }
    }


class ReplanningParams(BaseModel):
    housing_density: int = Field(64, ge=5, le=100, description="Housing density: homes per built block.")
    green_space_target: int = Field(35, ge=5, le=80, description="Green space target: share reserved as parks.")
    parking_pressure: int = Field(18, ge=0, le=80, description="Parking pressure: surface parking demand.")
    road_fill: int = Field(35, ge=0, le=100, description="Road fill: boundary anchors connected.")
    road_alignment: int = Field(72, ge=0, le=100, description="Road alignment: how straight corridors run.")
    height_ambition: int = Field(58, ge=0, le=100, description="Height ambition: massing of tall buildings.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "housing_density": 64,
                    "green_space_target": 35,
                    "parking_pressure": 18,
                    "road_fill": 35,
                    "road_alignment": 72,
                    "height_ambition": 58,
                }
            ]
        }
    }


class MessageResponse(BaseModel):
    message: str = Field(..., description="Human-readable response message.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "UrbanFlux backend is running"},
                {"message": "Hello World"},
            ]
        }
    }


class PopulationRequest(BaseModel):
    polygon: GeoJSONPolygon = Field(..., description="Selected area as a GeoJSON Polygon, MultiPolygon, or Feature.")


class PopulationResponse(BaseModel):
    approximate_population: int = Field(..., ge=0, description="Estimated population inside the selected area.")
    lsoa_count: int = Field(..., ge=0, description="Number of intersecting LSOA geometries used.")
    area_km2: float = Field(..., ge=0, description="Approximate selected area in square kilometres.")
    note: str = Field("2021 Census, LSOA-level intersection", description="Calculation note and data source context.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "approximate_population": 2480,
                    "lsoa_count": 5,
                    "area_km2": 0.42,
                    "note": "2021 Census, LSOA-level intersection",
                }
            ]
        }
    }


class ImpactMetric(BaseModel):
    improved_metric: str = Field(..., description="Name of the improved metric.")
    improved_value: str = Field(..., description="Estimated metric value after replanning.")
    delta: str = Field(..., description="Difference compared with the previous or baseline value.")
    source: str = Field(..., description="Source URL for the data, benchmark, or method.")


class ImpactRequest(BaseModel):
    polygon: GeoJSONPolygon = Field(..., description="Selected area as a GeoJSON Polygon, MultiPolygon, or Feature.")
    params: ReplanningParams = Field(default_factory=ReplanningParams, description="User-selected replanning parameters.")


class ImpactResponse(BaseModel):
    approximate_population: int = Field(..., ge=0, description="Estimated population affected by replanning.")
    area_km2: float = Field(..., ge=0, description="Approximate selected area in square kilometres.")
    metrics: list[ImpactMetric] = Field(..., description="List of estimated impact metrics.")
    note: str = Field("Illustrative estimates - model integration in progress", description="Calculation note.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "approximate_population": 2480,
                    "area_km2": 0.42,
                    "metrics": [
                        {
                            "improved_metric": "Cycling mode share",
                            "improved_value": "+1.5 percentage points",
                            "delta": "+1.5pp vs baseline",
                            "source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
                        }
                    ],
                    "note": "Illustrative estimates - model integration in progress",
                }
            ]
        }
    }


class BoroughDataTestResponse(BaseModel):
    coordinates: dict[str, float] = Field(..., description="Input WGS84 coordinates.")
    borough: dict[str, Any] | None = Field(None, description="Resolved London borough for the coordinates.")
    summary_by_theme: list[dict[str, Any]] = Field(..., description="Row and CSV counts grouped by theme.")
    top_datasets: list[dict[str, Any]] = Field(..., description="Top datasets for the resolved borough.")
    latest_rows_by_theme: list[dict[str, Any]] = Field(
        ...,
        description="Most recent available source row preview for each returned theme.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coordinates": {"lat": 51.5074, "lon": -0.1278},
                    "borough": {"name": "Westminster", "code": "E09000033"},
                    "summary_by_theme": [
                        {
                            "theme": "housing",
                            "row_count": 1234,
                            "csv_file_count": 12,
                            "min_date_start": "2018-01-01",
                            "max_date_end": "2024-12-31",
                        }
                    ],
                    "top_datasets": [
                        {
                            "theme": "housing",
                            "row_count": 200,
                            "dataset_title": "Example dataset",
                            "resource_title": "Example resource",
                        }
                    ],
                    "latest_rows_by_theme": [
                        {
                            "theme": "housing",
                            "dataset_title": "Example dataset",
                            "resource_title": "Example resource",
                            "row_number": 42,
                            "date_start": "2024-01-01",
                            "date_end": "2024-12-31",
                            "source_row_preview": "key: value",
                        }
                    ],
                }
            ]
        }
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_shapely_geom(polygon: GeoJSONPolygon):
    """Turn a GeoJSONPolygon (Feature or bare geometry) into a Shapely geometry."""
    raw: dict
    if polygon.type == "Feature":
        raw = polygon.geometry  # type: ignore[assignment]
    else:
        raw = polygon.dict(exclude_none=True)
    try:
        return shape(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid GeoJSON geometry: {exc}")


def _population_in_polygon(sel_geom) -> tuple[int, int]:
    """Return (total_population, lsoa_count) for LSOAs intersecting sel_geom."""
    features = _load_lsoa_features()
    total_pop = 0
    count = 0
    for feat in features:
        lsoa_geom = feat["geometry"]
        if not sel_geom.intersects(lsoa_geom):
            continue
        # Weight by intersection fraction
        try:
            intersection = sel_geom.intersection(lsoa_geom)
            fraction = intersection.area / lsoa_geom.area if lsoa_geom.area > 0 else 0
        except Exception:
            fraction = 1.0
        total_pop += round(feat["population"] * fraction)
        count += 1
    return total_pop, count


def _area_km2(geom) -> float:
    """Approximate area in km² using a simple degree→metre conversion near London."""
    # 1° lat ≈ 111,320 m; 1° lon ≈ 111,320 * cos(51.5°) ≈ 69,600 m
    # For a small polygon this is accurate to ~1 %.
    DEG_LAT_M = 111_320
    DEG_LON_M = 69_600
    bounds = geom.bounds  # (minx, miny, maxx, maxy) in lon/lat
    # Scale coordinates to metres before computing area
    from shapely.affinity import scale
    geom_m = scale(geom, xfact=DEG_LON_M, yfact=DEG_LAT_M, origin=(0, 0))
    return geom_m.area / 1_000_000


def _compute_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
) -> list[ImpactMetric]:
    """
    Return illustrative impact metrics.

    These are intentionally conservative estimates derived from published
    London / TfL benchmarks.  Eugene's model will replace this function.
    """

    density = params.housing_density / 100
    parking_pressure = params.parking_pressure / 100
    road_fill = params.road_fill / 100
    road_alignment = params.road_alignment / 100
    height_ambition = params.height_ambition / 100

    # Road-km estimate: assume a rough street grid density of ~12 km per km²
    # in inner London (TfL Street Types report, 2023), scaled by road fill.
    road_km = round(area_km2 * 12 * road_fill, 1)

    # --- Walking / cycling accessibility ---
    # TfL: each km of coherent active-travel corridor increases cycling mode
    # share by ~0.3 percentage points in the surrounding LSOA (LCWIP 2023).
    cycling_boost_pp = round(road_km * (0.18 + road_alignment * 0.12), 1)

    # --- Housing capacity ---
    # Illustrative capacity uplift driven by denser blocks and taller massing.
    homes_capacity_uplift_pct = round((density * 26) + (height_ambition * 18), 1)

    # --- Green space ---
    # Each 1 % increase in green space cover in an LSOA correlates with
    # ~0.15 °C reduction in summer peak temperature (UCL Urban Cooling, 2022).
    temp_reduction = round(params.green_space_target * 0.15, 2)

    # --- Parking pressure ---
    # Surface parking pressure consumes land that could otherwise be used for
    # homes, green space, or active frontage.
    productive_land_gain_pct = round(max(0, 0.8 - parking_pressure) * 12.5, 1)

    # --- Active travel health ---
    # WHO HEAT tool: each additional km of walking/cycling infrastructure per
    # 1 000 residents prevents ~0.4 premature deaths/year.
    lives_saved_per_year = round((road_km / max(population, 1)) * 1000 * 0.4, 2)

    metrics: list[ImpactMetric] = [
        ImpactMetric(
            improved_metric="Cycling mode share",
            improved_value=f"+{cycling_boost_pp} percentage points",
            delta=f"+{cycling_boost_pp}pp vs baseline",
            source="https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
        ),
        ImpactMetric(
            improved_metric="Housing capacity",
            improved_value=f"+{homes_capacity_uplift_pct}%",
            delta=f"+{homes_capacity_uplift_pct}% vs baseline massing",
            source="https://data.london.gov.uk/dataset/land-area-and-population-density-ward-and-borough-e1zp8/",
        ),
        ImpactMetric(
            improved_metric="Summer peak temperature",
            improved_value=f"-{temp_reduction} °C",
            delta=f"-{temp_reduction} °C vs no green space change",
            source="https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/climate-change/urban-greening",
        ),
        ImpactMetric(
            improved_metric="Productive land released from parking",
            improved_value=f"+{productive_land_gain_pct}%",
            delta=f"+{productive_land_gain_pct}% vs maximum parking pressure",
            source="https://data.london.gov.uk/dataset/car-parking-and-london-s-available-space",
        ),
        ImpactMetric(
            improved_metric="Premature deaths prevented (active travel)",
            improved_value=f"{lives_saved_per_year} lives/year",
            delta=f"+{lives_saved_per_year} vs baseline",
            source="https://www.euro.who.int/en/health-topics/environment-and-health/Transport-and-health/activities/quantifying-health-impacts-of-transport/heat-tool",
        ),
    ]

    return metrics


# ---------------------------------------------------------------------------
# Nemotron impact helpers
# ---------------------------------------------------------------------------

NEMOTRON_IMPACT_SYSTEM_PROMPT = """You are an urban planning impact analyst for London.

You will be given:
- Area statistics: population, size in km², and borough name
- Replanning parameters chosen by a planner (housing density, green space target, parking pressure, road fill, road alignment, height ambition) — all as integers 0–100
- Real borough data rows from the London Datastore (housing, transport, planning, socioeconomic themes)
- Benchmark impact metrics already calculated from published sources

Your task is to return a JSON array of impact metrics, using the benchmark values as a baseline and refining them where the real borough data justifies it.

Rules:
- Only use the sources and data provided. Do not hallucinate statistics, datasets, or sources.
- If real borough data supports a more precise estimate, use it and cite the dataset.
- If there is no relevant data for a metric, set improved_value and delta to "" (empty string).
- Return ONLY a valid JSON array. No preamble, no explanation, no markdown, no code fences.
- Every object in the array must have exactly these four string fields: improved_metric, improved_value, delta, source.

Example output format:
[
  {
    "improved_metric": "Cycling mode share",
    "improved_value": "+3.2 percentage points",
    "delta": "+3.2pp vs baseline",
    "source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit"
  }
]"""


_TRUSTED_THEMES = {"housing", "transport", "planning_land", "socioeconomic"}
_NEMOTRON_TIMEOUT_S = 12  # wall-clock seconds before we fall back to benchmarks


def _fetch_borough_rows(lat: float, lon: float) -> str:
    """
    Pull the latest row preview for each trusted theme from Eugene's SQLite
    via the live /borough-data-test endpoint. Returns a formatted string
    for inclusion in the Nemotron prompt, or empty string on failure.
    """
    try:
        params = urllib.parse.urlencode({"lat": lat, "lon": lon})
        req = urllib.request.Request(
            f"https://api.urbanflux.london/borough-data-test?{params}",
            headers={"User-Agent": "UrbanFlux/1.0"},
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read())
    except Exception:
        return ""

    lines = []
    borough_name = (data.get("borough") or {}).get("name", "")
    if borough_name:
        lines.append(f"Borough: {borough_name}")

    for row in data.get("latest_rows_by_theme", []):
        if row.get("theme") not in _TRUSTED_THEMES:
            continue
        preview = (row.get("source_row_preview") or "").strip()
        date = row.get("date_start") or ""
        if preview:
            lines.append(f"[{row['theme']}] {date}: {preview}")

    return "\n".join(lines)


def _metrics_to_text(metrics: list[ImpactMetric]) -> str:
    return "\n".join(
        f"- {m.improved_metric}: {m.improved_value} (delta: {m.delta}, source: {m.source})"
        for m in metrics
    )


def _call_nemotron(prompt: str) -> list[ImpactMetric] | None:
    """
    Call Nemotron via fal.ai and parse the structured JSON response.
    Returns None if the call fails or returns unparseable output.
    """
    try:
        import fal_client
    except ImportError:
        return None

    fal_key = os.getenv("FAL_KEY")
    if not fal_key:
        return None

    try:
        result = fal_client.subscribe(
            "openrouter/router",
            arguments={
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "system_prompt": NEMOTRON_IMPACT_SYSTEM_PROMPT,
                "prompt": prompt,
            },
            with_logs=False,
        )
    except Exception:
        return None

    raw = (
        result.get("output")
        or result.get("text")
        or (result.get("choices") or [{}])[0].get("message", {}).get("content")
        or ""
    )

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return None
        metrics = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            metrics.append(ImpactMetric(
                improved_metric=str(item.get("improved_metric", "")),
                improved_value=str(item.get("improved_value", "")),
                delta=str(item.get("delta", "")),
                source=str(item.get("source", "")),
            ))
        return metrics if metrics else None
    except (json.JSONDecodeError, Exception):
        return None


def _nemotron_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
    benchmark_metrics: list[ImpactMetric],
    lat: float,
    lon: float,
) -> tuple[list[ImpactMetric], str]:
    """
    Try to get Nemotron-refined metrics within the timeout window.
    Falls back to benchmark metrics if Nemotron is too slow or unavailable.
    Returns (metrics, note).
    """
    borough_rows = _fetch_borough_rows(lat, lon)
    borough_name = ""
    for line in borough_rows.splitlines():
        if line.startswith("Borough:"):
            borough_name = line.replace("Borough:", "").strip()
            break

    prompt = f"""Area statistics:
- Population: {population:,}
- Area: {area_km2} km²
- Borough: {borough_name or "unknown"}

Replanning parameters (0–100 scale):
- Housing density: {params.housing_density}
- Green space target: {params.green_space_target}
- Parking pressure: {params.parking_pressure}
- Road fill: {params.road_fill}
- Road alignment: {params.road_alignment}
- Height ambition: {params.height_ambition}

Real borough data from London Datastore:
{borough_rows if borough_rows else "(unavailable)"}

Benchmark impact metrics (use as baseline):
{_metrics_to_text(benchmark_metrics)}

Return the refined JSON array of impact metrics."""

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call_nemotron, prompt)
        try:
            nemotron_metrics = future.result(timeout=_NEMOTRON_TIMEOUT_S)
        except FuturesTimeoutError:
            nemotron_metrics = None

    if nemotron_metrics:
        note = (
            f"Refined by Nvidia Nemotron using real {borough_name} data"
            if borough_name else
            "Refined by Nvidia Nemotron using London Datastore data"
        )
        return nemotron_metrics, note

    # Fallback
    note = (
        f"Benchmark estimates for {borough_name}" if borough_name
        else "Illustrative benchmark estimates"
    )
    return benchmark_metrics, note


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/",
    tags=["status"],
    summary="Backend status",
    description="Returns a basic message confirming that the UrbanFlux backend is running.",
    response_model=MessageResponse,
)
def root() -> MessageResponse:
    return MessageResponse(message="UrbanFlux backend is running")


@app.get(
    "/hello",
    tags=["status"],
    summary="Hello World",
    description="Returns a Hello World message for API connectivity checks.",
    response_model=MessageResponse,
)
def hello_world() -> MessageResponse:
    return MessageResponse(message="Hello World")


# ---------------------------------------------------------------------------
# New endpoints
# ---------------------------------------------------------------------------

@app.post(
    "/population",
    tags=["population"],
    summary="Calculate selected-area population",
    description=(
        "Calculates approximate population for a selected GeoJSON area by intersecting "
        "the polygon with London LSOA geometries and weighting population by overlap."
    ),
    response_model=PopulationResponse,
    responses={
        422: {"description": "Invalid GeoJSON geometry or request payload."},
        503: {"description": "Population/boundary data source unavailable."},
    },
)
def get_population(request: PopulationRequest) -> PopulationResponse:
    """
    Return approximate population for the supplied GeoJSON polygon.

    The polygon should be in WGS-84 (lon/lat).  Population is estimated by
    intersecting the polygon with 2021-Census LSOA boundaries and weighting
    each LSOA's population by the intersection area fraction.
    """
    geom = _extract_shapely_geom(request.polygon)
    area = _area_km2(geom)

    try:
        population, lsoa_count = _population_in_polygon(geom)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return PopulationResponse(
        approximate_population=population,
        lsoa_count=lsoa_count,
        area_km2=round(area, 4),
    )


@app.post(
    "/impact",
    tags=["impact"],
    summary="Calculate replanning impact",
    description=(
        "Calculates illustrative impact metrics for a selected GeoJSON area and the "
        "replanning parameters chosen in the frontend UI."
    ),
    response_model=ImpactResponse,
    responses={
        422: {"description": "Invalid GeoJSON geometry or request payload."},
        503: {"description": "Population/boundary data source unavailable."},
    },
)
def get_impact(request: ImpactRequest) -> ImpactResponse:
    """
    Return replanning impact metrics for the supplied polygon and parameters.

    Flow:
    1. Calculate population from LSOA intersection.
    2. Compute benchmark metrics from published London/TfL sources.
    3. Fetch real borough data rows from the London Datastore (via SQLite).
    4. Pass everything to Nvidia Nemotron for refinement (12 s timeout).
    5. Fall back to benchmark metrics if Nemotron is unavailable or too slow.
    """
    geom = _extract_shapely_geom(request.polygon)
    area = _area_km2(geom)

    try:
        population, _ = _population_in_polygon(geom)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    benchmark_metrics = _compute_impact_metrics(population, area, request.params)

    centroid = geom.centroid
    metrics, note = _nemotron_impact_metrics(
        population=population,
        area_km2=round(area, 4),
        params=request.params,
        benchmark_metrics=benchmark_metrics,
        lat=centroid.y,
        lon=centroid.x,
    )

    return ImpactResponse(
        approximate_population=population,
        area_km2=round(area, 4),
        metrics=metrics,
        note=note,
    )


@app.get(
    "/borough-data-test",
    tags=["borough-data"],
    summary="Test borough mapped data by coordinates",
    description=(
        "Resolves a London borough from WGS84 latitude/longitude and returns the same mapped-data "
        "summary used by `backend/data_sources/test.py`: summary by theme, top datasets, and a "
        "latest-row preview for each theme."
    ),
    response_model=BoroughDataTestResponse,
    responses={
        422: {"description": "Invalid coordinates or query parameters."},
        503: {"description": "Mapped data package unavailable or failed to load."},
    },
)
def get_borough_data_test(
    lat: float = Query(..., ge=49.0, le=61.0, description="WGS84 latitude."),
    lon: float = Query(..., ge=-8.0, le=2.0, description="WGS84 longitude."),
    top_datasets_limit: int = Query(5, ge=1, le=30, description="Number of top datasets to return."),
    theme: str | None = Query(None, description="Optional single theme for latest-row lookup."),
) -> BoroughDataTestResponse:
    try:
        payload = build_borough_data_test_response(
            lat=lat,
            lon=lon,
            top_datasets_limit=top_datasets_limit,
            theme=theme,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return BoroughDataTestResponse(**payload)
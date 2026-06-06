from __future__ import annotations

import json
import os
import sys
import time
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
    source: str = Field(
        ...,
        description="Primary London Datastore dataset or CSV URL backing the estimate, or an empty string.",
    )
    methodology_source: str = Field(
        "",
        description="Optional external method URL used for the calculation, never the primary data source.",
    )
    basis: str = Field(
        "",
        description="Short explanation of the mapped data and selected-area inputs used.",
    )


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
                            "source": "https://data.london.gov.uk/dataset/example-transport-data/",
                            "methodology_source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
                            "basis": "Mapped Westminster transport row + selected area/sliders",
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
                            "dataset_url": "https://data.london.gov.uk/dataset/example/",
                            "resource_title": "Example resource",
                            "csv_url": "https://data.london.gov.uk/download/example/example.csv",
                        }
                    ],
                    "latest_rows_by_theme": [
                        {
                            "theme": "housing",
                            "dataset_title": "Example dataset",
                            "dataset_url": "https://data.london.gov.uk/dataset/example/",
                            "resource_title": "Example resource",
                            "csv_url": "https://data.london.gov.uk/download/example/example.csv",
                            "source_url": "https://data.london.gov.uk/dataset/example/",
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


_METHODOLOGY_TFL_STREETS = "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit"
_METHODOLOGY_WHO_HEAT = "https://www.who.int/tools/heat-for-walking-and-cycling"
_METHODOLOGY_URBAN_GREENING = (
    "https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/"
    "parks-green-spaces-and-biodiversity/urban-greening"
)
_METHODOLOGY_LONDON_PLAN_TRANSPORT = (
    "https://www.london.gov.uk/programmes-strategies/planning/london-plan/"
    "the-london-plan-2021-online/chapter-10-transport"
)


def _is_london_datastore_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc == "data.london.gov.uk"


def _row_source(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    for key in ("source_url", "dataset_url", "csv_url"):
        source = _normalise_source_url(row.get(key))
        if source and _is_london_datastore_url(source):
            return source
    return ""


def _row_basis(
    borough_name: str,
    theme_label: str,
    row: dict[str, Any] | None,
    source: str,
) -> str:
    borough = borough_name or "resolved borough"
    if source:
        title = (
            (row or {}).get("dataset_title")
            or (row or {}).get("resource_title")
            or "mapped London Datastore"
        )
        return f"Mapped {borough} {theme_label} row ({title}) + selected area/sliders"
    return f"Benchmark method only; mapped {theme_label} borough row unavailable"


def _compute_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
    borough_name: str = "",
    rows_by_theme: dict[str, dict[str, Any]] | None = None,
) -> list[ImpactMetric]:
    """
    Return London-data-first impact metrics.

    Values are deterministic estimates from selected-area population/size and
    replanning sliders. The primary source, when available, is the mapped
    London Datastore row for the resolved borough. External links are retained
    only as methodology references.
    """
    rows_by_theme = rows_by_theme or {}

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

    # --- Local heat exposure ---
    # Green space is a design target, not a direct weather forecast. Keep this
    # as a conservative local microclimate proxy capped below 1 °C.
    cooling_c = round(min(0.8, max(0, (params.green_space_target - 5) / 75 * 0.8)), 2)

    # --- Parking pressure ---
    # Surface parking pressure consumes land that could otherwise be used for
    # homes, green space, or active frontage.
    productive_land_gain_pct = round(max(0, 0.8 - parking_pressure) * 12.5, 1)

    # --- Active travel health ---
    # WHO HEAT tool: each additional km of walking/cycling infrastructure per
    # 1 000 residents prevents ~0.4 premature deaths/year.
    lives_saved_per_year = round((road_km / max(population, 1)) * 1000 * 0.4, 2)

    transport_row = rows_by_theme.get("transport")
    housing_row = rows_by_theme.get("housing")
    planning_row = rows_by_theme.get("planning_land")
    socioeconomic_row = rows_by_theme.get("socioeconomic")

    transport_source = _row_source(transport_row)
    housing_source = _row_source(housing_row)
    planning_source = _row_source(planning_row)
    socioeconomic_source = _row_source(socioeconomic_row)

    metrics: list[ImpactMetric] = [
        ImpactMetric(
            improved_metric="Cycling mode share",
            improved_value=f"+{cycling_boost_pp} percentage points",
            delta=f"+{cycling_boost_pp}pp vs baseline",
            source=transport_source,
            methodology_source=_METHODOLOGY_TFL_STREETS,
            basis=_row_basis(borough_name, "transport", transport_row, transport_source),
        ),
        ImpactMetric(
            improved_metric="Housing capacity",
            improved_value=f"+{homes_capacity_uplift_pct}%",
            delta=f"+{homes_capacity_uplift_pct}% vs baseline massing",
            source=housing_source,
            basis=_row_basis(borough_name, "housing", housing_row, housing_source),
        ),
        ImpactMetric(
            improved_metric="Local summer heat exposure",
            improved_value=f"-{cooling_c} °C",
            delta=f"-{cooling_c} °C local heat proxy vs low-greening scenario",
            source=planning_source,
            methodology_source=_METHODOLOGY_URBAN_GREENING,
            basis=_row_basis(borough_name, "planning/land", planning_row, planning_source),
        ),
        ImpactMetric(
            improved_metric="Productive land released from parking",
            improved_value=f"+{productive_land_gain_pct}%",
            delta=f"+{productive_land_gain_pct}% vs maximum parking pressure",
            source=planning_source,
            methodology_source=_METHODOLOGY_LONDON_PLAN_TRANSPORT,
            basis=_row_basis(borough_name, "planning/land", planning_row, planning_source),
        ),
        ImpactMetric(
            improved_metric="Premature deaths prevented (active travel)",
            improved_value=f"{lives_saved_per_year} lives/year",
            delta=f"+{lives_saved_per_year} vs baseline",
            source=socioeconomic_source or transport_source,
            methodology_source=_METHODOLOGY_WHO_HEAT,
            basis=(
                _row_basis(borough_name, "socioeconomic", socioeconomic_row, socioeconomic_source)
                if socioeconomic_source
                else _row_basis(borough_name, "transport", transport_row, transport_source)
            ),
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
- London-data-first impact metrics already calculated from selected-area inputs and mapped borough data

Your task is to return a JSON array of impact metrics, using the provided London-data-first values as a baseline and refining them only where the real borough data justifies it.

Rules:
- Only use the sources and data provided. Do not hallucinate statistics, datasets, or sources.
- The source field must be either "" or exactly one London Datastore URL from the allowed source URLs list in the user prompt. Do not create, repair, shorten, or guess URLs.
- External methodology URLs such as TfL or WHO must never appear in source. They may appear only in methodology_source if they were already provided.
- If real borough data supports a more precise estimate, use it and cite the mapped London Datastore dataset in source.
- If there is no relevant data for a metric, set improved_value and delta to "" (empty string).
- Treat Local summer heat exposure as a conservative local microclimate / heat-exposure proxy only. Never describe it as citywide weather, forecast weather, or an actual air-temperature change across London.
- Return ONLY a valid JSON array. No preamble, no explanation, no markdown, no code fences.
- Every object in the array must have exactly these six string fields: improved_metric, improved_value, delta, source, methodology_source, basis.

Example output format:
[
  {
    "improved_metric": "Cycling mode share",
    "improved_value": "+3.2 percentage points",
    "delta": "+3.2pp vs baseline",
    "source": "https://data.london.gov.uk/dataset/example-transport-data/",
    "methodology_source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
    "basis": "Mapped Westminster transport row + selected area/sliders"
  }
]"""


_TRUSTED_THEMES = {"housing", "transport", "planning_land", "socioeconomic"}
_NEMOTRON_TIMEOUT_S = 12  # wall-clock seconds before we fall back to benchmarks
_SOURCE_VALIDATION_TIMEOUT_S = 2.5
_SOURCE_VALIDATION_TTL_S = 6 * 60 * 60
_SOURCE_VALIDATION_MAX_WORKERS = 5
_SOURCE_VALIDATION_CACHE: dict[str, tuple[float, bool]] = {}


def _normalise_source_url(url: object) -> str:
    return str(url or "").strip()


def _source_url_is_well_formed(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _source_url_is_live(url: str) -> bool:
    if not url or not _source_url_is_well_formed(url):
        return False

    now = time.time()
    cached = _SOURCE_VALIDATION_CACHE.get(url)
    if cached and now - cached[0] < _SOURCE_VALIDATION_TTL_S:
        return cached[1]

    try:
        import httpx

        with httpx.Client(
            follow_redirects=True,
            timeout=_SOURCE_VALIDATION_TIMEOUT_S,
            headers={"User-Agent": "UrbanFlux-source-check/1.0"},
        ) as client:
            response = client.head(url)
            if response.status_code in {405, 501}:
                response = client.get(url, headers={"Range": "bytes=0-0"})
            is_live = response.status_code < 400
    except Exception:
        is_live = False

    _SOURCE_VALIDATION_CACHE[url] = (now, is_live)
    return is_live


def _validate_metric_sources(metrics: list[ImpactMetric], allowed_sources: set[str]) -> list[ImpactMetric]:
    """
    Keep primary sources constrained to mapped London Datastore URLs.

    We intentionally do not live-check the URLs here: source validation should
    enforce provenance, not make metrics disappear because a source site is slow.
    """
    return [
        metric.model_copy(update={"source": source if source in allowed_sources else ""})
        for metric in metrics
        for source in [_normalise_source_url(metric.source)]
    ]


def _source_catalogue_text(allowed_sources: set[str]) -> str:
    if not allowed_sources:
        return "(none)"
    return "\n".join(f"- {source}" for source in sorted(allowed_sources))


def _fetch_borough_context(
    lat: float,
    lon: float,
) -> tuple[str, dict[str, dict[str, Any]], str, set[str]]:
    """
    Pull latest mapped rows for trusted themes from Eugene's SQLite path.

    Returns (borough_name, rows_by_theme, prompt_text, allowed_sources). The
    allowed sources are only underlying London Datastore URLs, never the
    UrbanFlux wrapper endpoint.
    """
    try:
        data = build_borough_data_test_response(
            lat=lat,
            lon=lon,
            top_datasets_limit=30,
        )
    except Exception:
        return "", {}, "", set()

    lines = []
    allowed_sources: set[str] = set()
    rows_by_theme: dict[str, dict[str, Any]] = {}
    borough_name = (data.get("borough") or {}).get("name", "")
    if borough_name:
        lines.append(f"Borough: {borough_name}")

    for row in data.get("latest_rows_by_theme", []):
        theme = row.get("theme")
        if theme not in _TRUSTED_THEMES:
            continue
        rows_by_theme[theme] = row
        preview = (row.get("source_row_preview") or "").strip()
        date = row.get("date_start") or ""
        source_url = _row_source(row)
        if source_url:
            allowed_sources.add(source_url)
        for source in (row.get("source_url"), row.get("dataset_url"), row.get("csv_url")):
            source = _normalise_source_url(source)
            if source and _is_london_datastore_url(source):
                allowed_sources.add(source)
        dataset_title = row.get("dataset_title") or "Unknown dataset"
        resource_title = row.get("resource_title") or "Unknown resource"
        if preview:
            lines.append(
                f"[{row['theme']}] {date}: {preview} "
                f"(dataset: {dataset_title}; resource: {resource_title}; source: {source_url})"
            )

    return borough_name, rows_by_theme, "\n".join(lines), allowed_sources


def _fetch_borough_rows(lat: float, lon: float) -> tuple[str, set[str]]:
    """Compatibility wrapper for tests and Nemotron prompt formatting."""
    _, _, borough_rows, allowed_sources = _fetch_borough_context(lat, lon)
    return borough_rows, allowed_sources


def _metrics_to_text(metrics: list[ImpactMetric]) -> str:
    return "\n".join(
        (
            f"- {m.improved_metric}: {m.improved_value} "
            f"(delta: {m.delta}, source: {m.source}, "
            f"methodology_source: {m.methodology_source}, basis: {m.basis})"
        )
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
                methodology_source=str(item.get("methodology_source", "")),
                basis=str(item.get("basis", "")),
            ))
        return metrics if metrics else None
    except (json.JSONDecodeError, Exception):
        return None


def _nemotron_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
    london_metrics: list[ImpactMetric],
    borough_name: str,
    borough_rows: str,
    borough_sources: set[str],
) -> tuple[list[ImpactMetric], str]:
    """
    Try to get Nemotron-refined metrics within the timeout window.
    Falls back to London-data-first deterministic metrics if Nemotron is too
    slow or unavailable.
    Returns (metrics, note).
    """
    allowed_sources = {
        _normalise_source_url(metric.source)
        for metric in london_metrics
        if _normalise_source_url(metric.source)
    }
    allowed_sources.update(borough_sources)

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

London-data-first impact metrics (use as baseline):
{_metrics_to_text(london_metrics)}

Allowed source URLs for the source field (London Datastore only):
{_source_catalogue_text(allowed_sources)}

Return the refined JSON array of impact metrics."""

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call_nemotron, prompt)
        try:
            nemotron_metrics = future.result(timeout=_NEMOTRON_TIMEOUT_S)
        except FuturesTimeoutError:
            nemotron_metrics = None

    if nemotron_metrics:
        nemotron_metrics = _validate_metric_sources(nemotron_metrics, allowed_sources)
        note = (
            f"Refined by Nvidia Nemotron using real {borough_name} data"
            if borough_name else
            "Refined by Nvidia Nemotron using London Datastore data"
        )
        return nemotron_metrics, note

    # Fallback
    has_london_sources = any(_normalise_source_url(metric.source) for metric in london_metrics)
    if borough_name and has_london_sources:
        note = f"London Datastore mapped estimates for {borough_name}"
    elif borough_name:
        note = f"Benchmark-method estimates for {borough_name}; mapped rows unavailable"
    else:
        note = "Benchmark-method estimates; mapped borough data unavailable"
    return _validate_metric_sources(london_metrics, allowed_sources), note


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
    2. Resolve the selected area's centroid to mapped London Datastore borough rows.
    3. Compute London-data-first metrics from selected area, UI parameters, and mapped rows.
    4. Optionally pass everything to Nvidia Nemotron for refinement (12 s timeout).
    5. Fall back to deterministic London-data-first metrics if Nemotron is unavailable or too slow.
    """
    geom = _extract_shapely_geom(request.polygon)
    area = _area_km2(geom)

    try:
        population, _ = _population_in_polygon(geom)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    centroid = geom.centroid
    borough_name, rows_by_theme, borough_rows, borough_sources = _fetch_borough_context(
        lat=centroid.y,
        lon=centroid.x,
    )
    london_metrics = _compute_impact_metrics(
        population,
        area,
        request.params,
        borough_name=borough_name,
        rows_by_theme=rows_by_theme,
    )
    metrics, note = _nemotron_impact_metrics(
        population=population,
        area_km2=round(area, 4),
        params=request.params,
        london_metrics=london_metrics,
        borough_name=borough_name,
        borough_rows=borough_rows,
        borough_sources=borough_sources,
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

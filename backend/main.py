from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
from functools import lru_cache
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from shapely.geometry import shape
from shapely.ops import unary_union

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
    road_width_m: float = Field(10.0, ge=1.0, le=80.0, description="Planned road width in metres.")
    lanes: int = Field(2, ge=1, le=8, description="Planned number of traffic lanes.")
    speed_limit_kmh: int = Field(30, ge=5, le=130, description="Proposed road speed limit in km/h.")
    cycle_lane: bool = Field(False, description="Whether protected cycle lanes are included.")
    green_space_pct: float = Field(0.0, ge=0.0, le=100.0, description="Target green space percentage.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "road_width_m": 10.0,
                    "lanes": 2,
                    "speed_limit_kmh": 30,
                    "cycle_lane": True,
                    "green_space_pct": 35.0,
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

    # Road-km estimate: assume a rough street grid density of ~12 km per km²
    # in inner London (TfL Street Types report, 2023).
    road_km = round(area_km2 * 12, 1)

    # --- Walking / cycling accessibility ---
    # TfL: each km of new protected cycle lane increases cycling mode share
    # by ~0.3 percentage points in the surrounding LSOA (LCWIP 2023).
    cycling_boost_pp = round(road_km * 0.3 if params.cycle_lane else 0, 1)

    # --- Air quality ---
    # LAEI 2019: road transport contributes ~50 % of NOₓ in inner London.
    # Lower speed limits reduce NOₓ by ~6 % per 10 km/h reduction from 50 km/h.
    baseline_speed = 50
    speed_reduction_steps = max(0, (baseline_speed - params.speed_limit_kmh) // 10)
    nox_reduction_pct = round(speed_reduction_steps * 6, 1)

    # --- Green space ---
    # Each 1 % increase in green space cover in an LSOA correlates with
    # ~0.15 °C reduction in summer peak temperature (UCL Urban Cooling, 2022).
    temp_reduction = round(params.green_space_pct * 0.15, 2)

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
            improved_metric="Road NOₓ emissions",
            improved_value=f"-{nox_reduction_pct}%",
            delta=f"-{nox_reduction_pct}% vs current speed limit",
            source="https://data.london.gov.uk/dataset/london-atmospheric-emissions-inventory--laei--2019",
        ),
        ImpactMetric(
            improved_metric="Summer peak temperature",
            improved_value=f"-{temp_reduction} °C",
            delta=f"-{temp_reduction} °C vs no green space change",
            source="https://www.london.gov.uk/programmes-strategies/environment-and-climate-change/climate-change/urban-greening",
        ),
        ImpactMetric(
            improved_metric="Premature deaths prevented (active travel)",
            improved_value=f"{lives_saved_per_year} lives/year",
            delta=f"+{lives_saved_per_year} vs baseline",
            source="https://www.euro.who.int/en/health-topics/environment-and-health/Transport-and-health/activities/quantifying-health-impacts-of-transport/heat-tool",
        ),
        ImpactMetric(
            improved_metric="Estimated population affected",
            improved_value=f"{population:,}",
            delta="N/A",
            source="https://www.nomisweb.co.uk/output/census/2021/census2021-ts001.zip",
        ),
    ]

    return metrics


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

    Population is calculated from LSOA intersection; impact metrics are
    derived from published London/TfL benchmarks (illustrative until
    Eugene's model is integrated via data_sources).
    """
    geom = _extract_shapely_geom(request.polygon)
    area = _area_km2(geom)

    try:
        population, _ = _population_in_polygon(geom)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    metrics = _compute_impact_metrics(population, area, request.params)

    return ImpactResponse(
        approximate_population=population,
        area_km2=round(area, 4),
        metrics=metrics,
    )

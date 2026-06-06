from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException, Query


_BACKEND_DIR = Path(__file__).resolve().parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app_setup import create_app
from borough_context import _fetch_borough_context as _fetch_borough_context_impl
from borough_data import build_borough_data_test_response
from impact import (
    _METHODOLOGY_LONDON_PLAN_TRANSPORT,
    _METHODOLOGY_TFL_STREETS,
    _METHODOLOGY_URBAN_GREENING,
    _METHODOLOGY_WHO_HEAT,
    _compute_impact_metrics,
    _is_london_datastore_url,
    _normalise_source_url,
    _row_basis,
    _row_source,
)
from nemotron_adapter import (
    NEMOTRON_IMPACT_SYSTEM_PROMPT,
    _call_nemotron,
    _metrics_to_text,
    _nemotron_impact_metrics as _nemotron_impact_metrics_impl,
    _source_catalogue_text,
    _validate_metric_sources,
)
from population import (
    _LSOA_BOUNDARIES_PATH,
    _POPULATION_JSON_PATH,
    _area_km2,
    _extract_shapely_geom,
    _fetch_arcgis_features,
    _load_lsoa_features,
    _population_in_polygon,
)
from schemas import (
    BoroughDataTestResponse,
    GeoJSONPolygon,
    ImpactMetric,
    ImpactRequest,
    ImpactResponse,
    MessageResponse,
    PopulationRequest,
    PopulationResponse,
    ReplanningParams,
)


app = create_app()


def _fetch_borough_context(
    lat: float,
    lon: float,
) -> tuple[str, dict[str, dict], str, set[str]]:
    return _fetch_borough_context_impl(lat, lon, build_borough_data_test_response)


def _nemotron_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
    london_metrics: list[ImpactMetric],
    borough_name: str,
    borough_rows: str,
    borough_sources: set[str],
) -> tuple[list[ImpactMetric], str]:
    return _nemotron_impact_metrics_impl(
        population=population,
        area_km2=area_km2,
        params=params,
        london_metrics=london_metrics,
        borough_name=borough_name,
        borough_rows=borough_rows,
        borough_sources=borough_sources,
        call_nemotron=_call_nemotron,
    )


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

    The polygon should be in WGS-84 (lon/lat). Population is estimated by
    intersecting the polygon with 2021-Census LSOA boundaries and weighting
    each LSOA's population by the intersection area fraction.
    """
    geom = _extract_shapely_geom(request.polygon)
    area = _area_km2(geom)

    try:
        population, lsoa_count = _population_in_polygon(geom)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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

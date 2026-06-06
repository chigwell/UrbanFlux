from __future__ import annotations

import urllib.parse
from typing import Any

from schemas import ImpactMetric, ReplanningParams


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


def _normalise_source_url(url: object) -> str:
    return str(url or "").strip()


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

    road_km = round(area_km2 * 12 * road_fill, 1)
    cycling_boost_pp = round(road_km * (0.18 + road_alignment * 0.12), 1)
    homes_capacity_uplift_pct = round((density * 26) + (height_ambition * 18), 1)
    cooling_c = round(min(0.8, max(0, (params.green_space_target - 5) / 75 * 0.8)), 2)
    productive_land_gain_pct = round(max(0, 0.8 - parking_pressure) * 12.5, 1)
    lives_saved_per_year = round((road_km / max(population, 1)) * 1000 * 0.4, 2)

    transport_row = rows_by_theme.get("transport")
    housing_row = rows_by_theme.get("housing")
    planning_row = rows_by_theme.get("planning_land")
    socioeconomic_row = rows_by_theme.get("socioeconomic")

    transport_source = _row_source(transport_row)
    housing_source = _row_source(housing_row)
    planning_source = _row_source(planning_row)
    socioeconomic_source = _row_source(socioeconomic_row)

    return [
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

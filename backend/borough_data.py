from __future__ import annotations

from typing import Any

try:
    from utils import _latest_rows_for_themes
except ImportError:
    from backend.utils import _latest_rows_for_themes


def _get_data_source_functions():
    try:
        from data_sources import get_borough_summary, resolve_borough
    except ImportError:
        from backend.data_sources import get_borough_summary, resolve_borough
    return get_borough_summary, resolve_borough


def build_borough_data_test_response(
    lat: float,
    lon: float,
    top_datasets_limit: int,
    theme: str | None = None,
) -> dict[str, Any]:
    get_borough_summary, resolve_borough = _get_data_source_functions()
    borough = resolve_borough(lat, lon)
    if borough is None:
        return {
            "coordinates": {"lat": lat, "lon": lon},
            "borough": None,
            "summary_by_theme": [],
            "top_datasets": [],
            "latest_rows_by_theme": [],
        }

    summary = get_borough_summary(lat, lon, top_datasets_limit=top_datasets_limit)
    themes = [theme] if theme else [item["theme"] for item in summary["themes"]]
    latest_rows = _latest_rows_for_themes(borough["name"], themes)

    return {
        "coordinates": {"lat": lat, "lon": lon},
        "borough": borough,
        "summary_by_theme": summary["themes"],
        "top_datasets": summary["top_datasets"],
        "latest_rows_by_theme": latest_rows,
    }

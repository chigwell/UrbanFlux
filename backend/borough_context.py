from __future__ import annotations

from typing import Any, Callable

from impact import _is_london_datastore_url, _normalise_source_url, _row_source


_TRUSTED_THEMES = {"housing", "transport", "planning_land", "socioeconomic"}


def _fetch_borough_context(
    lat: float,
    lon: float,
    build_response: Callable[..., dict[str, Any]],
) -> tuple[str, dict[str, dict[str, Any]], str, set[str]]:
    """
    Pull latest mapped rows for trusted themes from the mapped-data package.

    Returns (borough_name, rows_by_theme, prompt_text, allowed_sources). The
    allowed sources are only underlying London Datastore URLs, never the
    UrbanFlux wrapper endpoint.
    """
    try:
        data = build_response(
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

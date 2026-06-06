from __future__ import annotations

from typing import Any


def _get_london_mapped_core_functions():
    try:
        from data_sources.london_mapped_data_package.london_mapped_data.core import (
            connect_db,
            row_to_dict,
        )
    except ImportError:
        from backend.data_sources.london_mapped_data_package.london_mapped_data.core import (
            connect_db,
            row_to_dict,
        )
    return connect_db, row_to_dict


_LONDON_MAPPED_INDEXES_READY = False


def _ensure_london_mapped_indexes(connect_db) -> None:
    global _LONDON_MAPPED_INDEXES_READY
    if _LONDON_MAPPED_INDEXES_READY:
        return

    try:
        with connect_db() as conn:
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_urbanflux_rows_borough_status_csv_date
                ON csv_row_transformations (
                    borough_name,
                    status,
                    csv_file_id,
                    date_end,
                    date_start,
                    row_number
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_urbanflux_csv_files_theme_id
                ON dataset_csv_files (theme, id)
                """
            )
        _LONDON_MAPPED_INDEXES_READY = True
    except Exception:
        _LONDON_MAPPED_INDEXES_READY = True


def _preview_source_row(source_row: object) -> str:
    if isinstance(source_row, dict):
        return "; ".join(f"{key}: {value}" for key, value in list(source_row.items())[:6])
    return str(source_row or "")


def _format_latest_theme_row(theme: str, row: dict[str, Any] | None) -> dict[str, Any]:
    if row is None:
        return {
            "theme": theme,
            "dataset_title": None,
            "resource_title": None,
            "row_number": None,
            "date_start": None,
            "date_end": None,
            "source_row_preview": "No dated row found",
        }

    return {
        "theme": theme,
        "dataset_title": row.get("dataset_title"),
        "resource_title": row.get("resource_title"),
        "row_number": row.get("row_number"),
        "date_start": row.get("date_start"),
        "date_end": row.get("date_end"),
        "source_row_preview": _preview_source_row(row.get("source_row")),
    }


def _latest_rows_for_themes(borough_name: str, themes: list[str]) -> list[dict[str, Any]]:
    theme_list = [item for item in themes if item]
    if not theme_list:
        return []

    connect_db, row_to_dict = _get_london_mapped_core_functions()
    _ensure_london_mapped_indexes(connect_db)

    placeholders = ", ".join("?" for _ in theme_list)
    sql = f"""
        WITH ranked_rows AS (
            SELECT
                r.id,
                r.csv_file_id,
                r.row_number,
                r.date_start,
                r.date_end,
                r.borough_name,
                r.date_status,
                r.borough_status,
                r.status AS row_status,
                r.error_message,
                r.source_row_json,
                ds.id AS source_id,
                ds.title AS dataset_title,
                ds.description AS dataset_description,
                ds.dataset_url,
                ds.organisation_name,
                cf.id AS source_file_id,
                cf.title AS resource_title,
                cf.description AS resource_description,
                cf.csv_url,
                cf.theme,
                ROW_NUMBER() OVER (
                    PARTITION BY cf.theme
                    ORDER BY
                        COALESCE(r.date_end, r.date_start, '') DESC,
                        COALESCE(r.date_start, '') DESC,
                        r.row_number DESC,
                        r.id DESC
                ) AS row_rank
            FROM csv_row_transformations r
            JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE r.borough_name = ?
              AND r.status IN ('success', 'partial')
              AND cf.theme IN ({placeholders})
        )
        SELECT *
        FROM ranked_rows
        WHERE row_rank = 1
    """

    with connect_db() as conn:
        rows = conn.execute(sql, [borough_name, *theme_list]).fetchall()

    latest_by_theme = {
        row["theme"]: _format_latest_theme_row(row["theme"], row_to_dict(row))
        for row in rows
    }
    return [
        latest_by_theme.get(theme_name, _format_latest_theme_row(theme_name, None))
        for theme_name in theme_list
    ]

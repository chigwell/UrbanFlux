from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterator

from .geo import find_borough
from .themes import THEMES


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PACKAGE_ROOT / "data" / "london_mapped_compact.sqlite3"


def resolve_db_path(db_path: str | Path | None = None) -> Path:
    path = Path(db_path).expanduser() if db_path else DEFAULT_DB_PATH
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(f"Mapped data DB not found: {path}")
    return path


def connect_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(resolve_db_path(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def validate_theme(theme: str | None) -> None:
    if theme is not None and theme not in THEMES:
        supported = ", ".join(sorted(THEMES))
        raise ValueError(f"Unsupported theme {theme!r}. Supported themes: {supported}")


def resolve_borough(lat: float, lon: float, db_path: str | Path | None = None) -> dict | None:
    return find_borough(lat, lon, resolve_db_path(db_path))


def parse_source_row(raw_json: str | None) -> dict[str, Any] | list[Any] | str | None:
    if raw_json is None:
        return None
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "csv_file_id": row["csv_file_id"],
        "row_number": row["row_number"],
        "theme": row["theme"],
        "date_start": row["date_start"],
        "date_end": row["date_end"],
        "borough_name": row["borough_name"],
        "row_status": row["row_status"],
        "date_status": row["date_status"],
        "borough_status": row["borough_status"],
        "error_message": row["error_message"],
        "source": {
            "source_id": row["source_id"],
            "dataset_title": row["dataset_title"],
            "dataset_description": row["dataset_description"],
            "dataset_url": row["dataset_url"],
            "organisation_name": row["organisation_name"],
            "source_file_id": row["source_file_id"],
            "resource_title": row["resource_title"],
            "resource_description": row["resource_description"],
            "csv_url": row["csv_url"],
        },
        "source_row": parse_source_row(row["source_row_json"]),
    }


def status_clause(include_partial: bool) -> str:
    return "r.status IN ('success', 'partial')" if include_partial else "r.status = 'success'"


def data_sql(theme: str | None, include_partial: bool, limit: int | None) -> str:
    filters = [f"{status_clause(include_partial)}"]
    if theme is not None:
        filters.append("cf.theme = :theme")
    where_sql = " AND ".join(filters)
    limit_sql = "" if limit is None else "LIMIT :limit OFFSET :offset"
    return f"""
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
      cf.theme
    FROM csv_row_transformations r
    JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
    JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
    WHERE r.borough_name = :borough_name
      AND {where_sql}
    ORDER BY r.id
    {limit_sql}
    """


def fetch_rows(
    conn: sqlite3.Connection,
    borough_name: str,
    theme: str | None,
    include_partial: bool,
    limit: int | None,
    offset: int,
) -> list[dict[str, Any]]:
    params = {
        "borough_name": borough_name,
        "theme": theme,
        "limit": limit,
        "offset": offset,
    }
    rows = conn.execute(data_sql(theme, include_partial, limit), params).fetchall()
    return [row_to_dict(row) for row in rows]


def get_borough_data(
    lat: float,
    lon: float,
    theme: str | None = None,
    include_partial: bool = True,
    limit: int | None = None,
    offset: int = 0,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    validate_theme(theme)
    if limit is not None and limit < 1:
        raise ValueError("limit must be None or a positive integer")
    if offset < 0:
        raise ValueError("offset must be zero or greater")

    db = resolve_db_path(db_path)
    borough = find_borough(lat, lon, db)
    if borough is None:
        return {
            "borough": None,
            "filters": {"theme": theme, "include_partial": include_partial},
            "pagination": {"limit": limit, "offset": offset, "returned": 0, "next_offset": None},
            "rows": [],
        }

    with connect_db(db) as conn:
        rows = fetch_rows(conn, borough["name"], theme, include_partial, limit, offset)

    return {
        "borough": borough,
        "filters": {"theme": theme, "include_partial": include_partial},
        "pagination": {
            "limit": limit,
            "offset": offset,
            "returned": len(rows),
            "next_offset": offset + len(rows) if limit is not None and len(rows) == limit else None,
        },
        "rows": rows,
    }


def iter_borough_data(
    lat: float,
    lon: float,
    theme: str | None = None,
    include_partial: bool = True,
    batch_size: int = 1000,
    db_path: str | Path | None = None,
) -> Iterator[dict[str, Any]]:
    validate_theme(theme)
    if batch_size < 1:
        raise ValueError("batch_size must be a positive integer")

    db = resolve_db_path(db_path)
    borough = find_borough(lat, lon, db)
    if borough is None:
        return

    offset = 0
    with connect_db(db) as conn:
        while True:
            rows = fetch_rows(conn, borough["name"], theme, include_partial, batch_size, offset)
            if not rows:
                break
            yield from rows
            offset += len(rows)


def get_borough_summary(
    lat: float,
    lon: float,
    db_path: str | Path | None = None,
    top_datasets_limit: int = 30,
) -> dict[str, Any]:
    if top_datasets_limit < 1:
        raise ValueError("top_datasets_limit must be a positive integer")

    db = resolve_db_path(db_path)
    borough = find_borough(lat, lon, db)
    if borough is None:
        return {"borough": None, "themes": [], "top_datasets": []}

    with connect_db(db) as conn:
        theme_rows = conn.execute(
            """
            SELECT
              cf.theme,
              COUNT(*) AS row_count,
              COUNT(DISTINCT r.csv_file_id) AS csv_file_count,
              MIN(r.date_start) AS min_date_start,
              MAX(r.date_end) AS max_date_end
            FROM csv_row_transformations r
            JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
            WHERE r.borough_name = :borough_name
              AND r.status IN ('success', 'partial')
            GROUP BY cf.theme
            ORDER BY row_count DESC
            """,
            {"borough_name": borough["name"]},
        ).fetchall()
        dataset_rows = conn.execute(
            """
            SELECT
              ds.id AS source_id,
              cf.id AS source_file_id,
              ds.title AS dataset_title,
              cf.title AS resource_title,
              cf.theme,
              COUNT(*) AS row_count,
              MIN(r.date_start) AS min_date_start,
              MAX(r.date_end) AS max_date_end
            FROM csv_row_transformations r
            JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE r.borough_name = :borough_name
              AND r.status IN ('success', 'partial')
            GROUP BY ds.id, cf.id
            ORDER BY row_count DESC
            LIMIT :limit
            """,
            {"borough_name": borough["name"], "limit": top_datasets_limit},
        ).fetchall()

    return {
        "borough": borough,
        "themes": [dict(row) for row in theme_rows],
        "top_datasets": [dict(row) for row in dataset_rows],
    }

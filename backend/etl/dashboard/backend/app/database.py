from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .config import get_settings
from .transformation_schema import RULE_SCHEMA_VERSION


SCHEMA = """
CREATE TABLE IF NOT EXISTS dataset_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    uuid TEXT NOT NULL UNIQUE,

    source_code TEXT UNIQUE,

    dataset_url TEXT NOT NULL UNIQUE,

    title TEXT NOT NULL,
    description TEXT,

    organisation_name TEXT,
    licence_name TEXT,

    created_at_source TEXT,
    updated_at_source TEXT,

    tags_json TEXT NOT NULL DEFAULT '[]',
    categories_json TEXT NOT NULL DEFAULT '[]',

    raw_metadata_json TEXT,

    scraped_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dataset_sources_uuid
    ON dataset_sources(uuid);

CREATE INDEX IF NOT EXISTS idx_dataset_sources_source_code
    ON dataset_sources(source_code);

CREATE INDEX IF NOT EXISTS idx_dataset_sources_title
    ON dataset_sources(title);

CREATE INDEX IF NOT EXISTS idx_dataset_sources_updated_at_source
    ON dataset_sources(updated_at_source);

CREATE TRIGGER IF NOT EXISTS trg_dataset_sources_updated_at_local
AFTER UPDATE ON dataset_sources
FOR EACH ROW
BEGIN
    UPDATE dataset_sources
    SET updated_at_local = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS dataset_csv_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_source_id INTEGER NOT NULL,

    resource_uuid TEXT,
    resource_code TEXT,
    title TEXT NOT NULL,
    description TEXT,

    csv_url TEXT NOT NULL,
    local_path TEXT,
    file_name TEXT,

    file_size_bytes INTEGER,
    source_file_size_bytes INTEGER,
    content_hash TEXT,
    format TEXT NOT NULL DEFAULT 'csv',

    status INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    downloaded_at TEXT,

    raw_metadata_json TEXT,
    created_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(dataset_source_id)
        REFERENCES dataset_sources(id)
        ON DELETE CASCADE,
    UNIQUE(dataset_source_id, csv_url)
);

CREATE INDEX IF NOT EXISTS idx_dataset_csv_files_source
    ON dataset_csv_files(dataset_source_id);

CREATE INDEX IF NOT EXISTS idx_dataset_csv_files_status
    ON dataset_csv_files(status);

CREATE INDEX IF NOT EXISTS idx_dataset_csv_files_resource_uuid
    ON dataset_csv_files(resource_uuid);

CREATE TRIGGER IF NOT EXISTS trg_dataset_csv_files_updated_at_local
AFTER UPDATE ON dataset_csv_files
FOR EACH ROW
BEGIN
    UPDATE dataset_csv_files
    SET updated_at_local = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mode TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    pages_scanned INTEGER NOT NULL DEFAULT 0,
    datasets_seen INTEGER NOT NULL DEFAULT 0,
    sources_upserted INTEGER NOT NULL DEFAULT 0,
    csv_files_seen INTEGER NOT NULL DEFAULT 0,
    csv_files_downloaded INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0,
    message TEXT
);

CREATE TABLE IF NOT EXISTS csv_transformation_plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    csv_file_id INTEGER NOT NULL UNIQUE,

    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    rule_schema_version INTEGER NOT NULL DEFAULT 1,
    csv_content_hash TEXT,
    model TEXT,
    llm_endpoint TEXT,

    header_json TEXT NOT NULL DEFAULT '[]',
    sample_rows_json TEXT NOT NULL DEFAULT '[]',
    prompt_messages_json TEXT NOT NULL DEFAULT '[]',
    response_json TEXT,

    date_range_status TEXT,
    date_range_rule_json TEXT,
    borough_status TEXT,
    borough_rule_json TEXT,
    transformation_summary TEXT,
    error_message TEXT,

    planned_at TEXT,
    created_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(csv_file_id)
        REFERENCES dataset_csv_files(id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_csv_transformation_plans_status
    ON csv_transformation_plans(status);

CREATE TRIGGER IF NOT EXISTS trg_csv_transformation_plans_updated_at_local
AFTER UPDATE ON csv_transformation_plans
FOR EACH ROW
BEGIN
    UPDATE csv_transformation_plans
    SET updated_at_local = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS csv_row_transformations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    csv_file_id INTEGER NOT NULL,
    transformation_plan_id INTEGER NOT NULL,
    row_number INTEGER NOT NULL,

    source_row_hash TEXT NOT NULL,
    source_row_json TEXT NOT NULL,

    date_start TEXT,
    date_end TEXT,
    borough_name TEXT,
    date_status TEXT NOT NULL,
    borough_status TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT,

    created_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(csv_file_id)
        REFERENCES dataset_csv_files(id)
        ON DELETE CASCADE,
    FOREIGN KEY(transformation_plan_id)
        REFERENCES csv_transformation_plans(id)
        ON DELETE CASCADE,
    UNIQUE(csv_file_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_csv_file
    ON csv_row_transformations(csv_file_id);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_borough
    ON csv_row_transformations(borough_name);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_date_start
    ON csv_row_transformations(date_start);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_date_end
    ON csv_row_transformations(date_end);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_borough_dates
    ON csv_row_transformations(borough_name, date_start, date_end);

CREATE INDEX IF NOT EXISTS idx_csv_row_transformations_status
    ON csv_row_transformations(status);

CREATE TRIGGER IF NOT EXISTS trg_csv_row_transformations_updated_at_local
AFTER UPDATE ON csv_row_transformations
FOR EACH ROW
BEGIN
    UPDATE csv_row_transformations
    SET updated_at_local = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS london_borough_boundaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    borough_name TEXT NOT NULL UNIQUE,
    borough_code TEXT,
    source_url TEXT,
    source_file_name TEXT,
    coordinate_system TEXT,
    geometry_type TEXT,
    border_coordinates_json TEXT NOT NULL,
    source_file_hash TEXT,
    ingested_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at_local TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_london_borough_boundaries_name
    ON london_borough_boundaries(borough_name);

CREATE TRIGGER IF NOT EXISTS trg_london_borough_boundaries_updated_at_local
AFTER UPDATE ON london_borough_boundaries
FOR EACH ROW
BEGIN
    UPDATE london_borough_boundaries
    SET updated_at_local = CURRENT_TIMESTAMP
    WHERE id = OLD.id;
END;
"""


def _database_path() -> Path:
    settings = get_settings()
    return settings.database_path


def get_connection() -> sqlite3.Connection:
    db_path = _database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    with connect() as connection:
        connection.executescript(SCHEMA)
        _ensure_column(
            connection,
            table_name="csv_transformation_plans",
            column_name="rule_schema_version",
            column_definition="INTEGER NOT NULL DEFAULT 1",
        )
        _ensure_column(
            connection,
            table_name="csv_transformation_plans",
            column_name="csv_content_hash",
            column_definition="TEXT",
        )


def _ensure_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    value = dict(row)
    for key in ("tags_json", "categories_json", "raw_metadata_json"):
        if key in value and isinstance(value[key], str):
            try:
                value[key.removesuffix("_json")] = json.loads(value[key])
            except json.JSONDecodeError:
                value[key.removesuffix("_json")] = value[key]
    if "border_coordinates_json" in value and isinstance(value["border_coordinates_json"], str):
        try:
            value["border_coordinates"] = json.loads(value["border_coordinates_json"])
        except json.JSONDecodeError:
            value["border_coordinates"] = value["border_coordinates_json"]
    for key in (
        "header_json",
        "sample_rows_json",
        "prompt_messages_json",
        "response_json",
        "date_range_rule_json",
        "borough_rule_json",
        "source_row_json",
    ):
        if key in value and isinstance(value[key], str):
            try:
                value[key.removesuffix("_json")] = json.loads(value[key])
            except json.JSONDecodeError:
                value[key.removesuffix("_json")] = value[key]
    return value


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def upsert_dataset_source(connection: sqlite3.Connection, source: dict[str, Any]) -> int:
    connection.execute(
        """
        INSERT INTO dataset_sources (
            uuid,
            source_code,
            dataset_url,
            title,
            description,
            organisation_name,
            licence_name,
            created_at_source,
            updated_at_source,
            tags_json,
            categories_json,
            raw_metadata_json,
            scraped_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(uuid) DO UPDATE SET
            source_code = excluded.source_code,
            dataset_url = excluded.dataset_url,
            title = excluded.title,
            description = excluded.description,
            organisation_name = excluded.organisation_name,
            licence_name = excluded.licence_name,
            created_at_source = excluded.created_at_source,
            updated_at_source = excluded.updated_at_source,
            tags_json = excluded.tags_json,
            categories_json = excluded.categories_json,
            raw_metadata_json = excluded.raw_metadata_json,
            scraped_at = CURRENT_TIMESTAMP
        """,
        (
            source["uuid"],
            source.get("source_code"),
            source["dataset_url"],
            source["title"],
            source.get("description"),
            source.get("organisation_name"),
            source.get("licence_name"),
            source.get("created_at_source"),
            source.get("updated_at_source"),
            _json(source.get("tags")),
            _json(source.get("categories")),
            _json(source.get("raw_metadata")),
        ),
    )
    row = connection.execute(
        "SELECT id FROM dataset_sources WHERE uuid = ?",
        (source["uuid"],),
    ).fetchone()
    if row is None:
        raise RuntimeError("Dataset source upsert did not return a row")
    return int(row["id"])


def upsert_csv_file(
    connection: sqlite3.Connection,
    dataset_source_id: int,
    csv_file: dict[str, Any],
) -> int:
    connection.execute(
        """
        INSERT INTO dataset_csv_files (
            dataset_source_id,
            resource_uuid,
            resource_code,
            title,
            description,
            csv_url,
            local_path,
            file_name,
            file_size_bytes,
            source_file_size_bytes,
            content_hash,
            format,
            status,
            error_message,
            downloaded_at,
            raw_metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_source_id, csv_url) DO UPDATE SET
            resource_uuid = excluded.resource_uuid,
            resource_code = excluded.resource_code,
            title = excluded.title,
            description = excluded.description,
            file_name = excluded.file_name,
            source_file_size_bytes = excluded.source_file_size_bytes,
            content_hash = excluded.content_hash,
            format = excluded.format,
            raw_metadata_json = excluded.raw_metadata_json
        """,
        (
            dataset_source_id,
            csv_file.get("resource_uuid"),
            csv_file.get("resource_code"),
            csv_file["title"],
            csv_file.get("description"),
            csv_file["csv_url"],
            csv_file.get("local_path"),
            csv_file.get("file_name"),
            csv_file.get("file_size_bytes"),
            csv_file.get("source_file_size_bytes"),
            csv_file.get("content_hash"),
            csv_file.get("format", "csv"),
            csv_file.get("status", 0),
            csv_file.get("error_message"),
            csv_file.get("downloaded_at"),
            _json(csv_file.get("raw_metadata")),
        ),
    )
    row = connection.execute(
        """
        SELECT id
        FROM dataset_csv_files
        WHERE dataset_source_id = ? AND csv_url = ?
        """,
        (dataset_source_id, csv_file["csv_url"]),
    ).fetchone()
    if row is None:
        raise RuntimeError("CSV file upsert did not return a row")
    return int(row["id"])


def update_csv_file_status(
    connection: sqlite3.Connection,
    csv_file_id: int,
    *,
    status: int,
    local_path: str | None = None,
    file_size_bytes: int | None = None,
    error_message: str | None = None,
    downloaded_at: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE dataset_csv_files
        SET status = ?,
            local_path = COALESCE(?, local_path),
            file_size_bytes = COALESCE(?, file_size_bytes),
            error_message = ?,
            downloaded_at = COALESCE(?, downloaded_at)
        WHERE id = ?
        """,
        (
            status,
            local_path,
            file_size_bytes,
            error_message,
            downloaded_at,
            csv_file_id,
        ),
    )


def create_sync_run(connection: sqlite3.Connection, *, mode: str) -> int:
    cursor = connection.execute(
        "INSERT INTO sync_runs (mode) VALUES (?)",
        (mode,),
    )
    return int(cursor.lastrowid)


def finish_sync_run(
    connection: sqlite3.Connection,
    sync_run_id: int,
    *,
    status: str,
    pages_scanned: int,
    datasets_seen: int,
    sources_upserted: int,
    csv_files_seen: int,
    csv_files_downloaded: int,
    errors_count: int,
    message: str | None,
) -> None:
    connection.execute(
        """
        UPDATE sync_runs
        SET status = ?,
            finished_at = CURRENT_TIMESTAMP,
            pages_scanned = ?,
            datasets_seen = ?,
            sources_upserted = ?,
            csv_files_seen = ?,
            csv_files_downloaded = ?,
            errors_count = ?,
            message = ?
        WHERE id = ?
        """,
        (
            status,
            pages_scanned,
            datasets_seen,
            sources_upserted,
            csv_files_seen,
            csv_files_downloaded,
            errors_count,
            message,
            sync_run_id,
        ),
    )


def get_stats() -> dict[str, Any]:
    with connect() as connection:
        counts = connection.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM dataset_sources) AS sources_count,
                (SELECT COUNT(*) FROM dataset_csv_files) AS csv_files_count,
                (SELECT COUNT(*) FROM dataset_csv_files WHERE status = 0) AS pending_count,
                (SELECT COUNT(*) FROM dataset_csv_files WHERE status = 1) AS success_count,
                (SELECT COUNT(*) FROM dataset_csv_files WHERE status = -1) AS error_count
            """
        ).fetchone()
        last_sync = connection.execute(
            """
            SELECT *
            FROM sync_runs
            ORDER BY started_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    data = dict(counts) if counts else {}
    data["last_sync"] = row_to_dict(last_sync)
    return data


def list_sources(
    *,
    page: int,
    page_size: int,
    search: str | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    where = ""
    params: list[Any] = []
    if search:
        where = "WHERE ds.title LIKE ? OR ds.organisation_name LIKE ? OR ds.source_code LIKE ?"
        term = f"%{search}%"
        params.extend([term, term, term])

    with connect() as connection:
        total = connection.execute(
            f"SELECT COUNT(*) AS total FROM dataset_sources ds {where}",
            params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT
                ds.*,
                COUNT(cf.id) AS csv_count,
                COALESCE(SUM(CASE WHEN cf.status = 0 THEN 1 ELSE 0 END), 0) AS pending_count,
                COALESCE(SUM(CASE WHEN cf.status = 1 THEN 1 ELSE 0 END), 0) AS success_count,
                COALESCE(SUM(CASE WHEN cf.status = -1 THEN 1 ELSE 0 END), 0) AS error_count
            FROM dataset_sources ds
            LEFT JOIN dataset_csv_files cf ON cf.dataset_source_id = ds.id
            {where}
            GROUP BY ds.id
            ORDER BY
                COALESCE(ds.updated_at_source, ds.scraped_at) DESC,
                ds.title COLLATE NOCASE ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {
        "items": [row_to_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_source(source_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                ds.*,
                COUNT(cf.id) AS csv_count,
                COALESCE(SUM(CASE WHEN cf.status = 0 THEN 1 ELSE 0 END), 0) AS pending_count,
                COALESCE(SUM(CASE WHEN cf.status = 1 THEN 1 ELSE 0 END), 0) AS success_count,
                COALESCE(SUM(CASE WHEN cf.status = -1 THEN 1 ELSE 0 END), 0) AS error_count
            FROM dataset_sources ds
            LEFT JOIN dataset_csv_files cf ON cf.dataset_source_id = ds.id
            WHERE ds.id = ?
            GROUP BY ds.id
            """,
            (source_id,),
        ).fetchone()
    return row_to_dict(row)


def list_csv_files(
    *,
    source_id: int,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    with connect() as connection:
        total = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM dataset_csv_files
            WHERE dataset_source_id = ?
            """,
            (source_id,),
        ).fetchone()["total"]
        rows = connection.execute(
            """
            SELECT *
            FROM dataset_csv_files
            WHERE dataset_source_id = ?
            ORDER BY title COLLATE NOCASE ASC, id ASC
            LIMIT ? OFFSET ?
            """,
            (source_id, page_size, offset),
        ).fetchall()
    return {
        "items": [row_to_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_csv_file(csv_file_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                cf.*,
                ds.title AS source_title,
                ds.id AS source_id,
                ds.dataset_url AS source_url
            FROM dataset_csv_files cf
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE cf.id = ?
            """,
            (csv_file_id,),
        ).fetchone()
    return row_to_dict(row)


def list_csv_file_ids_for_download(
    *,
    retry_errors: bool = True,
    limit: int | None = None,
) -> list[int]:
    where = "status != 1" if retry_errors else "status = 0"
    params: list[Any] = []
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT id
            FROM dataset_csv_files
            WHERE {where}
            ORDER BY id ASC
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [int(row["id"]) for row in rows]


def list_csv_file_ids_for_transformation_planning(
    *,
    retry_errors: bool = False,
    minimum_rule_schema_version: int | None = None,
    limit: int | None = None,
) -> list[int]:
    params: list[Any] = []
    outdated_clause = ""
    if minimum_rule_schema_version is not None:
        outdated_clause = "OR COALESCE(tp.rule_schema_version, 1) < ?"
        params.append(minimum_rule_schema_version)
    if retry_errors:
        where = """
            cf.status = 1
            AND cf.local_path IS NOT NULL
            AND (
                tp.id IS NULL
                OR tp.status != 'success'
                OR (
                    cf.content_hash IS NOT NULL
                    AND COALESCE(tp.csv_content_hash, '') != cf.content_hash
                )
                {outdated_clause}
            )
        """
    else:
        where = """
            cf.status = 1
            AND cf.local_path IS NOT NULL
            AND (
                tp.id IS NULL
                OR (
                    cf.content_hash IS NOT NULL
                    AND COALESCE(tp.csv_content_hash, '') != cf.content_hash
                )
                {outdated_clause}
            )
        """
    where = where.format(outdated_clause=outdated_clause)
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT cf.id
            FROM dataset_csv_files cf
            LEFT JOIN csv_transformation_plans tp ON tp.csv_file_id = cf.id
            WHERE {where}
            ORDER BY cf.id ASC
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [int(row["id"]) for row in rows]


def get_csv_file_with_source(csv_file_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                cf.*,
                ds.title AS source_title,
                ds.description AS source_description,
                ds.organisation_name AS source_organisation_name,
                ds.dataset_url AS source_url,
                ds.tags_json AS source_tags_json,
                ds.categories_json AS source_categories_json
            FROM dataset_csv_files cf
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE cf.id = ?
            """,
            (csv_file_id,),
        ).fetchone()
    return row_to_dict(row)


def upsert_csv_transformation_plan(
    connection: sqlite3.Connection,
    *,
    csv_file_id: int,
    plan: dict[str, Any],
) -> int:
    connection.execute(
        "DELETE FROM csv_row_transformations WHERE csv_file_id = ?",
        (csv_file_id,),
    )
    connection.execute(
        """
        INSERT INTO csv_transformation_plans (
            csv_file_id,
            status,
            attempts,
            rule_schema_version,
            csv_content_hash,
            model,
            llm_endpoint,
            header_json,
            sample_rows_json,
            prompt_messages_json,
            response_json,
            date_range_status,
            date_range_rule_json,
            borough_status,
            borough_rule_json,
            transformation_summary,
            error_message,
            planned_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(csv_file_id) DO UPDATE SET
            status = excluded.status,
            attempts = excluded.attempts,
            rule_schema_version = excluded.rule_schema_version,
            csv_content_hash = excluded.csv_content_hash,
            model = excluded.model,
            llm_endpoint = excluded.llm_endpoint,
            header_json = excluded.header_json,
            sample_rows_json = excluded.sample_rows_json,
            prompt_messages_json = excluded.prompt_messages_json,
            response_json = excluded.response_json,
            date_range_status = excluded.date_range_status,
            date_range_rule_json = excluded.date_range_rule_json,
            borough_status = excluded.borough_status,
            borough_rule_json = excluded.borough_rule_json,
            transformation_summary = excluded.transformation_summary,
            error_message = excluded.error_message,
            planned_at = CURRENT_TIMESTAMP
        """,
        (
            csv_file_id,
            plan["status"],
            plan.get("attempts", 0),
            plan.get("rule_schema_version", 1),
            plan.get("csv_content_hash"),
            plan.get("model"),
            plan.get("llm_endpoint"),
            _json(plan.get("header")),
            _json(plan.get("sample_rows")),
            _json(plan.get("prompt_messages")),
            _json(plan.get("response")) if plan.get("response") is not None else None,
            plan.get("date_range_status"),
            _json(plan.get("date_range_rule")),
            plan.get("borough_status"),
            _json(plan.get("borough_rule")),
            plan.get("transformation_summary"),
            plan.get("error_message"),
        ),
    )
    row = connection.execute(
        """
        SELECT id
        FROM csv_transformation_plans
        WHERE csv_file_id = ?
        """,
        (csv_file_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError("CSV transformation plan upsert did not return a row")
    return int(row["id"])


def get_csv_transformation_plan(csv_file_id: int) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                tp.*,
                cf.content_hash AS csv_current_content_hash,
                CASE
                    WHEN cf.content_hash IS NOT NULL
                     AND COALESCE(tp.csv_content_hash, '') != cf.content_hash THEN 1
                    ELSE 0
                END AS csv_content_changed,
                COALESCE(row_counts.row_total_count, 0) AS row_total_count,
                COALESCE(row_counts.row_success_count, 0) AS row_success_count,
                COALESCE(row_counts.row_partial_count, 0) AS row_partial_count,
                COALESCE(row_counts.row_error_count, 0) AS row_error_count
            FROM csv_transformation_plans tp
            JOIN dataset_csv_files cf ON cf.id = tp.csv_file_id
            LEFT JOIN (
                SELECT
                    csv_file_id,
                    COUNT(*) AS row_total_count,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS row_success_count,
                    SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) AS row_partial_count,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS row_error_count
                FROM csv_row_transformations
                GROUP BY csv_file_id
            ) row_counts ON row_counts.csv_file_id = tp.csv_file_id
            WHERE tp.csv_file_id = ?
            """,
            (csv_file_id,),
        ).fetchone()
    return _transformation_plan_dict(row) if row is not None else None


def _load_json_field(item: dict[str, Any], key: str, default: Any) -> None:
    value = item.get(key)
    if isinstance(value, str):
        try:
            item[key] = json.loads(value)
        except json.JSONDecodeError:
            item[key] = default
    elif value is None:
        item[key] = default


def _transformation_plan_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = row_to_dict(row)
    _load_json_field(item, "header_json", [])
    _load_json_field(item, "sample_rows_json", [])
    _load_json_field(item, "prompt_messages_json", [])
    _load_json_field(item, "response_json", None)
    _load_json_field(item, "date_range_rule_json", None)
    _load_json_field(item, "borough_rule_json", None)
    response = item.get("response_json")
    warnings = response.get("warnings") if isinstance(response, dict) else []
    item["warning_count"] = len(warnings) if isinstance(warnings, list) else 0
    return item


def list_csv_transformation_plans(
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    max_confidence: float | None = None,
    has_warnings: bool | None = None,
    csv_changed: bool | None = None,
    old_schema: bool | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    offset = (page - 1) * page_size
    filters: list[str] = []
    params: list[Any] = []
    if status:
        filters.append("tp.status = ?")
        params.append(status)
    if max_confidence is not None:
        filters.append(
            """
            (
                CAST(json_extract(tp.date_range_rule_json, '$.confidence') AS REAL) <= ?
                OR CAST(json_extract(tp.borough_rule_json, '$.confidence') AS REAL) <= ?
            )
            """
        )
        params.extend([max_confidence, max_confidence])
    if has_warnings is not None:
        comparator = ">" if has_warnings else "="
        filters.append(
            f"COALESCE(json_array_length(json_extract(tp.response_json, '$.warnings')), 0) {comparator} 0"
        )
    if csv_changed is not None:
        if csv_changed:
            filters.append(
                "cf.content_hash IS NOT NULL AND COALESCE(tp.csv_content_hash, '') != cf.content_hash"
            )
        else:
            filters.append(
                "cf.content_hash IS NULL OR tp.csv_content_hash = cf.content_hash"
            )
    if old_schema is not None:
        comparator = "<" if old_schema else ">="
        filters.append(f"COALESCE(tp.rule_schema_version, 1) {comparator} ?")
        params.append(RULE_SCHEMA_VERSION)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    with connect() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM csv_transformation_plans tp
            JOIN dataset_csv_files cf ON cf.id = tp.csv_file_id
            {where}
            """,
            params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT
                tp.*,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                cf.content_hash AS csv_current_content_hash,
                CASE
                    WHEN cf.content_hash IS NOT NULL
                     AND COALESCE(tp.csv_content_hash, '') != cf.content_hash THEN 1
                    ELSE 0
                END AS csv_content_changed,
                ds.title AS source_title,
                COALESCE(row_counts.row_total_count, 0) AS row_total_count,
                COALESCE(row_counts.row_success_count, 0) AS row_success_count,
                COALESCE(row_counts.row_partial_count, 0) AS row_partial_count,
                COALESCE(row_counts.row_error_count, 0) AS row_error_count
            FROM csv_transformation_plans tp
            JOIN dataset_csv_files cf ON cf.id = tp.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            LEFT JOIN (
                SELECT
                    csv_file_id,
                    COUNT(*) AS row_total_count,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS row_success_count,
                    SUM(CASE WHEN status = 'partial' THEN 1 ELSE 0 END) AS row_partial_count,
                    SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) AS row_error_count
                FROM csv_row_transformations
                GROUP BY csv_file_id
            ) row_counts ON row_counts.csv_file_id = tp.csv_file_id
            {where}
            ORDER BY tp.updated_at_local DESC, tp.id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {
        "items": [_transformation_plan_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def list_csv_file_ids_for_row_transformation(
    *,
    retry: bool = False,
    limit: int | None = None,
) -> list[int]:
    params: list[Any] = []
    if retry:
        where = """
            tp.status = 'success'
            AND COALESCE(tp.rule_schema_version, 1) >= ?
            AND (
                cf.content_hash IS NULL
                OR tp.csv_content_hash = cf.content_hash
            )
        """
        params.append(RULE_SCHEMA_VERSION)
    else:
        where = """
            (
                tp.status = 'success'
                AND COALESCE(tp.rule_schema_version, 1) >= ?
                AND (
                    cf.content_hash IS NULL
                    OR tp.csv_content_hash = cf.content_hash
                )
                AND NOT EXISTS (
                    SELECT 1
                    FROM csv_row_transformations rt
                    WHERE rt.csv_file_id = tp.csv_file_id
                )
            )
            OR (
                tp.status = 'success'
                AND COALESCE(tp.rule_schema_version, 1) >= ?
                AND (
                    cf.content_hash IS NULL
                    OR tp.csv_content_hash = cf.content_hash
                )
                AND EXISTS (
                    SELECT 1
                    FROM csv_row_transformations rt
                    WHERE rt.csv_file_id = tp.csv_file_id
                      AND rt.status = 'error'
                )
            )
        """
        params.extend([RULE_SCHEMA_VERSION, RULE_SCHEMA_VERSION])
    limit_clause = ""
    if limit is not None:
        limit_clause = "LIMIT ?"
        params.append(limit)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT tp.csv_file_id
            FROM csv_transformation_plans tp
            JOIN dataset_csv_files cf ON cf.id = tp.csv_file_id
            WHERE {where}
            ORDER BY tp.csv_file_id ASC
            {limit_clause}
            """,
            params,
        ).fetchall()
    return [int(row["csv_file_id"]) for row in rows]


def clear_csv_row_transformations(
    connection: sqlite3.Connection,
    *,
    csv_file_id: int,
) -> None:
    connection.execute(
        "DELETE FROM csv_row_transformations WHERE csv_file_id = ?",
        (csv_file_id,),
    )


def insert_csv_row_transformations(
    connection: sqlite3.Connection,
    *,
    rows: list[dict[str, Any]],
) -> None:
    connection.executemany(
        """
        INSERT INTO csv_row_transformations (
            csv_file_id,
            transformation_plan_id,
            row_number,
            source_row_hash,
            source_row_json,
            date_start,
            date_end,
            borough_name,
            date_status,
            borough_status,
            status,
            error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(csv_file_id, row_number) DO UPDATE SET
            transformation_plan_id = excluded.transformation_plan_id,
            source_row_hash = excluded.source_row_hash,
            source_row_json = excluded.source_row_json,
            date_start = excluded.date_start,
            date_end = excluded.date_end,
            borough_name = excluded.borough_name,
            date_status = excluded.date_status,
            borough_status = excluded.borough_status,
            status = excluded.status,
            error_message = excluded.error_message
        """,
        [
            (
                row["csv_file_id"],
                row["transformation_plan_id"],
                row["row_number"],
                row["source_row_hash"],
                _json(row["source_row"]),
                row.get("date_start"),
                row.get("date_end"),
                row.get("borough_name"),
                row["date_status"],
                row["borough_status"],
                row["status"],
                row.get("error_message"),
            )
            for row in rows
        ],
    )


def list_csv_row_transformations(
    *,
    csv_file_id: int,
    page: int,
    page_size: int,
    status: str | None = None,
    date_status: str | None = None,
    borough_status: str | None = None,
    borough_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    offset = (page - 1) * page_size
    where = "WHERE csv_file_id = ?"
    params: list[Any] = [csv_file_id]
    if status:
        where += " AND status = ?"
        params.append(status)
    if date_status:
        where += " AND date_status = ?"
        params.append(date_status)
    if borough_status:
        where += " AND borough_status = ?"
        params.append(borough_status)
    if borough_name:
        where += " AND borough_name = ?"
        params.append(_canonical_borough_filter(borough_name))
    if date_from:
        where += " AND date_end IS NOT NULL AND date_end >= ?"
        params.append(date_from)
    if date_to:
        where += " AND date_start IS NOT NULL AND date_start <= ?"
        params.append(date_to)

    with connect() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM csv_row_transformations
            {where}
            """,
            params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT *
            FROM csv_row_transformations
            {where}
            ORDER BY row_number ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {
        "items": [_row_transformation_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def _row_transformation_dict(row: sqlite3.Row) -> dict[str, Any]:
    item = row_to_dict(row)
    source_row = item.get("source_row_json")
    if isinstance(source_row, str):
        try:
            item["source_row_json"] = json.loads(source_row)
        except json.JSONDecodeError:
            item["source_row_json"] = {}
    elif source_row is None:
        item["source_row_json"] = {}
    return item


def _row_transformation_filters(
    *,
    status: str | None = None,
    date_status: str | None = None,
    borough_status: str | None = None,
    borough_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    csv_file_id: int | None = None,
) -> tuple[str, list[Any]]:
    filters: list[str] = []
    params: list[Any] = []
    if status:
        filters.append("rt.status = ?")
        params.append(status)
    if date_status:
        filters.append("rt.date_status = ?")
        params.append(date_status)
    if borough_status:
        filters.append("rt.borough_status = ?")
        params.append(borough_status)
    if borough_name:
        filters.append("rt.borough_name = ?")
        params.append(_canonical_borough_filter(borough_name))
    if date_from:
        filters.append("rt.date_end IS NOT NULL AND rt.date_end >= ?")
        params.append(date_from)
    if date_to:
        filters.append("rt.date_start IS NOT NULL AND rt.date_start <= ?")
        params.append(date_to)
    if csv_file_id is not None:
        filters.append("rt.csv_file_id = ?")
        params.append(csv_file_id)
    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    return where, params


def list_all_csv_row_transformations(
    *,
    page: int,
    page_size: int,
    status: str | None = None,
    date_status: str | None = None,
    borough_status: str | None = None,
    borough_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    csv_file_id: int | None = None,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    offset = (page - 1) * page_size
    where, params = _row_transformation_filters(
        status=status,
        date_status=date_status,
        borough_status=borough_status,
        borough_name=borough_name,
        date_from=date_from,
        date_to=date_to,
        csv_file_id=csv_file_id,
    )

    with connect() as connection:
        total = connection.execute(
            f"""
            SELECT COUNT(*) AS total
            FROM csv_row_transformations rt
            {where}
            """,
            params,
        ).fetchone()["total"]
        rows = connection.execute(
            f"""
            SELECT
                rt.*,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                ds.title AS source_title
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            {where}
            ORDER BY rt.updated_at_local DESC, rt.csv_file_id ASC, rt.row_number ASC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()
    return {
        "items": [_row_transformation_dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def export_csv_row_transformations(
    *,
    status: str | None = None,
    date_status: str | None = None,
    borough_status: str | None = None,
    borough_name: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    csv_file_id: int | None = None,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 50000)
    where, params = _row_transformation_filters(
        status=status,
        date_status=date_status,
        borough_status=borough_status,
        borough_name=borough_name,
        date_from=date_from,
        date_to=date_to,
        csv_file_id=csv_file_id,
    )
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                rt.*,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                ds.title AS source_title
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            {where}
            ORDER BY rt.csv_file_id ASC, rt.row_number ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [_row_transformation_dict(row) for row in rows]


def export_borough_mapping_errors(
    *,
    csv_file_ids: list[int] | None = None,
    limit: int = 10000,
) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 50000)
    where = "WHERE rt.borough_status != 'success'"
    params: list[Any] = []
    if csv_file_ids:
        placeholders = ", ".join("?" for _ in csv_file_ids)
        where += f" AND rt.csv_file_id IN ({placeholders})"
        params.extend(csv_file_ids)
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                rt.*,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                ds.title AS source_title,
                ds.id AS source_id
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            {where}
            ORDER BY rt.csv_file_id ASC, rt.row_number ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
        return [_row_transformation_dict(row) for row in rows]


def export_borough_mapping_error_summary(
    *,
    csv_file_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    where = "WHERE rt.borough_status != 'success'"
    params: list[Any] = []
    if csv_file_ids:
        placeholders = ", ".join("?" for _ in csv_file_ids)
        where += f" AND rt.csv_file_id IN ({placeholders})"
        params.extend(csv_file_ids)

    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT
                rt.csv_file_id AS csv_file_id,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                ds.id AS source_id,
                ds.title AS source_title,
                COUNT(rt.id) AS error_rows_count,
                SUM(CASE WHEN rt.borough_status = 'not_london_borough' THEN 1 ELSE 0 END) AS not_london_borough_count,
                SUM(CASE WHEN rt.borough_status = 'not_identifiable' THEN 1 ELSE 0 END) AS not_identifiable_count,
                SUM(CASE WHEN rt.borough_status = 'error' THEN 1 ELSE 0 END) AS error_count,
                SUM(CASE WHEN rt.borough_status = 'unsupported' THEN 1 ELSE 0 END) AS unsupported_count
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            {where}
            GROUP BY rt.csv_file_id, cf.title, cf.file_name, ds.id, ds.title
            ORDER BY rt.csv_file_id ASC
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def export_borough_coverage_summary(
    *,
    csv_file_ids: list[int] | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 20000)
    where = "WHERE rt.csv_file_id IS NOT NULL"
    params: list[Any] = []
    if csv_file_ids:
        placeholders = ", ".join("?" for _ in csv_file_ids)
        where += f" AND rt.csv_file_id IN ({placeholders})"
        params.extend(csv_file_ids)

    with connect() as connection:
        all_borough_rows = connection.execute(
            """
            SELECT borough_name
            FROM london_borough_boundaries
            ORDER BY borough_name ASC
            """
        ).fetchall()
        all_boroughs = [str(row["borough_name"]) for row in all_borough_rows]

        rows = connection.execute(
            f"""
            SELECT
                cf.id AS csv_file_id,
                cf.title AS csv_title,
                cf.file_name AS csv_file_name,
                ds.id AS source_id,
                ds.title AS source_title,
                COUNT(rt.id) AS row_total_count,
                SUM(CASE WHEN rt.borough_status = 'success' THEN 1 ELSE 0 END) AS row_success_count,
                SUM(CASE WHEN rt.borough_status = 'not_london_borough' THEN 1 ELSE 0 END) AS row_not_london_count,
                SUM(CASE WHEN rt.borough_status = 'not_identifiable' THEN 1 ELSE 0 END) AS row_not_identifiable_count,
                SUM(CASE WHEN rt.borough_status = 'error' THEN 1 ELSE 0 END) AS row_error_count,
                SUM(CASE WHEN rt.borough_status = 'unsupported' THEN 1 ELSE 0 END) AS row_unsupported_count,
                COUNT(DISTINCT CASE
                    WHEN rt.borough_status = 'success' AND rt.borough_name IS NOT NULL
                    THEN rt.borough_name
                    ELSE NULL
                END) AS mapped_borough_count,
                REPLACE(
                    GROUP_CONCAT(DISTINCT CASE
                    WHEN rt.borough_status = 'success' AND rt.borough_name IS NOT NULL
                    THEN rt.borough_name
                    ELSE NULL
                END),
                    ',',
                    '|'
                ) AS mapped_boroughs
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            {where}
            GROUP BY cf.id, cf.title, cf.file_name, ds.id, ds.title
            ORDER BY cf.id ASC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()

    result: list[dict[str, Any]] = []
    total_boroughs = len(all_boroughs)
    for row in rows:
        item = row_to_dict(row)
        mapped = item.get("mapped_boroughs")
        mapped_list = [] if not mapped else [entry for entry in str(mapped).split("|") if entry]
        mapped_list = sorted(set(mapped_list))
        item["mapped_boroughs"] = mapped_list
        item["missing_boroughs"] = [
            borough_name
            for borough_name in all_boroughs
            if borough_name not in mapped_list
        ]
        item["mapped_borough_count"] = int(item.get("mapped_borough_count") or 0)
        item["coverage_ratio"] = (
            float(item["mapped_borough_count"]) / float(total_boroughs)
            if total_boroughs else 0.0
        )
        item["total_london_boroughs"] = int(total_boroughs)
        item["missing_borough_count"] = len(item["missing_boroughs"])
        item["rows_not_mapped"] = int(item.get("row_total_count") or 0) - int(item.get("row_success_count") or 0)
        result.append(item)

    return result


def export_global_borough_coverage_summary() -> dict[str, Any]:
    with connect() as connection:
        all_borough_rows = connection.execute(
            """
            SELECT borough_name
            FROM london_borough_boundaries
            ORDER BY borough_name ASC
            """
        ).fetchall()
        all_boroughs = [str(row["borough_name"]) for row in all_borough_rows]

        summary = connection.execute(
            """
            SELECT
                COUNT(rt.id) AS row_total_count,
                SUM(CASE WHEN rt.borough_status = 'success' THEN 1 ELSE 0 END) AS row_success_count,
                SUM(CASE WHEN rt.borough_status = 'not_london_borough' THEN 1 ELSE 0 END) AS row_not_london_count,
                SUM(CASE WHEN rt.borough_status = 'not_identifiable' THEN 1 ELSE 0 END) AS row_not_identifiable_count,
                SUM(CASE WHEN rt.borough_status = 'error' THEN 1 ELSE 0 END) AS row_error_count,
                SUM(CASE WHEN rt.borough_status = 'unsupported' THEN 1 ELSE 0 END) AS row_unsupported_count,
                COUNT(DISTINCT CASE
                    WHEN rt.borough_status = 'success' AND rt.borough_name IS NOT NULL
                    THEN rt.borough_name
                    ELSE NULL
                END) AS mapped_borough_count,
                REPLACE(
                    GROUP_CONCAT(DISTINCT CASE
                    WHEN rt.borough_status = 'success' AND rt.borough_name IS NOT NULL
                    THEN rt.borough_name
                    ELSE NULL
                END),
                    ',',
                    '|'
                ) AS mapped_boroughs,
                COUNT(DISTINCT cf.id) AS transformed_file_count
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            """
        ).fetchone()

    total_boroughs = len(all_boroughs)
    mapped_list = []
    if summary and summary["mapped_boroughs"]:
        mapped_list = sorted(
            set(
                entry
                for entry in str(summary["mapped_boroughs"]).split("|")
                if entry
            )
        )
    missing_boroughs = [
        borough_name
        for borough_name in all_boroughs
        if borough_name not in mapped_list
    ]
    if summary is None:
        return {
            "row_total_count": 0,
            "row_success_count": 0,
            "row_not_london_count": 0,
            "row_not_identifiable_count": 0,
            "row_error_count": 0,
            "row_unsupported_count": 0,
            "mapped_borough_count": 0,
            "mapped_boroughs": [],
            "missing_borough_count": total_boroughs,
            "missing_boroughs": missing_boroughs,
            "total_london_boroughs": total_boroughs,
            "coverage_ratio": 0.0,
            "transformed_file_count": 0,
            "rows_not_mapped": 0,
        }

    item = row_to_dict(summary)
    item["mapped_boroughs"] = mapped_list
    item["missing_boroughs"] = missing_boroughs
    mapped_count = int(item.get("mapped_borough_count") or 0)
    item["mapped_borough_count"] = mapped_count
    item["total_london_boroughs"] = int(total_boroughs)
    item["missing_borough_count"] = len(missing_boroughs)
    item["coverage_ratio"] = (float(mapped_count) / float(total_boroughs)) if total_boroughs else 0.0
    item["rows_not_mapped"] = int(item.get("row_total_count") or 0) - int(item.get("row_success_count") or 0)
    return item


def list_borough_row_data(
    *,
    borough_name: str,
    rows_per_file: int = 10,
    max_files: int = 30,
) -> dict[str, Any]:
    canonical_borough_name = _canonical_borough_filter(borough_name)
    rows_per_file = min(max(rows_per_file, 1), 100)
    max_files = min(max(max_files, 1), 100)

    with connect() as connection:
        totals = connection.execute(
            """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT rt.csv_file_id) AS total_files,
                COUNT(DISTINCT ds.id) AS total_datasets
            FROM csv_row_transformations rt
            JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE rt.borough_name = ?
              AND rt.borough_status = 'success'
            """,
            (canonical_borough_name,),
        ).fetchone()
        rows = connection.execute(
            """
            WITH filtered AS (
                SELECT
                    rt.*,
                    cf.title AS csv_title,
                    cf.file_name AS csv_file_name,
                    ds.id AS source_id,
                    ds.title AS source_title
                FROM csv_row_transformations rt
                JOIN dataset_csv_files cf ON cf.id = rt.csv_file_id
                JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
                WHERE rt.borough_name = ?
                  AND rt.borough_status = 'success'
            ),
            selected_files AS (
                SELECT
                    source_id,
                    source_title,
                    csv_file_id,
                    csv_title,
                    csv_file_name,
                    COUNT(*) AS file_total_rows
                FROM filtered
                GROUP BY source_id, source_title, csv_file_id, csv_title, csv_file_name
                ORDER BY
                    COALESCE(source_title, '') ASC,
                    COALESCE(csv_title, csv_file_name, '') ASC,
                    csv_file_id ASC
                LIMIT ?
            ),
            ranked AS (
                SELECT
                    f.*,
                    sf.file_total_rows,
                    ROW_NUMBER() OVER (
                        PARTITION BY f.csv_file_id
                        ORDER BY
                            f.date_start IS NULL ASC,
                            f.date_start ASC,
                            f.row_number ASC
                    ) AS file_row_rank
                FROM filtered f
                JOIN selected_files sf ON sf.csv_file_id = f.csv_file_id
            )
            SELECT *
            FROM ranked
            WHERE file_row_rank <= ?
            ORDER BY
                COALESCE(source_title, '') ASC,
                COALESCE(csv_title, csv_file_name, '') ASC,
                csv_file_id ASC,
                file_row_rank ASC
            """,
            (canonical_borough_name, max_files, rows_per_file),
        ).fetchall()

    datasets_by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        item = _row_transformation_dict(row)
        source_id = int(item["source_id"])
        csv_file_id = int(item["csv_file_id"])
        dataset = datasets_by_id.setdefault(
            source_id,
            {
                "source_id": source_id,
                "source_title": item.get("source_title"),
                "files": [],
                "_files_by_id": {},
            },
        )
        files_by_id = dataset["_files_by_id"]
        file_item = files_by_id.get(csv_file_id)
        if file_item is None:
            file_item = {
                "csv_file_id": csv_file_id,
                "csv_title": item.get("csv_title"),
                "csv_file_name": item.get("csv_file_name"),
                "total_rows": item.get("file_total_rows", 0),
                "rows": [],
            }
            files_by_id[csv_file_id] = file_item
            dataset["files"].append(file_item)
        for transient_key in ("source_id", "file_total_rows", "file_row_rank"):
            item.pop(transient_key, None)
        file_item["rows"].append(item)

    datasets = []
    for dataset in datasets_by_id.values():
        dataset.pop("_files_by_id", None)
        datasets.append(dataset)

    return {
        "borough_name": canonical_borough_name,
        "rows_per_file": rows_per_file,
        "max_files": max_files,
        "total_rows": int(totals["total_rows"] or 0),
        "total_files": int(totals["total_files"] or 0),
        "total_datasets": int(totals["total_datasets"] or 0),
        "datasets": datasets,
    }


def csv_row_transformation_stats(csv_file_id: int) -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM csv_row_transformations
            WHERE csv_file_id = ?
            GROUP BY status
            ORDER BY status
            """,
            (csv_file_id,),
        ).fetchall()
    counts = {str(row["status"]): int(row["count"]) for row in rows}
    counts["total"] = sum(counts.values())
    return counts


def _normalise_borough_filter(value: str) -> str:
    normalised = value.lower().replace("&", " and ")
    normalised = re.sub(r"\bcity of westminster\b", "westminster", normalised)
    normalised = re.sub(r"\b(city of )?westminster city\b", "westminster", normalised)
    normalised = re.sub(r"\broyal borough of\b", " ", normalised)
    normalised = re.sub(r"\blondon borough of\b", " ", normalised)
    normalised = re.sub(r"\bborough of\b", " ", normalised)
    return re.sub(r"[^a-z0-9]+", " ", normalised).strip()


def _canonical_borough_filter(value: str) -> str:
    normalised_value = _normalise_borough_filter(value)
    aliases = {
        "city": "City of London",
        "city of london": "City of London",
        "westminster city": "Westminster",
        "kensington chelsea": "Kensington and Chelsea",
        "richmond": "Richmond upon Thames",
        "kingston": "Kingston upon Thames",
        "barking": "Barking and Dagenham",
        "barking dagenham": "Barking and Dagenham",
    }
    if normalised_value in aliases:
        return aliases[normalised_value]

    with connect() as connection:
        rows = connection.execute(
            """
            SELECT borough_name, borough_code
            FROM london_borough_boundaries
            """
        ).fetchall()
    for row in rows:
        borough_name = str(row["borough_name"])
        if normalised_value == _normalise_borough_filter(borough_name):
            return borough_name
        borough_code = row["borough_code"]
        if borough_code and normalised_value == _normalise_borough_filter(str(borough_code)):
            return borough_name
    return value.strip()


def transformation_overview_stats() -> dict[str, Any]:
    with connect() as connection:
        downloaded_csv_files = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM dataset_csv_files
            WHERE status = 1 AND local_path IS NOT NULL
            """
        ).fetchone()["count"]
        plan_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM csv_transformation_plans
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        row_status_rows = connection.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM csv_row_transformations
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        row_files = connection.execute(
            "SELECT COUNT(DISTINCT csv_file_id) AS count FROM csv_row_transformations"
        ).fetchone()["count"]
        pending_plans = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM dataset_csv_files cf
            LEFT JOIN csv_transformation_plans tp ON tp.csv_file_id = cf.id
            WHERE cf.status = 1
              AND cf.local_path IS NOT NULL
              AND (
                tp.id IS NULL
                OR (
                    cf.content_hash IS NOT NULL
                    AND COALESCE(tp.csv_content_hash, '') != cf.content_hash
                )
              )
            """
        ).fetchone()["count"]
        outdated_successful_plans = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM csv_transformation_plans
            WHERE status = 'success'
              AND COALESCE(rule_schema_version, 1) < ?
            """,
            (RULE_SCHEMA_VERSION,),
        ).fetchone()["count"]
        pending_row_applications = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM csv_transformation_plans tp
            JOIN dataset_csv_files cf ON cf.id = tp.csv_file_id
            WHERE tp.status = 'success'
              AND COALESCE(tp.rule_schema_version, 1) >= ?
              AND (
                cf.content_hash IS NULL
                OR tp.csv_content_hash = cf.content_hash
              )
              AND NOT EXISTS (
                SELECT 1
                FROM csv_row_transformations rt
                WHERE rt.csv_file_id = tp.csv_file_id
              )
            """
            ,
            (RULE_SCHEMA_VERSION,),
        ).fetchone()["count"]

    plan_status = {str(row["status"]): int(row["count"]) for row in plan_rows}
    row_status = {str(row["status"]): int(row["count"]) for row in row_status_rows}
    return {
        "current_rule_schema_version": RULE_SCHEMA_VERSION,
        "downloaded_csv_files": int(downloaded_csv_files),
        "planned_csv_files": sum(plan_status.values()),
        "plan_status": plan_status,
        "row_transformed_csv_files": int(row_files),
        "row_status": row_status,
        "row_transformations": sum(row_status.values()),
        "pending_plans": int(pending_plans),
        "outdated_successful_plans": int(outdated_successful_plans),
        "pending_row_applications": int(pending_row_applications),
    }


def upsert_london_borough_boundary(
    connection: sqlite3.Connection,
    borough: dict[str, Any],
) -> int:
    connection.execute(
        """
        INSERT INTO london_borough_boundaries (
            borough_name,
            borough_code,
            source_url,
            source_file_name,
            coordinate_system,
            geometry_type,
            border_coordinates_json,
            source_file_hash
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(borough_name) DO UPDATE SET
            borough_code = excluded.borough_code,
            source_url = excluded.source_url,
            source_file_name = excluded.source_file_name,
            coordinate_system = excluded.coordinate_system,
            geometry_type = excluded.geometry_type,
            border_coordinates_json = excluded.border_coordinates_json,
            source_file_hash = excluded.source_file_hash
        """,
        (
            borough["borough_name"],
            borough.get("borough_code"),
            borough.get("source_url"),
            borough.get("source_file_name"),
            borough.get("coordinate_system"),
            borough.get("geometry_type"),
            _json(borough.get("borders")),
            borough.get("source_file_hash"),
        ),
    )
    row = connection.execute(
        """
        SELECT id
        FROM london_borough_boundaries
        WHERE borough_name = ?
        """,
        (borough["borough_name"],),
    ).fetchone()
    if row is None:
        raise RuntimeError("London borough boundary upsert did not return a row")
    return int(row["id"])


def clear_london_borough_boundaries(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM london_borough_boundaries")


def list_london_borough_boundaries() -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                borough_name,
                borough_code,
                source_url,
                source_file_name,
                coordinate_system,
                geometry_type,
                border_coordinates_json,
                source_file_hash,
                ingested_at,
                updated_at_local
            FROM london_borough_boundaries
            ORDER BY borough_name
            """,
        ).fetchall()
    return {
        "items": [row_to_dict(row) for row in rows],
        "total": len(rows),
    }


def list_london_boroughs() -> dict[str, Any]:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT
                borough_name,
                borough_code
            FROM london_borough_boundaries
            ORDER BY borough_name
            """,
        ).fetchall()
    return {
        "items": [row_to_dict(row) for row in rows],
        "total": len(rows),
    }

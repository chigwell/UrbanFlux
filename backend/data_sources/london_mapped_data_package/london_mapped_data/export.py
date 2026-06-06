from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .themes import THEME_CASE_SQL, THEMES


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PACKAGE_ROOT / "data" / "london_mapped_compact.sqlite3"
SCHEMA_VERSION = "1"


def slugify(value: str) -> str:
    cleaned = []
    for char in value.lower():
        cleaned.append(char if char.isalnum() else "-")
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or "unknown"


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def build_compact_db(source: Path, out: Path) -> None:
    source = source.resolve()
    out = out.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Source DB not found: {source}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    conn = sqlite3.connect(out)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")
        conn.execute("PRAGMA temp_store = MEMORY")
        conn.execute("ATTACH DATABASE ? AS src", (str(source),))

        conn.execute(
            """
            CREATE TABLE manifest (
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE london_borough_boundaries AS
            SELECT
              id,
              borough_name,
              borough_code,
              coordinate_system,
              geometry_type,
              border_coordinates_json
            FROM src.london_borough_boundaries
            """
        )
        conn.execute(
            f"""
            CREATE TEMP TABLE usable_files AS
            SELECT
              cf.id AS csv_file_id,
              {THEME_CASE_SQL} AS theme
            FROM src.csv_transformation_plans p
            JOIN src.dataset_csv_files cf ON cf.id = p.csv_file_id
            JOIN src.dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE p.status = 'success'
              AND p.borough_status IN ('row_rule', 'file_constant')
            """
        )
        conn.execute(
            """
            CREATE TABLE dataset_sources AS
            SELECT DISTINCT
              ds.id,
              ds.uuid,
              ds.source_code,
              ds.dataset_url,
              ds.title,
              ds.description,
              ds.organisation_name,
              ds.licence_name,
              ds.created_at_source,
              ds.updated_at_source,
              ds.tags_json,
              ds.categories_json
            FROM src.dataset_sources ds
            JOIN src.dataset_csv_files cf ON cf.dataset_source_id = ds.id
            JOIN usable_files uf ON uf.csv_file_id = cf.id
            """
        )
        conn.execute(
            """
            CREATE TABLE dataset_csv_files AS
            SELECT
              cf.id,
              cf.dataset_source_id,
              cf.resource_uuid,
              cf.resource_code,
              cf.title,
              cf.description,
              cf.csv_url,
              NULL AS local_path,
              cf.file_name,
              cf.file_size_bytes,
              cf.source_file_size_bytes,
              cf.content_hash,
              cf.format,
              cf.status,
              uf.theme
            FROM src.dataset_csv_files cf
            JOIN usable_files uf ON uf.csv_file_id = cf.id
            """
        )
        conn.execute(
            """
            CREATE TABLE csv_transformation_plans AS
            SELECT
              p.id,
              p.csv_file_id,
              p.status,
              p.model,
              p.llm_endpoint,
              p.date_range_status,
              p.borough_status,
              p.transformation_summary,
              p.planned_at,
              p.rule_schema_version,
              p.csv_content_hash
            FROM src.csv_transformation_plans p
            JOIN usable_files uf ON uf.csv_file_id = p.csv_file_id
            WHERE p.status = 'success'
              AND p.borough_status IN ('row_rule', 'file_constant')
            """
        )
        conn.execute(
            """
            CREATE TABLE csv_row_transformations AS
            SELECT
              r.id,
              r.csv_file_id,
              r.transformation_plan_id,
              r.row_number,
              r.source_row_hash,
              r.source_row_json,
              r.date_start,
              r.date_end,
              r.borough_name,
              r.date_status,
              r.borough_status,
              r.status,
              r.error_message
            FROM src.csv_row_transformations r
            JOIN usable_files uf ON uf.csv_file_id = r.csv_file_id
            WHERE r.borough_name IS NOT NULL
              AND trim(r.borough_name) != ''
              AND r.status IN ('success', 'partial')
            """
        )

        conn.execute("CREATE INDEX idx_boundaries_borough_name ON london_borough_boundaries (borough_name)")
        conn.execute("CREATE INDEX idx_files_theme_id ON dataset_csv_files (theme, id)")
        conn.execute("CREATE INDEX idx_files_source ON dataset_csv_files (dataset_source_id)")
        conn.execute("CREATE INDEX idx_plans_file_status_borough ON csv_transformation_plans (csv_file_id, status, borough_status)")
        conn.execute("CREATE INDEX idx_rows_borough_status_file_id ON csv_row_transformations (borough_name, status, csv_file_id, id)")
        conn.execute("CREATE INDEX idx_rows_csv_file_id ON csv_row_transformations (csv_file_id)")

        stats = {
            "schema_version": SCHEMA_VERSION,
            "source_db_path": "sanitized-public-export",
            "exported_at_utc": datetime.now(timezone.utc).isoformat(),
            "borough_count": conn.execute("SELECT COUNT(*) FROM london_borough_boundaries").fetchone()[0],
            "usable_csv_file_count": conn.execute("SELECT COUNT(*) FROM dataset_csv_files").fetchone()[0],
            "mapped_row_count": conn.execute("SELECT COUNT(*) FROM csv_row_transformations").fetchone()[0],
        }
        conn.executemany(
            "INSERT INTO manifest (key, value) VALUES (?, ?)",
            [(key, str(value)) for key, value in stats.items()],
        )
        conn.commit()
        conn.execute("ANALYZE")
    finally:
        conn.close()


def zip_bundle(db: Path, out: Path) -> None:
    db = db.resolve()
    out = out.resolve()
    if not db.exists():
        raise FileNotFoundError(f"Compact DB not found: {db}")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in [
            PACKAGE_ROOT / "pyproject.toml",
            PACKAGE_ROOT / "README.md",
            PACKAGE_ROOT / "scripts" / "build_bundle.py",
        ]:
            if path.exists():
                archive.write(path, path.relative_to(PACKAGE_ROOT.parent))
        for path in (PACKAGE_ROOT / "london_mapped_data").glob("*.py"):
            archive.write(path, path.relative_to(PACKAGE_ROOT.parent))
        archive.write(db, PACKAGE_ROOT.relative_to(PACKAGE_ROOT.parent) / "data" / "london_mapped_compact.sqlite3")


def export_csv(db: Path, out: Path) -> None:
    db = db.resolve()
    out = out.resolve()
    if not db.exists():
        raise FileNotFoundError(f"Compact DB not found: {db}")
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    query = """
    SELECT
      r.id,
      r.csv_file_id,
      r.row_number,
      cf.theme,
      r.date_start,
      r.date_end,
      r.borough_name,
      r.date_status,
      r.borough_status,
      r.status AS row_status,
      r.error_message,
      ds.id AS source_id,
      ds.title AS dataset_title,
      ds.dataset_url,
      ds.organisation_name,
      cf.id AS source_file_id,
      cf.title AS resource_title,
      cf.csv_url,
      r.source_row_json
    FROM csv_row_transformations r
    JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
    JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
    WHERE r.borough_name = :borough_name
      AND cf.theme = :theme
    ORDER BY r.id
    """

    with connect(db) as conn:
        pairs = conn.execute(
            """
            SELECT DISTINCT r.borough_name, cf.theme
            FROM csv_row_transformations r
            JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
            ORDER BY r.borough_name, cf.theme
            """
        ).fetchall()
        for pair in pairs:
            borough = pair["borough_name"]
            theme = pair["theme"]
            borough_dir = out / slugify(borough)
            borough_dir.mkdir(parents=True, exist_ok=True)
            csv_path = borough_dir / f"{slugify(theme)}.csv"
            rows = conn.execute(query, {"borough_name": borough, "theme": theme})
            first = rows.fetchone()
            if first is None:
                continue
            with csv_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=first.keys())
                writer.writeheader()
                writer.writerow(dict(first))
                for row in rows:
                    writer.writerow(dict(row))

    manifest = {"source_db": str(db), "exported_at_utc": datetime.now(timezone.utc).isoformat()}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and export the London mapped data bundle.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-db", help="Build compact SQLite DB from source datastore.")
    build_parser.add_argument("--source", required=True, type=Path)
    build_parser.add_argument("--out", default=DEFAULT_DB, type=Path)

    zip_parser = subparsers.add_parser("zip", help="Create deployable package zip.")
    zip_parser.add_argument("--db", default=DEFAULT_DB, type=Path)
    zip_parser.add_argument("--out", required=True, type=Path)

    csv_parser = subparsers.add_parser("csv", help="Export compact DB to borough/theme CSV files.")
    csv_parser.add_argument("--db", default=DEFAULT_DB, type=Path)
    csv_parser.add_argument("--out", required=True, type=Path)

    args = parser.parse_args()
    if args.command == "build-db":
        build_compact_db(args.source, args.out)
        print(f"Built compact DB: {args.out}")
    elif args.command == "zip":
        zip_bundle(args.db, args.out)
        print(f"Built bundle zip: {args.out}")
    elif args.command == "csv":
        export_csv(args.db, args.out)
        print(f"Exported CSV data: {args.out}")


if __name__ == "__main__":
    main()

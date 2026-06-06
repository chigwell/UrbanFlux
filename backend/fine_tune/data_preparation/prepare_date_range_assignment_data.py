from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - requirements install provides tqdm.
    def tqdm(iterable=None, *args, **kwargs):
        return iterable if iterable is not None else _FallbackProgress(*args, **kwargs)

    class _FallbackProgress:
        def __init__(self, total=None, **_kwargs):
            self.total = total

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, amount=1):
            return None

        def set_postfix(self, **_kwargs):
            return None


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().with_name("urbanflux_date_range_training.jsonl")

try:
    from .prepare_borough_assignment_data import (  # type: ignore[import-not-found]
        csv_headers,
        get_data_db_path,
        metadata_description,
        parse_source_row,
    )
except ImportError:  # pragma: no cover - used when running this file directly.
    from prepare_borough_assignment_data import (  # type: ignore[no-redef]
        csv_headers,
        get_data_db_path,
        metadata_description,
        parse_source_row,
    )


def connect_data_db(db_path: Path | None = None) -> sqlite3.Connection:
    resolved_path = (db_path or get_data_db_path()).resolve()
    conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "csv_file_id": row["csv_file_id"],
        "row_number": row["row_number"],
        "borough_name": row["borough_name"],
        "theme": row["theme"],
        "date_start": row["date_start"],
        "date_end": row["date_end"],
        "source": {
            "dataset_title": row["dataset_title"],
            "dataset_description": row["dataset_description"],
            "dataset_url": row["dataset_url"],
            "organisation_name": row["organisation_name"],
            "resource_title": row["resource_title"],
            "resource_description": row["resource_description"],
            "csv_url": row["csv_url"],
        },
        "source_row": parse_source_row(row["source_row_json"]),
    }


def fetch_borough_theme_pairs(
    conn: sqlite3.Connection,
    borough: str | None = None,
    theme: str | None = None,
    success_only: bool = False,
) -> list[tuple[str, str]]:
    statuses = "r.status = 'success'" if success_only else "r.status IN ('success', 'partial')"
    filters = [
        "r.borough_name IS NOT NULL",
        "r.borough_name != ''",
        "cf.theme IS NOT NULL",
        "r.date_start IS NOT NULL",
        "r.date_start != ''",
        "r.date_end IS NOT NULL",
        "r.date_end != ''",
        statuses,
    ]
    params: dict[str, Any] = {}
    if borough:
        filters.append("r.borough_name = :borough")
        params["borough"] = borough
    if theme:
        filters.append("cf.theme = :theme")
        params["theme"] = theme

    sql = f"""
        SELECT DISTINCT r.borough_name, cf.theme
        FROM csv_row_transformations r
        JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
        WHERE {" AND ".join(filters)}
        ORDER BY r.borough_name, cf.theme
    """
    rows = conn.execute(sql, params).fetchall()
    return [(row["borough_name"], row["theme"]) for row in rows]


def fetch_rows_for_pair(
    conn: sqlite3.Connection,
    borough_name: str,
    theme: str,
    limit: int,
    success_only: bool = False,
) -> list[dict[str, Any]]:
    status_clause = "r.status = 'success'" if success_only else "r.status IN ('success', 'partial')"
    sql = f"""
        SELECT
            r.id,
            r.csv_file_id,
            r.row_number,
            r.borough_name,
            r.date_start,
            r.date_end,
            r.source_row_json,
            cf.theme,
            ds.title AS dataset_title,
            ds.description AS dataset_description,
            ds.dataset_url,
            ds.organisation_name,
            cf.title AS resource_title,
            cf.description AS resource_description,
            cf.csv_url
        FROM csv_row_transformations r
        JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
        JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
        WHERE r.borough_name = :borough_name
          AND cf.theme = :theme
          AND r.date_start IS NOT NULL
          AND r.date_start != ''
          AND r.date_end IS NOT NULL
          AND r.date_end != ''
          AND {status_clause}
        ORDER BY
            COALESCE(r.date_end, r.date_start, '') DESC,
            COALESCE(r.date_start, '') DESC,
            r.row_number DESC,
            r.id DESC
        LIMIT :limit
    """
    rows = conn.execute(
        sql,
        {"borough_name": borough_name, "theme": theme, "limit": limit},
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def fetch_training_rows(
    conn: sqlite3.Connection,
    max_rows_per_borough_theme: int,
    borough: str | None = None,
    theme: str | None = None,
    success_only: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for borough_name, theme_name in fetch_borough_theme_pairs(
        conn,
        borough=borough,
        theme=theme,
        success_only=success_only,
    ):
        rows.extend(
            fetch_rows_for_pair(
                conn,
                borough_name=borough_name,
                theme=theme_name,
                limit=max_rows_per_borough_theme,
                success_only=success_only,
            )
        )
    return rows


def build_user_prompt(row: dict[str, Any]) -> str:
    source = row.get("source") or {}
    source_row = row.get("source_row")
    prompt = {
        "task": "Identify the date range represented by this CSV row. Return only the date range.",
        "source_metadata": metadata_description(source),
        "csv_headers": csv_headers(source_row),
        "csv_row": source_row,
    }
    return json.dumps(prompt, ensure_ascii=False, sort_keys=True)


def build_assistant_answer(row: dict[str, Any]) -> str:
    answer = {
        "date_start": row.get("date_start"),
        "date_end": row.get("date_end"),
    }
    return json.dumps(answer, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def output_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "content": build_user_prompt(row)},
            {"role": "assistant", "content": build_assistant_answer(row)},
        ]
    }


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_jsonl(output_path: Path, rows: list[dict[str, Any]], overwrite: bool) -> None:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output already exists. Use --overwrite to replace it: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite and output_path.exists():
        output_path.unlink()

    with tqdm(total=len(rows), unit="row") as progress:
        for row in rows:
            append_jsonl(output_path, output_record(row))
            progress.update(1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare no-LLM UrbanFlux date-range fine-tune JSONL data."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-rows-per-borough-theme", type=int, default=100)
    parser.add_argument("--borough")
    parser.add_argument("--theme")
    parser.add_argument("--success-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.max_rows_per_borough_theme < 1:
        raise ValueError("--max-rows-per-borough-theme must be at least 1")


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    args.output = args.output.resolve()

    with connect_data_db() as conn:
        rows = fetch_training_rows(
            conn,
            max_rows_per_borough_theme=args.max_rows_per_borough_theme,
            borough=args.borough,
            theme=args.theme,
            success_only=args.success_only,
        )

    if args.dry_run:
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "output": str(args.output),
                    "max_rows_per_borough_theme": args.max_rows_per_borough_theme,
                    "borough": args.borough,
                    "theme": args.theme,
                    "success_only": args.success_only,
                },
                indent=2,
            )
        )
        return 0

    write_jsonl(args.output, rows, overwrite=args.overwrite)
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())

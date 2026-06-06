from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - requirements install provides tqdm.
    def tqdm(iterable=None, *args, **kwargs):
        class _FallbackProgress:
            def __init__(self, total=None, initial=0, **_kwargs):
                self.total = total
                self.n = initial

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def update(self, amount=1):
                self.n += amount

            def set_postfix(self, **_kwargs):
                return None

        if iterable is not None:
            return iterable
        return _FallbackProgress(*args, **kwargs)


BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_OUTPUT_PATH = Path(__file__).resolve().with_name("urbanflux_replanning_training.jsonl")
DEFAULT_ERRORS_OUTPUT_PATH = Path(__file__).resolve().with_name("urbanflux_replanning_errors.jsonl")
DEFAULT_MAX_RETRIES = 5

GENERATION_SYSTEM_PROMPT = """Return only valid JSON: a list of objects with exactly these keys:
improved_metric, improved_value, delta."""

PARAMETER_DESCRIPTIONS = {
    "density": "Housing density: homes per built block",
    "green": "Green space target: share reserved as parks",
    "parking": "Parking pressure: surface parking demand",
    "street": "Road fill: boundary anchors connected",
    "alignment": "Road alignment: how straight corridors run",
    "height": "Height ambition: massing of tall buildings",
}

SCENARIO_RANGES = {
    "area_change_percent": (0, 100),
    "density": (5, 100),
    "green": (5, 80),
    "parking": (0, 80),
    "street": (0, 100),
    "alignment": (0, 100),
    "height": (0, 100),
}


@dataclass(frozen=True)
class Scenario:
    area_change_percent: int
    density: int
    green: int
    parking: int
    street: int
    alignment: int
    height: int


def parse_source_row(raw_json: str | None) -> dict[str, Any] | list[Any] | str | None:
    if raw_json is None:
        return None
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return raw_json


def source_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
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


def get_data_db_path() -> Path:
    from data_sources import LONDON_MAPPED_DATA_DB_PATH, ensure_london_mapped_data

    ensure_london_mapped_data()
    return LONDON_MAPPED_DATA_DB_PATH


def connect_data_db(db_path: Path | None = None) -> sqlite3.Connection:
    resolved_path = (db_path or get_data_db_path()).resolve()
    conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_query_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_urbanflux_ft_rows_borough_status_csv_date
        ON csv_row_transformations (
            borough_name,
            status,
            csv_file_id,
            date_end,
            date_start,
            row_number,
            id
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_urbanflux_ft_csv_files_theme_id
        ON dataset_csv_files (theme, id)
        """
    )


def fetch_recent_rows(
    conn: sqlite3.Connection,
    max_rows_per_borough_theme: int,
    borough: str | None = None,
    theme: str | None = None,
) -> list[dict[str, Any]]:
    pairs = fetch_borough_theme_pairs(conn, borough=borough, theme=theme)
    rows: list[dict[str, Any]] = []
    for borough_name, theme_name in pairs:
        rows.extend(
            fetch_recent_rows_for_pair(
                conn,
                borough_name=borough_name,
                theme=theme_name,
                limit=max_rows_per_borough_theme,
            )
        )
    return rows


def fetch_borough_theme_pairs(
    conn: sqlite3.Connection,
    borough: str | None = None,
    theme: str | None = None,
) -> list[tuple[str, str]]:
    filters = ["r.borough_name IS NOT NULL", "r.status IN ('success', 'partial')", "cf.theme IS NOT NULL"]
    params: dict[str, Any] = {}
    if borough:
        filters.append("r.borough_name = :borough")
        params["borough"] = borough
    if theme:
        filters.append("cf.theme = :theme")
        params["theme"] = theme

    where_sql = " AND ".join(filters)
    sql = f"""
        SELECT DISTINCT r.borough_name, cf.theme
        FROM csv_row_transformations r
        JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
        WHERE {where_sql}
        ORDER BY r.borough_name, cf.theme
    """
    rows = conn.execute(sql, params).fetchall()
    return [(row["borough_name"], row["theme"]) for row in rows]


def fetch_recent_rows_for_pair(
    conn: sqlite3.Connection,
    borough_name: str,
    theme: str,
    limit: int,
) -> list[dict[str, Any]]:
    sql = """
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
          AND r.status IN ('success', 'partial')
          AND cf.theme = :theme
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
    return [source_row_to_dict(row) for row in rows]


def stable_int_seed(seed: int, row_key: str, scenario_index: int) -> int:
    digest = hashlib.sha256(f"{seed}:{row_key}:{scenario_index}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def row_identity(row: dict[str, Any]) -> str:
    return "|".join(
        str(row.get(key, ""))
        for key in ("borough_name", "theme", "id", "csv_file_id", "row_number")
    )


def generate_scenario(seed: int, row_key: str, scenario_index: int) -> Scenario:
    import random

    rng = random.Random(stable_int_seed(seed, row_key, scenario_index))
    values = {
        name: rng.randint(bounds[0], bounds[1])
        for name, bounds in SCENARIO_RANGES.items()
    }
    return Scenario(**values)


def combination_key(row: dict[str, Any], seed: int, scenario_index: int, scenario: Scenario) -> str:
    payload = {
        "row": {
            "borough_name": row.get("borough_name"),
            "theme": row.get("theme"),
            "id": row.get("id"),
            "csv_file_id": row.get("csv_file_id"),
            "row_number": row.get("row_number"),
        },
        "seed": seed,
        "scenario_index": scenario_index,
        "scenario": asdict(scenario),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_user_prompt(row: dict[str, Any], scenario: Scenario, key: str) -> str:
    payload = {
        "combination_key": key,
        "task": "Predict replanning impact metric changes for this London borough scenario.",
        "borough": row.get("borough_name"),
        "theme": row.get("theme"),
        "date_start": row.get("date_start"),
        "date_end": row.get("date_end"),
        "source": row.get("source"),
        "borough_data": row.get("source_row"),
        "replanning_scenario": {
            "area_change_percent": scenario.area_change_percent,
            "parameters": {
                "density": scenario.density,
                "green": scenario.green,
                "parking": scenario.parking,
                "street": scenario.street,
                "alignment": scenario.alignment,
                "height": scenario.height,
            },
            "parameter_descriptions": PARAMETER_DESCRIPTIONS,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def validation_error_message(error: str, invalid_content: str) -> str:
    return (
        "The previous response was invalid. "
        f"Validation error: {error}. "
        "Return only a JSON list of objects with improved_metric, improved_value, and delta. "
        f"Previous response: {invalid_content}"
    )


def validate_model_output(content: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response is not valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, list):
        raise ValueError("response must be a JSON list")
    if not parsed:
        raise ValueError("response list must not be empty")

    required_keys = {"improved_metric", "improved_value", "delta"}
    validated: list[dict[str, Any]] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, dict):
            raise ValueError(f"item {index} must be an object")
        missing = required_keys - set(item)
        if missing:
            raise ValueError(f"item {index} missing keys: {', '.join(sorted(missing))}")
        extra = set(item) - required_keys
        if extra:
            raise ValueError(f"item {index} has extra keys: {', '.join(sorted(extra))}")
        for key in required_keys:
            if item[key] is None or item[key] == "":
                raise ValueError(f"item {index} has empty {key}")
        validated.append({key: item[key] for key in ("improved_metric", "improved_value", "delta")})
    return validated


def normalize_model_output(content: str) -> str:
    validated = validate_model_output(content)
    return json.dumps(validated, ensure_ascii=False, separators=(",", ":"))


def output_record(user_prompt: str, assistant_content: str) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": assistant_content},
        ]
    }


def extract_completed_key(record: dict[str, Any]) -> str | None:
    messages = record.get("messages")
    if not isinstance(messages, list):
        return None
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        key = payload.get("combination_key")
        return key if isinstance(key, str) else None
    return None


def load_completed_keys(output_path: Path) -> set[str]:
    if not output_path.exists():
        return set()

    completed: set[str] = set()
    with output_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = extract_completed_key(record)
            if key:
                completed.add(key)
    return completed


def build_chat_model():
    base_url = os.environ.get("URBANFLUX_LLM_BASE_URL")
    token = os.environ.get("URBANFLUX_LLM_TOKEN")
    model = os.environ.get("URBANFLUX_LLM_MODEL")
    missing = [
        name
        for name, value in {
            "URBANFLUX_LLM_BASE_URL": base_url,
            "URBANFLUX_LLM_TOKEN": token,
            "URBANFLUX_LLM_MODEL": model,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain-openai is required for model calls. Install backend requirements first."
        ) from exc

    return ChatOpenAI(
        model=str(model),
        api_key=str(token),
        base_url=str(base_url),
        temperature=0,
    )


def get_message_content(response: Any) -> str:
    content = getattr(response, "content", response)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return str(content)


def invoke_with_retries(
    chat_model: Any,
    system_prompt: str,
    user_prompt: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> tuple[str | None, list[dict[str, str]], str | None, str | None]:
    attempts: list[dict[str, str]] = []
    messages: list[tuple[str, str]] = [("system", system_prompt), ("user", user_prompt)]
    last_error: str | None = None
    last_content: str | None = None

    for _ in range(max_retries):
        response = chat_model.invoke(messages)
        last_content = get_message_content(response).strip()
        try:
            normalized = normalize_model_output(last_content)
            return normalized, attempts, None, last_content
        except ValueError as exc:
            last_error = str(exc)
            attempts.append({"error": last_error, "content": last_content})
            messages.append(("assistant", last_content))
            messages.append(("user", validation_error_message(last_error, last_content)))

    return None, attempts, last_error, last_content


def iter_planned_combinations(
    rows: Iterable[dict[str, Any]],
    seed: int,
    scenarios_per_row: int,
) -> Iterable[tuple[dict[str, Any], int, Scenario, str]]:
    for row in rows:
        key_base = row_identity(row)
        for scenario_index in range(scenarios_per_row):
            scenario = generate_scenario(seed, key_base, scenario_index)
            key = combination_key(row, seed, scenario_index, scenario)
            yield row, scenario_index, scenario, key


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare UrbanFlux replanning fine-tune JSONL data.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--errors-output", type=Path, default=DEFAULT_ERRORS_OUTPUT_PATH)
    parser.add_argument("--max-rows-per-borough-theme", type=int, default=100)
    parser.add_argument("--scenarios-per-row", type=int, default=1)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--borough")
    parser.add_argument("--theme")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.max_rows_per_borough_theme < 1:
        raise ValueError("--max-rows-per-borough-theme must be at least 1")
    if args.scenarios_per_row < 1:
        raise ValueError("--scenarios-per-row must be at least 1")


def run(args: argparse.Namespace) -> int:
    validate_args(args)
    args.output = args.output.resolve()
    args.errors_output = args.errors_output.resolve()

    with connect_data_db() as conn:
        rows = fetch_recent_rows(
            conn,
            max_rows_per_borough_theme=args.max_rows_per_borough_theme,
            borough=args.borough,
            theme=args.theme,
        )

    completed_keys = load_completed_keys(args.output)
    planned = list(iter_planned_combinations(rows, args.seed, args.scenarios_per_row))
    pending = [
        item
        for item in planned
        if item[3] not in completed_keys
    ]

    if args.dry_run:
        print(
            json.dumps(
                {
                    "rows": len(rows),
                    "planned_combinations": len(planned),
                    "completed_combinations": len(planned) - len(pending),
                    "pending_combinations": len(pending),
                    "output": str(args.output),
                    "errors_output": str(args.errors_output),
                },
                indent=2,
            )
        )
        return 0

    chat_model = build_chat_model()
    skipped = len(planned) - len(pending)
    failures = 0
    retries = 0

    with tqdm(total=len(planned), initial=skipped, unit="combo") as progress:
        progress.set_postfix(rows=len(rows), skipped=skipped, retries=retries, failures=failures)
        for row, scenario_index, scenario, key in pending:
            user_prompt = build_user_prompt(row, scenario, key)
            assistant_content, attempts, error, last_content = invoke_with_retries(
                chat_model,
                GENERATION_SYSTEM_PROMPT,
                user_prompt,
            )
            retries += len(attempts)
            if assistant_content is None:
                failures += 1
                append_jsonl(
                    args.errors_output,
                    {
                        "combination_key": key,
                        "metadata": {
                            "borough_name": row.get("borough_name"),
                            "theme": row.get("theme"),
                            "id": row.get("id"),
                            "csv_file_id": row.get("csv_file_id"),
                            "row_number": row.get("row_number"),
                            "scenario_index": scenario_index,
                        },
                        "scenario": asdict(scenario),
                        "attempts": attempts,
                        "last_error": error,
                        "last_model_content": last_content,
                    },
                )
            else:
                append_jsonl(args.output, output_record(user_prompt, assistant_content))

            progress.update(1)
            progress.set_postfix(rows=len(rows), skipped=skipped, retries=retries, failures=failures)

    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())

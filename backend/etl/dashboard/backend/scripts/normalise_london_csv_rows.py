#!/usr/bin/env python3
"""
Normalise London Datastore CSV rows.

Input metadata:
- backend/data/london_datastore.sqlite3
- dataset_sources
- dataset_csv_files

Output tables created in the same SQLite DB:
- normalised_csv_rows
- csv_normalisation_errors
- csv_file_mapping_rules

Usage:
    python backend/scripts/normalise_london_csv_rows.py --self-test
    python backend/scripts/normalise_london_csv_rows.py --dry-run --limit-files 5
    python backend/scripts/normalise_london_csv_rows.py --limit-files 50
    python backend/scripts/normalise_london_csv_rows.py --force --limit-files 10
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

try:
    from dateutil import parser as date_parser
except ImportError:  # pragma: no cover
    date_parser = None


DEFAULT_METADATA_DB = "backend/data/london_datastore.sqlite3"
DEFAULT_CSV_ROOT = "backend/data/csv"

LLM_JSON_SCHEMA_NAME = "csv_mapping_rule"

LONDON_BOROUGHS: dict[str, dict[str, str]] = {
    "city of london": {"code": "E09000001", "name": "City of London"},
    "barking and dagenham": {"code": "E09000002", "name": "Barking and Dagenham"},
    "barnet": {"code": "E09000003", "name": "Barnet"},
    "bexley": {"code": "E09000004", "name": "Bexley"},
    "brent": {"code": "E09000005", "name": "Brent"},
    "bromley": {"code": "E09000006", "name": "Bromley"},
    "camden": {"code": "E09000007", "name": "Camden"},
    "croydon": {"code": "E09000008", "name": "Croydon"},
    "ealing": {"code": "E09000009", "name": "Ealing"},
    "enfield": {"code": "E09000010", "name": "Enfield"},
    "greenwich": {"code": "E09000011", "name": "Greenwich"},
    "hackney": {"code": "E09000012", "name": "Hackney"},
    "hammersmith and fulham": {"code": "E09000013", "name": "Hammersmith and Fulham"},
    "haringey": {"code": "E09000014", "name": "Haringey"},
    "harrow": {"code": "E09000015", "name": "Harrow"},
    "havering": {"code": "E09000016", "name": "Havering"},
    "hillingdon": {"code": "E09000017", "name": "Hillingdon"},
    "hounslow": {"code": "E09000018", "name": "Hounslow"},
    "islington": {"code": "E09000019", "name": "Islington"},
    "kensington and chelsea": {"code": "E09000020", "name": "Kensington and Chelsea"},
    "kingston upon thames": {"code": "E09000021", "name": "Kingston upon Thames"},
    "lambeth": {"code": "E09000022", "name": "Lambeth"},
    "lewisham": {"code": "E09000023", "name": "Lewisham"},
    "merton": {"code": "E09000024", "name": "Merton"},
    "newham": {"code": "E09000025", "name": "Newham"},
    "redbridge": {"code": "E09000026", "name": "Redbridge"},
    "richmond upon thames": {"code": "E09000027", "name": "Richmond upon Thames"},
    "southwark": {"code": "E09000028", "name": "Southwark"},
    "sutton": {"code": "E09000029", "name": "Sutton"},
    "tower hamlets": {"code": "E09000030", "name": "Tower Hamlets"},
    "waltham forest": {"code": "E09000031", "name": "Waltham Forest"},
    "wandsworth": {"code": "E09000032", "name": "Wandsworth"},
    "westminster": {"code": "E09000033", "name": "Westminster"},
}

BOROUGH_ALIASES: dict[str, str] = {
    "city": "city of london",
    "london city": "city of london",
    "city london": "city of london",
    "westminster city council": "westminster",
    "city of westminster": "westminster",
    "royal borough of greenwich": "greenwich",
    "greenwich london boro": "greenwich",
    "rbkc": "kensington and chelsea",
    "royal borough of kensington and chelsea": "kensington and chelsea",
    "kingston": "kingston upon thames",
    "royal borough of kingston upon thames": "kingston upon thames",
    "hammersmith & fulham": "hammersmith and fulham",
    "kensington & chelsea": "kensington and chelsea",
    "barking & dagenham": "barking and dagenham",
    "richmond": "richmond upon thames",
    "tower hamlet": "tower hamlets",
}

AGGREGATE_AREAS: dict[str, dict[str, str]] = {
    "london": {"kind": "london_total", "code": "E12000007", "name": "London"},
    "greater london": {"kind": "london_total", "code": "E12000007", "name": "London"},
    "all london": {"kind": "london_total", "code": "E12000007", "name": "London"},
    "total london": {"kind": "london_total", "code": "E12000007", "name": "London"},
    "inner london": {"kind": "london_subregion", "code": None, "name": "Inner London"},
    "outer london": {"kind": "london_subregion", "code": None, "name": "Outer London"},
    "all": {"kind": "aggregate_total", "code": None, "name": "All"},
    "total": {"kind": "aggregate_total", "code": None, "name": "Total"},
    "england": {"kind": "uk_all", "code": "E92000001", "name": "England"},
    "uk": {"kind": "uk_all", "code": "K02000001", "name": "United Kingdom"},
    "united kingdom": {"kind": "uk_all", "code": "K02000001", "name": "United Kingdom"},
}

BOROUGH_CODE_TO_NAME: dict[str, dict[str, str]] = {
    value["code"].upper(): value for value in LONDON_BOROUGHS.values()
}

AREA_COLUMN_HINTS = (
    "area",
    "borough",
    "local authority",
    "local_authority",
    "lad",
    "la name",
    "la_name",
    "district",
    "ward",
    "geography",
    "geographic",
    "place",
    "name",
)

AREA_CODE_COLUMN_HINTS = (
    "code",
    "area code",
    "area_code",
    "gss",
    "ons",
    "lad code",
    "lad_code",
)

DATE_COLUMN_HINTS = (
    "date",
    "year",
    "month",
    "quarter",
    "period",
    "time",
    "financial year",
    "financial_year",
)

TEXT_NULLS = {"", "-", "n/a", "na", "null", "none", "..", ":"}


@dataclass(frozen=True)
class SourceFile:
    source_id: int
    source_file_id: int
    file_path: str
    source_description: str


@dataclass(frozen=True)
class MappingRule:
    area_columns: list[str]
    date_columns: list[str]
    measure_columns: list[str]
    skip_columns: list[str]
    confidence: float
    reason: str
    source: str


@dataclass(frozen=True)
class NormalisedArea:
    area_kind: str
    area_code: str | None
    area_name: str | None
    area_raw: str | None
    area_confidence: float
    area_reason: str


@dataclass(frozen=True)
class NormalisedDate:
    date_start: str | None
    date_end: str | None
    date_precision: str
    date_raw: str | None
    date_confidence: float
    date_reason: str


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


def load_env(project_root: Path) -> None:
    load_env_file(project_root / "backend" / ".env")
    load_env_file(project_root / ".env")


def connect_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def ensure_output_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS csv_file_mapping_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            source_file_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            file_hash TEXT,
            rule_json TEXT NOT NULL,
            rule_source TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'ok',
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source_file_id, file_hash)
        );

        CREATE TABLE IF NOT EXISTS normalised_csv_rows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            source_file_id INTEGER NOT NULL,
            input_file TEXT NOT NULL,
            input_row_number INTEGER NOT NULL,
            output_row_number INTEGER NOT NULL,
            input_row_hash TEXT NOT NULL,

            measure_column TEXT,
            measure_name TEXT,
            measure_value TEXT,

            area_kind TEXT NOT NULL DEFAULT 'unknown',
            area_code TEXT,
            area_name TEXT,
            area_raw TEXT,
            area_confidence REAL NOT NULL DEFAULT 0,
            area_reason TEXT,

            date_start TEXT,
            date_end TEXT,
            date_precision TEXT NOT NULL DEFAULT 'unknown',
            date_raw TEXT,
            date_confidence REAL NOT NULL DEFAULT 0,
            date_reason TEXT,

            normalizer_status TEXT NOT NULL,
            normalizer_errors TEXT,
            rule_source TEXT,
            rule_confidence REAL NOT NULL DEFAULT 0,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE UNIQUE INDEX IF NOT EXISTS uq_normalised_csv_rows_dedupe
            ON normalised_csv_rows (
                source_file_id,
                input_row_number,
                IFNULL(measure_column, ''),
                IFNULL(date_raw, ''),
                input_row_hash
            );

        CREATE TABLE IF NOT EXISTS csv_normalisation_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER,
            source_file_id INTEGER,
            input_file TEXT,
            input_row_number INTEGER,
            stage TEXT NOT NULL,
            error_code TEXT NOT NULL,
            error_message TEXT NOT NULL,
            error_detail TEXT,
            row_json TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """    )
    conn.commit()


def fetch_source_files(conn: sqlite3.Connection, limit_files: int | None) -> list[SourceFile]:
    sql = """
        SELECT
            ds.id AS source_id,
            cf.id AS source_file_id,
            cf.local_path AS file_path,
            TRIM(
              COALESCE(ds.title, '') || CHAR(10) ||
              COALESCE(ds.description, '') || CHAR(10) ||
              'Dataset URL: ' || COALESCE(ds.dataset_url, '') || CHAR(10) ||
              'Publisher: ' || COALESCE(ds.organisation_name, '') || CHAR(10) ||
              'Resource title: ' || COALESCE(cf.title, '') || CHAR(10) ||
              'Resource description: ' || COALESCE(cf.description, '') || CHAR(10) ||
              'CSV URL: ' || COALESCE(cf.csv_url, '')
            ) AS source_description
        FROM dataset_csv_files cf
        JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
        WHERE cf.status = 1
          AND cf.local_path IS NOT NULL
          AND TRIM(cf.local_path) != ''
        ORDER BY ds.id, cf.id
    """

    if limit_files is not None:
        sql += " LIMIT ?"
        rows = conn.execute(sql, (limit_files,)).fetchall()
    else:
        rows = conn.execute(sql).fetchall()

    return [
        SourceFile(
            source_id=int(row["source_id"]),
            source_file_id=int(row["source_file_id"]),
            file_path=str(row["file_path"]),
            source_description=str(row["source_description"] or ""),
        )
        for row in rows
    ]


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalise_text(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\ufeff", "")
    text = text.strip().lower()
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def is_nullish(value: Any) -> bool:
    return normalise_text(value) in TEXT_NULLS


def sniff_dialect(path: Path, encoding: str) -> csv.Dialect:
    sample = path.read_text(encoding=encoding, errors="replace")[:65536]
    try:
        return csv.Sniffer().sniff(sample)
    except csv.Error:
        return csv.excel


def detect_encoding(path: Path) -> str:
    raw = path.read_bytes()[:4096]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        raw.decode("utf-8")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "latin-1"


def read_sample_rows(path: Path, max_rows: int = 25) -> tuple[list[str], list[dict[str, str]], str]:
    encoding = detect_encoding(path)
    dialect = sniff_dialect(path, encoding)

    with path.open("r", encoding=encoding, errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, dialect=dialect)
        headers = [header or "" for header in (reader.fieldnames or [])]
        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader):
            if index >= max_rows:
                break
            rows.append({str(k or ""): str(v or "") for k, v in row.items()})

    return headers, rows, encoding


def choose_area_columns(headers: list[str], sample_rows: list[dict[str, str]]) -> list[str]:
    scored: list[tuple[int, str]] = []

    for header in headers:
        h = normalise_text(header)
        score = 0

        # Strong explicit dimensions.
        if h in {
            "area name",
            "area",
            "borough",
            "borough name",
            "local authority",
            "local authority name",
            "la name",
            "lad name",
            "district",
            "geography",
            "geography name",
        }:
            score += 100

        if h in {
            "area code",
            "area_code",
            "code",
            "gss code",
            "ons code",
            "lad code",
            "local authority code",
        }:
            score += 95

        # Weak hints only if the column is not obviously a measure.
        if any(token in h for token in ("hectares", "population", "people", "count", "number", "rate")):
            score -= 100

        values = [row.get(header, "") for row in sample_rows[:20]]
        borough_hits = 0
        for value in values:
            area = normalise_area_from_value(value)
            if area.area_kind != "unknown":
                borough_hits += 1

        score += borough_hits * 8

        if score > 0:
            scored.append((score, header))

    scored.sort(reverse=True)
    return [header for _, header in scored[:2]]


def choose_date_columns(headers: list[str], sample_rows: list[dict[str, str]]) -> list[str]:
    del sample_rows

    scored: list[tuple[int, str]] = []

    for header in headers:
        h = normalise_text(header)
        score = 0

        if h in {
            "date",
            "year",
            "month",
            "quarter",
            "period",
            "time period",
            "financial year",
            "financial_year",
        }:
            score += 100
        elif any(h == hint or h.endswith(f" {hint}") for hint in DATE_COLUMN_HINTS):
            score += 20

        # Do not treat measure columns as date columns just because their values are numeric.
        if any(token in h for token in ("people", "population", "count", "number", "rate", "total")):
            score -= 100

        if score > 0:
            scored.append((score, header))

    scored.sort(reverse=True)
    return [header for _, header in scored[:3]]


def choose_measure_columns(
    headers: list[str],
    area_columns: list[str],
    date_columns: list[str],
) -> list[str]:
    excluded = set(area_columns) | set(date_columns)
    measure_columns: list[str] = []

    for header in headers:
        if header in excluded:
            continue

        h = normalise_text(header)

        if h in {"", "notes", "note", "source", "url"}:
            continue

        if h in {
            "area code",
            "area name",
            "borough",
            "borough name",
            "local authority",
            "local authority name",
            "lad code",
            "lad name",
        }:
            continue

        measure_columns.append(header)

    return measure_columns


def heuristic_mapping_rule(headers: list[str], sample_rows: list[dict[str, str]]) -> MappingRule:
    area_columns = choose_area_columns(headers, sample_rows)
    date_columns = choose_date_columns(headers, sample_rows)
    measure_columns = choose_measure_columns(headers, area_columns, date_columns)

    confidence = 0.35
    if area_columns:
        confidence += 0.25
    if date_columns or any(normalise_date(header).date_precision != "unknown" for header in headers):
        confidence += 0.20
    if measure_columns:
        confidence += 0.10

    return MappingRule(
        area_columns=area_columns,
        date_columns=date_columns,
        measure_columns=measure_columns,
        skip_columns=[],
        confidence=min(confidence, 0.85),
        reason="Heuristic rule from headers and sample values.",
        source="heuristic",
    )


def llm_available() -> bool:
    return bool(os.environ.get("LLM7_TOKEN") and os.environ.get("LLM7_API_BASE_URL"))


def build_llm_payload(
    model: str,
    source_description: str,
    headers: list[str],
    sample_rows: list[dict[str, str]],
    response_format: dict[str, Any],
) -> dict[str, Any]:
    compact_rows = sample_rows[:10]

    system = (
        "You infer CSV mapping rules for a batch ETL pipeline. "
        "Return only valid JSON. Do not explain outside JSON."
    )

    user = {
        "task": (
            "Infer which CSV columns identify London area, date/period, and measure values. "
            "Prefer London borough/local authority mapping if present. "
            "If dates are encoded in column headers, put those columns into measure_columns. "
            "Do not invent column names. Use exact header names only."
        ),
        "expected_json_fields": {
            "area_columns": "list of exact header names likely containing borough/area/code",
            "date_columns": "list of exact header names likely containing date/year/month/period",
            "measure_columns": "list of exact header names containing values to output",
            "skip_columns": "list of exact header names that should be ignored",
            "confidence": "number from 0 to 1",
            "reason": "short explanation",
        },
        "source_description": source_description[:6000],
        "headers": headers,
        "sample_rows": compact_rows,
    }

    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 1200,
        "response_format": response_format,
    }


def call_llm7_json(
    source_description: str,
    headers: list[str],
    sample_rows: list[dict[str, str]],
) -> dict[str, Any]:
    api_base = os.environ["LLM7_API_BASE_URL"].rstrip("/")
    token = os.environ["LLM7_TOKEN"]
    model = os.environ.get("LLM7_MODEL", "gpt-4o-mini")
    timeout = float(os.environ.get("LLM7_REQUEST_TIMEOUT_SECONDS", "60"))
    endpoint = f"{api_base}/chat/completions"

    schema_format = {
        "type": "json_schema",
        "json_schema": {
            "name": LLM_JSON_SCHEMA_NAME,
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "area_columns": {"type": "array", "items": {"type": "string"}},
                    "date_columns": {"type": "array", "items": {"type": "string"}},
                    "measure_columns": {"type": "array", "items": {"type": "string"}},
                    "skip_columns": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "area_columns",
                    "date_columns",
                    "measure_columns",
                    "skip_columns",
                    "confidence",
                    "reason",
                ],
            },
        },
    }

    json_object_format = {"type": "json_object"}

    last_error: Exception | None = None

    for response_format in (schema_format, json_object_format):
        for attempt in range(3):
            payload = build_llm_payload(
                model=model,
                source_description=source_description,
                headers=headers,
                sample_rows=sample_rows,
                response_format=response_format,
            )

            request = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )

            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))

                content = body["choices"][0]["message"]["content"]
                return json.loads(content)

            except urllib.error.HTTPError as exc:
                last_error = exc
                if response_format == schema_format and exc.code in {400, 422}:
                    break
                time.sleep(2**attempt)

            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(2**attempt)

    raise RuntimeError(f"LLM7 call failed: {last_error}")


def validate_rule(raw_rule: dict[str, Any], headers: list[str]) -> MappingRule:
    header_set = set(headers)

    def keep_known(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return [str(value) for value in values if str(value) in header_set]

    confidence = raw_rule.get("confidence", 0)
    try:
        confidence_float = float(confidence)
    except (TypeError, ValueError):
        confidence_float = 0.0

    return MappingRule(
        area_columns=keep_known(raw_rule.get("area_columns")),
        date_columns=keep_known(raw_rule.get("date_columns")),
        measure_columns=keep_known(raw_rule.get("measure_columns")),
        skip_columns=keep_known(raw_rule.get("skip_columns")),
        confidence=max(0.0, min(confidence_float, 1.0)),
        reason=str(raw_rule.get("reason") or "LLM inferred mapping rule."),
        source="llm7",
    )


def infer_mapping_rule(
    source: SourceFile,
    headers: list[str],
    sample_rows: list[dict[str, str]],
) -> MappingRule:
    heuristic = heuristic_mapping_rule(headers, sample_rows)

    if not llm_available():
        return heuristic

    try:
        raw_rule = call_llm7_json(source.source_description, headers, sample_rows)
        llm_rule = validate_rule(raw_rule, headers)

        if not llm_rule.area_columns and heuristic.area_columns:
            return MappingRule(
                area_columns=heuristic.area_columns,
                date_columns=llm_rule.date_columns or heuristic.date_columns,
                measure_columns=llm_rule.measure_columns or heuristic.measure_columns,
                skip_columns=llm_rule.skip_columns,
                confidence=min(llm_rule.confidence, 0.65),
                reason=f"{llm_rule.reason} Area columns filled by heuristic fallback.",
                source="llm7+heuristic",
            )

        return llm_rule

    except Exception:
        return heuristic


def normalise_area_from_value(value: Any) -> NormalisedArea:
    raw = None if value is None else str(value).strip()
    key = normalise_text(raw)

    if not key:
        return NormalisedArea(
            area_kind="unknown",
            area_code=None,
            area_name=None,
            area_raw=raw,
            area_confidence=0.0,
            area_reason="Empty area value.",
        )

    upper = str(raw).strip().upper()
    if upper in BOROUGH_CODE_TO_NAME:
        area = BOROUGH_CODE_TO_NAME[upper]
        return NormalisedArea(
            area_kind="london_borough",
            area_code=area["code"],
            area_name=area["name"],
            area_raw=raw,
            area_confidence=1.0,
            area_reason="Exact GSS borough code match.",
        )

    if key in BOROUGH_ALIASES:
        key = BOROUGH_ALIASES[key]

    if key in AGGREGATE_AREAS:
        area = AGGREGATE_AREAS[key]
        return NormalisedArea(
            area_kind=area["kind"],
            area_code=area["code"],
            area_name=area["name"],
            area_raw=raw,
            area_confidence=0.95,
            area_reason="Exact aggregate London area match.",
        )

    if key in LONDON_BOROUGHS:
        area = LONDON_BOROUGHS[key]
        return NormalisedArea(
            area_kind="london_borough",
            area_code=area["code"],
            area_name=area["name"],
            area_raw=raw,
            area_confidence=1.0,
            area_reason="Exact borough name/alias match.",
        )

    best_key = None
    best_score = 0.0
    tokens = set(key.split())

    for borough_key in LONDON_BOROUGHS:
        borough_tokens = set(borough_key.split())
        if not tokens or not borough_tokens:
            continue

        overlap = len(tokens & borough_tokens) / len(tokens | borough_tokens)
        containment = 1.0 if borough_key in key or key in borough_key else 0.0
        score = max(overlap, containment * 0.92)

        if score > best_score:
            best_score = score
            best_key = borough_key

    if best_key and best_score >= 0.72:
        area = LONDON_BOROUGHS[best_key]
        return NormalisedArea(
            area_kind="london_borough",
            area_code=area["code"],
            area_name=area["name"],
            area_raw=raw,
            area_confidence=round(best_score, 3),
            area_reason="Fuzzy borough name match.",
        )

    return NormalisedArea(
        area_kind="unknown",
        area_code=None,
        area_name=None,
        area_raw=raw,
        area_confidence=0.0,
        area_reason="No London borough match.",
    )


def normalise_area(row: dict[str, str], rule: MappingRule) -> NormalisedArea:
    candidates: list[str] = []

    for column in rule.area_columns:
        value = row.get(column)
        if value is not None and not is_nullish(value):
            candidates.append(value)

    for candidate in candidates:
        area = normalise_area_from_value(candidate)
        if area.area_kind != "unknown":
            return area

    raw = " | ".join(candidates) if candidates else None
    return NormalisedArea(
        area_kind="unknown",
        area_code=None,
        area_name=None,
        area_raw=raw,
        area_confidence=0.0,
        area_reason="No configured area column matched a London borough.",
    )


def normalise_date(value: Any) -> NormalisedDate:
    raw = None if value is None else str(value).strip()
    text = "" if raw is None else raw.strip()

    if not text or normalise_text(text) in TEXT_NULLS:
        return NormalisedDate(
            date_start=None,
            date_end=None,
            date_precision="unknown",
            date_raw=raw,
            date_confidence=0.0,
            date_reason="Empty date value.",
        )

    lowered = text.lower().strip()

    year_range_match = re.search(
        r"\b(20\d{2}|19\d{2})\s*[-–—]\s*(20\d{2}|19\d{2})\b",
        lowered,
    )
    if year_range_match:
        start_year = int(year_range_match.group(1))
        end_year = int(year_range_match.group(2))

        return NormalisedDate(
            date_start=f"{start_year:04d}-01-01",
            date_end=f"{end_year:04d}-12-31",
            date_precision="year_range",
            date_raw=raw,
            date_confidence=0.90,
            date_reason="Parsed year range.",
        )

    financial_match = re.search(
        r"\b(?:fy|financial year)?\s*(20\d{2}|19\d{2})\s*[/\-]\s*(\d{2})\b",
        lowered,
    )
    if financial_match:
        start_year = int(financial_match.group(1))
        end_part = financial_match.group(2)
        end_year = int(str(start_year)[:2] + end_part)

        return NormalisedDate(
            date_start=f"{start_year:04d}-04-01",
            date_end=f"{end_year:04d}-03-31",
            date_precision="financial_year",
            date_raw=raw,
            date_confidence=0.95,
            date_reason="Parsed UK financial year.",
        )

    quarter_match = re.search(r"\b(?:q([1-4])\s*[-/]?\s*(20\d{2}|19\d{2})|(20\d{2}|19\d{2})\s*[-/]?\s*q([1-4]))\b", lowered)
    if quarter_match:
        quarter = int(quarter_match.group(1) or quarter_match.group(4))
        year = int(quarter_match.group(2) or quarter_match.group(3))
        starts = {
            1: (1, 1, 3, 31),
            2: (4, 1, 6, 30),
            3: (7, 1, 9, 30),
            4: (10, 1, 12, 31),
        }
        start_month, start_day, end_month, end_day = starts[quarter]

        return NormalisedDate(
            date_start=f"{year:04d}-{start_month:02d}-{start_day:02d}",
            date_end=f"{year:04d}-{end_month:02d}-{end_day:02d}",
            date_precision="quarter",
            date_raw=raw,
            date_confidence=0.95,
            date_reason="Parsed calendar quarter.",
        )


    year_match = re.search(r"\b(20\d{2}|19\d{2})\b", lowered)
    if year_match and len(re.findall(r"\b(20\d{2}|19\d{2})\b", lowered)) == 1:
        year = int(year_match.group(1))

        month_match = re.search(
            r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\b",
            lowered,
        )

        if month_match:
            month_lookup = {
                "jan": 1,
                "feb": 2,
                "mar": 3,
                "apr": 4,
                "may": 5,
                "jun": 6,
                "jul": 7,
                "aug": 8,
                "sep": 9,
                "sept": 9,
                "oct": 10,
                "nov": 11,
                "dec": 12,
            }
            month = month_lookup[month_match.group(1)]
            end_day = 31
            if month in {4, 6, 9, 11}:
                end_day = 30
            elif month == 2:
                end_day = 29 if year % 4 == 0 else 28

            return NormalisedDate(
                date_start=f"{year:04d}-{month:02d}-01",
                date_end=f"{year:04d}-{month:02d}-{end_day:02d}",
                date_precision="month",
                date_raw=raw,
                date_confidence=0.90,
                date_reason="Parsed month and year.",
            )

        return NormalisedDate(
            date_start=f"{year:04d}-01-01",
            date_end=f"{year:04d}-12-31",
            date_precision="year",
            date_raw=raw,
            date_confidence=0.95,
            date_reason="Parsed year.",
        )

    if date_parser is not None:
        try:
            parsed = date_parser.parse(text, fuzzy=True, dayfirst=True)
            parsed_date = parsed.date().isoformat()
            return NormalisedDate(
                date_start=parsed_date,
                date_end=parsed_date,
                date_precision="day",
                date_raw=raw,
                date_confidence=0.75,
                date_reason="Parsed by dateutil.",
            )
        except (ValueError, OverflowError):
            pass

    return NormalisedDate(
        date_start=None,
        date_end=None,
        date_precision="unknown",
        date_raw=raw,
        date_confidence=0.0,
        date_reason="Could not parse date.",
    )


def normalise_date_from_description(source_description: str) -> NormalisedDate:
    candidates: list[str] = []

    # Prefer explicit census/year-like phrases over arbitrary URLs.
    patterns = [
        r"\b(?:census|mid-year|mid year|population|estimate|estimates|data for|year)\s+(20\d{2}|19\d{2})\b",
        r"\b(20\d{2}|19\d{2})\s+(?:census|population|estimate|estimates)\b",
        r"\b(?:fy|financial year)\s*(20\d{2}|19\d{2})\s*[/\-]\s*(\d{2})\b",
        r"\bq[1-4]\s*[-/]?\s*(20\d{2}|19\d{2})\b",
        r"\b(20\d{2}|19\d{2})\b",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, source_description, flags=re.IGNORECASE):
            candidates.append(match.group(0))

    for candidate in candidates:
        parsed = normalise_date(candidate)
        if parsed.date_precision != "unknown":
            return NormalisedDate(
                date_start=parsed.date_start,
                date_end=parsed.date_end,
                date_precision=parsed.date_precision,
                date_raw=candidate,
                date_confidence=max(0.55, parsed.date_confidence - 0.20),
                date_reason="Parsed from dataset/resource description fallback.",
            )

    return NormalisedDate(
        date_start=None,
        date_end=None,
        date_precision="unknown",
        date_raw=None,
        date_confidence=0.0,
        date_reason="No parseable date in dataset/resource description.",
    )



def normalise_date_for_row(
    row: dict[str, str],
    rule: MappingRule,
    measure_column: str | None,
    fallback_date: NormalisedDate | None = None,
) -> NormalisedDate:
    if measure_column:
        from_measure_header = normalise_date(measure_column)
        if from_measure_header.date_precision != "unknown":
            return from_measure_header

    for column in rule.date_columns:
        value = row.get(column)
        parsed = normalise_date(value)
        if parsed.date_precision != "unknown":
            return parsed

    if fallback_date is not None and fallback_date.date_precision != "unknown":
        return fallback_date

    return NormalisedDate(
        date_start=None,
        date_end=None,
        date_precision="unknown",
        date_raw=None,
        date_confidence=0.0,
        date_reason="No parseable date in row, measure column, or source description.",
    )


def row_to_hashable_json(row: dict[str, str]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _append_error_record(
    records: list[dict[str, Any]] | None,
    source: SourceFile,
    *,
    input_row_number: int | None,
    stage: str,
    error_code: str,
    error_message: str,
    error_detail: str | None = None,
    row: dict[str, str] | None = None,
) -> None:
    if records is None:
        return

    records.append(
        {
            "source_id": source.source_id,
            "source_file_id": source.source_file_id,
            "file_path": source.file_path,
            "input_row_number": input_row_number,
            "stage": stage,
            "error_code": error_code,
            "error_message": error_message,
            "error_detail": error_detail,
            "row_json": json.dumps(row, ensure_ascii=False) if row is not None else None,
        }
    )


def insert_error(
    conn: sqlite3.Connection,
    source: SourceFile,
    input_row_number: int | None,
    stage: str,
    error_code: str,
    error_message: str,
    error_detail: str | None = None,
    row: dict[str, str] | None = None,
    dry_run: bool = False,
    error_records: list[dict[str, Any]] | None = None,
) -> None:
    if dry_run:
        print(
            f"[DRY-RUN][ERROR] file={source.source_file_id} row={input_row_number} "
            f"stage={stage} code={error_code}: {error_message}"
        )
        _append_error_record(
            error_records,
            source,
            input_row_number=input_row_number,
            stage=stage,
            error_code=error_code,
            error_message=error_message,
            error_detail=error_detail,
            row=row,
        )
        return

    conn.execute(
        """
        INSERT INTO csv_normalisation_errors (
            source_id,
            source_file_id,
            input_file,
            input_row_number,
            stage,
            error_code,
            error_message,
            error_detail,
            row_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source.source_id,
            source.source_file_id,
            source.file_path,
            input_row_number,
            stage,
            error_code,
            error_message,
            error_detail,
            json.dumps(row, ensure_ascii=False) if row is not None else None,
        ),
    )
    _append_error_record(
        error_records,
        source,
        input_row_number=input_row_number,
        stage=stage,
        error_code=error_code,
        error_message=error_message,
        error_detail=error_detail,
        row=row,
    )


def store_mapping_rule(
    conn: sqlite3.Connection,
    source: SourceFile,
    path_hash: str,
    rule: MappingRule,
    dry_run: bool,
) -> None:
    rule_json = json.dumps(
        {
            "area_columns": rule.area_columns,
            "date_columns": rule.date_columns,
            "measure_columns": rule.measure_columns,
            "skip_columns": rule.skip_columns,
            "confidence": rule.confidence,
            "reason": rule.reason,
            "source": rule.source,
        },
        ensure_ascii=False,
        sort_keys=True,
    )

    if dry_run:
        print(f"[DRY-RUN] mapping rule for file={source.source_file_id}: {rule_json}")
        return

    conn.execute(
        """
        INSERT INTO csv_file_mapping_rules (
            source_id,
            source_file_id,
            file_path,
            file_hash,
            rule_json,
            rule_source,
            confidence,
            status,
            error_message,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'ok', NULL, CURRENT_TIMESTAMP)
        ON CONFLICT(source_file_id, file_hash) DO UPDATE SET
            rule_json = excluded.rule_json,
            rule_source = excluded.rule_source,
            confidence = excluded.confidence,
            status = 'ok',
            error_message = NULL,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            source.source_id,
            source.source_file_id,
            source.file_path,
            path_hash,
            rule_json,
            rule.source,
            rule.confidence,
        ),
    )


def already_processed(
    conn: sqlite3.Connection,
    source_file_id: int,
    file_path: str,
    force: bool,
) -> bool:
    if force:
        return False

    row = conn.execute(
        """
        SELECT 1
        FROM normalised_csv_rows
        WHERE source_file_id = ?
          AND input_file = ?
        LIMIT 1
        """,
        (source_file_id, file_path),
    ).fetchone()

    return row is not None


def insert_normalised_row(
    conn: sqlite3.Connection,
    source: SourceFile,
    input_row_number: int,
    output_row_number: int,
    row_hash: str,
    measure_column: str | None,
    measure_name: str | None,
    measure_value: str | None,
    area: NormalisedArea,
    parsed_date: NormalisedDate,
    status: str,
    errors: list[str],
    rule: MappingRule,
    dry_run: bool,
) -> None:
    if dry_run:
        print(
            "[DRY-RUN][ROW] "
            f"file={source.source_file_id} row={input_row_number} out={output_row_number} "
            f"area={area.area_name or 'UNKNOWN'} date={parsed_date.date_start or 'UNKNOWN'} "
            f"measure={measure_column or ''} status={status}"
        )
        return

    conn.execute(
        """
        INSERT OR IGNORE INTO normalised_csv_rows (
            source_id,
            source_file_id,
            input_file,
            input_row_number,
            output_row_number,
            input_row_hash,

            measure_column,
            measure_name,
            measure_value,

            area_kind,
            area_code,
            area_name,
            area_raw,
            area_confidence,
            area_reason,

            date_start,
            date_end,
            date_precision,
            date_raw,
            date_confidence,
            date_reason,

            normalizer_status,
            normalizer_errors,
            rule_source,
            rule_confidence
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source.source_id,
            source.source_file_id,
            source.file_path,
            input_row_number,
            output_row_number,
            row_hash,
            measure_column,
            measure_name,
            measure_value,
            area.area_kind,
            area.area_code,
            area.area_name,
            area.area_raw,
            area.area_confidence,
            area.area_reason,
            parsed_date.date_start,
            parsed_date.date_end,
            parsed_date.date_precision,
            parsed_date.date_raw,
            parsed_date.date_confidence,
            parsed_date.date_reason,
            status,
            "; ".join(errors) if errors else None,
            rule.source,
            rule.confidence,
        ),
    )


def iter_csv_rows(path: Path) -> tuple[list[str], Any, str]:
    encoding = detect_encoding(path)
    dialect = sniff_dialect(path, encoding)
    handle = path.open("r", encoding=encoding, errors="replace", newline="")
    reader = csv.DictReader(handle, dialect=dialect)
    headers = [header or "" for header in (reader.fieldnames or [])]
    return headers, reader, encoding


def process_file(
    conn: sqlite3.Connection,
    source: SourceFile,
    dry_run: bool,
    force: bool,
    commit_every: int,
    error_records: list[dict[str, Any]] | None = None,
) -> tuple[int, int]:
    path = Path(source.file_path)

    if not path.exists():
        insert_error(
            conn,
            source,
            input_row_number=None,
            stage="file",
            error_code="file_not_found",
            error_message=f"CSV file does not exist: {path}",
            dry_run=dry_run,
            error_records=error_records,
        )
        return 0, 1

    if already_processed(conn, source.source_file_id, source.file_path, force=force):
        print(f"[SKIP] already processed source_file_id={source.source_file_id} path={path}")
        return 0, 0

    path_hash = file_hash(path)
    headers, sample_rows, _encoding = read_sample_rows(path)
    if not headers:
        insert_error(
            conn,
            source,
            input_row_number=None,
            stage="profile",
            error_code="no_headers",
            error_message="CSV has no headers.",
            dry_run=dry_run,
            error_records=error_records,
        )
        return 0, 1

    rule = infer_mapping_rule(source, headers, sample_rows)
    fallback_date = normalise_date_from_description(source.source_description)

    if dry_run:
        print(
            "[DRY-RUN] fallback date for "
            f"file={source.source_file_id}: "
            f"{fallback_date.date_start or 'UNKNOWN'} "
            f"precision={fallback_date.date_precision} "
            f"raw={fallback_date.date_raw!r}"
        )

    store_mapping_rule(conn, source, path_hash, rule, dry_run=dry_run)

    if not rule.area_columns:
        insert_error(
            conn,
            source,
            input_row_number=None,
            stage="mapping",
            error_code="area_columns_not_found",
            error_message="Could not infer area columns.",
            error_detail=rule.reason,
            dry_run=dry_run,
            error_records=error_records,
        )

    if not rule.date_columns and not any(
        normalise_date(header).date_precision != "unknown" for header in headers
    ):
        insert_error(
            conn,
            source,
            input_row_number=None,
            stage="mapping",
            error_code="date_columns_not_found",
            error_message="Could not infer date columns or date-bearing measure headers.",
            error_detail=rule.reason,
            dry_run=dry_run,
            error_records=error_records,
        )

    rows_written = 0
    errors_written = 0
    output_row_number = 0

    csv_headers, reader, _encoding = iter_csv_rows(path)
    measure_columns = rule.measure_columns

    if not measure_columns:
        excluded = set(rule.area_columns) | set(rule.date_columns) | set(rule.skip_columns)
        measure_columns = [header for header in csv_headers if header not in excluded]

    try:
        for input_row_number, row in enumerate(reader, start=2):
            safe_row = {str(k or ""): str(v or "") for k, v in row.items()}
            row_hash = stable_hash(row_to_hashable_json(safe_row))
            area = normalise_area(safe_row, rule)

            target_measure_columns = measure_columns or [None]
            row_error_logged = False

            for measure_column in target_measure_columns:
                parsed_date = normalise_date_for_row(
                    safe_row,
                    rule,
                    measure_column,
                    fallback_date=fallback_date,
                )
                errors: list[str] = []

                if area.area_kind == "unknown":
                    errors.append("area_not_normalised")
                elif area.area_kind != "london_borough":
                    errors.append(f"area_aggregate_or_non_borough:{area.area_name or area.area_kind}")

                if parsed_date.date_precision == "unknown":
                    errors.append("date_not_normalised")

                status = "ok" if not errors else "needs_review"

                if measure_column is None:
                    measure_value = None
                    measure_name = None
                else:
                    measure_value = safe_row.get(measure_column)
                    measure_name = measure_column

                    if is_nullish(measure_value):
                        continue

                output_row_number += 1

                insert_normalised_row(
                    conn=conn,
                    source=source,
                    input_row_number=input_row_number,
                    output_row_number=output_row_number,
                    row_hash=row_hash,
                    measure_column=measure_column,
                    measure_name=measure_name,
                    measure_value=measure_value,
                    area=area,
                    parsed_date=parsed_date,
                    status=status,
                    errors=errors,
                    rule=rule,
                    dry_run=dry_run,
                )
                rows_written += 1

                if errors and not row_error_logged:
                    errors_written += 1
                    row_error_logged = True
                    insert_error(
                        conn,
                        source,
                        input_row_number=input_row_number,
                        stage="row",
                        error_code="normalisation_incomplete",
                        error_message=", ".join(errors),
                        error_detail=(
                            f"area={area.area_reason}; "
                            f"date={parsed_date.date_reason}; "
                            f"first_measure_column={measure_column}"
                        ),
                        row=safe_row,
                        dry_run=dry_run,
                        error_records=error_records,
                    )

            if not dry_run and rows_written % commit_every == 0:
                conn.commit()

    except Exception as exc:  # noqa: BLE001
        errors_written += 1
        insert_error(
            conn,
            source,
            input_row_number=None,
            stage="process",
            error_code="unhandled_exception",
            error_message=str(exc),
            error_detail=traceback.format_exc(),
            dry_run=dry_run,
            error_records=error_records,
        )

    finally:
        if hasattr(reader, "reader") and hasattr(reader.reader, "close"):
            reader.reader.close()

    if not dry_run:
        conn.commit()

    return rows_written, errors_written


def run_self_test() -> int:
    test_cases = [
        ("City of London", "E09000001", "City of London"),
        ("Hammersmith & Fulham", "E09000013", "Hammersmith and Fulham"),
        ("Royal Borough of Greenwich", "E09000011", "Greenwich"),
        ("Westminster", "E09000033", "Westminster"),
        ("E09000022", "E09000022", "Lambeth"),
    ]

    for raw, expected_code, expected_name in test_cases:
        area = normalise_area_from_value(raw)
        assert area.area_code == expected_code, (raw, area)
        assert area.area_name == expected_name, (raw, area)

    date_cases = [
        ("1991", "1991-01-01", "1991-12-31", "year"),
        ("2020-2022", "2020-01-01", "2022-12-31", "year_range"),
        ("Q2 2021", "2021-04-01", "2021-06-30", "quarter"),
        ("2021/22", "2021-04-01", "2022-03-31", "financial_year"),
        ("March 2020", "2020-03-01", "2020-03-31", "month"),
    ]

    for raw, expected_start, expected_end, expected_precision in date_cases:
        parsed = normalise_date(raw)
        assert parsed.date_start == expected_start, (raw, parsed)
        assert parsed.date_end == expected_end, (raw, parsed)
        assert parsed.date_precision == expected_precision, (raw, parsed)

    print("[OK] self-test passed")
    return 0


def write_error_log(error_records: list[dict[str, Any]], path: str) -> None:
    target = Path(path)
    if not error_records:
        target.unlink(missing_ok=True)
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "source_file_id",
                "file_path",
                "input_row_number",
                "stage",
                "error_code",
                "error_message",
                "error_detail",
                "row_json",
            ],
        )
        writer.writeheader()
        for record in error_records:
            writer.writerow(record)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metadata-db", default=DEFAULT_METADATA_DB)
    parser.add_argument("--csv-root", default=DEFAULT_CSV_ROOT)
    parser.add_argument("--limit-files", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--commit-every", type=int, default=500)
    parser.add_argument("--error-log", default=None, help="CSV file path for collected error records.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.self_test:
        return run_self_test()

    project_root = Path.cwd()
    load_env(project_root)

    db_path = Path(args.metadata_db)
    if not db_path.exists():
        print(f"[FATAL] metadata DB does not exist: {db_path}", file=sys.stderr)
        return 2

    conn = connect_db(db_path)
    ensure_output_schema(conn)

    source_files = fetch_source_files(conn, args.limit_files)
    print(f"[INFO] files selected: {len(source_files)}")
    print(f"[INFO] LLM7 enabled: {llm_available()}")
    print(f"[INFO] dry-run: {args.dry_run}")

    total_rows = 0
    total_errors = 0
    error_records: list[dict[str, Any]] = []

    for index, source in enumerate(source_files, start=1):
        print(
            f"[INFO] [{index}/{len(source_files)}] "
            f"source_file_id={source.source_file_id} path={source.file_path}"
        )

        try:
            rows, errors = process_file(
                conn=conn,
                source=source,
                dry_run=args.dry_run,
                force=args.force,
                commit_every=args.commit_every,
                error_records=error_records,
            )
            total_rows += rows
            total_errors += errors
            print(
                f"[INFO] done source_file_id={source.source_file_id} "
                f"rows={rows} errors={errors}"
            )

        except KeyboardInterrupt:
            print("[FATAL] interrupted by user", file=sys.stderr)
            return 130

        except Exception as exc:  # noqa: BLE001
            total_errors += 1
            insert_error(
                conn,
                source,
                input_row_number=None,
                stage="file",
                error_code="file_failed",
                error_message=str(exc),
                error_detail=traceback.format_exc(),
                dry_run=args.dry_run,
                error_records=error_records,
            )
            if not args.dry_run:
                conn.commit()
            print(f"[ERROR] failed source_file_id={source.source_file_id}: {exc}")

    print(f"[DONE] rows_written={total_rows} errors={total_errors}")
    if args.error_log:
        write_error_log(error_records, args.error_log)
        print(f"[DONE] error-log={args.error_log} records={len(error_records)}")
    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

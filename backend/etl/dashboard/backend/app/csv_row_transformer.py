from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
from calendar import monthrange
import re
from typing import Any

from .csv_preview import iter_csv_rows
from .database import (
    clear_csv_row_transformations,
    connect,
    csv_row_transformation_stats,
    get_csv_file,
    get_csv_transformation_plan,
    init_db,
    insert_csv_row_transformations,
    list_csv_file_ids_for_row_transformation,
    list_london_borough_boundaries,
)
from .transformation_schema import RULE_SCHEMA_VERSION


BATCH_SIZE = 1000


@dataclass(slots=True)
class RowTransformationOptions:
    limit: int | None = None
    retry: bool = False
    csv_file_id: int | None = None


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _plan_json_object(plan: dict[str, Any], json_key: str, legacy_key: str) -> dict[str, Any]:
    return _json_object(plan.get(json_key) if plan.get(json_key) is not None else plan.get(legacy_key))


def _normalise_name(value: str) -> str:
    normalised = value.lower().replace("&", " and ")
    normalised = re.sub(r"\bcity of westminster\b", "westminster", normalised)
    normalised = re.sub(r"\b(city of )?westminster city\b", "westminster", normalised)
    normalised = re.sub(r"\broyal borough of\b", " ", normalised)
    normalised = re.sub(r"\blondon borough of\b", " ", normalised)
    normalised = re.sub(r"\bborough of\b", " ", normalised)
    return re.sub(r"[^a-z0-9]+", " ", normalised).strip()


def _is_non_london_scope(text: str) -> bool:
    normalised = _normalise_name(text)
    if normalised in {"city london", "city of london"}:
        return False
    exact_non_london = {
        "london",
        "england",
        "uk",
        "uk wide",
        "englandwide",
        "england wide",
    }
    if normalised in exact_non_london:
        return True
    if normalised.startswith("all london") or normalised.startswith("greater london"):
        return True
    if normalised.startswith("total london") or normalised.startswith("entire london"):
        return True
    if normalised.startswith("all england") or normalised.startswith("all uk"):
        return True
    return any(
        phrase in normalised
        for phrase in {
            "all london",
            "greater london",
            "londonwide",
            "london wide",
            "england",
            "england-wide",
            "englandwide",
            "uk",
            "united kingdom",
            "ukwide",
            "uk wide",
            "total london",
            "entire london",
            "all england",
            "all uk",
            "all greater london",
        }
    )


def _borough_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for boundary in list_london_borough_boundaries()["items"]:
        name = str(boundary["borough_name"])
        lookup[_normalise_name(name)] = name
        code = boundary.get("borough_code")
        if code:
            lookup[_normalise_name(str(code))] = name
    lookup["city"] = "City of London"
    lookup["city of london"] = "City of London"
    lookup["westminster city"] = "Westminster"
    lookup["kensington chelsea"] = "Kensington and Chelsea"
    lookup["richmond"] = "Richmond upon Thames"
    lookup["kingston"] = "Kingston upon Thames"
    lookup["barking"] = "Barking and Dagenham"
    lookup["barking dagenham"] = "Barking and Dagenham"
    return lookup


def _normalise_borough(value: Any, lookup: dict[str, str]) -> str | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if _is_non_london_scope(text):
        return None
    normalised = _normalise_name(text)
    if normalised in lookup:
        return lookup[normalised]
    for key, borough_name in lookup.items():
        if key and len(key) >= 8 and key in normalised:
            return borough_name
    if normalised.startswith("e09") or normalised.startswith("e090"):
        compact = re.sub(r"[^a-z0-9]+", "", normalised)
        if compact in lookup:
            return lookup[compact]
    return None


def _normalise_borough_with_reason(
    value: Any,
    lookup: dict[str, str],
) -> tuple[str | None, str | None, str | None]:
    text = "" if value is None else str(value).strip()
    if not text:
        return None, "empty_borough_value", None
    if _is_non_london_scope(text):
        return None, "non_london_scope", f"{text}"
    normalised = _normalise_name(text)
    if normalised in lookup:
        return lookup[normalised], None, text
    for key, borough_name in lookup.items():
        if key and len(key) >= 8 and key in normalised:
            return borough_name, None, text
    if normalised.startswith("e09") or normalised.startswith("e090"):
        compact = re.sub(r"[^a-z0-9]+", "", normalised)
        if compact in lookup:
            return lookup[compact], None, text
    return None, "unmatched_borough_value", f"{text}"


def _parse_year(value: Any) -> int | None:
    text = "" if value is None else str(value).strip()
    match = re.search(r"\b(19|20)\d{2}\b", text)
    if not match:
        return None
    return int(match.group(0))


def _parse_month(value: Any) -> int | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{1,2}", text):
        month = int(text)
        return month if 1 <= month <= 12 else None
    lowered = text.lower()
    numeric_prefix = re.match(r"^(\d{1,2})\b", lowered)
    if numeric_prefix:
        month = int(numeric_prefix.group(1))
        if 1 <= month <= 12:
            return month
    for month in range(1, 13):
        month_names = {
            datetime(2000, month, 1).strftime("%B").lower(),
            datetime(2000, month, 1).strftime("%b").lower(),
        }
        if lowered in month_names:
            return month
        if any(re.search(rf"\b{re.escape(month_name)}\b", lowered) for month_name in month_names):
            return month
    return None


def _parse_quarter(value: Any) -> int | None:
    text = "" if value is None else str(value).strip().lower()
    if re.fullmatch(r"[1-4]", text):
        return int(text)
    match = re.search(r"\bq([1-4])\b|\bquarter\s*([1-4])\b", text)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _period_for_parts(
    year: int,
    month: int | None = None,
    quarter: int | None = None,
    year_start_month: int = 1,
) -> tuple[str, str]:
    if quarter is not None:
        start_month_index = year_start_month - 1 + (quarter - 1) * 3
        end_month_index = start_month_index + 2
        start_year = year + start_month_index // 12
        end_year = year + end_month_index // 12
        start_month = start_month_index % 12 + 1
        end_month = end_month_index % 12 + 1
        end_day = monthrange(end_year, end_month)[1]
        return date(start_year, start_month, 1).isoformat(), date(end_year, end_month, end_day).isoformat()
    if month is not None:
        end_day = monthrange(year, month)[1]
        return date(year, month, 1).isoformat(), date(year, month, end_day).isoformat()
    if year_start_month != 1:
        end_month = year_start_month - 1
        end_year = year + 1
        end_day = monthrange(end_year, end_month)[1]
        return date(year, year_start_month, 1).isoformat(), date(end_year, end_month, end_day).isoformat()
    return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()


def _period_for_year_range(start_year: int, end_year: int, year_start_month: int = 1) -> tuple[str, str]:
    if year_start_month != 1:
        end_month = year_start_month - 1
        end_day = monthrange(end_year, end_month)[1]
        return date(start_year, year_start_month, 1).isoformat(), date(end_year, end_month, end_day).isoformat()
    return date(start_year, 1, 1).isoformat(), date(end_year, 12, 31).isoformat()


def _expand_two_digit_year(start_year: int, end_suffix: int) -> int:
    century = start_year // 100 * 100
    end_year = century + end_suffix
    if end_year < start_year:
        end_year += 100
    return end_year


def _clean_period_text(text: str) -> str:
    cleaned = text.strip()
    cleaned = cleaned.replace("\u2013", "-").replace("\u2014", "-")
    cleaned = re.sub(
        r"^(?:fy|financial year|academic year|year)(?![a-z])\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


def _parse_date_or_period(
    value: Any,
    granularity: str | None = None,
    year_start_month: int = 1,
) -> tuple[str | None, str | None]:
    text = _clean_period_text("" if value is None else str(value))
    if not text:
        return None, None

    if re.fullmatch(r"\d{5}", text):
        serial = int(text)
        if 20000 <= serial <= 80000:
            parsed = date(1899, 12, 30) + timedelta(days=serial)
            parsed_iso = parsed.isoformat()
            return parsed_iso, parsed_iso

    spaced_range = re.fullmatch(r"(.+?)\s+(?:to|-)\s+(.+)", text, flags=re.IGNORECASE)
    if spaced_range:
        start, _ = _parse_date_or_period(spaced_range.group(1), granularity, year_start_month)
        end_start, end = _parse_date_or_period(spaced_range.group(2), granularity, year_start_month)
        if start and (end or end_start):
            return start, end or end_start

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            parsed = date.fromisoformat(text).isoformat()
            return parsed, parsed
        except ValueError:
            return None, None

    if re.fullmatch(r"\d{4}", text):
        return _period_for_parts(int(text), year_start_month=year_start_month)

    nhs_period_match = re.fullmatch(r"Y(\d{2})Q([0-4])", text, flags=re.IGNORECASE)
    if nhs_period_match:
        year = 2000 + int(nhs_period_match.group(1))
        raw_quarter = int(nhs_period_match.group(2))
        quarter = 1 if raw_quarter == 0 else raw_quarter
        return _period_for_parts(year, quarter=quarter)

    quarter_match = re.fullmatch(r"((?:19|20)\d{2})\s*[-/ ]?\s*Q([1-4])", text, flags=re.IGNORECASE)
    if quarter_match:
        return _period_for_parts(int(quarter_match.group(1)), quarter=int(quarter_match.group(2)))

    quarter_year_match = re.fullmatch(
        r"(?:Q([1-4])|quarter\s*([1-4]))\s*((?:19|20)\d{2})",
        text,
        flags=re.IGNORECASE,
    )
    if quarter_year_match:
        quarter = int(quarter_year_match.group(1) or quarter_year_match.group(2))
        return _period_for_parts(int(quarter_year_match.group(3)), quarter=quarter)

    month_match = re.fullmatch(r"((?:19|20)\d{2})[-/](\d{1,2})", text)
    if month_match:
        month = int(month_match.group(2))
        if 1 <= month <= 12:
            return _period_for_parts(int(month_match.group(1)), month=month)

    fiscal_match = re.fullmatch(r"((?:19|20)\d{2})\s*[-/]\s*(\d{2})", text)
    if fiscal_match:
        start_year = int(fiscal_match.group(1))
        end_year = _expand_two_digit_year(start_year, int(fiscal_match.group(2)))
        return _period_for_year_range(start_year, end_year, year_start_month=year_start_month if year_start_month != 1 else 4)

    year_range_match = re.fullmatch(r"((?:19|20)\d{2})\s*(?:-|/|to)\s*((?:19|20)\d{2})", text, flags=re.IGNORECASE)
    if year_range_match:
        start_year = int(year_range_match.group(1))
        end_year = int(year_range_match.group(2))
        return _period_for_year_range(start_year, end_year, year_start_month=year_start_month)

    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%m/%d/%Y",
        "%m-%d-%Y",
        "%m/%d/%y",
        "%m-%d-%y",
        "%d %B %Y",
        "%d %b %Y",
        "%d %B %y",
        "%d %b %y",
        "%B %Y",
        "%b %Y",
        "%B %y",
        "%b %y",
        "%B-%Y",
        "%b-%Y",
        "%B-%y",
        "%b-%y",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if fmt in {
            "%B %Y",
            "%b %Y",
            "%B %y",
            "%b %y",
            "%B-%Y",
            "%b-%Y",
            "%B-%y",
            "%b-%y",
        } or granularity == "month":
            return _period_for_parts(parsed.year, month=parsed.month)
        parsed_iso = parsed.date().isoformat()
        return parsed_iso, parsed_iso

    return None, None


def _first_existing_column(row: dict[str, str], columns: list[Any]) -> str | None:
    for column in columns:
        name = str(column)
        if name in row:
            return name
    return None


def _named_column(row: dict[str, str], output: dict[str, Any], key: str) -> str | None:
    value = output.get(key)
    if isinstance(value, str) and value in row:
        return value
    return None


def _header_contains_period(header: str) -> bool:
    text = _clean_period_text(header)
    if re.search(r"(?:19|20)\d{2}\s*[-/]\s*\d{2}(?!\d)", text):
        return True
    if re.search(r"(?:^|[^0-9])(?:19|20)\d{2}(?:$|[^0-9])", text):
        return True
    return bool(re.search(r"Y\d{2}Q[0-4]", text, flags=re.IGNORECASE))


def _looks_like_wide_metric_date_columns(row: dict[str, str], columns: list[Any]) -> bool:
    existing_columns = [str(column) for column in columns if str(column) in row]
    if len(existing_columns) < 2:
        return False
    dated_headers = [column for column in existing_columns if _header_contains_period(column)]
    if len(dated_headers) < 2:
        return False
    parseable_values = [
        column
        for column in dated_headers
        if all(_parse_date_or_period(row.get(column)))
    ]
    return len(parseable_values) == 0


def _parse_unique_embedded_nhs_period(row: dict[str, str]) -> tuple[str | None, str | None]:
    matches: list[tuple[str, str]] = []
    for value in row.values():
        text = "" if value is None else str(value)
        exact_match = re.fullmatch(r"Y\d{2}Q[0-4]", text.strip(), flags=re.IGNORECASE)
        if exact_match:
            matches.append((exact_match.group(0).upper(), "exact"))
            continue
        for embedded_match in re.finditer(r"Y\d{2}Q[0-4]", text, flags=re.IGNORECASE):
            matches.append((embedded_match.group(0).upper(), "embedded"))

    distinct_exact = {match for match, match_type in matches if match_type == "exact"}
    if len(distinct_exact) == 1:
        return _parse_date_or_period(next(iter(distinct_exact)))

    distinct_all = {match for match, _ in matches}
    if len(distinct_all) == 1:
        return _parse_date_or_period(next(iter(distinct_all)))

    return None, None


def _year_start_month(output: dict[str, Any]) -> int:
    value = output.get("year_range_start_month")
    if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 12:
        return value
    return 1


def _date_values(row: dict[str, str], date_rule: dict[str, Any]) -> tuple[str | None, str | None, str, str | None]:
    status = date_rule.get("status")
    output = _json_object(date_rule.get("output"))
    granularity = output.get("date_granularity") if isinstance(output.get("date_granularity"), str) else None
    year_start_month = _year_start_month(output)
    if status == "not_identifiable":
        return None, None, "not_identifiable", None

    if status == "file_constant":
        start, inferred_end = _parse_date_or_period(output.get("start_date_expression"), granularity, year_start_month)
        explicit_end_start, explicit_end = _parse_date_or_period(output.get("end_date_expression"), granularity, year_start_month)
        end = explicit_end or explicit_end_start or inferred_end or start
        if start and end:
            return start, end, "success", None
        return None, None, "error", "File-level date rule did not contain parseable dates"

    if status == "row_rule":
        start_column = _named_column(row, output, "start_date_column")
        end_column = _named_column(row, output, "end_date_column")
        if start_column and end_column:
            start, _ = _parse_date_or_period(row.get(start_column), granularity, year_start_month)
            end_start, end = _parse_date_or_period(row.get(end_column), granularity, year_start_month)
            if start and (end or end_start):
                return start, end or end_start, "success", None
            return None, None, "error", f"Could not parse date range columns: {start_column}, {end_column}"

        year_column = _named_column(row, output, "year_column")
        if year_column:
            year = _parse_year(row.get(year_column))
            month_column = _named_column(row, output, "month_column")
            quarter_column = _named_column(row, output, "quarter_column")
            month = _parse_month(row.get(month_column)) if month_column else None
            quarter = _parse_quarter(row.get(quarter_column)) if quarter_column else None
            if year:
                start, end = _period_for_parts(
                    year,
                    month=month,
                    quarter=quarter,
                    year_start_month=year_start_month,
                )
                return start, end, "success", None
            return None, None, "error", f"Could not parse year column: {year_column}"

        date_column = _named_column(row, output, "date_column")
        if date_column:
            start, end = _parse_date_or_period(row.get(date_column), granularity, year_start_month)
            if start and end:
                return start, end, "success", None
            fallback_start, fallback_end = _parse_unique_embedded_nhs_period(row)
            if fallback_start and fallback_end:
                return fallback_start, fallback_end, "success", None
            return None, None, "error", f"Could not parse date column: {date_column}"

        columns = date_rule.get("columns") if isinstance(date_rule.get("columns"), list) else []
        if _looks_like_wide_metric_date_columns(row, columns):
            return (
                None,
                None,
                "not_identifiable",
                "Date is encoded across multiple metric columns; raw row needs unpivoting before a single date can be assigned",
            )
        if len(columns) >= 2:
            start_column = str(columns[0])
            end_column = str(columns[1])
            start, _ = _parse_date_or_period(row.get(start_column), granularity, year_start_month)
            end_start, end = _parse_date_or_period(row.get(end_column), granularity, year_start_month)
            if start and (end or end_start):
                return start, end or end_start, "success", None
            return None, None, "error", f"Could not parse date range columns: {start_column}, {end_column}"
        column = _first_existing_column(row, columns)
        if column:
            start, end = _parse_date_or_period(row.get(column), granularity, year_start_month)
            if start and end:
                return start, end, "success", None
            return None, None, "error", f"Could not parse date column: {column}"
        return None, None, "unsupported", "Date row rule does not name an existing column"

    return None, None, "unsupported", f"Unsupported date rule status: {status}"


def _borough_value(
    row: dict[str, str],
    borough_rule: dict[str, Any],
    lookup: dict[str, str],
) -> tuple[str | None, str, str | None]:
    status = borough_rule.get("status")
    output = _json_object(borough_rule.get("output"))
    if status == "not_identifiable":
        return None, "not_identifiable", None

    if status == "file_constant":
        borough, status_code, borough_value = _normalise_borough_with_reason(
            output.get("constant_borough"),
            lookup,
        )
        if borough:
            return borough, "success", None
        if status_code == "non_london_scope":
            return None, "not_london_borough", f"File constant maps to non-London scope: {borough_value}"
        return None, "error", "File-level borough rule did not contain a known London borough"

    if status == "row_rule":
        columns = borough_rule.get("columns") if isinstance(borough_rule.get("columns"), list) else []
        column = _named_column(row, output, "borough_column") or _first_existing_column(row, columns)
        if not column:
            return None, "unsupported", "Borough row rule does not name an existing column"
        borough, status_code, borough_value = _normalise_borough_with_reason(
            row.get(column),
            lookup,
        )
        if borough:
            return borough, "success", None
        if status_code == "non_london_scope":
            return None, "not_london_borough", f"Value maps to non-London scope: {borough_value}"
        return None, "not_london_borough", f"Value is not a London borough: {borough_value}"

    return None, "unsupported", f"Unsupported borough rule status: {status}"


def _row_hash(row: dict[str, str]) -> str:
    payload = json.dumps(row, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _combined_status(date_status: str, borough_status: str) -> str:
    if date_status == "success" and borough_status == "success":
        return "success"
    if borough_status not in {"success"}:
        return "error"
    if date_status in {"error", "unsupported"} or borough_status in {"error", "unsupported"}:
        return "error"
    return "partial"


def apply_csv_row_transformations(csv_file_id: int, *, replace: bool = True) -> dict[str, Any]:
    init_db()
    csv_file = get_csv_file(csv_file_id)
    if csv_file is None:
        raise ValueError(f"CSV file {csv_file_id} does not exist")
    if csv_file.get("status") != 1 or not csv_file.get("local_path"):
        raise ValueError(f"CSV file {csv_file_id} has not been downloaded successfully")

    plan = get_csv_transformation_plan(csv_file_id)
    if plan is None or plan.get("status") != "success":
        raise ValueError(f"CSV file {csv_file_id} does not have a successful transformation plan")
    if int(plan.get("rule_schema_version") or 1) < RULE_SCHEMA_VERSION:
        raise ValueError(
            f"CSV file {csv_file_id} has an outdated transformation plan schema; replan before applying rows"
        )
    current_hash = csv_file.get("content_hash")
    if current_hash and plan.get("csv_content_hash") != current_hash:
        raise ValueError(f"CSV file {csv_file_id} has changed since its transformation plan was created")

    date_rule = _plan_json_object(plan, "date_range_rule_json", "date_range_rule")
    borough_rule = _plan_json_object(plan, "borough_rule_json", "borough_rule")
    if not date_rule:
        raise ValueError(f"CSV file {csv_file_id} has an empty date range transformation rule")
    if not borough_rule:
        raise ValueError(f"CSV file {csv_file_id} has an empty borough transformation rule")
    borough_lookup = _borough_lookup()
    transformation_plan_id = int(plan["id"])
    pending_rows: list[dict[str, Any]] = []
    counts = {"success": 0, "partial": 0, "error": 0}

    with connect() as connection:
        if replace:
            clear_csv_row_transformations(connection, csv_file_id=csv_file_id)

        for row_number, _, row in iter_csv_rows(str(csv_file["local_path"])):
            date_start, date_end, date_status, date_error = _date_values(row, date_rule)
            borough_name, borough_status, borough_error = _borough_value(row, borough_rule, borough_lookup)
            status = _combined_status(date_status, borough_status)
            counts[status] += 1
            error_parts = [part for part in (date_error, borough_error) if part]
            pending_rows.append(
                {
                    "csv_file_id": csv_file_id,
                    "transformation_plan_id": transformation_plan_id,
                    "row_number": row_number,
                    "source_row_hash": _row_hash(row),
                    "source_row": row,
                    "date_start": date_start,
                    "date_end": date_end,
                    "borough_name": borough_name,
                    "date_status": date_status,
                    "borough_status": borough_status,
                    "status": status,
                    "error_message": "; ".join(error_parts) or None,
                }
            )
            if len(pending_rows) >= BATCH_SIZE:
                insert_csv_row_transformations(connection, rows=pending_rows)
                pending_rows = []

        if pending_rows:
            insert_csv_row_transformations(connection, rows=pending_rows)

    return {
        "csv_file_id": csv_file_id,
        "rows": sum(counts.values()),
        **counts,
    }


def apply_pending_csv_row_transformations(options: RowTransformationOptions | None = None) -> dict[str, Any]:
    options = options or RowTransformationOptions()
    init_db()
    if options.csv_file_id is not None:
        csv_file_ids = [options.csv_file_id]
    else:
        csv_file_ids = list_csv_file_ids_for_row_transformation(
            retry=options.retry,
            limit=options.limit,
        )

    items = [apply_csv_row_transformations(csv_file_id, replace=True) for csv_file_id in csv_file_ids]
    return {
        "total_files": len(items),
        "total_rows": sum(item["rows"] for item in items),
        "success_rows": sum(item["success"] for item in items),
        "partial_rows": sum(item["partial"] for item in items),
        "error_rows": sum(item["error"] for item in items),
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply saved CSV transformation plans to CSV rows.")
    parser.add_argument("--csv-file-id", type=int, default=None, help="Apply one specific CSV file plan.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of planned CSV files to apply.")
    parser.add_argument("--retry", action="store_true", help="Re-apply files that already have row outputs.")
    parser.add_argument("--stats", type=int, default=None, metavar="CSV_FILE_ID", help="Print row transformation stats for a CSV file.")
    args = parser.parse_args()

    if args.stats is not None:
        result = csv_row_transformation_stats(args.stats)
    else:
        result = apply_pending_csv_row_transformations(
            RowTransformationOptions(
                limit=args.limit,
                retry=args.retry,
                csv_file_id=args.csv_file_id,
            )
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

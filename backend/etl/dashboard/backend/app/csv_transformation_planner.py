from __future__ import annotations

import argparse
from datetime import date
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from .config import get_settings
from .csv_preview import preview_csv
from .database import (
    connect,
    get_csv_file_with_source,
    init_db,
    list_london_borough_boundaries,
    list_csv_file_ids_for_transformation_planning,
    upsert_csv_transformation_plan,
)
from .transformation_schema import RULE_SCHEMA_VERSION


MAX_ERROR_CHARS = 1800
MAX_CELL_CHARS = 240


@dataclass(slots=True)
class TransformationPlanningOptions:
    limit: int | None = None
    retry_errors: bool = False
    retry_outdated_successes: bool = False
    sample_rows: int = 8
    max_attempts: int = 3
    dry_run: bool = False


def _truncate(value: Any, max_chars: int = MAX_CELL_CHARS) -> str:
    text = "" if value is None else str(value)
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}..."


def _compact_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {str(key): _truncate(value) for key, value in row.items()}
        for row in rows
    ]


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _context_for_csv(csv_file_id: int, sample_rows: int) -> dict[str, Any]:
    csv_file = get_csv_file_with_source(csv_file_id)
    if csv_file is None:
        raise ValueError(f"CSV file {csv_file_id} does not exist")
    if csv_file.get("status") != 1 or not csv_file.get("local_path"):
        raise ValueError(f"CSV file {csv_file_id} has not been downloaded successfully")

    preview = preview_csv(
        str(csv_file["local_path"]),
        page=1,
        page_size=sample_rows,
        count_total=False,
    )
    borough_boundaries = list_london_borough_boundaries()["items"]
    borough_names = [str(item["borough_name"]) for item in borough_boundaries]
    borough_codes = [
        str(item["borough_code"])
        for item in borough_boundaries
        if item.get("borough_code")
    ]
    borough_records = [
        {
            "borough_name": item["borough_name"],
            "borough_code": item.get("borough_code"),
        }
        for item in borough_boundaries
    ]
    return {
        "csv_file_id": csv_file_id,
        "dataset": {
            "title": csv_file.get("source_title"),
            "description": _truncate(csv_file.get("source_description"), 1600),
            "organisation_name": csv_file.get("source_organisation_name"),
            "url": csv_file.get("source_url"),
            "tags": _json_list(csv_file.get("source_tags_json")),
            "categories": _json_list(csv_file.get("source_categories_json")),
        },
        "csv_resource": {
            "title": csv_file.get("title"),
            "description": _truncate(csv_file.get("description"), 1000),
            "url": csv_file.get("csv_url"),
            "file_name": csv_file.get("file_name"),
            "content_hash": csv_file.get("content_hash"),
        },
        "headers": preview["columns"],
        "sample_rows": _compact_rows(preview["rows"]),
        "valid_london_boroughs": borough_names,
        "valid_london_borough_codes": borough_codes,
        "valid_london_borough_records": borough_records,
    }


def _system_prompt() -> str:
    return (
        "You define reusable row-level transformation rules for London Datastore CSV files. "
        "Return only valid JSON. Do not include markdown. "
        "The rules must be based only on dataset metadata, CSV resource metadata, headers, "
        "and sample rows. Do not invent columns. "
        "For dates, decide whether each row can be assigned a date range. If a row has one date, "
        "start and end should be the same. If the whole file describes one fixed date/range, "
        "describe that file-level constant rule. "
        "Inspect sample values before choosing a date column: a column named Period is not usable "
        "unless its sample values actually look like dates or periods. If another column contains "
        "period tokens such as Y09Q0, choose that column instead. "
        "If years or financial years appear only as repeated metric headers across many columns, "
        "do not create a row_rule from those metric columns because one raw row spans multiple dates; "
        "use date_range.status not_identifiable and mention that unpivoting would be required. "
        "For boroughs, decide whether the whole file is about one London borough, whether a "
        "specific column identifies the borough by name or borough code, or whether borough cannot be identified. "
        "If sample values or metadata suggest the file is London-wide, England-wide, UK-wide, "
        "or any other aggregate geography, set borough status to not_identifiable and do not return "
        "a constant/row value for London-wide aggregates. "
        "Do not invent a borough column. A column named Area, Borough, Code, New Code, OrgCode, "
        "or similar is only usable when sample values match valid London borough names or codes. "
        "Prefer explicit column names and deterministic parsing instructions over vague semantics. "
        "Use only valid_london_boroughs for constant borough values. "
        "Every output field ending with _column must be an exact CSV header string from headers, "
        "or null if unused. For file_constant date rules, start_date_expression and "
        "end_date_expression must be concrete ISO dates in YYYY-MM-DD format; for a single date, "
        "use the same date for both start and end."
    )


def _user_prompt(context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "task": "Create reusable transformation rules for assigning date ranges and London boroughs to every row in this CSV file later.",
            "required_json_shape": {
                "date_range": {
                    "status": "one of: row_rule, file_constant, not_identifiable",
                    "confidence": "number from 0 to 1",
                    "rule_description": "short deterministic rule or reason unavailable",
                    "columns": "array of header names used",
                    "output": {
                        "start_date_expression": "for file_constant: literal ISO YYYY-MM-DD start date; for row_rule: optional derivation text; else null",
                        "end_date_expression": "for file_constant: literal ISO YYYY-MM-DD end date, same as start for one date; for row_rule: optional derivation text; else null",
                        "date_granularity": "day/month/quarter/year/range/unknown",
                        "date_column": "single header containing a date/period, or null",
                        "start_date_column": "header containing range start, or null",
                        "end_date_column": "header containing range end, or null",
                        "year_column": "header containing year, or null",
                        "month_column": "header containing month number/name, or null",
                        "quarter_column": "header containing quarter, or null",
                        "year_range_start_month": "optional number 1-12 for year/fiscal/academic ranges; 1 calendar year, 4 financial year, 9 academic year",
                    },
                },
                "borough": {
                    "status": "one of: row_rule, file_constant, not_identifiable",
                    "confidence": "number from 0 to 1",
                    "rule_description": "short deterministic rule or reason unavailable",
                    "columns": "array of header names used",
                    "output": {
                        "borough_expression": "how to derive normalized London borough name, or null",
                        "constant_borough": "borough name if file_constant, else null",
                        "borough_column": "header containing borough name/code if row_rule, else null",
                    },
                },
                "summary": "short human-readable summary of both transformations",
                "warnings": "array of caveats",
            },
            "csv_context": context,
        },
        ensure_ascii=False,
    )


def _extract_content(response: dict[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM response does not contain choices")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response choice does not contain a message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM response message content is empty")
    return content.strip()


def _parse_json_content(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        payload = json.loads(content[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON response must be an object")
    return payload


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (str(item).strip() for item in value) if item]


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value).strip() or None


def _validate_confidence(value: Any, *, label: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label}.confidence must be a number from 0 to 1")
    if value < 0 or value > 1:
        raise ValueError(f"{label}.confidence must be between 0 and 1")


def _normalise_warnings(payload: dict[str, Any]) -> None:
    warnings = payload.get("warnings")
    if warnings is None:
        payload["warnings"] = []
        return
    if not isinstance(warnings, list):
        raise ValueError("LLM JSON response field warnings must be an array")
    payload["warnings"] = [str(warning) for warning in warnings]


def _normalise_borough_label(value: str) -> str:
    normalised = value.lower().replace("&", " and ")
    normalised = re.sub(r"\bcity of westminster\b", "westminster", normalised)
    normalised = re.sub(r"\b(city of )?westminster city\b", "westminster", normalised)
    normalised = re.sub(r"\broyal borough of\b", " ", normalised)
    normalised = re.sub(r"\blondon borough of\b", " ", normalised)
    normalised = re.sub(r"\bborough of\b", " ", normalised)
    return re.sub(r"[^a-z0-9]+", " ", normalised).strip()


def _normalise_header_reference(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def _infer_column_from_expression(expression: str, headers: set[str]) -> str | None:
    text = _normalise_header_reference(expression)
    if not text:
        return None
    candidates: list[tuple[int, str]] = []
    for header in headers:
        normalised_header = _normalise_header_reference(header)
        if normalised_header and normalised_header in text:
            candidates.append((len(normalised_header), header))
    if candidates:
        candidates.sort(reverse=True, key=lambda item: item[0])
        return candidates[0][1]

    header_by_words = [
        header for header in headers
        if f"column {str(header).lower()}" in text or f"{str(header).lower()} column" in text
    ]
    if len(header_by_words) == 1:
        return header_by_words[0]

    return None


def _infer_borough_rule_from_expression(context: dict[str, Any], rule: dict[str, Any]) -> None:
    output = rule.get("output")
    if not isinstance(output, dict):
        return
    if rule.get("status") != "not_identifiable":
        return
    expression = _optional_string(output.get("borough_expression"))
    if expression is None:
        return
    inferred = _infer_column_from_expression(
        expression,
        {str(header) for header in context["headers"]},
    )
    if inferred is None:
        return
    rule["status"] = "row_rule"
    if rule.get("rule_description") is None:
        rule["rule_description"] = "Inferred borough column from LLM expression."
    else:
        rule["rule_description"] = f"{rule['rule_description']} (inferred borough column from expression)."
    output["borough_column"] = inferred
    rule["columns"] = [inferred]
    rule.setdefault("confidence", 0.6)


def _infer_date_rule_from_expression(context: dict[str, Any], rule: dict[str, Any]) -> None:
    output = rule.get("output")
    if not isinstance(output, dict):
        return
    if rule.get("status") != "not_identifiable":
        return
    expression = _optional_string(output.get("start_date_expression"))
    if expression is None:
        return
    inferred = _infer_column_from_expression(
        expression,
        {str(header) for header in context["headers"]},
    )
    if inferred is None:
        return
    if inferred.lower().startswith("year"):
        rule["status"] = "row_rule"
        output["year_column"] = inferred
        output["date_column"] = None
        rule.setdefault("confidence", 0.6)
        if rule.get("rule_description") is None:
            rule["rule_description"] = "Inferred year column from LLM expression."
        else:
            rule["rule_description"] = f"{rule['rule_description']} (inferred date column from expression)."
        rule["columns"] = [inferred]
    elif inferred.lower().startswith("month"):
        rule["status"] = "row_rule"
        output["month_column"] = inferred
        output["date_column"] = None
        rule.setdefault("confidence", 0.6)
        if rule.get("rule_description") is None:
            rule["rule_description"] = "Inferred month column from LLM expression."
        else:
            rule["rule_description"] = f"{rule['rule_description']} (inferred date column from expression)."
        rule["columns"] = [inferred]
    elif inferred.lower().startswith("date") or "date" in inferred.lower():
        rule["status"] = "row_rule"
        output["date_column"] = inferred
        rule.setdefault("confidence", 0.6)
        if rule.get("rule_description") is None:
            rule["rule_description"] = "Inferred date column from LLM expression."
        else:
            rule["rule_description"] = f"{rule['rule_description']} (inferred date column from expression)."
        rule["columns"] = [inferred]


def _canonical_borough_value(value: str, boroughs: list[dict[str, Any]]) -> str | None:
    normalised_value = _normalise_borough_label(value)
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
    for borough in boroughs:
        borough_name = str(borough["borough_name"])
        if normalised_value == _normalise_borough_label(borough_name):
            return borough_name
        borough_code = borough.get("borough_code")
        if borough_code and normalised_value == _normalise_borough_label(str(borough_code)):
            return borough_name
    return None


def _looks_like_aggregate_scope(value: str) -> bool:
    normalised = _normalise_borough_label(value)
    if normalised in {"city london", "city of london"}:
        return False
    if normalised in {"london", "england", "uk", "united kingdom", "great britain"}:
        return True
    if normalised.startswith("all london") or normalised.startswith("all england") or normalised.startswith("all uk"):
        return True
    if normalised.startswith("greater london") or normalised.startswith("total london") or normalised.startswith("entire london"):
        return True
    if "london-wide" in normalised or "london wide" in normalised:
        return True
    if "england-wide" in normalised or "england wide" in normalised:
        return True
    if "uk-wide" in normalised or "uk wide" in normalised:
        return True
    if normalised in {"whole london", "london all", "all london boroughs", "all london borough"}:
        return True
    return False


def _validate_iso_date(value: Any, *, label: str) -> str:
    text = _optional_string(value)
    if text is None:
        raise ValueError(f"{label} is required")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{label} must be a concrete ISO date in YYYY-MM-DD format: {text}") from exc


def _validate_columns(
    *,
    label: str,
    output: dict[str, Any],
    output_keys: list[str],
    columns: list[str],
    known_headers: set[str],
) -> None:
    for column in columns:
        if column not in known_headers:
            raise ValueError(f"{label}.columns contains unknown header: {column}")
    for key in output_keys:
        column = _optional_string(output.get(key))
        if column is not None and column not in known_headers:
            raise ValueError(f"{label}.output.{key} contains unknown header: {column}")


def _normalise_header_reference(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _repair_column_references(
    *,
    rule: dict[str, Any],
    output_keys: list[str],
    known_headers: set[str],
) -> None:
    normalised_headers = {
        _normalise_header_reference(header): header
        for header in known_headers
    }
    repaired_columns: list[str] = []
    for column in _string_list(rule.get("columns")):
        if column in known_headers:
            repaired_columns.append(column)
            continue
        repaired = normalised_headers.get(_normalise_header_reference(column))
        if repaired is not None:
            repaired_columns.append(repaired)
    rule["columns"] = repaired_columns

    output = rule.get("output")
    if not isinstance(output, dict):
        return
    for key in output_keys:
        column = _optional_string(output.get(key))
        if column is None or column in known_headers:
            continue
        repaired = normalised_headers.get(_normalise_header_reference(column))
        output[key] = repaired


def _downgrade_unusable_row_rule(
    *,
    rule: dict[str, Any],
    column_keys: list[str],
    reason: str,
) -> None:
    if rule.get("status") != "row_rule":
        return
    output = rule.get("output")
    if not isinstance(output, dict):
        return
    if rule.get("columns") or any(_optional_string(output.get(key)) for key in column_keys):
        return
    rule["status"] = "not_identifiable"
    rule["confidence"] = 0
    rule["rule_description"] = reason


def _has_any_output_column(output: dict[str, Any], keys: list[str]) -> bool:
    return any(_optional_string(output.get(key)) for key in keys)


def _validate_optional_month(value: Any, *, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 1 or value > 12:
        raise ValueError(f"{label} must be an integer from 1 to 12")


def _validate_plan(payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    date_range = payload.get("date_range")
    borough = payload.get("borough")
    if not isinstance(date_range, dict):
        raise ValueError("LLM JSON response is missing object field: date_range")
    if not isinstance(borough, dict):
        raise ValueError("LLM JSON response is missing object field: borough")
    if not isinstance(date_range.get("output"), dict):
        date_range["output"] = {}
    if not isinstance(borough.get("output"), dict):
        borough["output"] = {}
    known_headers = set(str(header) for header in context["headers"])
    known_boroughs = context.get("valid_london_borough_records")
    if not isinstance(known_boroughs, list):
        known_boroughs = [{"borough_name": name, "borough_code": None} for name in context["valid_london_boroughs"]]
    for label, value in (("date_range", date_range), ("borough", borough)):
        status = value.get("status")
        if status not in {"row_rule", "file_constant", "not_identifiable"}:
            raise ValueError(f"{label}.status has invalid value: {status}")
        _validate_confidence(value.get("confidence"), label=label)
        if not isinstance(value.get("rule_description"), str):
            raise ValueError(f"{label}.rule_description must be a string")
        if not isinstance(value.get("output"), dict):
            raise ValueError(f"{label}.output must be an object")

    _infer_borough_rule_from_expression(context, borough)
    _infer_date_rule_from_expression(context, date_range)

    date_columns = _string_list(date_range.get("columns"))
    date_output = date_range["output"]
    date_column_keys = [
        "date_column",
        "start_date_column",
        "end_date_column",
        "year_column",
        "month_column",
        "quarter_column",
    ]
    _repair_column_references(
        rule=date_range,
        output_keys=date_column_keys,
        known_headers=known_headers,
    )
    _downgrade_unusable_row_rule(
        rule=date_range,
        column_keys=date_column_keys,
        reason="No exact CSV header can be used to derive row-level dates.",
    )
    date_columns = _string_list(date_range.get("columns"))
    _validate_columns(
        label="date_range",
        output=date_output,
        output_keys=date_column_keys,
        columns=date_columns,
        known_headers=known_headers,
    )
    _validate_optional_month(
        date_output.get("year_range_start_month"),
        label="date_range.output.year_range_start_month",
    )
    if date_range["status"] == "row_rule":
        has_date_column = _has_any_output_column(
            date_output,
            ["date_column", "year_column", "start_date_column"],
        )
        if not has_date_column and not date_columns:
            raise ValueError("date_range row_rule must name at least one usable date column")
        if (
            _optional_string(date_output.get("end_date_column"))
            and not _optional_string(date_output.get("start_date_column"))
        ):
            raise ValueError("date_range.output.end_date_column requires start_date_column")
    if date_range["status"] == "file_constant":
        start_date = _validate_iso_date(
            date_output.get("start_date_expression"),
            label="date_range.output.start_date_expression",
        )
        end_expression = _optional_string(date_output.get("end_date_expression"))
        if end_expression is not None:
            end_date = _validate_iso_date(
                end_expression,
                label="date_range.output.end_date_expression",
            )
            if end_date < start_date:
                raise ValueError("date_range.output.end_date_expression must be on or after start_date_expression")

    borough_columns = _string_list(borough.get("columns"))
    borough_output = borough["output"]
    _repair_column_references(
        rule=borough,
        output_keys=["borough_column"],
        known_headers=known_headers,
    )
    _downgrade_unusable_row_rule(
        rule=borough,
        column_keys=["borough_column"],
        reason="No exact CSV header can be used to derive a London borough.",
    )
    borough_columns = _string_list(borough.get("columns"))
    _validate_columns(
        label="borough",
        output=borough_output,
        output_keys=["borough_column"],
        columns=borough_columns,
        known_headers=known_headers,
    )
    if borough["status"] == "row_rule":
        if not _optional_string(borough_output.get("borough_column")) and not borough_columns:
            raise ValueError("borough row_rule must name a usable borough column")
    if borough["status"] == "file_constant":
        constant_borough = _optional_string(borough_output.get("constant_borough"))
        if not constant_borough:
            raise ValueError("borough file_constant requires output.constant_borough")
        canonical_borough = _canonical_borough_value(constant_borough, known_boroughs)
        if canonical_borough is None:
            if _looks_like_aggregate_scope(constant_borough):
                borough["status"] = "not_identifiable"
                borough["confidence"] = min(float(borough.get("confidence", 0.0)), 0.35)
                borough["rule_description"] = (
                    "File-level borough is aggregate geography (e.g., London-wide/England/UK), "
                    "so per-row borough mapping cannot be reliably derived."
                )
                borough_columns = []
                borough["columns"] = []
                borough_output["constant_borough"] = None
                borough_output["borough_column"] = None
            else:
                raise ValueError(f"borough.output.constant_borough is not a valid London borough: {constant_borough}")
        else:
            borough_output["constant_borough"] = canonical_borough

    if not isinstance(payload.get("summary"), str):
        raise ValueError("LLM JSON response is missing string field: summary")
    _normalise_warnings(payload)
    return payload


def _llm_messages(context: dict[str, Any], previous_errors: list[str]) -> list[dict[str, str]]:
    messages = [
        {"role": "system", "content": _system_prompt()},
        {"role": "user", "content": _user_prompt(context)},
    ]
    if previous_errors:
        messages.append(
            {
                "role": "user",
                "content": (
                    "Retry. The previous attempt failed with this truncated error. "
                    "Return corrected JSON only.\n"
                    + "\n".join(previous_errors[-2:])
                ),
            }
        )
    return messages


def _call_llm(messages: list[dict[str, str]]) -> dict[str, Any]:
    settings = get_settings()
    if not settings.llm7_token:
        raise RuntimeError("LLM7_TOKEN is missing from backend/.env or environment")

    endpoint = settings.llm7_api_base_url.rstrip("/") + "/chat/completions"
    schema_payload = {
        "type": "json_schema",
        "json_schema": {
            "name": "london_csv_transformation_plan",
            "strict": False,
            "schema": {"type": "object"},
        },
    }
    body = {
        "model": settings.llm7_model,
        "messages": messages,
        "temperature": 0,
        "response_format": schema_payload,
    }
    with httpx.Client(timeout=settings.llm7_request_timeout_seconds) as client:
        for preferred_format in (schema_payload, {"type": "json_object"}):
            payload = dict(body)
            payload["response_format"] = preferred_format
            response = client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {settings.llm7_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if response.status_code == 400 and preferred_format.get("type") == "json_schema":
                continue
            response.raise_for_status()
            return response.json()
    raise RuntimeError("LLM call did not return a successful response")


def plan_csv_transformation(
    csv_file_id: int,
    *,
    sample_rows: int = 8,
    max_attempts: int = 3,
    dry_run: bool = False,
) -> dict[str, Any]:
    context = _context_for_csv(csv_file_id, sample_rows)
    settings = get_settings()
    previous_errors: list[str] = []
    prompt_messages: list[dict[str, str]] = []

    if dry_run:
        return {
            "csv_file_id": csv_file_id,
            "status": "dry_run",
            "rule_schema_version": RULE_SCHEMA_VERSION,
            "context": context,
        }

    response_payload: dict[str, Any] | None = None
    parsed_plan: dict[str, Any] | None = None
    attempts = 0
    error_message: str | None = None

    for attempt in range(1, max(1, max_attempts) + 1):
        attempts = attempt
        prompt_messages = _llm_messages(context, previous_errors)
        try:
            response_payload = _call_llm(prompt_messages)
            parsed_plan = _validate_plan(
                _parse_json_content(_extract_content(response_payload)),
                context,
            )
            error_message = None
            break
        except Exception as exc:
            error_message = _truncate(f"{type(exc).__name__}: {exc}", MAX_ERROR_CHARS)
            previous_errors.append(error_message)

    if parsed_plan is None:
        llm_endpoint = settings.llm7_api_base_url.rstrip("/") + "/chat/completions"
        db_plan = {
            "status": "error",
            "attempts": attempts,
            "rule_schema_version": RULE_SCHEMA_VERSION,
            "csv_content_hash": context["csv_resource"].get("content_hash"),
            "model": settings.llm7_model,
            "llm_endpoint": llm_endpoint,
            "header": context["headers"],
            "sample_rows": context["sample_rows"],
            "prompt_messages": prompt_messages,
            "response": response_payload,
            "error_message": error_message,
        }
    else:
        llm_endpoint = settings.llm7_api_base_url.rstrip("/") + "/chat/completions"
        db_plan = {
            "status": "success",
            "attempts": attempts,
            "rule_schema_version": RULE_SCHEMA_VERSION,
            "csv_content_hash": context["csv_resource"].get("content_hash"),
            "model": settings.llm7_model,
            "llm_endpoint": llm_endpoint,
            "header": context["headers"],
            "sample_rows": context["sample_rows"],
            "prompt_messages": prompt_messages,
            "response": parsed_plan,
            "date_range_status": parsed_plan["date_range"]["status"],
            "date_range_rule": parsed_plan["date_range"],
            "borough_status": parsed_plan["borough"]["status"],
            "borough_rule": parsed_plan["borough"],
            "transformation_summary": parsed_plan["summary"],
            "error_message": None,
        }

    with connect() as connection:
        plan_id = upsert_csv_transformation_plan(
            connection,
            csv_file_id=csv_file_id,
            plan=db_plan,
        )

    return {
        "csv_file_id": csv_file_id,
        "plan_id": plan_id,
        "status": db_plan["status"],
        "attempts": attempts,
        "error_message": error_message,
    }


def plan_pending_csv_transformations(options: TransformationPlanningOptions | None = None) -> dict[str, Any]:
    options = options or TransformationPlanningOptions()
    init_db()
    csv_file_ids = list_csv_file_ids_for_transformation_planning(
        retry_errors=options.retry_errors,
        minimum_rule_schema_version=RULE_SCHEMA_VERSION if options.retry_outdated_successes else None,
        limit=options.limit,
    )
    results = []
    for csv_file_id in csv_file_ids:
        results.append(
            plan_csv_transformation(
                csv_file_id,
                sample_rows=options.sample_rows,
                max_attempts=options.max_attempts,
                dry_run=options.dry_run,
            )
        )
    return {
        "total": len(csv_file_ids),
        "success": sum(1 for result in results if result["status"] == "success"),
        "error": sum(1 for result in results if result["status"] == "error"),
        "items": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create LLM transformation plans for downloaded CSV files.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of CSV files to process.")
    parser.add_argument("--csv-file-id", type=int, default=None, help="Process one specific CSV file.")
    parser.add_argument("--retry-errors", action="store_true", help="Retry files with non-success plans.")
    parser.add_argument("--retry-outdated-successes", action="store_true", help="Retry successful plans saved with an older rule schema.")
    parser.add_argument("--sample-rows", type=int, default=8, help="Number of first rows to show the LLM.")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum LLM attempts per CSV file.")
    parser.add_argument("--dry-run", action="store_true", help="Print context without calling LLM or saving.")
    args = parser.parse_args()

    if args.csv_file_id is not None:
        result = plan_csv_transformation(
            args.csv_file_id,
            sample_rows=args.sample_rows,
            max_attempts=args.max_attempts,
            dry_run=args.dry_run,
        )
    else:
        result = plan_pending_csv_transformations(
            TransformationPlanningOptions(
                limit=args.limit,
                retry_errors=args.retry_errors,
                retry_outdated_successes=args.retry_outdated_successes,
                sample_rows=args.sample_rows,
                max_attempts=args.max_attempts,
                dry_run=args.dry_run,
            )
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

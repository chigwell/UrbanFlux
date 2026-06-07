from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import json
from typing import Any

from .csv_row_transformer import apply_csv_row_transformations
from .csv_transformation_planner import plan_csv_transformation
from .database import (
    get_csv_file,
    export_borough_mapping_errors,
    export_borough_mapping_error_summary,
    export_borough_coverage_summary,
    export_global_borough_coverage_summary,
    get_csv_transformation_plan,
    init_db,
    list_csv_file_ids_for_row_transformation,
    list_csv_file_ids_for_transformation_planning,
    transformation_overview_stats,
)
from .transformation_schema import RULE_SCHEMA_VERSION


def _write_error_log(
    csv_file_ids: list[int],
    path: str,
    plan_results: list[dict[str, Any]],
) -> int:
    if not csv_file_ids:
        Path(path).unlink(missing_ok=True)
        if not any(item.get("status") != "success" for item in plan_results):
            return 0
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    rows = export_borough_mapping_errors(csv_file_ids=csv_file_ids, limit=50000)
    plan_errors = [
        item
        for item in plan_results
        if str(item.get("status")) != "success"
    ]
    error_records: list[dict[str, Any]] = []

    for row in rows:
        error_records.append(
            {
                "source_id": row.get("source_id"),
                "csv_file_id": row.get("csv_file_id"),
                "row_number": row.get("row_number"),
                "borough_status": row.get("borough_status"),
                "borough_error_code": row.get("borough_status"),
                "date_status": row.get("date_status"),
                "status": row.get("status"),
                "borough_name": row.get("borough_name"),
                "error_message": row.get("error_message"),
                "date_start": row.get("date_start"),
                "date_end": row.get("date_end"),
                "source_row_json": json.dumps(row.get("source_row_json"), ensure_ascii=False),
                "csv_title": row.get("csv_title"),
                "csv_file_name": row.get("csv_file_name"),
                "source_title": row.get("source_title"),
                "log_kind": "row",
            }
        )

    for item in plan_errors:
        csv_file_id = int(item["csv_file_id"]) if item.get("csv_file_id") is not None else None
        csv_file = get_csv_file(csv_file_id) if csv_file_id is not None else None
        error_records.append(
            {
                "source_id": csv_file.get("source_id") if csv_file else None,
                "csv_file_id": csv_file_id,
                "row_number": None,
                "borough_status": None,
                "borough_error_code": item.get("status"),
                "date_status": None,
                "status": item.get("status"),
                "borough_name": None,
                "error_message": item.get("error_message"),
                "date_start": None,
                "date_end": None,
                "source_row_json": None,
                "csv_title": csv_file.get("title") if csv_file else None,
                "csv_file_name": csv_file.get("file_name") if csv_file else None,
                "source_title": csv_file.get("source_title") if csv_file else None,
                "log_kind": "plan",
            }
        )

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "csv_file_id",
                "row_number",
                "borough_status",
                "borough_error_code",
                "date_status",
                "status",
                "borough_name",
                "error_message",
                "date_start",
                "date_end",
                "source_row_json",
                "csv_title",
                "csv_file_name",
                "source_title",
                "log_kind",
            ],
        )
        writer.writeheader()
        for row in error_records:
            writer.writerow(row)
    return len(error_records)


def _write_row_error_log(
    csv_file_ids: list[int],
    path: str,
) -> int:
    if not csv_file_ids:
        Path(path).unlink(missing_ok=True)
        return 0
    rows = export_borough_mapping_errors(csv_file_ids=csv_file_ids, limit=50000)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "csv_file_id",
                "row_number",
                "borough_status",
                "borough_error_code",
                "date_status",
                "status",
                "borough_name",
                "error_message",
                "date_start",
                "date_end",
                "source_row_json",
                "csv_title",
                "csv_file_name",
                "source_title",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "source_id": row.get("source_id"),
                    "csv_file_id": row.get("csv_file_id"),
                    "row_number": row.get("row_number"),
                    "borough_status": row.get("borough_status"),
                    "borough_error_code": row.get("borough_status"),
                    "date_status": row.get("date_status"),
                    "status": row.get("status"),
                    "borough_name": row.get("borough_name"),
                    "error_message": row.get("error_message"),
                    "date_start": row.get("date_start"),
                    "date_end": row.get("date_end"),
                    "source_row_json": json.dumps(row.get("source_row_json"), ensure_ascii=False),
                    "csv_title": row.get("csv_title"),
                    "csv_file_name": row.get("csv_file_name"),
                    "source_title": row.get("source_title"),
                }
            )
    return len(rows)


def _write_borough_error_log(
    csv_file_ids: list[int],
    path: str,
    plan_results: list[dict[str, Any]],
) -> int:
    rows = export_borough_mapping_errors(csv_file_ids=csv_file_ids, limit=50000)
    plan_errors = [item for item in plan_results if str(item.get("status")) != "success"]

    error_records: list[dict[str, Any]] = []
    for row in rows:
        error_records.append(
            {
                "error_scope": "row",
                "source_id": row.get("source_id"),
                "csv_file_id": row.get("csv_file_id"),
                "row_number": row.get("row_number"),
                "borough_status": row.get("borough_status"),
                "borough_error_code": row.get("borough_status"),
                "status": row.get("status"),
                "borough_name": row.get("borough_name"),
                "error_message": row.get("error_message"),
                "source_row_json": json.dumps(row.get("source_row_json"), ensure_ascii=False),
                "csv_title": row.get("csv_title"),
                "csv_file_name": row.get("csv_file_name"),
                "source_title": row.get("source_title"),
            }
        )

    for item in plan_errors:
        csv_file_id = int(item["csv_file_id"]) if item.get("csv_file_id") is not None else None
        csv_file = get_csv_file(csv_file_id) if csv_file_id is not None else None
        error_records.append(
            {
                "error_scope": "plan",
                "source_id": csv_file.get("source_id") if csv_file else None,
                "csv_file_id": csv_file_id,
                "row_number": None,
                "borough_status": None,
                "borough_error_code": item.get("status"),
                "status": item.get("status"),
                "borough_name": None,
                "error_message": item.get("error_message"),
                "source_row_json": None,
                "csv_title": csv_file.get("title") if csv_file else None,
                "csv_file_name": csv_file.get("file_name") if csv_file else None,
                "source_title": csv_file.get("source_title") if csv_file else None,
            }
        )

    if not error_records:
        if not csv_file_ids and not plan_errors:
            Path(path).unlink(missing_ok=True)
            return 0
        if not csv_file_ids:
            return 0

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "error_scope",
                "source_id",
                "csv_file_id",
                "row_number",
                "borough_status",
                "borough_error_code",
                "status",
                "borough_name",
                "error_message",
                "source_row_json",
                "csv_title",
                "csv_file_name",
                "source_title",
            ],
        )
        writer.writeheader()
        for row in error_records:
            writer.writerow(row)

    return len(error_records)


def _write_error_summary_report(
    csv_file_ids: list[int],
    path: str,
    plan_results: list[dict[str, Any]],
) -> int:
    summary_rows = export_borough_mapping_error_summary(csv_file_ids=csv_file_ids)
    plan_errors = [
        item
        for item in plan_results
        if str(item.get("status")) != "success"
    ]

    plan_error_csvs = {
        int(item["csv_file_id"])
        for item in plan_errors
        if item.get("csv_file_id") is not None
    }

    if not csv_file_ids and not plan_error_csvs:
        Path(path).unlink(missing_ok=True)
        return 0

    by_csv: dict[int, dict[str, Any]] = {}
    for row in summary_rows:
        csv_file_id = int(row["csv_file_id"])
        by_csv[csv_file_id] = {
            "source_id": row.get("source_id"),
            "source_title": row.get("source_title"),
            "csv_file_id": csv_file_id,
            "csv_title": row.get("csv_title"),
            "csv_file_name": row.get("csv_file_name"),
            "error_rows_count": int(row.get("error_rows_count") or 0),
            "not_london_borough_count": int(row.get("not_london_borough_count") or 0),
            "not_identifiable_count": int(row.get("not_identifiable_count") or 0),
            "error_count": int(row.get("error_count") or 0),
            "unsupported_count": int(row.get("unsupported_count") or 0),
            "plan_status": None,
            "plan_error_message": None,
            "sample_row_numbers": [],
        }

    rows = export_borough_mapping_errors(csv_file_ids=csv_file_ids, limit=50000)
    for row in rows:
        csv_file_id = int(row["csv_file_id"])
        if csv_file_id not in by_csv:
            by_csv[csv_file_id] = {
                "source_id": row.get("source_id"),
                "source_title": row.get("source_title"),
                "csv_file_id": csv_file_id,
                "csv_title": row.get("csv_title"),
                "csv_file_name": row.get("csv_file_name"),
                "error_rows_count": 0,
                "not_london_borough_count": 0,
                "not_identifiable_count": 0,
                "error_count": 0,
                "unsupported_count": 0,
                "plan_status": None,
                "plan_error_message": None,
                "sample_row_numbers": [],
            }
        sample_list = by_csv[csv_file_id]["sample_row_numbers"]
        if len(sample_list) < 3 and row.get("row_number") is not None:
            sample_list.append(int(row["row_number"]))

    for item in plan_errors:
        csv_file_id = int(item["csv_file_id"]) if item.get("csv_file_id") is not None else None
        if csv_file_id is None:
            continue
        if csv_file_id not in by_csv:
            csv_file = get_csv_file(csv_file_id)
            by_csv[csv_file_id] = {
                "source_id": csv_file.get("source_id") if csv_file else None,
                "source_title": csv_file.get("source_title") if csv_file else None,
                "csv_file_id": csv_file_id,
                "csv_title": csv_file.get("title") if csv_file else item.get("csv_title"),
                "csv_file_name": csv_file.get("file_name") if csv_file else item.get("csv_file_name"),
                "error_rows_count": 0,
                "not_london_borough_count": 0,
                "not_identifiable_count": 0,
                "error_count": 0,
                "unsupported_count": 0,
                "plan_status": "plan_failed",
                "plan_error_message": item.get("error_message"),
                "sample_row_numbers": [],
            }
        by_csv[csv_file_id]["plan_status"] = "plan_failed"
        by_csv[csv_file_id]["plan_error_message"] = item.get("error_message")

    for csv_file_id in csv_file_ids:
        if csv_file_id not in by_csv and csv_file_id in plan_error_csvs:
            item = {
                "source_id": None,
                "source_title": None,
                "csv_file_id": csv_file_id,
                "csv_title": None,
                "csv_file_name": None,
                "error_rows_count": 0,
                "not_london_borough_count": 0,
                "not_identifiable_count": 0,
                "error_count": 0,
                "unsupported_count": 0,
                "plan_status": "plan_failed",
                "plan_error_message": None,
                "sample_row_numbers": [],
            }
            by_csv[csv_file_id] = item

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "source_title",
                "csv_file_id",
                "csv_title",
                "csv_file_name",
                "error_rows_count",
                "not_london_borough_count",
                "not_identifiable_count",
                "error_count",
                "unsupported_count",
                "plan_status",
                "plan_error_message",
                "sample_row_numbers",
            ],
        )
        writer.writeheader()
        for item in by_csv.values():
            item = dict(item)
            item["sample_row_numbers"] = "|".join(str(number) for number in item["sample_row_numbers"])
            writer.writerow(item)

    return len(by_csv)


def _write_coverage_report(
    csv_file_ids: list[int],
    path: str,
) -> int:
    rows = export_borough_coverage_summary(
        csv_file_ids=csv_file_ids,
        limit=max(len(csv_file_ids) * 3, 200) if csv_file_ids else 200,
    )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "source_id",
                "source_title",
                "csv_file_id",
                "csv_title",
                "csv_file_name",
                "row_total_count",
                "row_success_count",
                "row_not_london_count",
                "row_not_identifiable_count",
                "row_error_count",
                "row_unsupported_count",
                "rows_not_mapped",
                "mapped_borough_count",
                "missing_borough_count",
                "total_london_boroughs",
                "coverage_ratio",
                "mapped_boroughs",
                "missing_boroughs",
            ],
        )
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["mapped_boroughs"] = "|".join(row.get("mapped_boroughs", []) or [])
            row["missing_boroughs"] = "|".join(row.get("missing_boroughs", []) or [])
            row["coverage_ratio"] = f"{float(row.get('coverage_ratio') or 0.0):.4f}"
            writer.writerow(row)
    return len(rows)


def _write_global_coverage_report(path: str | None = None) -> tuple[int, dict[str, Any] | None]:
    if not path:
        return 0, None
    summary = export_global_borough_coverage_summary()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    import csv as _csv

    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = _csv.DictWriter(
            handle,
            fieldnames=[
                "row_total_count",
                "row_success_count",
                "row_not_london_count",
                "row_not_identifiable_count",
                "row_error_count",
                "row_unsupported_count",
                "mapped_borough_count",
                "missing_borough_count",
                "rows_not_mapped",
                "transformed_file_count",
                "total_london_boroughs",
                "coverage_ratio",
                "mapped_boroughs",
                "missing_boroughs",
            ],
        )
        writer.writeheader()
        if summary:
            row = dict(summary)
            row["mapped_boroughs"] = "|".join(row.get("mapped_boroughs", []) or [])
            row["missing_boroughs"] = "|".join(row.get("missing_boroughs", []) or [])
            row["coverage_ratio"] = f"{float(row.get('coverage_ratio') or 0.0):.4f}"
            writer.writerow(row)
    return 1, summary


@dataclass(slots=True)
class CsvTransformationPipelineOptions:
    limit: int | None = None
    retry_plan_errors: bool = False
    retry_outdated_successes: bool = False
    retry_row_outputs: bool = False
    sample_rows: int = 8
    max_attempts: int = 3
    apply_existing_successes: bool = True
    error_log: str | None = None
    error_row_log: str | None = None
    borough_error_log: str | None = None
    error_summary_report: str | None = None
    coverage_report: str | None = None
    global_coverage_report: str | None = None
    self_test: bool = False
    only_errors: bool = False


def _apply_if_success(csv_file_id: int) -> dict[str, Any] | None:
    plan = get_csv_transformation_plan(csv_file_id)
    if plan is None or plan.get("status") != "success":
        return None
    return apply_csv_row_transformations(csv_file_id, replace=True)


def run_csv_transformation_pipeline(
    options: CsvTransformationPipelineOptions | None = None,
) -> dict[str, Any]:
    options = options or CsvTransformationPipelineOptions()
    init_db()

    plan_ids = list_csv_file_ids_for_transformation_planning(
        retry_errors=options.retry_plan_errors,
        minimum_rule_schema_version=RULE_SCHEMA_VERSION if options.retry_outdated_successes else None,
        limit=options.limit,
    )
    plan_results: list[dict[str, Any]] = []
    apply_results: list[dict[str, Any]] = []
    applied_csv_ids: list[int] = []

    for csv_file_id in plan_ids:
        plan_result = plan_csv_transformation(
            csv_file_id,
            sample_rows=options.sample_rows,
            max_attempts=options.max_attempts,
            dry_run=options.self_test,
        )
        plan_results.append(plan_result)
        if options.self_test or options.only_errors:
            continue
        if plan_result.get("status") == "success":
            apply_result = _apply_if_success(csv_file_id)
            if apply_result is not None:
                apply_results.append(apply_result)
                applied_csv_ids.append(csv_file_id)

    if (not options.only_errors) and options.apply_existing_successes:
        remaining_limit = None
        if options.limit is not None:
            remaining_limit = max(options.limit - len(plan_ids), 0)
        if remaining_limit is None or remaining_limit > 0:
            apply_ids = list_csv_file_ids_for_row_transformation(
                retry=options.retry_row_outputs,
                limit=remaining_limit,
            )
            already_applied = {int(item["csv_file_id"]) for item in apply_results}
            for csv_file_id in apply_ids:
                if csv_file_id in already_applied:
                    continue
                apply_results.append(apply_csv_row_transformations(csv_file_id, replace=True))
                applied_csv_ids.append(csv_file_id)

    error_rows_count = 0
    if options.error_log:
        error_rows_count = _write_error_log(
            applied_csv_ids if not options.only_errors else plan_ids,
            options.error_log,
            plan_results,
        )

    row_error_rows_count = 0
    if options.error_row_log:
        row_error_rows_count = _write_row_error_log(
            applied_csv_ids if not options.only_errors else plan_ids,
            options.error_row_log,
        )

    borough_error_rows_count = 0
    if options.borough_error_log:
        borough_error_rows_count = _write_borough_error_log(
            applied_csv_ids if not options.only_errors else plan_ids,
            options.borough_error_log,
            plan_results,
        )

    error_summary_rows = 0
    if options.error_summary_report:
        error_summary_rows = _write_error_summary_report(
            applied_csv_ids if not options.only_errors else plan_ids,
            options.error_summary_report,
            plan_results,
        )

    coverage_rows = 0
    if options.coverage_report:
        coverage_rows = _write_coverage_report(
            applied_csv_ids if not options.only_errors else plan_ids,
            options.coverage_report,
        )

    global_coverage_rows = 0
    global_summary = None
    if options.global_coverage_report:
        global_coverage_rows, global_summary = _write_global_coverage_report(
            options.global_coverage_report,
        )

    return {
        "planned_files": len(plan_results),
        "plan_success": sum(1 for item in plan_results if item.get("status") == "success"),
        "plan_error": sum(1 for item in plan_results if item.get("status") == "error"),
        "applied_files": len(apply_results),
        "applied_rows": sum(int(item.get("rows", 0)) for item in apply_results),
        "applied_success_rows": sum(int(item.get("success", 0)) for item in apply_results),
        "applied_partial_rows": sum(int(item.get("partial", 0)) for item in apply_results),
        "applied_error_rows": sum(int(item.get("error", 0)) for item in apply_results),
        "error_log_rows": error_rows_count,
        "error_row_log_rows": row_error_rows_count,
        "borough_error_log_rows": borough_error_rows_count,
        "error_summary_rows": error_summary_rows,
        "coverage_rows": coverage_rows,
        "global_coverage_rows": global_coverage_rows,
        "global_coverage_summary": global_summary,
        "plans": plan_results,
        "applications": apply_results,
        "overview": transformation_overview_stats(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan CSV semantic mappings and apply successful plans to rows.")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of CSV files to process.")
    parser.add_argument("--retry-plan-errors", action="store_true", help="Retry missing or non-success LLM plans.")
    parser.add_argument("--retry-outdated-successes", action="store_true", help="Retry successful plans saved with an older rule schema.")
    parser.add_argument("--retry-row-outputs", action="store_true", help="Re-apply files that already have row outputs.")
    parser.add_argument("--sample-rows", type=int, default=8, help="Number of first rows to show the LLM.")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum LLM attempts per CSV file.")
    parser.add_argument(
        "--skip-existing-successes",
        action="store_true",
        help="Only process newly planned files; do not apply older successful plans.",
    )
    parser.add_argument("--error-log", default=None, help="CSV file path for non-London borough rows.")
    parser.add_argument("--error-row-log", default=None, help="CSV file path for row-level non-success borough mappings only.")
    parser.add_argument("--borough-error-log", default=None, help="CSV file path for all borough mapping errors (row + plan level).")
    parser.add_argument("--error-summary-report", default=None, help="CSV file path for per-file aggregate borough-mapping errors summary.")
    parser.add_argument("--coverage-report", default=None, help="CSV file path for per-file borough-mapping coverage summary.")
    parser.add_argument("--global-coverage-report", default=None, help="CSV file path for global borough-mapping coverage summary.")
    parser.add_argument("--self-test", action="store_true", help="Run planning checks only (no row application, no LLM calls).")
    parser.add_argument("--only-errors", action="store_true", help="Plan files and produce only error outputs; skip row transformation.")
    parser.add_argument("--stats", action="store_true", help="Print aggregate transformation stats only.")
    args = parser.parse_args()

    if args.stats:
        result = transformation_overview_stats()
    else:
        result = run_csv_transformation_pipeline(
            CsvTransformationPipelineOptions(
                limit=args.limit,
                retry_plan_errors=args.retry_plan_errors,
                retry_outdated_successes=args.retry_outdated_successes,
                retry_row_outputs=args.retry_row_outputs,
                sample_rows=args.sample_rows,
                max_attempts=args.max_attempts,
                apply_existing_successes=not args.skip_existing_successes,
                error_log=args.error_log,
                error_row_log=args.error_row_log,
                borough_error_log=args.borough_error_log,
                error_summary_report=args.error_summary_report,
                coverage_report=args.coverage_report,
                global_coverage_report=args.global_coverage_report,
                self_test=args.self_test,
                only_errors=args.only_errors,
            )
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

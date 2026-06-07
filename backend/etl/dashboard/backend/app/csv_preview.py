from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Iterator


def _dialect_for_sample(sample: str) -> csv.Dialect:
    try:
        detected = csv.Sniffer().sniff(sample)
        if not getattr(detected, "delimiter", ""):
            raise ValueError("empty delimiter")
        return detected
    except (csv.Error, ValueError):
        return csv.excel


def _reader_for_sample(handle: Path, sample: str) -> Iterator[list[str]]:
    dialect = _dialect_for_sample(sample)
    try:
        return csv.reader(handle, dialect)
    except (csv.Error, ValueError):
        return csv.reader(handle, csv.excel)


def _dedupe_headers(headers: list[str]) -> list[str]:
    result: list[str] = []
    seen: dict[str, int] = {}
    for index, header in enumerate(headers):
        name = header.strip() or f"column_{index + 1}"
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}_{count + 1}")
    return result


def iter_csv_rows(local_path: str) -> Iterator[tuple[int, list[str], dict[str, str]]]:
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file is missing at {path}")

    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        reader = _reader_for_sample(handle, sample)
        headers = _dedupe_headers(next(reader, []))
        for row_number, row in enumerate(reader, start=1):
            padded = [*row, *[""] * max(len(headers) - len(row), 0)]
            yield row_number, headers, dict(zip(headers, padded[: len(headers)], strict=False))


def read_csv_headers(local_path: str) -> list[str]:
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file is missing at {path}")

    with path.open("r", newline="", encoding="utf-8-sig", errors="replace") as handle:
        sample = handle.read(8192)
        handle.seek(0)
        reader = _reader_for_sample(handle, sample)
        return _dedupe_headers(next(reader, []))


def preview_csv(
    local_path: str,
    *,
    page: int,
    page_size: int,
    count_total: bool = False,
) -> dict[str, Any]:
    path = Path(local_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file is missing at {path}")

    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    start = (page - 1) * page_size
    rows: list[dict[str, str]] = []
    total_rows: int | None = 0 if count_total else None
    has_more = False

    headers: list[str] = []
    for index, (_, row_headers, row) in enumerate(iter_csv_rows(local_path)):
        headers = row_headers
        if count_total:
            total_rows = (total_rows or 0) + 1
        if index < start:
            continue
        if len(rows) >= page_size:
            has_more = True
            if not count_total:
                break
            continue
        rows.append(row)

    if not headers:
        headers = read_csv_headers(local_path)
    if not headers:
        return {
            "columns": [],
            "rows": [],
            "page": page,
            "page_size": page_size,
            "total_rows": 0,
            "has_more": False,
        }

    return {
        "columns": headers,
        "rows": rows,
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "has_more": has_more,
    }

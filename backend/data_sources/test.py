from __future__ import annotations

import argparse
from pathlib import Path
import sys


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR.parent.parent) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR.parent.parent))

from backend.data_sources import (
    get_borough_summary,
    iter_borough_data,
    resolve_borough,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print mapped London data for coordinates.")
    parser.add_argument("--lat", type=float, default=51.5074)
    parser.add_argument("--lon", type=float, default=-0.1278)
    parser.add_argument("--theme", default=None, help="Optional single theme to display.")
    args = parser.parse_args()

    lat = args.lat
    lon = args.lon

    borough = resolve_borough(lat, lon)
    print(f"# Borough data for {lat}, {lon}\n")
    print(f"**Borough:** {borough['name'] if borough else None}\n")
    if borough is None:
        return

    summary = get_borough_summary(lat, lon, top_datasets_limit=5)
    print("## Summary by theme\n")
    print("| Theme | Rows | CSV files | Date start | Date end |")
    print("|---|---:|---:|---|---|")
    for theme in summary["themes"]:
        print(
            f"| {theme['theme']} | {theme['row_count']} | {theme['csv_file_count']} | "
            f"{theme['min_date_start'] or ''} | {theme['max_date_end'] or ''} |"
        )

    print("\n## Top datasets\n")
    print("| Theme | Rows | Dataset | Resource |")
    print("|---|---:|---|---|")
    for dataset in summary["top_datasets"]:
        print(
            f"| {dataset['theme']} | {dataset['row_count']} | "
            f"{md(dataset['dataset_title'])} | {md(dataset['resource_title'])} |"
        )

    themes = [args.theme] if args.theme else [item["theme"] for item in summary["themes"]]
    print("\n## First row for each theme\n")
    print("| Theme | Dataset | Resource | Row number | Date start | Date end | Source row preview |")
    print("|---|---|---|---:|---|---|---|")
    for theme in themes:
        for row in iter_borough_data(lat, lon, theme=theme, batch_size=1):
            print(
                f"| {theme} | {md(row['source']['dataset_title'])} | "
                f"{md(row['source']['resource_title'])} | {row['row_number']} | "
                f"{row['date_start'] or ''} | {row['date_end'] or ''} | "
                f"{md(preview_source_row(row['source_row']))} |"
            )
            break


def md(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def preview_source_row(source_row: object) -> str:
    if isinstance(source_row, dict):
        items = list(source_row.items())[:6]
        return "; ".join(f"{key}: {value}" for key, value in items)
    return str(source_row)


if __name__ == "__main__":
    main()

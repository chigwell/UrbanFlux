import json
import sqlite3
from datetime import date

from backend.data_sources import LONDON_MAPPED_DATA_DB_PATH, ensure_london_mapped_data, get_borough_summary, resolve_borough


def md(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def preview_source_row(source_row: object) -> str:
    if isinstance(source_row, dict):
        items = list(source_row.items())[:6]
        return "; ".join(f"{key}: {value}" for key, value in items)
    return str(source_row)


def latest_row_for_theme(borough_name: str, theme: str) -> dict | None:
    today = date.today().isoformat()
    with sqlite3.connect(LONDON_MAPPED_DATA_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
              r.row_number,
              r.date_start,
              r.date_end,
              r.source_row_json,
              ds.title AS dataset_title,
              cf.title AS resource_title
            FROM csv_row_transformations r
            JOIN dataset_csv_files cf ON cf.id = r.csv_file_id
            JOIN dataset_sources ds ON ds.id = cf.dataset_source_id
            WHERE r.borough_name = :borough_name
              AND cf.theme = :theme
              AND r.status IN ('success', 'partial')
              AND COALESCE(NULLIF(r.date_end, ''), NULLIF(r.date_start, '')) IS NOT NULL
              AND COALESCE(NULLIF(r.date_end, ''), NULLIF(r.date_start, '')) <= :today
            ORDER BY
              COALESCE(NULLIF(r.date_end, ''), NULLIF(r.date_start, '')) DESC,
              NULLIF(r.date_start, '') DESC,
              r.id DESC
            LIMIT 1
            """,
            {"borough_name": borough_name, "theme": theme, "today": today},
        ).fetchone()

    if row is None:
        return None
    source_row = json.loads(row["source_row_json"]) if row["source_row_json"] else None
    return {**dict(row), "source_row": source_row}


lat = 51.5074
lon = -0.1278

ensure_london_mapped_data()
borough = resolve_borough(lat, lon)
summary = get_borough_summary(lat, lon)

print(f"# Borough data for {lat}, {lon}\n")
print(f"**Borough:** {borough['name'] if borough else None}\n")

if borough:
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

    print("\n## Most recent row for each theme\n")
    print("| Theme | Dataset | Resource | Row number | Date start | Date end | Source row preview |")
    print("|---|---|---|---:|---|---|---|")
    for theme in [item["theme"] for item in summary["themes"]]:
        row = latest_row_for_theme(borough["name"], theme)
        if row:
            print(
                f"| {theme} | {md(row['dataset_title'])} | "
                f"{md(row['resource_title'])} | {row['row_number']} | "
                f"{row['date_start'] or ''} | {row['date_end'] or ''} | "
                f"{md(preview_source_row(row['source_row']))} |"
            )
        else:
            print(f"| {theme} |  |  |  |  |  | No dated row found |")

from backend.data_sources import get_borough_summary, iter_borough_data, resolve_borough


def md(value: object) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")[:240]


def preview_source_row(source_row: object) -> str:
    if isinstance(source_row, dict):
        items = list(source_row.items())[:6]
        return "; ".join(f"{key}: {value}" for key, value in items)
    return str(source_row)


lat = 51.5074
lon = -0.1278

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

    print("\n## First row for each theme\n")
    print("| Theme | Dataset | Resource | Row number | Date start | Date end | Source row preview |")
    print("|---|---|---|---:|---|---|---|")
    for theme in [item["theme"] for item in summary["themes"]]:
        for row in iter_borough_data(lat, lon, theme=theme, batch_size=1):
            print(
                f"| {theme} | {md(row['source']['dataset_title'])} | "
                f"{md(row['source']['resource_title'])} | {row['row_number']} | "
                f"{row['date_start'] or ''} | {row['date_end'] or ''} | "
                f"{md(preview_source_row(row['source_row']))} |"
            )
            break

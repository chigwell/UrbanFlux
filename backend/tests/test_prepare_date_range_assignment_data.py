from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fine_tune.data_preparation import prepare_date_range_assignment_data as prep  # noqa: E402


def sample_row() -> dict:
    return {
        "id": 10,
        "csv_file_id": 20,
        "row_number": 30,
        "theme": "housing",
        "date_start": "2023-04-01",
        "date_end": "2024-03-31",
        "borough_name": "Westminster",
        "source": {
            "dataset_title": "Housing data",
            "dataset_description": "Affordable housing supply by borough.",
            "dataset_url": "https://data.london.gov.uk/example",
            "organisation_name": "Greater London Authority",
            "resource_title": "housing.csv",
            "resource_description": "CSV resource",
            "csv_url": "https://data.london.gov.uk/example.csv",
        },
        "source_row": {"Area": "Westminster", "Year": "2023-24", "Affordable Housing Supply": 286},
    }


def test_output_record_uses_source_row_prompt_and_date_range_only_assistant() -> None:
    record = prep.output_record(sample_row())

    assert [message["role"] for message in record["messages"]] == ["user", "assistant"]

    user_payload = json.loads(record["messages"][0]["content"])
    assert user_payload["task"] == "Identify the date range represented by this CSV row. Return only the date range."
    assert user_payload["csv_headers"] == ["Area", "Year", "Affordable Housing Supply"]
    assert user_payload["csv_row"]["Area"] == "Westminster"
    assert "Housing data" in user_payload["source_metadata"]
    assert "date_start" not in user_payload
    assert "date_end" not in user_payload

    assistant_payload = json.loads(record["messages"][1]["content"])
    assert assistant_payload == {
        "date_start": "2023-04-01",
        "date_end": "2024-03-31",
    }


def test_dry_run_counts_rows_without_writing(monkeypatch, tmp_path: Path, capsys) -> None:
    rows = [sample_row()]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(prep, "connect_data_db", lambda: FakeConnection())
    monkeypatch.setattr(prep, "fetch_training_rows", lambda conn, **kwargs: rows)

    args = argparse.Namespace(
        output=tmp_path / "date_range.jsonl",
        max_rows_per_borough_theme=100,
        borough=None,
        theme=None,
        success_only=False,
        dry_run=True,
        overwrite=False,
    )

    assert prep.run(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"] == 1
    assert not args.output.exists()

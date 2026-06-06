from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fine_tune.data_preparation import prepare_training_data as prep  # noqa: E402


def sample_row() -> dict:
    return {
        "id": 10,
        "csv_file_id": 20,
        "row_number": 30,
        "theme": "housing",
        "date_start": "2023-04-01",
        "date_end": "2024-03-31",
        "borough_name": "Westminster",
        "row_status": "success",
        "source": {
            "dataset_title": "Housing data",
            "dataset_url": "https://data.london.gov.uk/example",
            "resource_title": "housing.csv",
            "csv_url": "https://data.london.gov.uk/example.csv",
        },
        "source_row": {"Area": "Westminster", "Year": "2023-24", "Affordable Housing Supply": 286},
    }


def test_generate_scenario_is_deterministic_for_seed_row_and_index() -> None:
    row_key = "Westminster|housing|10|20|30"

    first = prep.generate_scenario(seed=42, row_key=row_key, scenario_index=0)
    second = prep.generate_scenario(seed=42, row_key=row_key, scenario_index=0)
    next_index = prep.generate_scenario(seed=42, row_key=row_key, scenario_index=1)

    assert first == second
    assert first != next_index
    assert 0 <= first.area_change_percent <= 100
    assert 5 <= first.density <= 100
    assert 5 <= first.green <= 80
    assert 0 <= first.parking <= 80


def test_load_completed_keys_reads_key_from_chat_user_message(tmp_path: Path) -> None:
    row = sample_row()
    scenario = prep.generate_scenario(42, prep.row_identity(row), 0)
    key = prep.combination_key(row, 42, 0, scenario)
    user_prompt = prep.build_user_prompt(row, scenario, key)
    output_path = tmp_path / "training.jsonl"
    output_path.write_text(
        json.dumps(prep.output_record(user_prompt, "[]")) + "\n",
        encoding="utf-8",
    )

    record = json.loads(output_path.read_text(encoding="utf-8"))
    assert [message["role"] for message in record["messages"]] == ["user", "assistant"]
    assert prep.load_completed_keys(output_path) == {key}


def test_validate_model_output_accepts_only_required_object_list() -> None:
    valid = '[{"improved_metric":"Affordable homes","improved_value":"320","delta":"+34"}]'

    parsed = prep.validate_model_output(valid)

    assert parsed == [
        {
            "improved_metric": "Affordable homes",
            "improved_value": "320",
            "delta": "+34",
        }
    ]

    with pytest.raises(ValueError, match="extra keys"):
        prep.validate_model_output(
            '[{"improved_metric":"x","improved_value":"y","delta":"z","extra":"no"}]'
        )


def test_retry_message_includes_validation_error_and_previous_content() -> None:
    message = prep.validation_error_message("response must be a JSON list", '{"bad": true}')

    assert "response must be a JSON list" in message
    assert '{"bad": true}' in message
    assert "Return only a JSON list" in message


def test_dry_run_counts_pending_without_building_model(monkeypatch, tmp_path: Path, capsys) -> None:
    rows = [sample_row()]

    class FakeConnection:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(prep, "connect_data_db", lambda: FakeConnection())
    monkeypatch.setattr(
        prep,
        "ensure_query_indexes",
        lambda conn: (_ for _ in ()).throw(AssertionError("default run must not create indexes")),
    )
    monkeypatch.setattr(prep, "fetch_recent_rows", lambda conn, **kwargs: rows)
    monkeypatch.setattr(prep, "load_completed_keys", lambda output_path: set())
    monkeypatch.setattr(
        prep,
        "build_chat_model",
        lambda: (_ for _ in ()).throw(AssertionError("dry run must not build a model")),
    )

    args = argparse.Namespace(
        output=tmp_path / "training.jsonl",
        errors_output=tmp_path / "errors.jsonl",
        max_rows_per_borough_theme=100,
        scenarios_per_row=2,
        seed=42,
        borough=None,
        theme=None,
        dry_run=True,
    )

    assert prep.run(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rows"] == 1
    assert payload["planned_combinations"] == 2
    assert payload["pending_combinations"] == 2

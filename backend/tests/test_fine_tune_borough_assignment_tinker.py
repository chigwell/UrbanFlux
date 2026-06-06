from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fine_tune.data_preparation import fine_tune_borough_assignment_tinker as ft  # noqa: E402


def write_dataset(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "Which borough is this?"},
                    {"role": "assistant", "content": "Westminster"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_jsonl_validates_chat_records(tmp_path: Path) -> None:
    dataset = tmp_path / "borough.jsonl"
    write_dataset(dataset)

    records = ft.load_jsonl(dataset)

    assert records[0]["messages"][1]["content"] == "Westminster"


def test_conversations_from_records_preserves_user_assistant_messages(tmp_path: Path) -> None:
    dataset = tmp_path / "borough.jsonl"
    write_dataset(dataset)
    records = ft.load_jsonl(dataset)

    conversations = ft.conversations_from_records(records)

    assert conversations == [
        [
            {"role": "user", "content": "Which borough is this?"},
            {"role": "assistant", "content": "Westminster"},
        ]
    ]


def test_batched_splits_items_by_batch_size() -> None:
    assert list(ft.batched([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_dry_run_does_not_require_tinker_imports_or_api_key(monkeypatch, tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "borough.jsonl"
    write_dataset(dataset)
    monkeypatch.delenv("TINKER_API_KEY", raising=False)
    monkeypatch.setattr(
        ft,
        "load_tinker_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("dry run must not import Tinker")),
    )

    args = argparse.Namespace(
        dataset=dataset,
        base_model="Qwen/Qwen3.5-4B",
        renderer="qwen3_5",
        checkpoint_name="test-checkpoint",
        rank=16,
        learning_rate=0.0002,
        batch_size=8,
        epochs=1,
        max_steps=None,
        max_examples=None,
        max_length=2048,
        dry_run=True,
    )

    assert ft.asyncio.run(ft.train(args)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"] == 1
    assert payload["base_model"] == "Qwen/Qwen3.5-4B"

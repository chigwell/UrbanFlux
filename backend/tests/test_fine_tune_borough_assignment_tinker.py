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


def test_save_persistent_sampler_checkpoint_uses_model_path() -> None:
    class FakeFuture:
        async def result_async(self):
            return "sampler://urbanflux-checkpoint"

    class FakeTrainingClient:
        def __init__(self):
            self.saved_name = None

        def save_weights_for_sampler(self, name: str):
            self.saved_name = name
            return FakeFuture()

    class FakeServiceClient:
        def __init__(self):
            self.model_path = None

        def create_sampling_client(self, model_path: str):
            self.model_path = model_path
            return {"sampling": True}

    service_client = FakeServiceClient()
    training_client = FakeTrainingClient()

    model_path, sampling_client = ft.asyncio.run(
        ft.save_persistent_sampler_checkpoint(
            service_client=service_client,
            training_client=training_client,
            checkpoint_name="urbanflux-test",
        )
    )

    assert training_client.saved_name == "urbanflux-test"
    assert model_path == "sampler://urbanflux-checkpoint"
    assert service_client.model_path == "sampler://urbanflux-checkpoint"
    assert sampling_client == {"sampling": True}


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
        base_model=ft.DEFAULT_BASE_MODEL,
        renderer=ft.DEFAULT_RENDERER,
        checkpoint_name="test-checkpoint",
        rank=16,
        learning_rate=0.0001,
        batch_size=2,
        epochs=1,
        max_steps=None,
        max_examples=None,
        max_length=4096,
        dry_run=True,
    )

    assert ft.asyncio.run(ft.train(args)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["records"] == 1
    assert payload["base_model"] == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
    assert payload["renderer"] == "nemotron3_disable_thinking"
    assert payload["batch_size"] == 2
    assert payload["learning_rate"] == 0.0001
    assert payload["max_length"] == 4096


def test_parse_args_defaults_to_nemotron3_disable_thinking() -> None:
    args = ft.parse_args([])

    assert args.base_model == "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
    assert args.renderer == "nemotron3_disable_thinking"
    assert args.batch_size == 2
    assert args.learning_rate == 0.0001
    assert args.max_length == 4096

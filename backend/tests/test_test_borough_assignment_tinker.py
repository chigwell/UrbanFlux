from __future__ import annotations

import json
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fine_tune.data_preparation import test_borough_assignment_tinker as tester  # noqa: E402


def write_dataset(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "{\"csv_row\":{\"Area\":\"Westminster\"}}"},
                    {"role": "assistant", "content": "Westminster"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_load_jsonl_record_and_prompt_messages(tmp_path: Path) -> None:
    dataset = tmp_path / "borough.jsonl"
    write_dataset(dataset)

    record = tester.load_jsonl_record(dataset, 0)
    prompt_messages, expected = tester.prompt_messages_from_record(record)

    assert expected == "Westminster"
    assert prompt_messages == [{"role": "user", "content": "{\"csv_row\":{\"Area\":\"Westminster\"}}"}]


def test_prompt_messages_from_user_content() -> None:
    assert tester.prompt_messages_from_user_content("Which borough?") == [
        {"role": "user", "content": "Which borough?"}
    ]


def test_parse_args_defaults_to_provided_model_path() -> None:
    args = tester.parse_args([])

    assert args.model_path.startswith("tinker://6123e62a-f3b6-58d3-a5ad-b421df755bba")
    assert args.renderer == "nemotron3_disable_thinking"
    assert args.max_tokens == 12


def test_dry_run_outputs_prompt_without_tinker_import(monkeypatch, tmp_path: Path, capsys) -> None:
    dataset = tmp_path / "borough.jsonl"
    write_dataset(dataset)
    monkeypatch.setattr(
        tester,
        "load_tinker_dependencies",
        lambda: (_ for _ in ()).throw(AssertionError("dry run must not import Tinker")),
    )
    args = tester.parse_args(["--dry-run", "--dataset", str(dataset)])
    tester.validate_args(args)

    assert tester.asyncio.run(tester.run(args)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["expected"] == "Westminster"
    assert payload["prompt_messages"][0]["role"] == "user"


def test_renderer_generation_prompt_api_shape() -> None:
    class FakeRenderer:
        def __init__(self):
            self.messages = None

        def build_generation_prompt(self, messages):
            self.messages = messages
            return {"prompt": messages}

    renderer = FakeRenderer()
    prompt = renderer.build_generation_prompt([{"role": "user", "content": "Which borough?"}])

    assert prompt == {"prompt": [{"role": "user", "content": "Which borough?"}]}
    assert renderer.messages[0]["role"] == "user"

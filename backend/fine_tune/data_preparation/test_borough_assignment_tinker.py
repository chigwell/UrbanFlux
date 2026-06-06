from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any


DEFAULT_MODEL_PATH = (
    "tinker://6123e62a-f3b6-58d3-a5ad-b421df755bba:train:0/"
    "sampler_weights/urbanflux-borough-nemotron3-nano-smoke"
)
DEFAULT_DATASET_PATH = Path(__file__).resolve().with_name("urbanflux_borough_assignment_training.jsonl")
DEFAULT_RENDERER = "nemotron3_disable_thinking"


def load_jsonl_record(path: Path, index: int) -> dict[str, Any]:
    if index < 0:
        raise ValueError("--example-index must be zero or greater")
    if not path.exists():
        raise FileNotFoundError(f"Dataset JSONL not found: {path}")

    with path.open("r", encoding="utf-8") as fh:
        for line_index, line in enumerate(fh):
            if line_index != index:
                continue
            record = json.loads(line)
            validate_record(record)
            return record
    raise IndexError(f"Dataset has no record at --example-index {index}: {path}")


def validate_record(record: dict[str, Any]) -> None:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError("Record must contain chat messages with user and assistant entries")
    if messages[-1].get("role") != "assistant":
        raise ValueError("Last training message must be assistant")
    if not any(message.get("role") == "user" for message in messages):
        raise ValueError("Record must contain a user message")


def prompt_messages_from_record(record: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    validate_record(record)
    messages = record["messages"]
    expected = str(messages[-1]["content"])
    prompt_messages: list[dict[str, str]] = []
    for message in messages[:-1]:
        role = message.get("role")
        content = message.get("content")
        if role not in {"system", "user"}:
            continue
        if not isinstance(content, str):
            raise ValueError(f"Message content must be a string for role {role!r}")
        prompt_messages.append({"role": role, "content": content})
    return prompt_messages, expected


def prompt_messages_from_user_content(user_content: str) -> list[dict[str, str]]:
    return [{"role": "user", "content": user_content}]


def extract_generated_text(sample_result: Any, tokenizer: Any) -> str:
    samples = getattr(sample_result, "samples", None)
    if samples:
        first = samples[0]
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text

    sequences = getattr(sample_result, "sequences", None)
    if sequences:
        first = sequences[0]
        tokens = getattr(first, "tokens", None)
        if tokens is not None:
            return tokenizer.decode(tokens)

    if isinstance(sample_result, dict):
        for key in ("text", "output"):
            value = sample_result.get(key)
            if isinstance(value, str):
                return value
        samples = sample_result.get("samples")
        if isinstance(samples, list) and samples:
            first = samples[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                return first["text"]

    return str(sample_result)


def load_tinker_dependencies():
    try:
        import tinker
        from tinker_cookbook.renderers import get_renderer
    except ImportError as exc:
        raise RuntimeError(
            "Tinker inference dependencies are missing. Install them with: "
            "pip install -r data_preparation/requirements-tinker.txt"
        ) from exc
    return tinker, get_renderer


async def run(args: argparse.Namespace) -> int:
    if args.dry_run:
        if args.user_content:
            prompt_messages = prompt_messages_from_user_content(args.user_content)
            expected = None
        else:
            record = load_jsonl_record(args.dataset, args.example_index)
            prompt_messages, expected = prompt_messages_from_record(record)
        print(
            json.dumps(
                {
                    "model_path": args.model_path,
                    "renderer": args.renderer,
                    "max_tokens": args.max_tokens,
                    "temperature": args.temperature,
                    "prompt_messages": prompt_messages,
                    "expected": expected,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not os.environ.get("TINKER_API_KEY"):
        raise RuntimeError("Missing TINKER_API_KEY environment variable")

    tinker, get_renderer = load_tinker_dependencies()
    service_client = tinker.ServiceClient()
    sampling_client = service_client.create_sampling_client(model_path=args.model_path)
    tokenizer = sampling_client.get_tokenizer()
    renderer = get_renderer(args.renderer, tokenizer)

    if args.user_content:
        prompt_messages = prompt_messages_from_user_content(args.user_content)
        expected = None
    else:
        record = load_jsonl_record(args.dataset, args.example_index)
        prompt_messages, expected = prompt_messages_from_record(record)

    prompt = renderer.build_generation_prompt(prompt_messages)
    params = tinker.SamplingParams(
        max_tokens=args.max_tokens,
        temperature=args.temperature,
        stop=renderer.get_stop_sequences(),
    )
    result = sampling_client.sample(
        prompt=prompt,
        num_samples=1,
        sampling_params=params,
    ).result()
    generated = extract_generated_text(result, tokenizer).strip()

    print(
        json.dumps(
            {
                "model_path": args.model_path,
                "prompt_messages": prompt_messages,
                "expected": expected,
                "generated": generated,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test a Tinker borough-assignment sampler checkpoint.")
    parser.add_argument("--model-path", default=DEFAULT_MODEL_PATH)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--example-index", type=int, default=0)
    parser.add_argument("--renderer", default=DEFAULT_RENDERER)
    parser.add_argument("--max-tokens", type=int, default=12)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--user-content", help="Optional raw user prompt. Defaults to a JSONL example prompt.")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if not args.model_path.startswith("tinker://"):
        raise ValueError("--model-path must start with tinker://")
    if args.example_index < 0:
        raise ValueError("--example-index must be zero or greater")
    if args.max_tokens < 1:
        raise ValueError("--max-tokens must be at least 1")
    if args.temperature < 0:
        raise ValueError("--temperature must be zero or greater")
    args.dataset = args.dataset.resolve()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_args(args)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())

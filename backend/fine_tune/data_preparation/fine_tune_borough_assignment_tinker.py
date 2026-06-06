from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

try:
    from tqdm import tqdm
except ImportError:  # pragma: no cover - requirements install provides tqdm.
    def tqdm(iterable=None, *args, **kwargs):
        return iterable if iterable is not None else _FallbackProgress(*args, **kwargs)

    class _FallbackProgress:
        def __init__(self, total=None, **_kwargs):
            self.total = total

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def update(self, amount=1):
            return None

        def set_postfix(self, **_kwargs):
            return None


DEFAULT_DATASET_PATH = Path(__file__).resolve().with_name("urbanflux_borough_assignment_training.jsonl")
DEFAULT_BASE_MODEL = "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16"
DEFAULT_RENDERER = "nemotron3_disable_thinking"
DEFAULT_CHECKPOINT_NAME = "urbanflux-borough-assignment"


def load_jsonl(path: Path, max_examples: int | None = None) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Dataset JSONL not found: {path}")

    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at line {line_number}: {exc.msg}") from exc
            validate_training_record(record, line_number)
            records.append(record)
            if max_examples is not None and len(records) >= max_examples:
                break
    if not records:
        raise ValueError(f"No training records found in {path}")
    return records


def validate_training_record(record: dict[str, Any], line_number: int) -> None:
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError(f"Line {line_number}: expected a messages list with user and assistant messages")
    if messages[-1].get("role") != "assistant":
        raise ValueError(f"Line {line_number}: last message must be assistant")
    if not str(messages[-1].get("content", "")).strip():
        raise ValueError(f"Line {line_number}: assistant content must be a borough name")
    if not any(message.get("role") == "user" for message in messages):
        raise ValueError(f"Line {line_number}: expected at least one user message")


def conversations_from_records(records: Iterable[dict[str, Any]]) -> list[list[dict[str, str]]]:
    conversations: list[list[dict[str, str]]] = []
    for record in records:
        conversation: list[dict[str, str]] = []
        for message in record["messages"]:
            role = message.get("role")
            content = message.get("content")
            if role not in {"system", "user", "assistant"}:
                raise ValueError(f"Unsupported message role: {role!r}")
            if not isinstance(content, str):
                raise ValueError(f"Message content must be a string for role {role!r}")
            conversation.append({"role": role, "content": content})
        conversations.append(conversation)
    return conversations


def batched(items: list[Any], batch_size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def to_float_list(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (int, float)):
        return [float(value)]
    if isinstance(value, list):
        output: list[float] = []
        for item in value:
            output.extend(to_float_list(item))
        return output
    return []


def extract_loss(forward_backward_result: Any, batch: list[Any]) -> float | None:
    loss = getattr(forward_backward_result, "loss", None)
    if isinstance(loss, (int, float)):
        return float(loss)

    outputs = getattr(forward_backward_result, "loss_fn_outputs", None)
    if not outputs:
        return None

    logprobs: list[float] = []
    for output in outputs:
        if isinstance(output, dict):
            logprobs.extend(to_float_list(output.get("logprobs")))

    weights: list[float] = []
    for datum in batch:
        loss_inputs = getattr(datum, "loss_fn_inputs", {})
        if isinstance(loss_inputs, dict):
            weights.extend(to_float_list(loss_inputs.get("weights")))

    usable = min(len(logprobs), len(weights))
    weight_sum = sum(weights[:usable])
    if usable == 0 or weight_sum == 0:
        return None
    return -sum(logprobs[index] * weights[index] for index in range(usable)) / weight_sum


async def maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def result_if_future(value: Any) -> Any:
    value = await maybe_await(value)
    result_async = getattr(value, "result_async", None)
    if callable(result_async):
        return await result_async()
    return value


async def save_persistent_sampler_checkpoint(
    service_client: Any,
    training_client: Any,
    checkpoint_name: str,
) -> tuple[str, Any]:
    save_method = getattr(training_client, "save_weights_for_sampler", None)
    if save_method is None:
        raise RuntimeError(
            "Installed Tinker SDK does not expose save_weights_for_sampler(...). "
            "Upgrade Tinker or use a version that supports persistent sampler checkpoints."
        )

    model_path = await result_if_future(save_method(name=checkpoint_name))
    if not isinstance(model_path, str):
        model_path = str(model_path)

    create_method = getattr(service_client, "create_sampling_client", None)
    if create_method is not None:
        sampling_client = await maybe_await(create_method(model_path=model_path))
        return model_path, sampling_client

    create_async_method = getattr(service_client, "create_sampling_client_async", None)
    if create_async_method is not None:
        sampling_client = await maybe_await(create_async_method(model_path=model_path))
        return model_path, sampling_client

    return model_path, None


def load_tinker_dependencies():
    try:
        import tinker
        from tinker_cookbook.renderers import TrainOnWhat, get_renderer
        from tinker_cookbook.supervised.data import conversation_to_datum
    except ImportError as exc:
        raise RuntimeError(
            "Tinker fine-tuning dependencies are missing. Install them with: "
            "pip install tinker 'tinker-cookbook @ git+https://github.com/thinking-machines-lab/tinker-cookbook.git@nightly'"
        ) from exc
    return tinker, TrainOnWhat, get_renderer, conversation_to_datum


def build_training_data(
    records: list[dict[str, Any]],
    tokenizer: Any,
    renderer_name: str,
    max_length: int,
) -> list[Any]:
    _tinker, TrainOnWhat, get_renderer, conversation_to_datum = load_tinker_dependencies()
    renderer = get_renderer(renderer_name, tokenizer)
    conversations = conversations_from_records(records)
    return [
        conversation_to_datum(
            conversation,
            renderer,
            max_length=max_length,
            train_on_what=TrainOnWhat.LAST_ASSISTANT_MESSAGE,
        )
        for conversation in conversations
    ]


async def train(args: argparse.Namespace) -> int:
    records = load_jsonl(args.dataset, max_examples=args.max_examples)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dataset": str(args.dataset),
                    "records": len(records),
                    "base_model": args.base_model,
                    "renderer": args.renderer,
                    "rank": args.rank,
                    "batch_size": args.batch_size,
                    "epochs": args.epochs,
                    "max_steps": args.max_steps,
                    "learning_rate": args.learning_rate,
                    "max_length": args.max_length,
                    "checkpoint_name": args.checkpoint_name,
                },
                indent=2,
            )
        )
        return 0

    if not os.environ.get("TINKER_API_KEY"):
        raise RuntimeError("Missing TINKER_API_KEY environment variable")

    tinker, _TrainOnWhat, get_renderer, _conversation_to_datum = load_tinker_dependencies()
    service_client = tinker.ServiceClient()
    training_client = await service_client.create_lora_training_client_async(
        base_model=args.base_model,
        rank=args.rank,
    )
    tokenizer = training_client.get_tokenizer()

    training_data = build_training_data(
        records=records,
        tokenizer=tokenizer,
        renderer_name=args.renderer,
        max_length=args.max_length,
    )
    renderer = get_renderer(args.renderer, tokenizer)
    stop_sequences = renderer.get_stop_sequences()

    total_batches = math.ceil(len(training_data) / args.batch_size)
    planned_steps = args.epochs * total_batches
    if args.max_steps is not None:
        planned_steps = min(planned_steps, args.max_steps)

    losses: list[float] = []
    step = 0
    with tqdm(total=planned_steps, unit="step") as progress:
        for epoch in range(args.epochs):
            for batch in batched(training_data, args.batch_size):
                if args.max_steps is not None and step >= args.max_steps:
                    break

                started = time.time()
                forward_future = await training_client.forward_backward_async(batch, "cross_entropy")
                optim_future = await training_client.optim_step_async(
                    tinker.AdamParams(learning_rate=args.learning_rate)
                )
                forward_result = await forward_future.result_async()
                await optim_future.result_async()

                loss = extract_loss(forward_result, batch)
                if loss is not None:
                    losses.append(loss)

                step += 1
                progress.update(1)
                progress.set_postfix(
                    epoch=epoch + 1,
                    examples=len(batch),
                    loss=f"{loss:.4f}" if loss is not None else "n/a",
                    seconds=f"{time.time() - started:.1f}",
                )

            if args.max_steps is not None and step >= args.max_steps:
                break

    model_path, sampling_client = await save_persistent_sampler_checkpoint(
        service_client=service_client,
        training_client=training_client,
        checkpoint_name=args.checkpoint_name,
    )

    print(
        json.dumps(
            {
                "checkpoint_name": args.checkpoint_name,
                "model_path": model_path,
                "base_model": args.base_model,
                "renderer": args.renderer,
                "records": len(records),
                "steps": step,
                "final_loss": losses[-1] if losses else None,
                "stop_sequences": stop_sequences,
                "sampling_client_type": type(sampling_client).__name__ if sampling_client else None,
            },
            indent=2,
        )
    )
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fine-tune a Tinker LoRA model on UrbanFlux borough-assignment JSONL."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--renderer", default=DEFAULT_RENDERER)
    parser.add_argument("--checkpoint-name", default=DEFAULT_CHECKPOINT_NAME)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--learning-rate", type=float, default=0.0001)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--max-examples", type=int)
    parser.add_argument("--max-length", type=int, default=4096)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> None:
    if args.rank < 1:
        raise ValueError("--rank must be at least 1")
    if args.learning_rate <= 0:
        raise ValueError("--learning-rate must be positive")
    if args.batch_size < 1:
        raise ValueError("--batch-size must be at least 1")
    if args.epochs < 1:
        raise ValueError("--epochs must be at least 1")
    if args.max_steps is not None and args.max_steps < 1:
        raise ValueError("--max-steps must be at least 1 when provided")
    if args.max_examples is not None and args.max_examples < 1:
        raise ValueError("--max-examples must be at least 1 when provided")
    if args.max_length < 1:
        raise ValueError("--max-length must be at least 1")
    args.dataset = args.dataset.resolve()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    validate_args(args)
    return asyncio.run(train(args))


if __name__ == "__main__":
    raise SystemExit(main())

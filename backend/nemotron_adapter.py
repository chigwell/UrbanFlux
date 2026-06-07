from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Callable

from impact import _normalise_source_url
from schemas import ImpactMetric, ReplanningParams


NEMOTRON_IMPACT_SYSTEM_PROMPT = """You are an urban planning impact analyst for London.

You will be given:
- Area statistics: population, size in km², and borough name
- Replanning parameters chosen by a planner (housing density, green space target, parking pressure, road fill, road alignment, height ambition) — all as integers 0–100
- Real borough data rows from the London Datastore (housing, transport, planning, socioeconomic themes)
- London-data-first impact metrics already calculated from selected-area inputs and mapped borough data

Your task is to return a JSON array of impact metrics, using the provided London-data-first values as a baseline and refining them only where the real borough data justifies it.

Rules:
- Only use the sources and data provided. Do not hallucinate statistics, datasets, or sources.
- The source field must be either "" or exactly one London Datastore URL from the allowed source URLs list in the user prompt. Do not create, repair, shorten, or guess URLs.
- External methodology URLs such as TfL or WHO must never appear in source. They may appear only in methodology_source if they were already provided.
- If real borough data supports a more precise estimate, use it and cite the mapped London Datastore dataset in source.
- If there is no relevant data for a metric, set improved_value and delta to "" (empty string).
- Treat Local summer heat exposure as a conservative local microclimate / heat-exposure proxy only. Never describe it as citywide weather, forecast weather, or an actual air-temperature change across London.
- Return ONLY a valid JSON array. No preamble, no explanation, no markdown, no code fences.
- Every object in the array must have exactly these six string fields: improved_metric, improved_value, delta, source, methodology_source, basis.

Example output format:
[
  {
    "improved_metric": "Cycling mode share",
    "improved_value": "+3.2 percentage points",
    "delta": "+3.2pp vs baseline",
    "source": "https://data.london.gov.uk/dataset/example-transport-data/",
    "methodology_source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
    "basis": "Mapped Westminster transport row + selected area/sliders"
  }
]"""


_NEMOTRON_TIMEOUT_S = 12
_ENV_FILE = Path(__file__).resolve().with_name(".env")
_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
_FAL_APP = "openrouter/router"
_LOGGER = logging.getLogger("urbanflux.nemotron")


def _get_fal_key_with_source() -> tuple[str, str]:
    fal_key = os.getenv("FAL_KEY", "").strip()
    if fal_key:
        return fal_key, "environment"

    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == "FAL_KEY":
                return value.strip().strip("'\""), f"env_file:{_ENV_FILE}"
    except OSError:
        return "", "missing"

    return "", "missing"


def _get_fal_key() -> str:
    fal_key, _source = _get_fal_key_with_source()
    return fal_key


def _json_preview(value: object, limit: int = 20000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated {len(text) - limit} chars]"


def _log_nemotron_attempt(
    attempt_id: str,
    event: str,
    **details: object,
) -> None:
    _LOGGER.info(
        "Nemotron impact attempt %s %s %s",
        attempt_id,
        event,
        _json_preview(details),
    )


def _validate_metric_sources(metrics: list[ImpactMetric], allowed_sources: set[str]) -> list[ImpactMetric]:
    """
    Keep primary sources constrained to mapped London Datastore URLs.

    Source validation intentionally enforces provenance only; it does not make
    metrics disappear because an allowed source site is slow or unavailable.
    """
    return [
        metric.model_copy(update={"source": source if source in allowed_sources else ""})
        for metric in metrics
        for source in [_normalise_source_url(metric.source)]
    ]


def _source_catalogue_text(allowed_sources: set[str]) -> str:
    if not allowed_sources:
        return "(none)"
    return "\n".join(f"- {source}" for source in sorted(allowed_sources))


def _metrics_to_text(metrics: list[ImpactMetric]) -> str:
    return "\n".join(
        (
            f"- {m.improved_metric}: {m.improved_value} "
            f"(delta: {m.delta}, source: {m.source}, "
            f"methodology_source: {m.methodology_source}, basis: {m.basis})"
        )
        for m in metrics
    )


def _call_nemotron(prompt: str) -> tuple[list[ImpactMetric] | None, str]:
    """
    Call Nemotron via fal.ai and parse the structured JSON response.
    Returns metrics plus a stable reason code for browser diagnostics.
    """
    attempt_id = uuid.uuid4().hex[:8]
    started_at = time.monotonic()
    fal_key, fal_key_source = _get_fal_key_with_source()
    _log_nemotron_attempt(
        attempt_id,
        "start",
        fal_key_present=bool(fal_key),
        fal_key_source=fal_key_source,
        env_file=str(_ENV_FILE),
        env_file_exists=_ENV_FILE.exists(),
        app=_FAL_APP,
        model=_NEMOTRON_MODEL,
        system_prompt_chars=len(NEMOTRON_IMPACT_SYSTEM_PROMPT),
        prompt_chars=len(prompt),
    )
    if not fal_key:
        _log_nemotron_attempt(attempt_id, "fallback", reason="fal_key_missing")
        return None, "fal_key_missing"

    if not os.getenv("FAL_KEY"):
        os.environ["FAL_KEY"] = fal_key
        _log_nemotron_attempt(
            attempt_id,
            "loaded_fal_key_into_process_environment",
            source=fal_key_source,
        )

    try:
        import fal_client
    except ImportError:
        _log_nemotron_attempt(attempt_id, "fallback", reason="fal_client_unavailable")
        return None, "fal_client_unavailable"

    _log_nemotron_attempt(
        attempt_id,
        "request",
        app=_FAL_APP,
        model=_NEMOTRON_MODEL,
        with_logs=False,
        system_prompt=NEMOTRON_IMPACT_SYSTEM_PROMPT,
        prompt=prompt,
    )
    try:
        result = fal_client.subscribe(
            _FAL_APP,
            arguments={
                "model": _NEMOTRON_MODEL,
                "system_prompt": NEMOTRON_IMPACT_SYSTEM_PROMPT,
                "prompt": prompt,
            },
            with_logs=False,
        )
    except Exception as exc:
        _LOGGER.exception(
            "Nemotron impact attempt %s call failed after %.3fs",
            attempt_id,
            time.monotonic() - started_at,
        )
        return None, f"nemotron_call_failed:{type(exc).__name__}"

    _log_nemotron_attempt(
        attempt_id,
        "response",
        elapsed_s=round(time.monotonic() - started_at, 3),
        result_type=type(result).__name__,
        result_keys=sorted(result.keys()) if isinstance(result, dict) else [],
        result_preview=result,
    )

    raw = (
        result.get("output")
        or result.get("text")
        or (result.get("choices") or [{}])[0].get("message", {}).get("content")
        or ""
    )

    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            _log_nemotron_attempt(
                attempt_id,
                "fallback",
                reason="invalid_metric_json",
                raw_chars=len(raw),
                raw_preview=raw,
                parsed_type=type(parsed).__name__,
            )
            return None, "invalid_metric_json"
        metrics = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            metrics.append(
                ImpactMetric(
                    improved_metric=str(item.get("improved_metric", "")),
                    improved_value=str(item.get("improved_value", "")),
                    delta=str(item.get("delta", "")),
                    source=str(item.get("source", "")),
                    methodology_source=str(item.get("methodology_source", "")),
                    basis=str(item.get("basis", "")),
                )
            )
        if not metrics:
            _log_nemotron_attempt(
                attempt_id,
                "fallback",
                reason="invalid_metric_json",
                raw_chars=len(raw),
                raw_preview=raw,
                parsed_items=len(parsed),
                valid_metrics=0,
            )
            return None, "invalid_metric_json"
        _log_nemotron_attempt(
            attempt_id,
            "success",
            elapsed_s=round(time.monotonic() - started_at, 3),
            raw_chars=len(raw),
            raw_preview=raw,
            parsed_items=len(parsed),
            valid_metrics=len(metrics),
            metric_names=[metric.improved_metric for metric in metrics],
        )
        return metrics, "nemotron_refinement_succeeded"
    except Exception as exc:
        _LOGGER.exception(
            "Nemotron impact attempt %s response parse failed after %.3fs; raw preview: %s",
            attempt_id,
            time.monotonic() - started_at,
            raw[:4000],
        )
        return None, "invalid_metric_json"


def _nemotron_impact_metrics(
    population: int,
    area_km2: float,
    params: ReplanningParams,
    london_metrics: list[ImpactMetric],
    borough_name: str,
    borough_rows: str,
    borough_sources: set[str],
    call_nemotron: Callable[[str], tuple[list[ImpactMetric] | None, str]] | None = None,
) -> tuple[list[ImpactMetric], str, str, str]:
    """
    Try to get Nemotron-refined metrics within the timeout window.
    Falls back to London-data-first deterministic metrics if Nemotron is too
    slow or unavailable.
    """
    allowed_sources = {
        _normalise_source_url(metric.source)
        for metric in london_metrics
        if _normalise_source_url(metric.source)
    }
    allowed_sources.update(borough_sources)
    _LOGGER.info(
        "Preparing Nemotron impact refinement for borough=%s population=%s area_km2=%s "
        "london_metrics=%s borough_sources=%s allowed_sources=%s",
        borough_name or "unknown",
        population,
        area_km2,
        len(london_metrics),
        len(borough_sources),
        len(allowed_sources),
    )

    prompt = f"""Area statistics:
- Population: {population:,}
- Area: {area_km2} km²
- Borough: {borough_name or "unknown"}

Replanning parameters (0–100 scale):
- Housing density: {params.housing_density}
- Green space target: {params.green_space_target}
- Parking pressure: {params.parking_pressure}
- Road fill: {params.road_fill}
- Road alignment: {params.road_alignment}
- Height ambition: {params.height_ambition}

Real borough data from London Datastore:
{borough_rows if borough_rows else "(unavailable)"}

London-data-first impact metrics (use as baseline):
{_metrics_to_text(london_metrics)}

Allowed source URLs for the source field (London Datastore only):
{_source_catalogue_text(allowed_sources)}

Return the refined JSON array of impact metrics."""

    call_nemotron = call_nemotron or _call_nemotron

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(call_nemotron, prompt)
    try:
        nemotron_metrics, calculation_reason = future.result(timeout=_NEMOTRON_TIMEOUT_S)
    except FuturesTimeoutError:
        nemotron_metrics = None
        calculation_reason = "nemotron_timeout"
        _LOGGER.warning(
            "Nemotron impact refinement timed out after %ss for borough=%s",
            _NEMOTRON_TIMEOUT_S,
            borough_name or "unknown",
        )
        executor.shutdown(wait=False, cancel_futures=True)
    except Exception as exc:
        nemotron_metrics = None
        calculation_reason = f"nemotron_call_failed:{type(exc).__name__}"
        _LOGGER.exception("Nemotron impact refinement worker failed")
        executor.shutdown(wait=True)
    else:
        executor.shutdown(wait=True)

    if nemotron_metrics:
        nemotron_metrics = _validate_metric_sources(nemotron_metrics, allowed_sources)
        note = (
            f"Refined by Nvidia Nemotron using real {borough_name} data"
            if borough_name
            else "Refined by Nvidia Nemotron using London Datastore data"
        )
        _LOGGER.info(
            "Nemotron impact refinement selected engine=nemotron reason=%s metrics=%s",
            calculation_reason,
            len(nemotron_metrics),
        )
        return nemotron_metrics, note, "nemotron", calculation_reason

    has_london_sources = any(_normalise_source_url(metric.source) for metric in london_metrics)
    if borough_name and has_london_sources:
        note = f"London Datastore mapped estimates for {borough_name}"
    elif borough_name:
        note = f"Benchmark-method estimates for {borough_name}; mapped rows unavailable"
    else:
        note = "Benchmark-method estimates; mapped borough data unavailable"
    _LOGGER.info(
        "Nemotron impact refinement selected engine=deterministic_fallback reason=%s note=%s",
        calculation_reason,
        note,
    )
    return _validate_metric_sources(london_metrics, allowed_sources), note, "deterministic_fallback", calculation_reason

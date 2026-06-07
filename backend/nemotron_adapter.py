from __future__ import annotations

import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Callable

import httpx

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


_DEFAULT_IMPACT_LLM_TIMEOUT_S = 20
_ENV_FILE = Path(__file__).resolve().with_name(".env")
_NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"
_FAL_APP = "openrouter/router"
_FALLBACK_LLM_MODEL_ENV = "FALLBACK_LLM_PROVIDER_MODEL"
_FALLBACK_LLM_TOKEN_ENV = "FALLBACK_LLM_PROVIDER_TOKEN"
_FALLBACK_LLM_URL_ENV = "FALLBACK_LLM_PROVIDER_URL"
_LOGGER = logging.getLogger("urbanflux.nemotron")


def _impact_llm_timeout_s() -> float:
    value = os.getenv("IMPACT_LLM_TIMEOUT_S", "").strip() or _env_file_value("IMPACT_LLM_TIMEOUT_S")
    if not value:
        return _DEFAULT_IMPACT_LLM_TIMEOUT_S
    try:
        timeout = float(value)
    except ValueError:
        return _DEFAULT_IMPACT_LLM_TIMEOUT_S
    return max(1.0, timeout)


def _env_file_value(name: str) -> str:
    try:
        for line in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("'\"")
    except OSError:
        return ""

    return ""


def _get_env_with_source(name: str) -> tuple[str, str]:
    value = os.getenv(name, "").strip()
    if value:
        return value, "environment"

    value = _env_file_value(name)
    if value:
        return value, f"env_file:{_ENV_FILE}"

    return "", "missing"


def _get_fal_key_with_source() -> tuple[str, str]:
    return _get_env_with_source("FAL_KEY")


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


def _metrics_from_raw_response(
    raw: str,
    attempt_id: str,
    provider: str,
    started_at: float,
) -> tuple[list[ImpactMetric] | None, str]:
    try:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            _log_nemotron_attempt(
                attempt_id,
                "fallback",
                provider=provider,
                reason=f"{provider}_invalid_metric_json",
                raw_chars=len(raw),
                raw_preview=raw,
                parsed_type=type(parsed).__name__,
            )
            return None, f"{provider}_invalid_metric_json"
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
                provider=provider,
                reason=f"{provider}_invalid_metric_json",
                raw_chars=len(raw),
                raw_preview=raw,
                parsed_items=len(parsed),
                valid_metrics=0,
            )
            return None, f"{provider}_invalid_metric_json"
        _log_nemotron_attempt(
            attempt_id,
            "success",
            provider=provider,
            elapsed_s=round(time.monotonic() - started_at, 3),
            raw_chars=len(raw),
            raw_preview=raw,
            parsed_items=len(parsed),
            valid_metrics=len(metrics),
            metric_names=[metric.improved_metric for metric in metrics],
        )
        return metrics, f"{provider}_refinement_succeeded"
    except Exception:
        _LOGGER.exception(
            "Nemotron impact attempt %s %s response parse failed after %.3fs; raw preview: %s",
            attempt_id,
            provider,
            time.monotonic() - started_at,
            raw[:4000],
        )
        return None, f"{provider}_invalid_metric_json"


def _call_fal_nemotron(prompt: str, attempt_id: str, started_at: float) -> tuple[list[ImpactMetric] | None, str]:
    fal_key, fal_key_source = _get_fal_key_with_source()
    _log_nemotron_attempt(
        attempt_id,
        "fal_start",
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
        _log_nemotron_attempt(attempt_id, "fal_failed", reason="fal_key_missing")
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
        _log_nemotron_attempt(attempt_id, "fal_failed", reason="fal_client_unavailable")
        return None, "fal_client_unavailable"

    _log_nemotron_attempt(
        attempt_id,
        "fal_request",
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
            "Nemotron impact attempt %s FAL call failed after %.3fs",
            attempt_id,
            time.monotonic() - started_at,
        )
        return None, f"nemotron_call_failed:{type(exc).__name__}"

    _log_nemotron_attempt(
        attempt_id,
        "fal_response",
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
    return _metrics_from_raw_response(raw, attempt_id, "nemotron", started_at)


def _fallback_chat_completions_url(url: str) -> str:
    clean_url = url.rstrip("/")
    if clean_url.endswith("/chat/completions"):
        return clean_url
    return f"{clean_url}/chat/completions"


def _fallback_llm_config() -> tuple[str, str, str, str, str, str]:
    url, url_source = _get_env_with_source(_FALLBACK_LLM_URL_ENV)
    token, token_source = _get_env_with_source(_FALLBACK_LLM_TOKEN_ENV)
    model, model_source = _get_env_with_source(_FALLBACK_LLM_MODEL_ENV)
    return url, token, model or _NEMOTRON_MODEL, url_source, token_source, model_source or "default"


def _call_fallback_llm(
    prompt: str,
    attempt_id: str,
    started_at: float,
    primary_reason: str,
) -> tuple[list[ImpactMetric] | None, str]:
    url, token, model, url_source, token_source, model_source = _fallback_llm_config()
    chat_completions_url = _fallback_chat_completions_url(url) if url else ""
    _log_nemotron_attempt(
        attempt_id,
        "fallback_llm_start",
        url_present=bool(url),
        token_present=bool(token),
        url_source=url_source,
        token_source=token_source,
        model_source=model_source,
        model=model,
        primary_reason=primary_reason,
    )
    if not url or not token:
        missing = []
        if not url:
            missing.append(_FALLBACK_LLM_URL_ENV)
        if not token:
            missing.append(_FALLBACK_LLM_TOKEN_ENV)
        reason = f"fallback_llm_config_missing:{','.join(missing)}:after:{primary_reason}"
        _log_nemotron_attempt(attempt_id, "fallback_llm_failed", reason=reason)
        return None, reason

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": NEMOTRON_IMPACT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    _log_nemotron_attempt(
        attempt_id,
        "fallback_llm_request",
        url=chat_completions_url,
        model=model,
        payload=payload,
        primary_reason=primary_reason,
    )
    try:
        response = httpx.post(
            chat_completions_url,
            headers={
                "authorization": f"Bearer {token}",
                "content-type": "application/json",
            },
            json=payload,
            timeout=_impact_llm_timeout_s(),
        )
        response.raise_for_status()
    except Exception as exc:
        _LOGGER.exception(
            "Nemotron impact attempt %s fallback LLM call failed after %.3fs",
            attempt_id,
            time.monotonic() - started_at,
        )
        return None, f"fallback_llm_call_failed:{type(exc).__name__}:after:{primary_reason}"

    try:
        result = response.json()
    except Exception:
        result = {"raw_text": response.text}

    _log_nemotron_attempt(
        attempt_id,
        "fallback_llm_response",
        elapsed_s=round(time.monotonic() - started_at, 3),
        status_code=response.status_code,
        result_type=type(result).__name__,
        result_keys=sorted(result.keys()) if isinstance(result, dict) else [],
        result_preview=result,
    )

    raw = (
        result.get("output")
        or result.get("text")
        or (result.get("choices") or [{}])[0].get("message", {}).get("content")
        or result.get("raw_text")
        or ""
    )
    metrics, reason = _metrics_from_raw_response(raw, attempt_id, "fallback_llm", started_at)
    if metrics:
        return metrics, f"{reason}:after:{primary_reason}"
    return None, f"{reason}:after:{primary_reason}"


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
    _log_nemotron_attempt(
        attempt_id,
        "start",
        env_file=str(_ENV_FILE),
        env_file_exists=_ENV_FILE.exists(),
        primary_app=_FAL_APP,
        primary_model=_NEMOTRON_MODEL,
        system_prompt_chars=len(NEMOTRON_IMPACT_SYSTEM_PROMPT),
        prompt_chars=len(prompt),
    )

    metrics, primary_reason = _call_fal_nemotron(prompt, attempt_id, started_at)
    if metrics:
        return metrics, primary_reason

    _log_nemotron_attempt(
        attempt_id,
        "primary_provider_failed_trying_fallback_llm",
        primary_reason=primary_reason,
    )
    return _call_fallback_llm(prompt, attempt_id, started_at, primary_reason)


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
        timeout_s = _impact_llm_timeout_s()
        nemotron_metrics, calculation_reason = future.result(timeout=timeout_s)
    except FuturesTimeoutError:
        nemotron_metrics = None
        calculation_reason = "nemotron_timeout"
        _LOGGER.warning(
            "Nemotron impact refinement timed out after %ss for borough=%s",
            _impact_llm_timeout_s(),
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
        used_fallback_llm = calculation_reason.startswith("fallback_llm_refinement_succeeded")
        if used_fallback_llm:
            note = (
                f"Refined by fallback LLM provider using real {borough_name} data"
                if borough_name
                else "Refined by fallback LLM provider using London Datastore data"
            )
            engine = "fallback_llm"
        else:
            note = (
                f"Refined by Nvidia Nemotron using real {borough_name} data"
                if borough_name
                else "Refined by Nvidia Nemotron using London Datastore data"
            )
            engine = "nemotron"
        _LOGGER.info(
            "Nemotron impact refinement selected engine=%s reason=%s metrics=%s",
            engine,
            calculation_reason,
            len(nemotron_metrics),
        )
        return nemotron_metrics, note, engine, calculation_reason

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

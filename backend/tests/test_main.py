from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import nemotron_adapter  # noqa: E402
from utils import _format_latest_theme_row  # noqa: E402


client = TestClient(main.app)


SAMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-0.1312, 51.5069],
            [-0.1198, 51.5075],
            [-0.1158, 51.5015],
            [-0.1268, 51.4987],
            [-0.1355, 51.5018],
            [-0.1312, 51.5069],
        ]
    ],
}


def test_root_endpoint_returns_status_message() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "UrbanFlux backend is running"}


def test_hello_endpoint_returns_hello_world() -> None:
    response = client.get("/hello")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_population_endpoint_returns_selected_area_population(monkeypatch) -> None:
    monkeypatch.setattr(main, "_population_in_polygon", lambda geom: (2480, 5))

    response = client.post("/population", json={"polygon": SAMPLE_POLYGON})

    assert response.status_code == 200
    payload = response.json()
    assert payload["approximate_population"] == 2480
    assert payload["lsoa_count"] == 5
    assert payload["area_km2"] > 0
    assert payload["note"] == "2021 Census, LSOA-level intersection"


def test_impact_endpoint_returns_replanning_metrics(monkeypatch) -> None:
    monkeypatch.setattr(main, "_population_in_polygon", lambda geom: (2480, 5))
    monkeypatch.setattr(main, "_validate_metric_sources", lambda metrics, allowed_sources: metrics)
    transport_source = "https://data.london.gov.uk/dataset/transport-data/"
    housing_source = "https://data.london.gov.uk/dataset/housing-data/"
    planning_source = "https://data.london.gov.uk/dataset/planning-data/"
    socioeconomic_source = "https://data.london.gov.uk/dataset/socioeconomic-data/"
    monkeypatch.setattr(
        main,
        "_fetch_borough_context",
        lambda lat, lon: (
            "Westminster",
            {
                "transport": {
                    "theme": "transport",
                    "dataset_title": "Transport data",
                    "source_url": transport_source,
                },
                "housing": {
                    "theme": "housing",
                    "dataset_title": "Housing data",
                    "source_url": housing_source,
                },
                "planning_land": {
                    "theme": "planning_land",
                    "dataset_title": "Planning data",
                    "source_url": planning_source,
                },
                "socioeconomic": {
                    "theme": "socioeconomic",
                    "dataset_title": "Socioeconomic data",
                    "source_url": socioeconomic_source,
                },
            },
            "Borough: Westminster",
            {transport_source, housing_source, planning_source, socioeconomic_source},
        ),
    )

    response = client.post(
        "/impact",
        json={
            "polygon": SAMPLE_POLYGON,
            "params": {
                "housing_density": 64,
                "green_space_target": 20,
                "parking_pressure": 18,
                "road_fill": 35,
                "road_alignment": 72,
                "height_ambition": 58,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["approximate_population"] == 2480
    assert payload["area_km2"] > 0
    assert len(payload["metrics"]) == 5
    assert payload["metrics"][0]["improved_metric"] == "Cycling mode share"
    assert payload["metrics"][0]["source"] == transport_source
    assert payload["metrics"][0]["methodology_source"] == main._METHODOLOGY_TFL_STREETS
    assert "Mapped Westminster transport row" in payload["metrics"][0]["basis"]
    assert payload["note"] == "London Datastore mapped estimates for Westminster"
    assert payload["calculation_engine"] == "deterministic_fallback"
    assert payload["calculation_reason"] == (
        "fallback_llm_config_missing:FALLBACK_LLM_PROVIDER_URL,"
        "FALLBACK_LLM_PROVIDER_TOKEN:after:fal_key_missing"
    )


def test_default_heat_metric_is_local_and_capped() -> None:
    metrics = main._compute_impact_metrics(2480, 0.42, main.ReplanningParams())
    heat_metric = next(metric for metric in metrics if metric.improved_metric == "Local summer heat exposure")

    assert heat_metric.improved_value == "-0.32 °C"
    assert heat_metric.delta == "-0.32 °C local heat proxy vs low-greening scenario"


def test_impact_metrics_change_with_replanning_params() -> None:
    low = main._compute_impact_metrics(
        2480,
        0.42,
        main.ReplanningParams(
            housing_density=10,
            green_space_target=5,
            parking_pressure=80,
            road_fill=5,
            road_alignment=0,
            height_ambition=0,
        ),
    )
    high = main._compute_impact_metrics(
        2480,
        0.42,
        main.ReplanningParams(
            housing_density=100,
            green_space_target=80,
            parking_pressure=0,
            road_fill=100,
            road_alignment=100,
            height_ambition=100,
        ),
    )

    low_by_name = {metric.improved_metric: metric.improved_value for metric in low}
    high_by_name = {metric.improved_metric: metric.improved_value for metric in high}

    assert low_by_name["Cycling mode share"] != high_by_name["Cycling mode share"]
    assert low_by_name["Housing capacity"] != high_by_name["Housing capacity"]
    assert low_by_name["Local summer heat exposure"] != high_by_name["Local summer heat exposure"]
    assert low_by_name["Productive land released from parking"] != high_by_name["Productive land released from parking"]


def test_impact_metrics_use_london_sources_not_external_methodology() -> None:
    transport_source = "https://data.london.gov.uk/dataset/transport-data/"
    housing_source = "https://data.london.gov.uk/dataset/housing-data/"
    planning_source = "https://data.london.gov.uk/dataset/planning-data/"
    socioeconomic_source = "https://data.london.gov.uk/dataset/socioeconomic-data/"

    metrics = main._compute_impact_metrics(
        2480,
        0.42,
        main.ReplanningParams(),
        borough_name="Westminster",
        rows_by_theme={
            "transport": {"dataset_title": "Transport data", "source_url": transport_source},
            "housing": {"dataset_title": "Housing data", "source_url": housing_source},
            "planning_land": {"dataset_title": "Planning data", "source_url": planning_source},
            "socioeconomic": {"dataset_title": "Socioeconomic data", "source_url": socioeconomic_source},
        },
    )

    sources = {metric.source for metric in metrics}
    methodology_sources = {metric.methodology_source for metric in metrics}

    assert sources == {transport_source, housing_source, planning_source, socioeconomic_source}
    assert main._METHODOLOGY_TFL_STREETS not in sources
    assert main._METHODOLOGY_WHO_HEAT not in sources
    assert main._METHODOLOGY_TFL_STREETS in methodology_sources
    assert main._METHODOLOGY_WHO_HEAT in methodology_sources


def test_missing_london_rows_leave_source_empty_with_benchmark_basis() -> None:
    metrics = main._compute_impact_metrics(
        2480,
        0.42,
        main.ReplanningParams(),
        borough_name="Westminster",
        rows_by_theme={},
    )

    assert all(metric.source == "" for metric in metrics)
    assert all("Benchmark method only" in metric.basis for metric in metrics)


def test_nemotron_prompt_restricts_sources_and_weather_claims() -> None:
    prompt = main.NEMOTRON_IMPACT_SYSTEM_PROMPT

    assert "exactly one London Datastore URL from the allowed source URLs list" in prompt
    assert "must never appear in source" in prompt
    assert "Never describe it as citywide weather" in prompt


def test_validate_metric_sources_preserves_allowed_source() -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    metric = main.ImpactMetric(
        improved_metric="Housing capacity",
        improved_value="+1%",
        delta="+1% vs baseline",
        source=source,
    )

    validated = main._validate_metric_sources([metric], {source})

    assert validated[0].source == source


def test_validate_metric_sources_blanks_unlisted_source() -> None:
    metric = main.ImpactMetric(
        improved_metric="Housing capacity",
        improved_value="+1%",
        delta="+1% vs baseline",
        source="https://invented.example/source",
    )

    validated = main._validate_metric_sources([metric], {"https://data.london.gov.uk/dataset/example/"})

    assert validated[0].source == ""


def test_validate_metric_sources_preserves_allowed_source_without_live_check() -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    metric = main.ImpactMetric(
        improved_metric="Housing capacity",
        improved_value="+1%",
        delta="+1% vs baseline",
        source=source,
    )
    validated = main._validate_metric_sources([metric], {source})

    assert validated[0].source == source


def test_validate_metric_sources_keeps_empty_source_empty() -> None:
    metric = main.ImpactMetric(
        improved_metric="Housing capacity",
        improved_value="+1%",
        delta="+1% vs baseline",
        source="",
    )

    validated = main._validate_metric_sources([metric], {"https://data.london.gov.uk/dataset/example/"})

    assert validated[0].source == ""


def test_lsoa_paths_are_backend_relative(monkeypatch, tmp_path) -> None:
    monkeypatch.chdir(tmp_path)

    assert main._LSOA_BOUNDARIES_PATH.is_absolute()
    assert main._POPULATION_JSON_PATH.is_absolute()
    assert main._LSOA_BOUNDARIES_PATH.parent == BACKEND_DIR
    assert main._POPULATION_JSON_PATH.parent == BACKEND_DIR


def test_fetch_borough_context_filters_to_trusted_themes(monkeypatch) -> None:
    housing_source = "https://data.london.gov.uk/dataset/housing-data/"
    transport_source = "https://data.london.gov.uk/download/transport.csv"
    safety_source = "https://data.london.gov.uk/dataset/safety-data/"

    def fake_borough_data_response(lat: float, lon: float, top_datasets_limit: int):
        assert lat == 51.5074
        assert lon == -0.1278
        assert top_datasets_limit == 30
        return {
            "borough": {"name": "Westminster"},
            "latest_rows_by_theme": [
                {
                    "theme": "housing",
                    "dataset_title": "Housing data",
                    "source_url": housing_source,
                    "source_row_preview": "homes: 10",
                    "date_start": "2024-01-01",
                },
                {
                    "theme": "transport",
                    "dataset_title": "Transport data",
                    "source_url": "https://example.com/not-london",
                    "csv_url": transport_source,
                    "source_row_preview": "cycle: 2",
                    "date_start": "2024-02-01",
                },
                {
                    "theme": "safety",
                    "dataset_title": "Safety data",
                    "source_url": safety_source,
                    "source_row_preview": "crime: 3",
                    "date_start": "2024-03-01",
                },
            ],
        }

    monkeypatch.setattr(main, "build_borough_data_test_response", fake_borough_data_response)

    borough_name, rows_by_theme, borough_rows, allowed_sources = main._fetch_borough_context(51.5074, -0.1278)

    assert borough_name == "Westminster"
    assert set(rows_by_theme) == {"housing", "transport"}
    assert "[safety]" not in borough_rows
    assert housing_source in allowed_sources
    assert transport_source in allowed_sources
    assert safety_source not in allowed_sources


def test_fetch_borough_context_handles_missing_borough(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "build_borough_data_test_response",
        lambda lat, lon, top_datasets_limit: {"borough": None, "latest_rows_by_theme": []},
    )

    assert main._fetch_borough_context(51.5074, -0.1278) == ("", {}, "", set())


def test_call_nemotron_returns_none_without_fal_key(monkeypatch) -> None:
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.delenv("FALLBACK_LLM_PROVIDER_URL", raising=False)
    monkeypatch.delenv("FALLBACK_LLM_PROVIDER_TOKEN", raising=False)
    monkeypatch.setattr(nemotron_adapter, "_ENV_FILE", Path("/tmp/urbanflux-missing.env"))

    metrics, reason = main._call_nemotron("prompt")

    assert metrics is None
    assert reason == (
        "fallback_llm_config_missing:FALLBACK_LLM_PROVIDER_URL,"
        "FALLBACK_LLM_PROVIDER_TOKEN:after:fal_key_missing"
    )


def test_call_nemotron_reads_fal_key_from_env_file(monkeypatch, tmp_path) -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    env_file = tmp_path / ".env"
    env_file.write_text("FAL_KEY=file-key\n", encoding="utf-8")
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(nemotron_adapter, "_ENV_FILE", env_file)
    monkeypatch.setitem(
        sys.modules,
        "fal_client",
        types.SimpleNamespace(
            subscribe=lambda *args, **kwargs: (
                {
                    "output": json.dumps(
                        [
                            {
                                "improved_metric": "Housing capacity",
                                "improved_value": "+1%",
                                "delta": "+1% vs baseline",
                                "source": source,
                                "methodology_source": "",
                                "basis": "Mapped data",
                            }
                        ]
                    )
                }
                if os.environ.get("FAL_KEY") == "file-key"
                else (_ for _ in ()).throw(AssertionError("FAL_KEY was not loaded into os.environ"))
            )
        ),
    )

    metrics, reason = main._call_nemotron("prompt")

    assert metrics is not None
    assert reason == "nemotron_refinement_succeeded"


def test_call_nemotron_parses_valid_json(monkeypatch) -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setitem(
        sys.modules,
        "fal_client",
        types.SimpleNamespace(
            subscribe=lambda *args, **kwargs: {
                "output": json.dumps(
                    [
                        {
                            "improved_metric": "Housing capacity",
                            "improved_value": "+1%",
                            "delta": "+1% vs baseline",
                            "source": source,
                            "methodology_source": "",
                            "basis": "Mapped data",
                        }
                    ]
                )
            }
        ),
    )

    metrics, reason = main._call_nemotron("prompt")

    assert metrics is not None
    assert reason == "nemotron_refinement_succeeded"
    assert metrics[0].improved_metric == "Housing capacity"
    assert metrics[0].source == source


def test_call_nemotron_returns_none_for_invalid_json(monkeypatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.delenv("FALLBACK_LLM_PROVIDER_URL", raising=False)
    monkeypatch.delenv("FALLBACK_LLM_PROVIDER_TOKEN", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "fal_client",
        types.SimpleNamespace(subscribe=lambda *args, **kwargs: {"output": "not json"}),
    )

    metrics, reason = main._call_nemotron("prompt")

    assert metrics is None
    assert reason == (
        "fallback_llm_config_missing:FALLBACK_LLM_PROVIDER_URL,"
        "FALLBACK_LLM_PROVIDER_TOKEN:after:nemotron_invalid_metric_json"
    )


def test_call_nemotron_uses_fallback_llm_after_fal_failure(monkeypatch) -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    monkeypatch.setenv("FAL_KEY", "test-key")
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER_URL", "https://fallback.example/v1")
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER_TOKEN", "fallback-token")
    monkeypatch.setenv("FALLBACK_LLM_PROVIDER_MODEL", "fallback-model")
    monkeypatch.setitem(
        sys.modules,
        "fal_client",
        types.SimpleNamespace(
            subscribe=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fal down"))
        ),
    )

    class FakeResponse:
        status_code = 200
        text = ""

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                [
                                    {
                                        "improved_metric": "Housing capacity",
                                        "improved_value": "+3%",
                                        "delta": "+3% vs baseline",
                                        "source": source,
                                        "methodology_source": "",
                                        "basis": "Fallback mapped data",
                                    }
                                ]
                            )
                        }
                    }
                ]
            }

    calls = []

    def fake_post(url, headers, json, timeout):
        calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(nemotron_adapter.httpx, "post", fake_post)

    metrics, reason = main._call_nemotron("prompt")

    assert metrics is not None
    assert metrics[0].improved_metric == "Housing capacity"
    assert reason == "fallback_llm_refinement_succeeded:after:nemotron_call_failed:RuntimeError"
    assert calls[0]["url"] == "https://fallback.example/v1/chat/completions"
    assert calls[0]["headers"]["authorization"] == "Bearer fallback-token"
    assert calls[0]["json"]["model"] == "fallback-model"


def test_nemotron_impact_metrics_falls_back_when_unavailable(monkeypatch) -> None:
    source = "https://data.london.gov.uk/dataset/example/"
    london_metrics = [
        main.ImpactMetric(
            improved_metric="Housing capacity",
            improved_value="+1%",
            delta="+1% vs baseline",
            source=source,
        )
    ]
    monkeypatch.setattr(main, "_call_nemotron", lambda prompt: (None, "fal_key_missing"))

    metrics, note, calculation_engine, calculation_reason = main._nemotron_impact_metrics(
        population=2480,
        area_km2=0.42,
        params=main.ReplanningParams(),
        london_metrics=london_metrics,
        borough_name="Westminster",
        borough_rows="Borough: Westminster",
        borough_sources={source},
    )

    assert metrics == london_metrics
    assert note == "London Datastore mapped estimates for Westminster"
    assert calculation_engine == "deterministic_fallback"
    assert calculation_reason == "fal_key_missing"


def test_nemotron_impact_metrics_blanks_unallowed_refined_sources(monkeypatch) -> None:
    allowed_source = "https://data.london.gov.uk/dataset/example/"
    london_metrics = [
        main.ImpactMetric(
            improved_metric="Housing capacity",
            improved_value="+1%",
            delta="+1% vs baseline",
            source=allowed_source,
        )
    ]

    monkeypatch.setattr(
        main,
        "_call_nemotron",
        lambda prompt: (
            [
                main.ImpactMetric(
                    improved_metric="Housing capacity",
                    improved_value="+2%",
                    delta="+2% vs baseline",
                    source=allowed_source,
                ),
                main.ImpactMetric(
                    improved_metric="Invented",
                    improved_value="99",
                    delta="99",
                    source="https://invented.example/source",
                ),
            ],
            "nemotron_refinement_succeeded",
        ),
    )

    metrics, note, calculation_engine, calculation_reason = main._nemotron_impact_metrics(
        population=2480,
        area_km2=0.42,
        params=main.ReplanningParams(),
        london_metrics=london_metrics,
        borough_name="Westminster",
        borough_rows="Borough: Westminster",
        borough_sources={allowed_source},
    )

    assert note == "Refined by Nvidia Nemotron using real Westminster data"
    assert calculation_engine == "nemotron"
    assert calculation_reason == "nemotron_refinement_succeeded"
    assert metrics[0].source == allowed_source
    assert metrics[1].source == ""


def test_nemotron_impact_metrics_reports_fallback_llm_engine(monkeypatch) -> None:
    allowed_source = "https://data.london.gov.uk/dataset/example/"
    london_metrics = [
        main.ImpactMetric(
            improved_metric="Housing capacity",
            improved_value="+1%",
            delta="+1% vs baseline",
            source=allowed_source,
        )
    ]
    monkeypatch.setattr(
        main,
        "_call_nemotron",
        lambda prompt: (
            [
                main.ImpactMetric(
                    improved_metric="Housing capacity",
                    improved_value="+4%",
                    delta="+4% vs baseline",
                    source=allowed_source,
                )
            ],
            "fallback_llm_refinement_succeeded:after:nemotron_call_failed:RuntimeError",
        ),
    )

    metrics, note, calculation_engine, calculation_reason = main._nemotron_impact_metrics(
        population=2480,
        area_km2=0.42,
        params=main.ReplanningParams(),
        london_metrics=london_metrics,
        borough_name="Westminster",
        borough_rows="Borough: Westminster",
        borough_sources={allowed_source},
    )

    assert metrics[0].improved_value == "+4%"
    assert note == "Refined by fallback LLM provider using real Westminster data"
    assert calculation_engine == "fallback_llm"
    assert calculation_reason == "fallback_llm_refinement_succeeded:after:nemotron_call_failed:RuntimeError"


def test_nemotron_impact_metrics_merges_missing_deterministic_metrics(monkeypatch) -> None:
    allowed_source = "https://data.london.gov.uk/dataset/example/"
    london_metrics = [
        main.ImpactMetric(
            improved_metric="Housing capacity",
            improved_value="+1%",
            delta="+1% vs baseline",
            source=allowed_source,
        ),
        main.ImpactMetric(
            improved_metric="Cycling mode share",
            improved_value="+2 percentage points",
            delta="+2pp vs baseline",
            source=allowed_source,
        ),
    ]
    monkeypatch.setattr(
        main,
        "_call_nemotron",
        lambda prompt: (
            [
                main.ImpactMetric(
                    improved_metric="Housing capacity",
                    improved_value="+4%",
                    delta="+4% vs baseline",
                    source=allowed_source,
                ),
                main.ImpactMetric(
                    improved_metric=" housing   capacity ",
                    improved_value="+5%",
                    delta="+5% vs baseline",
                    source=allowed_source,
                ),
            ],
            "fallback_llm_refinement_succeeded:after:nemotron_call_failed:RuntimeError",
        ),
    )

    metrics, _note, calculation_engine, _calculation_reason = main._nemotron_impact_metrics(
        population=2480,
        area_km2=0.42,
        params=main.ReplanningParams(),
        london_metrics=london_metrics,
        borough_name="Westminster",
        borough_rows="Borough: Westminster",
        borough_sources={allowed_source},
    )

    assert calculation_engine == "fallback_llm"
    assert [metric.improved_metric for metric in metrics] == [
        "Housing capacity",
        "Cycling mode share",
    ]
    assert metrics[0].improved_value == "+4%"
    assert metrics[1].improved_value == "+2 percentage points"


def test_latest_theme_row_includes_source_links() -> None:
    row = {
        "row_number": 42,
        "date_start": "2024-01-01",
        "date_end": "2024-12-31",
        "source": {
            "dataset_title": "Housing data",
            "dataset_url": "https://data.london.gov.uk/dataset/housing-data/",
            "resource_title": "housing.csv",
            "csv_url": "https://data.london.gov.uk/download/housing.csv",
        },
        "source_row": {"Area": "Westminster", "Value": 286},
    }

    formatted = _format_latest_theme_row("housing", row)

    assert formatted["dataset_url"] == "https://data.london.gov.uk/dataset/housing-data/"
    assert formatted["csv_url"] == "https://data.london.gov.uk/download/housing.csv"
    assert formatted["source_url"] == "https://data.london.gov.uk/dataset/housing-data/"
    assert formatted["source_row_preview"] == "Area: Westminster; Value: 286"


def test_borough_data_test_endpoint_returns_mapped_data(monkeypatch) -> None:
    expected_payload = {
        "coordinates": {"lat": 51.5074, "lon": -0.1278},
        "borough": {"name": "Westminster", "code": "E09000033"},
        "summary_by_theme": [
            {
                "theme": "housing",
                "row_count": 123,
                "csv_file_count": 4,
                "min_date_start": "2020-01-01",
                "max_date_end": "2024-12-31",
            }
        ],
        "top_datasets": [
            {
                "theme": "housing",
                "row_count": 50,
                "dataset_title": "Housing data",
                "resource_title": "Housing CSV",
            }
        ],
        "latest_rows_by_theme": [
            {
                "theme": "housing",
                "dataset_title": "Housing data",
                "resource_title": "Housing CSV",
                "row_number": 42,
                "date_start": "2024-01-01",
                "date_end": "2024-12-31",
                "source_row_preview": "metric: value",
            }
        ],
    }

    def fake_borough_data_response(
        lat: float,
        lon: float,
        top_datasets_limit: int,
        theme: str | None = None,
    ):
        assert lat == 51.5074
        assert lon == -0.1278
        assert top_datasets_limit == 5
        assert theme is None
        return expected_payload

    monkeypatch.setattr(main, "build_borough_data_test_response", fake_borough_data_response)

    response = client.get("/borough-data-test?lat=51.5074&lon=-0.1278&top_datasets_limit=5")

    assert response.status_code == 200
    assert response.json() == expected_payload

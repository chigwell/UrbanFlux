from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402


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
    assert payload["note"] == "Benchmark estimates for Westminster"


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

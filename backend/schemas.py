from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GeoJSONPolygon(BaseModel):
    """A GeoJSON Polygon or MultiPolygon Feature or raw geometry."""

    type: str = Field(
        ...,
        description="GeoJSON object type. Use `Polygon`, `MultiPolygon`, or `Feature`.",
        examples=["Polygon"],
    )
    coordinates: Any | None = Field(
        default=None,
        description="GeoJSON coordinates for a raw Polygon or MultiPolygon geometry.",
    )
    geometry: Any | None = Field(
        default=None,
        description="GeoJSON geometry object when `type` is `Feature`.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
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
            ]
        }
    }


class ReplanningParams(BaseModel):
    housing_density: int = Field(64, ge=5, le=100, description="Housing density: homes per built block.")
    green_space_target: int = Field(35, ge=5, le=80, description="Green space target: share reserved as parks.")
    parking_pressure: int = Field(18, ge=0, le=80, description="Parking pressure: surface parking demand.")
    road_fill: int = Field(35, ge=0, le=100, description="Road fill: boundary anchors connected.")
    road_alignment: int = Field(72, ge=0, le=100, description="Road alignment: how straight corridors run.")
    height_ambition: int = Field(58, ge=0, le=100, description="Height ambition: massing of tall buildings.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "housing_density": 64,
                    "green_space_target": 35,
                    "parking_pressure": 18,
                    "road_fill": 35,
                    "road_alignment": 72,
                    "height_ambition": 58,
                }
            ]
        }
    }


class MessageResponse(BaseModel):
    message: str = Field(..., description="Human-readable response message.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {"message": "UrbanFlux backend is running"},
                {"message": "Hello World"},
            ]
        }
    }


class PopulationRequest(BaseModel):
    polygon: GeoJSONPolygon = Field(..., description="Selected area as a GeoJSON Polygon, MultiPolygon, or Feature.")


class PopulationResponse(BaseModel):
    approximate_population: int = Field(..., ge=0, description="Estimated population inside the selected area.")
    lsoa_count: int = Field(..., ge=0, description="Number of intersecting LSOA geometries used.")
    area_km2: float = Field(..., ge=0, description="Approximate selected area in square kilometres.")
    note: str = Field("2021 Census, LSOA-level intersection", description="Calculation note and data source context.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "approximate_population": 2480,
                    "lsoa_count": 5,
                    "area_km2": 0.42,
                    "note": "2021 Census, LSOA-level intersection",
                }
            ]
        }
    }


class ImpactMetric(BaseModel):
    improved_metric: str = Field(..., description="Name of the improved metric.")
    improved_value: str = Field(..., description="Estimated metric value after replanning.")
    delta: str = Field(..., description="Difference compared with the previous or baseline value.")
    source: str = Field(
        ...,
        description="Primary London Datastore dataset or CSV URL backing the estimate, or an empty string.",
    )
    methodology_source: str = Field(
        "",
        description="Optional external method URL used for the calculation, never the primary data source.",
    )
    basis: str = Field(
        "",
        description="Short explanation of the mapped data and selected-area inputs used.",
    )


class ImpactRequest(BaseModel):
    polygon: GeoJSONPolygon = Field(..., description="Selected area as a GeoJSON Polygon, MultiPolygon, or Feature.")
    params: ReplanningParams = Field(default_factory=ReplanningParams, description="User-selected replanning parameters.")


class ImpactResponse(BaseModel):
    approximate_population: int = Field(..., ge=0, description="Estimated population affected by replanning.")
    area_km2: float = Field(..., ge=0, description="Approximate selected area in square kilometres.")
    metrics: list[ImpactMetric] = Field(..., description="List of estimated impact metrics.")
    note: str = Field("Illustrative estimates - model integration in progress", description="Calculation note.")

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "approximate_population": 2480,
                    "area_km2": 0.42,
                    "metrics": [
                        {
                            "improved_metric": "Cycling mode share",
                            "improved_value": "+1.5 percentage points",
                            "delta": "+1.5pp vs baseline",
                            "source": "https://data.london.gov.uk/dataset/example-transport-data/",
                            "methodology_source": "https://tfl.gov.uk/corporate/publications-and-reports/streets-toolkit",
                            "basis": "Mapped Westminster transport row + selected area/sliders",
                        }
                    ],
                    "note": "Illustrative estimates - model integration in progress",
                }
            ]
        }
    }


class BoroughDataTestResponse(BaseModel):
    coordinates: dict[str, float] = Field(..., description="Input WGS84 coordinates.")
    borough: dict[str, Any] | None = Field(None, description="Resolved London borough for the coordinates.")
    summary_by_theme: list[dict[str, Any]] = Field(..., description="Row and CSV counts grouped by theme.")
    top_datasets: list[dict[str, Any]] = Field(..., description="Top datasets for the resolved borough.")
    latest_rows_by_theme: list[dict[str, Any]] = Field(
        ...,
        description="Most recent available source row preview for each returned theme.",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "coordinates": {"lat": 51.5074, "lon": -0.1278},
                    "borough": {"name": "Westminster", "code": "E09000033"},
                    "summary_by_theme": [
                        {
                            "theme": "housing",
                            "row_count": 1234,
                            "csv_file_count": 12,
                            "min_date_start": "2018-01-01",
                            "max_date_end": "2024-12-31",
                        }
                    ],
                    "top_datasets": [
                        {
                            "theme": "housing",
                            "row_count": 200,
                            "dataset_title": "Example dataset",
                            "dataset_url": "https://data.london.gov.uk/dataset/example/",
                            "resource_title": "Example resource",
                            "csv_url": "https://data.london.gov.uk/download/example/example.csv",
                        }
                    ],
                    "latest_rows_by_theme": [
                        {
                            "theme": "housing",
                            "dataset_title": "Example dataset",
                            "dataset_url": "https://data.london.gov.uk/dataset/example/",
                            "resource_title": "Example resource",
                            "csv_url": "https://data.london.gov.uk/download/example/example.csv",
                            "source_url": "https://data.london.gov.uk/dataset/example/",
                            "row_number": 42,
                            "date_start": "2024-01-01",
                            "date_end": "2024-12-31",
                            "source_row_preview": "key: value",
                        }
                    ],
                }
            ]
        }
    }

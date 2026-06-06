from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


TAGS_METADATA = [
    {
        "name": "status",
        "description": "Service status and connectivity checks.",
    },
    {
        "name": "population",
        "description": "Approximate population calculations for selected GeoJSON areas.",
    },
    {
        "name": "impact",
        "description": "Illustrative replanning impact calculations for selected areas and UI parameters.",
    },
    {
        "name": "borough-data",
        "description": "Test endpoints for mapped London borough datasets by coordinates.",
    },
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="UrbanFlux API",
        summary="FastAPI backend for UrbanFlux CityTwin.",
        description=(
            "UrbanFlux backend API for service checks, selected-area population estimates, "
            "and replanning impact calculations. OpenAPI is available at `/openapi.json`, "
            "Swagger UI at `/docs`, and ReDoc at `/redoc`."
        ),
        version="0.1.0",
        contact={
            "name": "UrbanFlux Team",
            "url": "https://urbanflux.london/",
        },
        openapi_tags=TAGS_METADATA,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return app

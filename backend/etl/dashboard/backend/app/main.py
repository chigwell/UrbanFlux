from __future__ import annotations

import asyncio
import csv
import io
import json
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .config import get_settings
from .csv_preview import preview_csv
from .csv_row_transformer import apply_csv_row_transformations
from .csv_transformation_planner import plan_csv_transformation
from .database import (
    csv_row_transformation_stats,
    export_csv_row_transformations,
    get_csv_file,
    get_csv_transformation_plan,
    get_source,
    get_stats,
    list_all_csv_row_transformations,
    list_borough_row_data,
    list_london_boroughs,
    list_london_borough_boundaries,
    init_db,
    list_csv_files,
    list_csv_row_transformations,
    list_csv_transformation_plans,
    list_sources,
    transformation_overview_stats,
)
from .download_jobs import DownloadJobManager
from .scraper import SyncOptions, download_csv_file_by_id, sync_catalogue
from .transformation_jobs import TransformationJobManager


class SyncRequest(BaseModel):
    mode: Literal["api", "pages"] = "api"
    download_files: bool = False
    limit: int | None = Field(default=None, ge=1)
    max_pages: int | None = Field(default=None, ge=1)
    max_file_size_mb: float | None = Field(default=None, gt=0)


class DownloadRequest(BaseModel):
    max_file_size_mb: float | None = Field(default=None, gt=0)


class PendingDownloadRequest(BaseModel):
    max_file_size_mb: float | None = Field(default=None, gt=0)
    retry_errors: bool = True
    limit: int | None = Field(default=None, ge=1)


class TransformationJobRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1)
    retry_plan_errors: bool = False
    retry_outdated_successes: bool = False
    retry_row_outputs: bool = False
    sample_rows: int = Field(default=8, ge=1, le=50)
    max_attempts: int = Field(default=3, ge=1, le=10)
    apply_existing_successes: bool = True


class TransformationPlanRequest(BaseModel):
    sample_rows: int = Field(default=8, ge=1, le=50)
    max_attempts: int = Field(default=3, ge=1, le=10)
    apply_rows: bool = False


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


settings = get_settings()
download_jobs = DownloadJobManager()
transformation_jobs = TransformationJobManager()
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _max_bytes(max_file_size_mb: float | None) -> int | None:
    if max_file_size_mb is None:
        return None
    return int(max_file_size_mb * 1024 * 1024)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/stats")
def stats() -> dict:
    return get_stats()


@app.get("/api/borough-boundaries")
def borough_boundaries() -> dict:
    return list_london_borough_boundaries()


@app.get("/api/boroughs")
def boroughs() -> dict:
    return list_london_boroughs()


@app.get("/api/borough-data")
def borough_data(
    borough_name: str = Query(min_length=1),
    rows_per_file: int = Query(default=10, ge=1, le=100),
    max_files: int = Query(default=30, ge=1, le=100),
) -> dict:
    return list_borough_row_data(
        borough_name=borough_name,
        rows_per_file=rows_per_file,
        max_files=max_files,
    )


@app.get("/api/sources")
def sources(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None),
) -> dict:
    return list_sources(page=page, page_size=page_size, search=search)


@app.get("/api/sources/{source_id}")
def source_detail(source_id: int) -> dict:
    source = get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Dataset source not found")
    return source


@app.get("/api/sources/{source_id}/csv-files")
def source_csv_files(
    source_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> dict:
    if get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Dataset source not found")
    return list_csv_files(source_id=source_id, page=page, page_size=page_size)


@app.get("/api/csv-files/{csv_file_id}")
def csv_file_detail(csv_file_id: int) -> dict:
    csv_file = get_csv_file(csv_file_id)
    if csv_file is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    return csv_file


@app.get("/api/csv-files/{csv_file_id}/preview")
def csv_file_preview(
    csv_file_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    count_total: bool = Query(default=False),
) -> dict:
    csv_file = get_csv_file(csv_file_id)
    if csv_file is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    if csv_file.get("status") != 1 or not csv_file.get("local_path"):
        raise HTTPException(status_code=409, detail="CSV file has not been downloaded successfully")
    try:
        preview = preview_csv(
            str(csv_file["local_path"]),
            page=page,
            page_size=page_size,
            count_total=count_total,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"file": csv_file, **preview}


@app.get("/api/transformation-plans")
def transformation_plans(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    status: str | None = Query(default=None),
    max_confidence: float | None = Query(default=None, ge=0, le=1),
    has_warnings: bool | None = Query(default=None),
    csv_changed: bool | None = Query(default=None),
    old_schema: bool | None = Query(default=None),
) -> dict:
    return list_csv_transformation_plans(
        page=page,
        page_size=page_size,
        status=status,
        max_confidence=max_confidence,
        has_warnings=has_warnings,
        csv_changed=csv_changed,
        old_schema=old_schema,
    )


@app.get("/api/transformation-stats")
def transformation_stats() -> dict:
    return transformation_overview_stats()


@app.get("/api/transformation-jobs/active")
def active_transformation_job() -> dict:
    return transformation_jobs.active_job()


@app.post("/api/transformation-jobs/pending")
def start_pending_transformation_job(request: TransformationJobRequest | None = None) -> dict:
    request = request or TransformationJobRequest()
    return transformation_jobs.start_pending_transformations(
        limit=request.limit,
        retry_plan_errors=request.retry_plan_errors,
        retry_outdated_successes=request.retry_outdated_successes,
        retry_row_outputs=request.retry_row_outputs,
        sample_rows=request.sample_rows,
        max_attempts=request.max_attempts,
        apply_existing_successes=request.apply_existing_successes,
    )


@app.post("/api/transformation-jobs/active/stop")
def stop_active_transformation_job() -> dict:
    return transformation_jobs.stop_active_job()


@app.get("/api/csv-files/{csv_file_id}/transformation-plan")
def csv_transformation_plan(csv_file_id: int) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    plan = get_csv_transformation_plan(csv_file_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="CSV transformation plan not found")
    return plan


@app.post("/api/csv-files/{csv_file_id}/transformation-plan/replan")
async def replan_csv_transformation(
    csv_file_id: int,
    request: TransformationPlanRequest | None = None,
) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    request = request or TransformationPlanRequest()
    try:
        plan_result = await asyncio.to_thread(
            plan_csv_transformation,
            csv_file_id,
            sample_rows=request.sample_rows,
            max_attempts=request.max_attempts,
        )
        if request.apply_rows and plan_result.get("status") == "success":
            plan_result["application"] = await asyncio.to_thread(
                apply_csv_row_transformations,
                csv_file_id,
            )
        return plan_result
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/csv-files/{csv_file_id}/row-transformations/apply")
async def apply_csv_file_row_transformations(csv_file_id: int) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    try:
        return await asyncio.to_thread(apply_csv_row_transformations, csv_file_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/csv-files/{csv_file_id}/row-transformations")
def csv_file_row_transformations(
    csv_file_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    date_status: str | None = Query(default=None),
    borough_status: str | None = Query(default=None),
    borough_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    return list_csv_row_transformations(
        csv_file_id=csv_file_id,
        page=page,
        page_size=page_size,
        status=status,
        date_status=date_status,
        borough_status=borough_status,
        borough_name=borough_name,
        date_from=date_from,
        date_to=date_to,
    )


@app.get("/api/csv-files/{csv_file_id}/row-transformations/stats")
def csv_file_row_transformation_stats(csv_file_id: int) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    return csv_row_transformation_stats(csv_file_id)


@app.get("/api/row-transformations")
def row_transformations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    status: str | None = Query(default=None),
    date_status: str | None = Query(default=None),
    borough_status: str | None = Query(default=None),
    borough_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    csv_file_id: int | None = Query(default=None, ge=1),
) -> dict:
    return list_all_csv_row_transformations(
        page=page,
        page_size=page_size,
        status=status,
        date_status=date_status,
        borough_status=borough_status,
        borough_name=borough_name,
        date_from=date_from,
        date_to=date_to,
        csv_file_id=csv_file_id,
    )


@app.get("/api/row-transformations/export.csv")
def export_row_transformations_csv(
    status: str | None = Query(default=None),
    date_status: str | None = Query(default=None),
    borough_status: str | None = Query(default=None),
    borough_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    csv_file_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=10000, ge=1, le=50000),
) -> Response:
    rows = export_csv_row_transformations(
        status=status,
        date_status=date_status,
        borough_status=borough_status,
        borough_name=borough_name,
        date_from=date_from,
        date_to=date_to,
        csv_file_id=csv_file_id,
        limit=limit,
    )
    output = io.StringIO()
    metadata_fields = [
        "csv_file_id",
        "csv_title",
        "source_title",
        "row_number",
        "status",
        "date_start",
        "date_end",
        "borough_name",
        "date_status",
        "borough_status",
        "error_message",
        "source_row_json",
    ]
    source_fields = sorted(
        {
            str(key)
            for row in rows
            for key in (row.get("source_row_json") or {}).keys()
        }
    )
    prefixed_source_fields = [f"source_{field}" for field in source_fields]
    writer = csv.DictWriter(
        output,
        fieldnames=[*metadata_fields, *prefixed_source_fields],
    )
    writer.writeheader()
    for row in rows:
        source_row = row.get("source_row_json") or {}
        output_row = {
            "csv_file_id": row.get("csv_file_id"),
            "csv_title": row.get("csv_title"),
            "source_title": row.get("source_title"),
            "row_number": row.get("row_number"),
            "status": row.get("status"),
            "date_start": row.get("date_start"),
            "date_end": row.get("date_end"),
            "borough_name": row.get("borough_name"),
            "date_status": row.get("date_status"),
            "borough_status": row.get("borough_status"),
            "error_message": row.get("error_message"),
            "source_row_json": json.dumps(source_row, ensure_ascii=False),
        }
        output_row.update({f"source_{field}": source_row.get(field) for field in source_fields})
        writer.writerow(output_row)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=london-row-transformations.csv"},
    )


@app.post("/api/sync")
async def run_sync(request: SyncRequest) -> dict:
    options = SyncOptions(
        mode=request.mode,
        download_files=request.download_files,
        limit=request.limit,
        max_pages=request.max_pages,
        max_file_size_bytes=_max_bytes(request.max_file_size_mb),
    )
    return await asyncio.to_thread(sync_catalogue, options)


@app.post("/api/csv-files/{csv_file_id}/download")
async def download_csv_file(csv_file_id: int, request: DownloadRequest | None = None) -> dict:
    if get_csv_file(csv_file_id) is None:
        raise HTTPException(status_code=404, detail="CSV file not found")
    max_file_size_mb = request.max_file_size_mb if request else None
    try:
        return await asyncio.to_thread(
            download_csv_file_by_id,
            csv_file_id,
            max_file_size_bytes=_max_bytes(max_file_size_mb),
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/download-jobs/active")
def active_download_job() -> dict:
    return download_jobs.active_job()


@app.post("/api/download-jobs/pending")
def start_pending_download_job(request: PendingDownloadRequest | None = None) -> dict:
    request = request or PendingDownloadRequest()
    return download_jobs.start_pending_downloads(
        max_file_size_bytes=_max_bytes(request.max_file_size_mb),
        retry_errors=request.retry_errors,
        limit=request.limit,
    )


@app.post("/api/download-jobs/active/stop")
def stop_active_download_job() -> dict:
    return download_jobs.stop_active_job()

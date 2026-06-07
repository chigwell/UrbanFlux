from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from .csv_row_transformer import apply_csv_row_transformations
from .csv_transformation_planner import plan_csv_transformation
from .database import (
    get_csv_file,
    init_db,
    list_csv_file_ids_for_row_transformation,
    list_csv_file_ids_for_transformation_planning,
    transformation_overview_stats,
)
from .transformation_schema import RULE_SCHEMA_VERSION


class TransformationJobManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._stop_requested = Event()
        self._state: dict[str, Any] | None = None
        self._worker: Thread | None = None

    def active_job(self) -> dict[str, Any]:
        with self._lock:
            if self._state is None:
                return self._idle_state()
            return self._snapshot(self._state)

    def start_pending_transformations(
        self,
        *,
        limit: int | None = None,
        retry_plan_errors: bool = False,
        retry_outdated_successes: bool = False,
        retry_row_outputs: bool = False,
        sample_rows: int = 8,
        max_attempts: int = 3,
        apply_existing_successes: bool = True,
    ) -> dict[str, Any]:
        init_db()
        with self._lock:
            if self._state and self._state["status"] == "running":
                return self._snapshot(self._state)
            self._stop_requested.clear()

        plan_ids = list_csv_file_ids_for_transformation_planning(
            retry_errors=retry_plan_errors,
            minimum_rule_schema_version=RULE_SCHEMA_VERSION if retry_outdated_successes else None,
            limit=limit,
        )
        apply_ids: list[int] = []
        if apply_existing_successes:
            remaining_limit = None
            if limit is not None:
                remaining_limit = max(limit - len(plan_ids), 0)
            if remaining_limit is None or remaining_limit > 0:
                apply_ids = list_csv_file_ids_for_row_transformation(
                    retry=retry_row_outputs,
                    limit=remaining_limit,
                )
                plan_id_set = set(plan_ids)
                apply_ids = [csv_file_id for csv_file_id in apply_ids if csv_file_id not in plan_id_set]

        total = len(plan_ids) + len(apply_ids)
        now = self._now()
        state = {
            "job_id": uuid4().hex,
            "status": "running" if total else "success",
            "total": total,
            "completed": 0,
            "planned_count": 0,
            "applied_count": 0,
            "success_count": 0,
            "error_count": 0,
            "current_file_id": None,
            "current_file_title": None,
            "current_step": None,
            "started_at": now,
            "finished_at": None if total else now,
            "message": None if total else "No CSV files are waiting for transformation.",
            "stats": transformation_overview_stats(),
        }

        with self._lock:
            self._state = state

        if total:
            self._worker = Thread(
                target=self._run_job,
                args=(state["job_id"], plan_ids, apply_ids, sample_rows, max_attempts),
                daemon=True,
            )
            self._worker.start()

        return self.active_job()

    def stop_active_job(self) -> dict[str, Any]:
        with self._lock:
            if not self._state or self._state["status"] != "running":
                return self._idle_state() if self._state is None else self._snapshot(self._state)
            self._stop_requested.set()
            self._state["message"] = "Stopping after the current transformation step."
            return self._snapshot(self._state)

    def _run_job(
        self,
        job_id: str,
        plan_ids: list[int],
        apply_ids: list[int],
        sample_rows: int,
        max_attempts: int,
    ) -> None:
        try:
            for csv_file_id in plan_ids:
                if self._stop_requested.is_set():
                    break
                self._update_current(job_id, csv_file_id, "planning")
                try:
                    plan = plan_csv_transformation(
                        csv_file_id,
                        sample_rows=sample_rows,
                        max_attempts=max_attempts,
                    )
                    if plan.get("status") != "success":
                        self._advance(job_id, success=False, planned=False, applied=False, message=plan.get("error_message"))
                        continue
                    self._update_current(job_id, csv_file_id, "applying")
                    apply_result = apply_csv_row_transformations(csv_file_id, replace=True)
                    row_errors = int(apply_result.get("error", 0))
                    self._advance(
                        job_id,
                        success=row_errors == 0,
                        planned=True,
                        applied=True,
                        message=(
                            f"{row_errors} row transformations failed for CSV file {csv_file_id}"
                            if row_errors
                            else None
                        ),
                    )
                except Exception as exc:
                    self._advance(job_id, success=False, planned=False, applied=False, message=str(exc))

            for csv_file_id in apply_ids:
                if self._stop_requested.is_set():
                    break
                self._update_current(job_id, csv_file_id, "applying")
                try:
                    apply_result = apply_csv_row_transformations(csv_file_id, replace=True)
                    row_errors = int(apply_result.get("error", 0))
                    self._advance(
                        job_id,
                        success=row_errors == 0,
                        planned=False,
                        applied=True,
                        message=(
                            f"{row_errors} row transformations failed for CSV file {csv_file_id}"
                            if row_errors
                            else None
                        ),
                    )
                except Exception as exc:
                    self._advance(job_id, success=False, planned=False, applied=False, message=str(exc))

            with self._lock:
                if not self._state or self._state["job_id"] != job_id:
                    return
                self._state["status"] = self._finished_status()
                self._state["current_file_id"] = None
                self._state["current_file_title"] = None
                self._state["current_step"] = None
                self._state["finished_at"] = self._now()
                self._state["stats"] = transformation_overview_stats()
                if self._state["status"] == "canceled":
                    self._state["message"] = "Transformation job stopped by user."
                elif self._state["error_count"]:
                    self._state["message"] = f"{self._state['error_count']} CSV transformations failed."
                else:
                    self._state["message"] = "All pending CSV transformations finished."
        except Exception as exc:
            with self._lock:
                if self._state and self._state["job_id"] == job_id:
                    self._state["status"] = "error"
                    self._state["finished_at"] = self._now()
                    self._state["message"] = str(exc)
                    self._state["stats"] = transformation_overview_stats()

    def _update_current(self, job_id: str, csv_file_id: int, step: str) -> None:
        csv_file = get_csv_file(csv_file_id) or {}
        self._update(
            job_id,
            current_file_id=csv_file_id,
            current_file_title=csv_file.get("title") or f"CSV file {csv_file_id}",
            current_step=step,
        )

    def _advance(
        self,
        job_id: str,
        *,
        success: bool,
        planned: bool,
        applied: bool,
        message: str | None,
    ) -> None:
        with self._lock:
            if not self._state or self._state["job_id"] != job_id:
                return
            self._state["completed"] += 1
            if planned:
                self._state["planned_count"] += 1
            if applied:
                self._state["applied_count"] += 1
            if success:
                self._state["success_count"] += 1
            else:
                self._state["error_count"] += 1
                self._state["message"] = message
            self._state["stats"] = transformation_overview_stats()

    def _update(self, job_id: str, **values: Any) -> None:
        with self._lock:
            if self._state and self._state["job_id"] == job_id:
                self._state.update(values)

    def _snapshot(self, state: dict[str, Any]) -> dict[str, Any]:
        data = dict(state)
        total = int(data["total"])
        completed = int(data["completed"])
        data["progress_percent"] = 100 if total == 0 else round(completed / total * 100, 1)
        data["is_running"] = data["status"] == "running"
        return data

    def _idle_state(self) -> dict[str, Any]:
        return {
            "job_id": None,
            "status": "idle",
            "total": 0,
            "completed": 0,
            "planned_count": 0,
            "applied_count": 0,
            "success_count": 0,
            "error_count": 0,
            "current_file_id": None,
            "current_file_title": None,
            "current_step": None,
            "started_at": None,
            "finished_at": None,
            "message": None,
            "stats": transformation_overview_stats(),
            "progress_percent": 0,
            "is_running": False,
        }

    def _finished_status(self) -> str:
        if self._stop_requested.is_set():
            return "canceled"
        if self._state and self._state["error_count"]:
            return "completed_with_errors"
        return "success"

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

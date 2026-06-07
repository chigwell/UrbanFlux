from __future__ import annotations

from datetime import UTC, datetime
from threading import Event, Lock, Thread
from typing import Any
from uuid import uuid4

from .database import get_csv_file, init_db, list_csv_file_ids_for_download
from .scraper import DownloadStopped, download_csv_file_by_id, sleep_between_downloads


class DownloadJobManager:
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

    def start_pending_downloads(
        self,
        *,
        max_file_size_bytes: int | None = None,
        retry_errors: bool = True,
        limit: int | None = None,
    ) -> dict[str, Any]:
        init_db()
        with self._lock:
            if self._state and self._state["status"] == "running":
                return self._snapshot(self._state)
            self._stop_requested.clear()

        csv_file_ids = list_csv_file_ids_for_download(
            retry_errors=retry_errors,
            limit=limit,
        )
        now = self._now()
        state = {
            "job_id": uuid4().hex,
            "status": "running" if csv_file_ids else "success",
            "total": len(csv_file_ids),
            "completed": 0,
            "success_count": 0,
            "error_count": 0,
            "current_file_id": None,
            "current_file_title": None,
            "started_at": now,
            "finished_at": None if csv_file_ids else now,
            "message": None if csv_file_ids else "No CSV files are waiting to be downloaded.",
        }

        with self._lock:
            self._state = state

        if csv_file_ids:
            self._worker = Thread(
                target=self._run_job,
                args=(state["job_id"], csv_file_ids, max_file_size_bytes),
                daemon=True,
            )
            self._worker.start()

        return self.active_job()

    def stop_active_job(self) -> dict[str, Any]:
        with self._lock:
            if not self._state or self._state["status"] != "running":
                return self._idle_state() if self._state is None else self._snapshot(self._state)
            self._stop_requested.set()
            self._state["message"] = "Stopping after the current download step."
            return self._snapshot(self._state)

    def _run_job(
        self,
        job_id: str,
        csv_file_ids: list[int],
        max_file_size_bytes: int | None,
    ) -> None:
        try:
            for csv_file_id in csv_file_ids:
                if self._stop_requested.is_set():
                    break
                csv_file = get_csv_file(csv_file_id) or {}
                self._update(
                    job_id,
                    current_file_id=csv_file_id,
                    current_file_title=csv_file.get("title") or f"CSV file {csv_file_id}",
                )

                try:
                    download_csv_file_by_id(
                        csv_file_id,
                        max_file_size_bytes=max_file_size_bytes,
                        should_stop=self._stop_requested.is_set,
                        wait=self._stop_requested.wait,
                    )
                    self._advance(job_id, success=True, message=None)
                except DownloadStopped:
                    self._stop_requested.set()
                    break
                except Exception as exc:
                    self._advance(job_id, success=False, message=str(exc))
                finally:
                    if not self._stop_requested.is_set():
                        try:
                            sleep_between_downloads(wait=self._stop_requested.wait)
                        except DownloadStopped:
                            self._stop_requested.set()

            with self._lock:
                if not self._state or self._state["job_id"] != job_id:
                    return
                self._state["status"] = self._finished_status()
                self._state["current_file_id"] = None
                self._state["current_file_title"] = None
                self._state["finished_at"] = self._now()
                if self._state["status"] == "canceled":
                    self._state["message"] = "Download stopped by user."
                elif self._state["error_count"]:
                    self._state["message"] = (
                        f"{self._state['error_count']} file downloads failed. "
                        "Open affected CSV records for details."
                    )
                else:
                    self._state["message"] = "All pending CSV files were downloaded."
        except Exception as exc:
            with self._lock:
                if self._state and self._state["job_id"] == job_id:
                    self._state["status"] = "error"
                    self._state["finished_at"] = self._now()
                    self._state["message"] = str(exc)

    def _advance(self, job_id: str, *, success: bool, message: str | None) -> None:
        with self._lock:
            if not self._state or self._state["job_id"] != job_id:
                return
            self._state["completed"] += 1
            if success:
                self._state["success_count"] += 1
            else:
                self._state["error_count"] += 1
                self._state["message"] = message

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
            "success_count": 0,
            "error_count": 0,
            "current_file_id": None,
            "current_file_title": None,
            "started_at": None,
            "finished_at": None,
            "message": None,
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

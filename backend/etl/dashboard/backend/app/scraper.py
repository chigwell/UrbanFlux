from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .config import get_settings
from .database import (
    connect,
    create_sync_run,
    finish_sync_run,
    get_csv_file,
    init_db,
    update_csv_file_status,
    upsert_csv_file,
    upsert_dataset_source,
)


CSV_STATUS_PENDING = 0
CSV_STATUS_SUCCESS = 1
CSV_STATUS_ERROR = -1
TRANSIENT_DOWNLOAD_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class DownloadStopped(Exception):
    """Raised when a user stops a background CSV download job."""


@dataclass(slots=True)
class SyncOptions:
    mode: str = "api"
    download_files: bool = False
    limit: int | None = None
    max_pages: int | None = None
    max_file_size_bytes: int | None = None


@dataclass(slots=True)
class SyncSummary:
    sync_run_id: int
    mode: str
    pages_scanned: int = 0
    datasets_seen: int = 0
    sources_upserted: int = 0
    csv_files_seen: int = 0
    csv_files_downloaded: int = 0
    errors_count: int = 0
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sync_run_id": self.sync_run_id,
            "mode": self.mode,
            "pages_scanned": self.pages_scanned,
            "datasets_seen": self.datasets_seen,
            "sources_upserted": self.sources_upserted,
            "csv_files_seen": self.csv_files_seen,
            "csv_files_downloaded": self.csv_files_downloaded,
            "errors_count": self.errors_count,
            "message": self.message,
        }


def _client() -> httpx.Client:
    settings = get_settings()
    return httpx.Client(
        follow_redirects=True,
        timeout=settings.request_timeout_seconds,
        headers={
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
            "User-Agent": "london-datastore-csv-dashboard/1.0",
        },
    )


def _base_url() -> str:
    return get_settings().datastore_base_url.rstrip("/")


def _json_response(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def fetch_export_catalogue(client: httpx.Client) -> list[dict[str, Any]]:
    base = _base_url()
    urls = [
        f"{base}/api/v3/datasets/export.json",
        f"{base}/api/datasets/export.json",
    ]
    last_error: Exception | None = None
    for url in urls:
        try:
            payload = _json_response(client.get(url))
            if isinstance(payload, list):
                return payload
            if isinstance(payload, dict):
                result = payload.get("result") or payload.get("datasets") or payload.get("data")
                if isinstance(result, list):
                    return result
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"Could not fetch metadata export: {last_error}")


def discover_dataset_urls_from_pages(
    client: httpx.Client,
    *,
    max_pages: int | None = None,
) -> tuple[list[str], int]:
    base = _base_url()
    seen: set[str] = set()
    urls: list[str] = []
    page = 1
    pages_scanned = 0

    while True:
        if max_pages is not None and page > max_pages:
            break
        page_url = f"{base}/dataset/?format=csv" if page == 1 else f"{base}/dataset/?format=csv&page={page}"
        response = client.get(page_url)
        response.raise_for_status()
        pages_scanned += 1
        soup = BeautifulSoup(response.text, "html.parser")

        page_urls: list[str] = []
        for anchor in soup.select('a[href^="/dataset/"], a[href^="https://data.london.gov.uk/dataset/"]'):
            href = anchor.get("href")
            if not href:
                continue
            absolute = urljoin(base, href)
            parsed = urlparse(absolute)
            path = parsed.path.rstrip("/")
            if path in {"", "/dataset"}:
                continue
            if parsed.query:
                continue
            if not path.startswith("/dataset/"):
                continue
            canonical = f"{parsed.scheme}://{parsed.netloc}{path}/"
            if canonical not in seen:
                seen.add(canonical)
                page_urls.append(canonical)
                urls.append(canonical)

        next_page = soup.find("a", href=re.compile(r"[?&]page="))
        if not page_urls or next_page is None:
            break
        page += 1

    return urls, pages_scanned


def dataset_id_from_url(dataset_url: str) -> str:
    code = urlparse(dataset_url).path.rstrip("/").split("/")[-1]
    suffix = code.rsplit("-", 1)[-1]
    return suffix if re.fullmatch(r"[a-z0-9]{5}", suffix) else code


def source_code_from_url(dataset_url: str) -> str:
    return urlparse(dataset_url).path.rstrip("/").split("/")[-1]


def fetch_dataset_detail(client: httpx.Client, dataset_url: str) -> dict[str, Any]:
    base = _base_url()
    dataset_id = dataset_id_from_url(dataset_url)
    api_url = f"{base}/api/v3/dataset/{dataset_id}"
    try:
        payload = _json_response(client.get(api_url))
        if isinstance(payload, dict):
            payload.setdefault("id", dataset_id)
            payload.setdefault("webpage", dataset_url)
            return payload
    except Exception:
        pass

    response = client.get(dataset_url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    title = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else dataset_id
    resources: list[dict[str, Any]] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        absolute = urljoin(base, href)
        path = urlparse(absolute).path.lower()
        text = anchor.get_text(" ", strip=True)
        if ".csv" in path or text.lower().endswith(".csv"):
            resources.append(
                {
                    "id": hashlib.sha1(absolute.encode("utf-8")).hexdigest()[:12],
                    "title": text or Path(path).name,
                    "filename": Path(urlparse(absolute).path).name,
                    "url": absolute,
                }
            )
    return {
        "id": dataset_id,
        "webpage": dataset_url,
        "title": title,
        "description": "",
        "resources": resources,
    }


def _html_to_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if "<" in text and ">" in text:
        return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)
    return text.strip() or None


def _title(value: Any) -> str | None:
    if isinstance(value, dict):
        raw = value.get("title") or value.get("name") or value.get("id")
        return str(raw) if raw else None
    if isinstance(value, str):
        return value
    return None


def _normalise_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def normalise_source(raw: dict[str, Any]) -> dict[str, Any]:
    dataset_url = raw.get("webpage") or raw.get("url") or raw.get("canonical") or ""
    if dataset_url and dataset_url.startswith("/"):
        dataset_url = urljoin(_base_url(), dataset_url)
    source_code = source_code_from_url(dataset_url) if dataset_url else str(raw.get("id"))
    dataset_id = str(raw.get("id") or dataset_id_from_url(dataset_url) or source_code)
    topics = _normalise_list(raw.get("topics") or raw.get("categories"))
    tags = _normalise_list(raw.get("tags"))

    return {
        "uuid": dataset_id,
        "source_code": source_code,
        "dataset_url": dataset_url.rstrip("/") + "/" if dataset_url else f"{_base_url()}/dataset/{source_code}/",
        "title": str(raw.get("title") or source_code),
        "description": _html_to_text(raw.get("description")),
        "organisation_name": (
            _title(raw.get("team"))
            or _title(raw.get("masthead"))
            or _title(raw.get("contact"))
        ),
        "licence_name": _title(raw.get("licence")),
        "created_at_source": raw.get("createdAt") or raw.get("created_at"),
        "updated_at_source": raw.get("updatedAt") or raw.get("updated_at"),
        "tags": [str(item.get("title") if isinstance(item, dict) else item) for item in tags],
        "categories": [
            str(item.get("title") if isinstance(item, dict) else item)
            for item in topics
        ],
        "raw_metadata": raw,
    }


def _resources(raw: dict[str, Any]) -> list[dict[str, Any]]:
    value = raw.get("resources") or []
    if isinstance(value, dict):
        result = []
        for key, resource in value.items():
            if isinstance(resource, dict):
                resource = {**resource}
                resource.setdefault("id", key)
                result.append(resource)
        return result
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _is_csv_resource(resource: dict[str, Any]) -> bool:
    parts = [
        str(resource.get("format") or ""),
        str(resource.get("mimetype") or ""),
        str(resource.get("filename") or ""),
        str(resource.get("title") or ""),
        str(resource.get("url") or ""),
    ]
    text = " ".join(parts).lower()
    return (
        "text/csv" in text
        or re.search(r"\bcsv\b", text) is not None
        or ".csv" in urlparse(str(resource.get("url") or "")).path.lower()
    )


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return cleaned[:160] or "file"


def normalise_csv_resource(
    raw_dataset: dict[str, Any],
    source: dict[str, Any],
    resource: dict[str, Any],
) -> dict[str, Any]:
    resource_id = str(resource.get("id") or resource.get("uuid") or "")
    url = str(resource.get("url") or "")
    csv_url = urljoin(_base_url(), url)
    filename = str(resource.get("filename") or Path(urlparse(csv_url).path).name or "")
    title = str(resource.get("title") or filename or resource_id or "CSV resource")
    if not filename:
        filename = f"{_safe_filename(title)}.csv"
    if not filename.lower().endswith(".csv") and ".csv" in urlparse(csv_url).path.lower():
        filename = Path(urlparse(csv_url).path).name
    if not filename.lower().endswith(".csv"):
        filename = f"{filename}.csv"

    resource_uuid = resource_id or hashlib.sha1(csv_url.encode("utf-8")).hexdigest()
    local_source = _safe_filename(source.get("source_code") or source["uuid"])
    local_name = _safe_filename(f"{resource_uuid}_{filename}")
    local_path = get_settings().csv_storage_dir / local_source / local_name

    return {
        "resource_uuid": resource_uuid,
        "resource_code": resource_id or None,
        "title": title,
        "description": _html_to_text(resource.get("description")),
        "csv_url": csv_url,
        "local_path": str(local_path),
        "file_name": filename,
        "source_file_size_bytes": resource.get("size"),
        "content_hash": resource.get("hash"),
        "format": "csv",
        "status": CSV_STATUS_PENDING,
        "raw_metadata": {
            **resource,
            "dataset": raw_dataset.get("id"),
        },
    }


def csv_resources_for_dataset(raw_dataset: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    resources = []
    for resource in _resources(raw_dataset):
        if _is_csv_resource(resource):
            resources.append(normalise_csv_resource(raw_dataset, source, resource))
    return resources


def download_csv_file_by_id(
    csv_file_id: int,
    *,
    max_file_size_bytes: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    wait: Callable[[float], bool] | None = None,
) -> dict[str, Any]:
    init_db()
    csv_file = get_csv_file(csv_file_id)
    if csv_file is None:
        raise ValueError(f"CSV file {csv_file_id} does not exist")

    try:
        result = download_csv_resource(
            csv_file,
            max_file_size_bytes=max_file_size_bytes,
            should_stop=should_stop,
            wait=wait,
        )
        with connect() as connection:
            update_csv_file_status(
                connection,
                csv_file_id,
                status=CSV_STATUS_SUCCESS,
                local_path=result["local_path"],
                file_size_bytes=result["file_size_bytes"],
                error_message=None,
                downloaded_at=datetime.now(UTC).isoformat(),
            )
        return result
    except DownloadStopped:
        raise
    except Exception as exc:
        with connect() as connection:
            update_csv_file_status(
                connection,
                csv_file_id,
                status=CSV_STATUS_ERROR,
                error_message=str(exc),
            )
        raise


def download_csv_resource(
    csv_file: dict[str, Any],
    *,
    max_file_size_bytes: int | None = None,
    should_stop: Callable[[], bool] | None = None,
    wait: Callable[[float], bool] | None = None,
) -> dict[str, Any]:
    local_path = Path(str(csv_file["local_path"]))
    local_path.parent.mkdir(parents=True, exist_ok=True)

    source_size = csv_file.get("source_file_size_bytes")
    if (
        max_file_size_bytes is not None
        and isinstance(source_size, int)
        and source_size > max_file_size_bytes
    ):
        raise RuntimeError(
            f"Remote file is {source_size} bytes, above configured limit {max_file_size_bytes}"
        )

    temp_path = local_path.with_suffix(local_path.suffix + ".part")
    settings = get_settings()
    retry_attempts = max(1, settings.download_retry_attempts)

    for attempt in range(1, retry_attempts + 1):
        try:
            _raise_if_stopped(should_stop)
            return _download_csv_resource_once(
                csv_file,
                temp_path=temp_path,
                local_path=local_path,
                max_file_size_bytes=max_file_size_bytes,
                should_stop=should_stop,
            )
        except DownloadStopped:
            _remove_partial_file(temp_path)
            raise
        except httpx.HTTPStatusError as exc:
            _remove_partial_file(temp_path)
            if not _should_retry_download(exc, attempt, retry_attempts):
                raise
            _wait_or_stop(_retry_sleep_seconds(exc, attempt), wait)
        except httpx.RequestError:
            _remove_partial_file(temp_path)
            if attempt >= retry_attempts:
                raise
            _wait_or_stop(_retry_sleep_seconds(None, attempt), wait)

    raise RuntimeError("CSV download retry loop ended unexpectedly")


def _download_csv_resource_once(
    csv_file: dict[str, Any],
    *,
    temp_path: Path,
    local_path: Path,
    max_file_size_bytes: int | None,
    should_stop: Callable[[], bool] | None,
) -> dict[str, Any]:
    bytes_written = 0
    with _client() as client:
        with client.stream("GET", str(csv_file["csv_url"])) as response:
            response.raise_for_status()
            with temp_path.open("wb") as handle:
                for chunk in response.iter_bytes():
                    if not chunk:
                        continue
                    _raise_if_stopped(should_stop)
                    bytes_written += len(chunk)
                    if max_file_size_bytes is not None and bytes_written > max_file_size_bytes:
                        raise RuntimeError(
                            f"Remote file exceeded configured limit {max_file_size_bytes}"
                        )
                    handle.write(chunk)

    temp_path.replace(local_path)
    return {
        "local_path": str(local_path),
        "file_size_bytes": bytes_written,
    }


def sleep_between_downloads(wait: Callable[[float], bool] | None = None) -> bool:
    delay = max(0.0, get_settings().download_request_delay_seconds)
    if delay:
        return _wait_or_stop(delay, wait)
    return False


def _wait_or_stop(delay: float, wait: Callable[[float], bool] | None = None) -> bool:
    if wait is not None:
        if wait(delay):
            raise DownloadStopped("Download stopped by user")
        return False
    time.sleep(delay)
    return False


def _raise_if_stopped(should_stop: Callable[[], bool] | None) -> None:
    if should_stop and should_stop():
        raise DownloadStopped("Download stopped by user")


def _should_retry_download(
    exc: httpx.HTTPStatusError,
    attempt: int,
    retry_attempts: int,
) -> bool:
    return (
        attempt < retry_attempts
        and exc.response.status_code in TRANSIENT_DOWNLOAD_STATUS_CODES
    )


def _retry_sleep_seconds(exc: httpx.HTTPStatusError | None, attempt: int) -> float:
    settings = get_settings()
    retry_after = _retry_after_seconds(exc.response.headers.get("retry-after")) if exc else None
    fallback = settings.download_retry_backoff_seconds * (2 ** (attempt - 1))
    delay = retry_after if retry_after is not None else fallback
    return min(max(delay, settings.download_request_delay_seconds), settings.download_max_retry_after_seconds)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        retry_at = parsedate_to_datetime(value)
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
    except (TypeError, ValueError):
        return None


def _remove_partial_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def sync_catalogue(options: SyncOptions | None = None) -> dict[str, Any]:
    options = options or SyncOptions()
    init_db()
    with connect() as connection:
        sync_run_id = create_sync_run(connection, mode=options.mode)

    summary = SyncSummary(sync_run_id=sync_run_id, mode=options.mode)
    status = "success"

    try:
        with _client() as client:
            if options.mode == "api":
                datasets = fetch_export_catalogue(client)
            elif options.mode == "pages":
                urls, pages_scanned = discover_dataset_urls_from_pages(
                    client,
                    max_pages=options.max_pages,
                )
                summary.pages_scanned = pages_scanned
                datasets = [fetch_dataset_detail(client, url) for url in urls]
            else:
                raise ValueError("mode must be 'api' or 'pages'")

        seen_sources: set[str] = set()
        for raw_dataset in datasets:
            if options.limit is not None and summary.sources_upserted >= options.limit:
                break
            summary.datasets_seen += 1
            source = normalise_source(raw_dataset)
            if source["uuid"] in seen_sources:
                continue
            resources = csv_resources_for_dataset(raw_dataset, source)
            if not resources:
                continue
            seen_sources.add(source["uuid"])
            with connect() as connection:
                source_id = upsert_dataset_source(connection, source)
                for resource in resources:
                    upsert_csv_file(connection, source_id, resource)
            summary.sources_upserted += 1
            summary.csv_files_seen += len(resources)

            if options.download_files:
                for resource in resources:
                    try:
                        with connect() as connection:
                            csv_id = upsert_csv_file(connection, source_id, resource)
                        download_csv_file_by_id(
                            csv_id,
                            max_file_size_bytes=options.max_file_size_bytes,
                        )
                        summary.csv_files_downloaded += 1
                    except Exception as exc:
                        summary.errors_count += 1
                        summary.message = str(exc)
                    finally:
                        sleep_between_downloads()

    except Exception as exc:
        status = "error"
        summary.errors_count += 1
        summary.message = str(exc)
    finally:
        with connect() as connection:
            finish_sync_run(
                connection,
                sync_run_id,
                status=status,
                pages_scanned=summary.pages_scanned,
                datasets_seen=summary.datasets_seen,
                sources_upserted=summary.sources_upserted,
                csv_files_seen=summary.csv_files_seen,
                csv_files_downloaded=summary.csv_files_downloaded,
                errors_count=summary.errors_count,
                message=summary.message,
            )

    return summary.to_dict()


def _max_bytes_from_mb(value: float | None) -> int | None:
    if value is None:
        return None
    return int(value * 1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync London Datastore CSV datasets")
    parser.add_argument("--mode", choices=["api", "pages"], default="api")
    parser.add_argument("--download", action="store_true", help="Download CSV files locally")
    parser.add_argument("--limit", type=int, default=None, help="Limit datasets processed")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit paginated pages crawled")
    parser.add_argument(
        "--max-file-size-mb",
        type=float,
        default=None,
        help="Skip downloads above this size",
    )
    args = parser.parse_args()
    result = sync_catalogue(
        SyncOptions(
            mode=args.mode,
            download_files=args.download,
            limit=args.limit,
            max_pages=args.max_pages,
            max_file_size_bytes=_max_bytes_from_mb(args.max_file_size_mb),
        )
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

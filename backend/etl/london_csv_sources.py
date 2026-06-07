from __future__ import annotations

import argparse
import html
import json
import math
import re
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BASE_URL = "https://data.london.gov.uk"
SEARCH_URL = f"{BASE_URL}/api/internal/search"
DATASET_URL = f"{BASE_URL}/api/v3/dataset"
DEFAULT_PAGE_SIZE = 10
MAX_RETRIES = 5


@dataclass(frozen=True)
class CsvResource:
    title: str
    url: str


@dataclass(frozen=True)
class Source:
    title: str
    description: str
    csv_resources: list[CsvResource]


class HttpClient:
    def __init__(self, headers: dict[str, str], timeout: float = 30.0) -> None:
        self.headers = headers
        self.timeout = timeout

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        if params:
            url = f"{url}?{urlencode(params)}"

        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            request = Request(url, headers=self.headers)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                if exc.code == 429 or 500 <= exc.code < 600:
                    delay = retry_delay(exc.headers.get("retry-after"), attempt)
                    print(
                        f"Retrying {url} after HTTP {exc.code}; sleeping {delay:.1f}s",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                    continue
                raise
            except URLError as exc:
                last_error = exc
                delay = retry_delay(None, attempt)
                print(f"Retrying {url} after {exc!r}; sleeping {delay:.1f}s", file=sys.stderr)
                time.sleep(delay)

        if last_error is not None:
            raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} retries") from last_error
        raise RuntimeError(f"Failed to fetch {url} after {MAX_RETRIES} retries")


def strip_html(value: str) -> str:
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n", value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html.unescape(value)
    value = value.replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def retry_delay(retry_after: str | None, attempt: int) -> float:
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass
    return min(60.0, 2.0**attempt)


def search_page(client: HttpClient, page: int) -> dict[str, Any]:
    return client.get_json(
        SEARCH_URL,
        params={
            "page": page,
            "q": "",
            "resources.format": "csv",
            "topics": "",
            "masthead": "",
            "geo": "",
            "customTags": "",
        },
    )


def dataset_detail(client: HttpClient, dataset_id: str) -> dict[str, Any]:
    return client.get_json(f"{DATASET_URL}/{dataset_id}")


def csv_resources(dataset: dict[str, Any]) -> list[CsvResource]:
    resources = dataset.get("resources") or {}
    csvs: list[tuple[int, CsvResource]] = []

    for resource in resources.values():
        if not isinstance(resource, dict):
            continue
        if str(resource.get("format", "")).lower() != "csv":
            continue

        title = str(resource.get("title") or resource.get("name") or "Untitled CSV")
        url = str(resource.get("url") or "")
        if not url:
            continue
        csvs.append((int(resource.get("order") or 0), CsvResource(title=title, url=url)))

    return [resource for _, resource in sorted(csvs, key=lambda item: item[0])]


def source_from_dataset(dataset: dict[str, Any]) -> Source:
    return Source(
        title=str(dataset.get("title") or "Untitled source"),
        description=strip_html(str(dataset.get("description") or "")),
        csv_resources=csv_resources(dataset),
    )


def iter_sources(client: HttpClient, max_pages: int | None = None) -> tuple[int, list[Source]]:
    first_page = search_page(client, 1)
    found = int(first_page.get("found") or 0)
    total_pages = math.ceil(found / DEFAULT_PAGE_SIZE) if found else 1
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)

    sources: list[Source] = []
    for page in range(1, total_pages + 1):
        page_data = first_page if page == 1 else search_page(client, page)
        print(f"Fetching page {page}/{total_pages}", file=sys.stderr)

        for hit in page_data.get("hits") or []:
            document = hit.get("document") or {}
            if document.get("type") != "dataset":
                continue

            dataset_id = document.get("id")
            if not dataset_id:
                continue

            dataset = dataset_detail(client, str(dataset_id))
            source = source_from_dataset(dataset)
            if source.csv_resources:
                sources.append(source)

    return total_pages, sources


def print_sources(sources: list[Source]) -> None:
    for index, source in enumerate(sources, start=1):
        print(f"{index}. {source.title}")
        print(f"Description: {source.description or '(none)'}")
        print("CSV files:")
        for csv in source.csv_resources:
            print(f"  - {csv.title}: {csv.url}")
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Print London Datastore CSV sources from "
            "https://data.london.gov.uk/dataset/?format=csv"
        )
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Limit the number of search pages to fetch. Defaults to every available page.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    headers = {
        "Accept": "application/json",
        "Referer": f"{BASE_URL}/dataset/?format=csv",
        "User-Agent": "UrbanFlux ETL contact: backend/etl/london_csv_sources.py",
    }
    client = HttpClient(headers=headers)
    total_pages, sources = iter_sources(client, max_pages=args.max_pages)

    print_sources(sources)
    print(f"Fetched {len(sources)} sources across {total_pages} page(s).")


if __name__ == "__main__":
    main()

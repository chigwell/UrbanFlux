from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path


PUBLIC_BUNDLE_URL = "https://pub-f20eb55e72ee41a5b80036ea8f6107bb.r2.dev/london_mapped_data_public_bundle.zip"
EXPECTED_SIZE_BYTES = 352_253_465
EXPECTED_ETAG = '"6667302866ff3cd39a8a9afc363dcee3-21"'
PACKAGE_DIR_NAME = "london_mapped_data_package"
PACKAGE_DB_RELATIVE_PATH = Path("data") / "london_mapped_compact.sqlite3"


def download(url: str, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "UrbanFlux-data-sources/1.0"})
    with urllib.request.urlopen(req, timeout=60) as response:
        expected_length = response.headers.get("Content-Length")
        expected_etag = response.headers.get("ETag")
        if expected_length and int(expected_length) != EXPECTED_SIZE_BYTES:
            raise RuntimeError(f"Unexpected bundle size header: {expected_length}")
        if expected_etag and expected_etag != EXPECTED_ETAG:
            raise RuntimeError(f"Unexpected bundle ETag: {expected_etag}")

        written = 0
        with target.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                written += len(chunk)
                if written % (32 * 1024 * 1024) < 1024 * 1024:
                    print(f"Downloaded {written / (1024 * 1024):.0f} MB")

    actual_size = target.stat().st_size
    if actual_size != EXPECTED_SIZE_BYTES:
        raise RuntimeError(f"Unexpected downloaded size: {actual_size}")


def extract(zip_path: Path, destination: Path, force: bool) -> Path:
    package_dir = destination / PACKAGE_DIR_NAME
    package_db = package_dir / PACKAGE_DB_RELATIVE_PATH
    if package_dir.exists():
        if not force and package_db.exists():
            print(f"Package already exists: {package_dir}")
            return package_dir
        shutil.rmtree(package_dir)

    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(destination)

    if not package_dir.exists():
        raise RuntimeError(f"Zip did not contain {PACKAGE_DIR_NAME}/")
    if not package_db.exists():
        raise RuntimeError(f"Zip did not contain {PACKAGE_DIR_NAME}/{PACKAGE_DB_RELATIVE_PATH}")
    return package_dir


def smoke_test(package_dir: Path) -> None:
    sys.path.insert(0, str(package_dir))
    from london_mapped_data import get_borough_data, resolve_borough

    borough = resolve_borough(51.5074, -0.1278)
    if not borough or borough.get("name") != "Westminster":
        raise RuntimeError(f"Unexpected borough smoke test result: {borough}")

    result = get_borough_data(51.5074, -0.1278, theme="housing", limit=1)
    if result["pagination"]["returned"] != 1:
        raise RuntimeError("Housing smoke test returned no rows")

    print("Smoke test OK: Westminster housing row returned")


def setup(
    force: bool = False,
    keep_zip: bool = False,
    url: str = PUBLIC_BUNDLE_URL,
    destination: Path | None = None,
    cache: Path | None = None,
) -> Path:
    destination = destination or Path(__file__).resolve().parent
    cache = cache or Path(__file__).resolve().parent / ".cache" / "london_mapped_data_public_bundle.zip"

    destination.mkdir(parents=True, exist_ok=True)
    if cache.exists() and cache.stat().st_size == EXPECTED_SIZE_BYTES:
        print(f"Using cached bundle: {cache}")
    else:
        with tempfile.NamedTemporaryFile(delete=False, dir=cache.parent if cache.parent.exists() else None) as tmp:
            tmp_path = Path(tmp.name)
        try:
            print(f"Downloading {url}")
            download(url, tmp_path)
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp_path.replace(cache)
        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    package_dir = extract(cache, destination, force)
    smoke_test(package_dir)

    if not keep_zip and cache.exists():
        cache.unlink()
        try:
            cache.parent.rmdir()
        except OSError:
            pass

    print(f"Ready: {package_dir}")
    return package_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Download and unpack the London mapped data package.")
    parser.add_argument("--url", default=PUBLIC_BUNDLE_URL)
    parser.add_argument("--destination", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--cache", type=Path, default=Path(__file__).resolve().parent / ".cache" / "london_mapped_data_public_bundle.zip")
    parser.add_argument("--force", action="store_true", help="Replace an existing london_mapped_data_package directory.")
    parser.add_argument("--keep-zip", action="store_true", help="Keep the downloaded zip in the cache path.")
    args = parser.parse_args()

    setup(force=args.force, keep_zip=args.keep_zip, url=args.url, destination=args.destination, cache=args.cache)


if __name__ == "__main__":
    main()

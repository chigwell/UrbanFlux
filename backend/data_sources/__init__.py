from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from .setup_london_mapped_data import PUBLIC_BUNDLE_URL, setup as setup_london_mapped_data


DATA_SOURCES_DIR = Path(__file__).resolve().parent
LONDON_MAPPED_DATA_PACKAGE_DIR = DATA_SOURCES_DIR / "london_mapped_data_package"


def ensure_london_mapped_data() -> Path:
    """Return the local package path, downloading/unpacking it on first use."""
    if not LONDON_MAPPED_DATA_PACKAGE_DIR.exists():
        setup_london_mapped_data()
    package_path = str(LONDON_MAPPED_DATA_PACKAGE_DIR)
    if package_path not in sys.path:
        sys.path.insert(0, package_path)
    return LONDON_MAPPED_DATA_PACKAGE_DIR


def get_london_mapped_data_api() -> Any:
    """Import and return the downloaded london_mapped_data package."""
    ensure_london_mapped_data()
    return importlib.import_module("london_mapped_data")


def resolve_borough(*args: Any, **kwargs: Any) -> Any:
    return get_london_mapped_data_api().resolve_borough(*args, **kwargs)


def get_borough_data(*args: Any, **kwargs: Any) -> Any:
    return get_london_mapped_data_api().get_borough_data(*args, **kwargs)


def iter_borough_data(*args: Any, **kwargs: Any) -> Any:
    return get_london_mapped_data_api().iter_borough_data(*args, **kwargs)


def get_borough_summary(*args: Any, **kwargs: Any) -> Any:
    return get_london_mapped_data_api().get_borough_summary(*args, **kwargs)


__all__ = [
    "DATA_SOURCES_DIR",
    "LONDON_MAPPED_DATA_PACKAGE_DIR",
    "PUBLIC_BUNDLE_URL",
    "ensure_london_mapped_data",
    "get_london_mapped_data_api",
    "setup_london_mapped_data",
    "resolve_borough",
    "get_borough_data",
    "iter_borough_data",
    "get_borough_summary",
]

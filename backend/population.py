from __future__ import annotations

import json
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from shapely.geometry import shape

from schemas import GeoJSONPolygon


_BACKEND_DIR = Path(__file__).resolve().parent
_LSOA_BOUNDARIES_PATH = _BACKEND_DIR / "london-lsoa-boundaries.geojson"
_POPULATION_JSON_PATH = _BACKEND_DIR / "london-lsoa-population.json"

# Fallback remote URL if local boundaries file is absent.
# Paginated: ArcGIS caps at 2000 features per request.
_ARCGIS_BASE_URL = (
    "https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/"
    "Lower_layer_Super_Output_Areas_December_2021_Boundaries_EW_BSC_V4/"
    "FeatureServer/0/query"
)
_LONDON_BBOX = "-0.5103751,51.2867602,0.3340155,51.6918741"


def _fetch_arcgis_features() -> list[dict]:
    """Paginate through ArcGIS to fetch all London LSOA boundary features."""
    all_features: list[dict] = []
    offset = 0
    page_size = 2000
    while True:
        params = urllib.parse.urlencode(
            {
                "geometry": _LONDON_BBOX,
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "LSOA21CD",
                "returnGeometry": "true",
                "f": "geojson",
                "resultRecordCount": page_size,
                "resultOffset": offset,
            }
        )
        url = f"{_ARCGIS_BASE_URL}?{params}"
        try:
            with urllib.request.urlopen(url, timeout=60) as resp:
                page = json.loads(resp.read())
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch LSOA boundaries from ArcGIS: {exc}") from exc
        features = page.get("features", [])
        all_features.extend(features)
        if not page.get("exceededTransferLimit") or len(features) == 0:
            break
        offset += page_size
    return all_features


@lru_cache(maxsize=1)
def _load_lsoa_features() -> list[dict]:
    """
    Load LSOA boundary + population into a list of dicts:
        {"geometry": shapely_geom, "code": "E01xxxxxx", "population": int}

    Priority:
    1. data_sources package (Eugene's work, imported if available)
    2. Backend-local london-lsoa-boundaries.geojson + london-lsoa-population.json
    3. Remote ArcGIS fetch (slow first call; cached thereafter)
    """
    try:
        from data_sources import get_lsoa_features  # type: ignore

        return get_lsoa_features()
    except (ImportError, AttributeError):
        pass

    try:
        with _POPULATION_JSON_PATH.open() as fh:
            pop_lookup: dict[str, int] = json.load(fh)
    except FileNotFoundError:
        pop_lookup = {}

    if _LSOA_BOUNDARIES_PATH.exists():
        with _LSOA_BOUNDARIES_PATH.open() as fh:
            gj = json.load(fh)
        raw_features = gj.get("features", [])
    else:
        raw_features = _fetch_arcgis_features()

    features = []
    for feat in raw_features:
        code = feat["properties"].get("LSOA21CD", "")
        population = pop_lookup.get(code, 0)
        try:
            geom = shape(feat["geometry"])
        except Exception:
            continue
        features.append({"geometry": geom, "code": code, "population": population})

    return features


def _extract_shapely_geom(polygon: GeoJSONPolygon):
    """Turn a GeoJSONPolygon (Feature or bare geometry) into a Shapely geometry."""
    if polygon.type == "Feature":
        raw = polygon.geometry
    else:
        raw = polygon.model_dump(exclude_none=True)
    try:
        return shape(raw)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Invalid GeoJSON geometry: {exc}") from exc


def _population_in_polygon(sel_geom) -> tuple[int, int]:
    """Return (total_population, lsoa_count) for LSOAs intersecting sel_geom."""
    features = _load_lsoa_features()
    total_pop = 0
    count = 0
    for feat in features:
        lsoa_geom = feat["geometry"]
        if not sel_geom.intersects(lsoa_geom):
            continue
        try:
            intersection = sel_geom.intersection(lsoa_geom)
            fraction = intersection.area / lsoa_geom.area if lsoa_geom.area > 0 else 0
        except Exception:
            fraction = 1.0
        total_pop += round(feat["population"] * fraction)
        count += 1
    return total_pop, count


def _area_km2(geom) -> float:
    """Approximate area in km² using a simple degree-to-metre conversion near London."""
    deg_lat_m = 111_320
    deg_lon_m = 69_600
    from shapely.affinity import scale

    geom_m = scale(geom, xfact=deg_lon_m, yfact=deg_lat_m, origin=(0, 0))
    return geom_m.area / 1_000_000

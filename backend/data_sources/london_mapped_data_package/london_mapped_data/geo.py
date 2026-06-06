from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class BoroughBoundary:
    name: str
    code: str | None
    rings: tuple[tuple[tuple[float, float], ...], ...]
    bbox: tuple[float, float, float, float]


def lat_lon_to_bng(lat: float, lon: float) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)

    a1 = 6378137.0
    b1 = 6356752.3141
    e2_1 = 1 - (b1 * b1) / (a1 * a1)
    nu1 = a1 / math.sqrt(1 - e2_1 * math.sin(lat_rad) ** 2)
    x1 = nu1 * math.cos(lat_rad) * math.cos(lon_rad)
    y1 = nu1 * math.cos(lat_rad) * math.sin(lon_rad)
    z1 = ((1 - e2_1) * nu1) * math.sin(lat_rad)

    tx, ty, tz = -446.448, 125.157, -542.060
    scale = 20.4894 * 1e-6
    rx = math.radians(-0.1502 / 3600)
    ry = math.radians(-0.2470 / 3600)
    rz = math.radians(-0.8421 / 3600)
    x2 = tx + (1 + scale) * x1 - rz * y1 + ry * z1
    y2 = ty + rz * x1 + (1 + scale) * y1 - rx * z1
    z2 = tz - ry * x1 + rx * y1 + (1 + scale) * z1

    a = 6377563.396
    b = 6356256.909
    e2 = 1 - (b * b) / (a * a)
    p = math.sqrt(x2 * x2 + y2 * y2)
    lat_osgb = math.atan2(z2, p * (1 - e2))
    while True:
        nu = a / math.sqrt(1 - e2 * math.sin(lat_osgb) ** 2)
        next_lat = math.atan2(z2 + e2 * nu * math.sin(lat_osgb), p)
        if abs(next_lat - lat_osgb) < 1e-12:
            lat_osgb = next_lat
            break
        lat_osgb = next_lat
    lon_osgb = math.atan2(y2, x2)

    f0 = 0.9996012717
    lat0 = math.radians(49.0)
    lon0 = math.radians(-2.0)
    n0 = -100000.0
    e0 = 400000.0
    n = (a - b) / (a + b)
    sin_lat = math.sin(lat_osgb)
    cos_lat = math.cos(lat_osgb)
    nu = a * f0 / math.sqrt(1 - e2 * sin_lat * sin_lat)
    rho = a * f0 * (1 - e2) / (1 - e2 * sin_lat * sin_lat) ** 1.5
    eta2 = nu / rho - 1

    ma = (1 + n + 1.25 * n * n + 1.25 * n**3) * (lat_osgb - lat0)
    mb = (3 * n + 3 * n * n + 21 / 8 * n**3) * math.sin(lat_osgb - lat0) * math.cos(lat_osgb + lat0)
    mc = (15 / 8 * n * n + 15 / 8 * n**3) * math.sin(2 * (lat_osgb - lat0)) * math.cos(2 * (lat_osgb + lat0))
    md = 35 / 24 * n**3 * math.sin(3 * (lat_osgb - lat0)) * math.cos(3 * (lat_osgb + lat0))
    m = b * f0 * (ma - mb + mc - md)

    d_lon = lon_osgb - lon0
    tan_lat = math.tan(lat_osgb)
    i = m + n0
    ii = nu / 2 * sin_lat * cos_lat
    iii = nu / 24 * sin_lat * cos_lat**3 * (5 - tan_lat**2 + 9 * eta2)
    iiia = nu / 720 * sin_lat * cos_lat**5 * (61 - 58 * tan_lat**2 + tan_lat**4)
    iv = nu * cos_lat
    v = nu / 6 * cos_lat**3 * (nu / rho - tan_lat**2)
    vi = nu / 120 * cos_lat**5 * (5 - 18 * tan_lat**2 + tan_lat**4 + 14 * eta2 - 58 * tan_lat**2 * eta2)

    northing = i + ii * d_lon**2 + iii * d_lon**4 + iiia * d_lon**6
    easting = e0 + iv * d_lon + v * d_lon**3 + vi * d_lon**5
    return easting, northing


def point_in_ring(x: float, y: float, ring: tuple[tuple[float, float], ...]) -> bool:
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point
        xj, yj = ring[j]
        if (yi > y) != (yj > y):
            x_at_y = (xj - xi) * (y - yi) / (yj - yi) + xi
            if x < x_at_y:
                inside = not inside
        j = i
    return inside


def point_in_polygon(x: float, y: float, boundary: BoroughBoundary) -> bool:
    min_x, min_y, max_x, max_y = boundary.bbox
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return False
    if not boundary.rings or not point_in_ring(x, y, boundary.rings[0]):
        return False
    return not any(point_in_ring(x, y, ring) for ring in boundary.rings[1:])


def parse_rings(raw: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    parsed = json.loads(raw)
    return tuple(tuple((float(point[0]), float(point[1])) for point in ring) for ring in parsed)


def make_bbox(rings: tuple[tuple[tuple[float, float], ...], ...]) -> tuple[float, float, float, float]:
    points = [point for ring in rings for point in ring]
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


@lru_cache(maxsize=8)
def load_borough_boundaries(db_path: str) -> tuple[BoroughBoundary, ...]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT borough_name, borough_code, border_coordinates_json
            FROM london_borough_boundaries
            ORDER BY borough_name
            """
        ).fetchall()
    finally:
        conn.close()

    boundaries = []
    for row in rows:
        rings = parse_rings(row["border_coordinates_json"])
        boundaries.append(
            BoroughBoundary(
                name=row["borough_name"],
                code=row["borough_code"],
                rings=rings,
                bbox=make_bbox(rings),
            )
        )
    return tuple(boundaries)


def find_borough(lat: float, lon: float, db_path: str | Path) -> dict | None:
    x, y = lat_lon_to_bng(lat, lon)
    for boundary in load_borough_boundaries(str(Path(db_path).resolve())):
        if point_in_polygon(x, y, boundary):
            return {
                "name": boundary.name,
                "code": boundary.code,
                "input": {"lat": lat, "lon": lon},
                "projected": {"easting": x, "northing": y, "crs": "EPSG:27700"},
            }
    return None

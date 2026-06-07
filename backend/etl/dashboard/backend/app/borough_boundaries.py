from __future__ import annotations

import argparse
import hashlib
import json
import math
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    import shapefile  # type: ignore
except ImportError as exc:
    raise RuntimeError(
        "pyshp is required to sync borough boundaries. Install with `pip install pyshp` "
        "or add it to backend/requirements.txt."
    ) from exc

from .config import get_settings
from .database import (
    connect,
    clear_london_borough_boundaries,
    init_db,
    upsert_london_borough_boundary,
)


def _geometry_field_candidates() -> dict[str, list[str]]:
    return {
        "name": [
        "borough_name",
        "borough",
        "boroname",
        "ladnm",
        "lad19nm",
        "lad20nm",
        "lad21nm",
        "lad22nm",
        "lad_name",
        "laua_nm",
        "lad_name",
        "laua_nm",
        "name",
        ],
        "code": [
            "borough_code",
            "borocode",
            "ladcd",
            "lad19cd",
            "lad20cd",
            "lad21cd",
            "lad22cd",
            "laua_code",
            "bng_code",
            "gss_code",
            "geo_code",
        ],
    }


def _safe_name(value: Any) -> str:
    value = "" if value is None else str(value).strip()
    return " ".join(value.split())

def _safe_text(value: Any) -> str | None:
    value = _safe_name(value)
    return value or None


def _field_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _normalize_point(point: tuple[float, float], decimals: int = 6) -> tuple[float, float]:
    return (round(point[0], decimals), round(point[1], decimals))


def _normalize_ring(ring: list[tuple[float, float]], decimals: int = 6) -> list[tuple[float, float]]:
    return [_normalize_point(point, decimals=decimals) for point in _unique_points(ring)]


def _unique_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    unique: list[tuple[float, float]] = []
    for point in points:
        if not unique or point != unique[-1]:
        # drop exact duplicate neighbour points for cleaner output
            unique.append(point)
    return unique


def _ring_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0
    area = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        area += (x1 * y2) - (x2 * y1)
    return area / 2.0


def _convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= 1:
        return points[:]

    unique_points = sorted(set(points))
    if len(unique_points) <= 1:
        return unique_points[:]

    def cross(
        origin: tuple[float, float],
        first: tuple[float, float],
        second: tuple[float, float],
    ) -> float:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique_points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique_points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    hull = lower[:-1] + upper[:-1]
    if hull[0] != hull[-1]:
        hull.append(hull[0])
    return hull


def _extract_outer_ring(shape: Any) -> list[tuple[float, float]]:
    points = [(float(x), float(y)) for x, y in shape.points]
    if len(points) < 4:
        return points
    parts: list[int] = list(shape.parts)
    parts.append(len(points))
    rings: list[tuple[float, list[tuple[float, float]]]] = []
    for index in range(len(parts) - 1):
        ring = points[parts[index] : parts[index + 1]]
        ring = _unique_points(ring)
        if len(ring) < 4:
            continue
        rings.append((abs(_ring_area(ring)), ring))
    if not rings:
        return _unique_points(points)
    _, ring = max(rings, key=lambda item: item[0])
    if ring[0] != ring[-1]:
        ring.append(ring[0])
    return ring


def _extract_rings(shape: Any) -> list[list[tuple[float, float]]]:
    points = [(float(x), float(y)) for x, y in shape.points]
    if len(points) < 4:
        return []

    parts: list[int] = list(shape.parts)
    parts.append(len(points))
    rings: list[list[tuple[float, float]]] = []
    for index in range(len(parts) - 1):
        ring = _unique_points(points[parts[index] : parts[index + 1]])
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        rings.append(ring)
    return rings


def _edge_key(first: tuple[float, float], second: tuple[float, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    return (first, second) if first <= second else (second, first)


def _build_outer_ring_from_edges(
    edges: set[tuple[tuple[float, float], tuple[float, float]]],
) -> list[tuple[float, float]]:
    if not edges:
        return []

    adjacency: dict[tuple[float, float], list[tuple[float, float]]] = {}
    for point_a, point_b in edges:
        adjacency.setdefault(point_a, []).append(point_b)
        adjacency.setdefault(point_b, []).append(point_a)

    if not adjacency:
        return []

    used: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    rings: list[list[tuple[float, float]]] = []

    def has_unvisited(point: tuple[float, float]) -> bool:
        return any(_edge_key(point, neighbour) not in used for neighbour in adjacency.get(point, []))

    for start in sorted(adjacency):
        if not has_unvisited(start):
            continue
        ring: list[tuple[float, float]] = []
        current = start
        previous: tuple[float, float] | None = None
        while True:
            ring.append(current)
            candidates = [neighbour for neighbour in adjacency[current] if _edge_key(current, neighbour) not in used]
            if not candidates:
                break
            if previous is not None and len(candidates) > 1:
                non_backtrack = [n for n in candidates if n != previous]
                if non_backtrack:
                    candidates = non_backtrack
            next_point = sorted(candidates)[0]
            used.add(_edge_key(current, next_point))
            previous, current = current, next_point
            if current == start:
                ring.append(start)
                break
            if len(ring) > len(edges) + 4:
                break
        if len(ring) >= 4 and ring[0] == ring[-1]:
            rings.append(ring)

    if not rings:
        return []

    candidate = max(rings, key=lambda item: abs(_ring_area(item)))
    if candidate[0] != candidate[-1]:
        candidate.append(candidate[0])
    return candidate


def _build_boundary_rings_from_edges(
    edges: set[tuple[tuple[float, float], tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    if not edges:
        return []

    adjacency: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    for point_a, point_b in edges:
        adjacency[point_a].add(point_b)
        adjacency[point_b].add(point_a)

    unused = set(edges)
    rings: list[list[tuple[float, float]]] = []

    while unused:
        start_a, start_b = min(unused)
        current = start_b
        previous = start_a
        ring = [start_a, start_b]
        unused.remove(_edge_key(start_a, start_b))

        while current != start_a:
            candidates = [
                next_point
                for next_point in sorted(adjacency[current])
                if next_point != previous and _edge_key(current, next_point) in unused
            ]
            if not candidates:
                break
            next_point = candidates[0]
            unused.remove(_edge_key(current, next_point))
            ring.append(next_point)
            previous, current = current, next_point

            if len(ring) > len(edges) + 2:
                break

        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)

    return sorted(rings, key=lambda ring: abs(_ring_area(ring)), reverse=True)


def _perpendicular_distance(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    (x0, y0), (x1, y1), (x2, y2) = point, start, end
    denominator = math.hypot(x2 - x1, y2 - y1)
    if denominator == 0:
        return math.hypot(x0 - x1, y0 - y1)
    numerator = abs((y2 - y1) * x0 - (x2 - x1) * y0 + x2 * y1 - y2 * x1)
    return numerator / denominator


def _rdp(
    points: list[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    first = points[0]
    last = points[-1]
    index = 0
    max_distance = 0.0
    for i in range(1, len(points) - 1):
        distance = _perpendicular_distance(points[i], first, last)
        if distance > max_distance:
            max_distance = distance
            index = i
    if max_distance <= epsilon:
        return [first, last]
    left = _rdp(points[: index + 1], epsilon)
    right = _rdp(points[index:], epsilon)
    return left[:-1] + right


def _simplify_polygon(
    ring: list[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    if len(ring) < 4 or epsilon <= 0:
        return ring
    closed = ring[0] == ring[-1]
    points = ring[:-1] if closed else ring[:]
    simplified = _rdp(points, epsilon)
    simplified = _unique_points(simplified)
    if not simplified:
        return []
    if closed:
        if simplified[0] != simplified[-1]:
            simplified.append(simplified[0])
    return simplified


def _select_field_name(
    fields: list[str],
    candidates: list[str],
) -> str | None:
    lowered = {field.lower(): field for field in fields}
    normalised = {_field_key(name): name for name in fields}
    for candidate in candidates:
        key = candidate.lower()
        if key in lowered:
            return lowered[key]
        normalized_candidate = _field_key(candidate)
        if normalized_candidate in normalised:
            return normalised[normalized_candidate]
        for field in lowered:
            if key in field:
                return lowered[field]
        for field in normalised:
            if normalized_candidate in field:
                return normalised[field]
    return None


def _projected_tolerance(points: list[tuple[float, float]]) -> float:
    xs, ys = zip(*points)
    width = max(xs) - min(xs)
    height = max(ys) - min(ys)
    max_span = max(width, height)
    if max(abs(min(xs)), abs(max(xs)), abs(min(ys)), abs(max(ys))) > 180:
        return max(20.0, max_span * 0.002)
    return max(0.00015, max_span * 0.0007)


def _read_projection(path: Path) -> str | None:
    projection_path = path.with_suffix(".prj")
    if not projection_path.exists():
        return None
    return projection_path.read_text(encoding="utf-8", errors="ignore").splitlines()[0].strip() or None


def _field_candidates(fields: list[str]) -> tuple[str | None, str | None]:
    name = _select_field_name(fields, _geometry_field_candidates()["name"])
    if name is None:
        for candidate in fields:
            if "name" in candidate.lower():
                name = candidate
                break
    code = _select_field_name(fields, _geometry_field_candidates()["code"])
    if code is None and len(fields) > 1:
        for candidate in fields:
            if "code" in candidate.lower() or candidate.lower().endswith("cd"):
                code = candidate
                break
    return name, code


def _to_records(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []
    return sorted(rows, key=lambda row: row["borough_name"])


def _load_records_from_shapefile(
    shapefile_path: Path,
    tolerance: float | None = None,
) -> list[dict[str, Any]]:
    reader = shapefile.Reader(str(shapefile_path))
    field_names = [field[0] for field in reader.fields[1:]]
    name_field, code_field = _field_candidates(field_names)
    if name_field is None:
        raise RuntimeError(
            "Could not detect borough name field in shapefile."
            f" Available fields: {field_names}"
        )

    grouped: dict[str, list[tuple[str | None, list[tuple[float, float]]]]] = defaultdict(list)
    for shape_record in reader.iterShapeRecords():
        record = shape_record.record.as_dict() if hasattr(shape_record.record, "as_dict") else None
        if record is None:
            record = {name: shape_record.record[index] for index, name in enumerate(field_names)}
        borough_name = _safe_text(record.get(name_field))
        if not borough_name:
            continue
        borough_code = _safe_text(record.get(code_field)) if code_field else None
        for ring in _extract_rings(shape_record.shape):
            if len(ring) < 4:
                continue
            if tolerance is not None and tolerance > 0:
                ring = _simplify_polygon(ring, tolerance)
                if len(ring) < 4:
                    continue
            grouped[borough_name].append((borough_code, _normalize_ring(ring)))

    if not grouped:
        raise RuntimeError("No borough geometries were extracted from the shapefile.")
    if len(grouped) > 150:
        sample = ", ".join(sorted(grouped)[:6])
        raise RuntimeError(
            "Could not identify borough-level geometry. "
            f"Detected {len(grouped)} unique names. Check field mapping and try again."
            f" Samples: {sample}"
        )

    boundaries = []
    for borough_name in sorted(grouped):
        records = grouped[borough_name]
        if len(records) == 1:
            code, ring = records[0]
            polygon = ring
            if ring[0] != ring[-1]:
                ring = list(ring) + [ring[0]]
            if tolerance is not None and tolerance > 0:
                polygon = _simplify_polygon(ring, tolerance)
            borders = [list(polygon)]
        else:
            edge_counts: Counter[tuple[tuple[float, float], tuple[float, float]]] = Counter()
            for _, ring in records:
                closed = ring[0] == ring[-1]
                ring_points = ring[:-1] if closed else ring
                if len(ring_points) < 3:
                    continue
                deduped = _unique_points(ring_points)
                for point_a, point_b in zip(deduped, deduped[1:] + deduped[:1]):
                    edge_counts[_edge_key(point_a, point_b)] += 1
            if not edge_counts:
                continue
            border_edges = {edge for edge, count in edge_counts.items() if count == 1}
            if not border_edges:
                fallback = _convex_hull([point for _, ring in records for point in ring])
                if len(fallback) < 4:
                    continue
                borders = [fallback]
            else:
                boundary_rings = _build_boundary_rings_from_edges(border_edges)
                if not boundary_rings:
                    fallback = _convex_hull([point for _, ring in records for point in ring])
                    if len(fallback) < 4:
                        continue
                    boundary_rings = [fallback]
                if tolerance is not None and tolerance > 0:
                    boundary_rings = [
                        simplified
                        for ring in boundary_rings
                        if len(simplified := _simplify_polygon(ring, tolerance)) >= 4
                    ]
                borders = [list(ring) for ring in boundary_rings]
            code = _safe_text(records[0][0]) if records[0][0] else None
        boundaries.append(
            {
                "borough_name": borough_name,
                "borough_code": code,
                "borders": borders,
            },
        )

    return _to_records(boundaries)


def _source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_shape_file(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "london-borough-boundary-sync/1.0"})
    with urlopen(request, timeout=60) as response:
        if response.getcode() != 200:
            raise RuntimeError(f"Failed to download shapefile. HTTP status: {response.getcode()}")
        target.write_bytes(response.read())
    return target


def _copy_file(source: Path, target: Path) -> Path:
    target.write_bytes(source.read_bytes())
    return target


def sync_london_borough_boundaries(
    shapefile_url: str | None = None,
    shape_file_path: str | None = None,
    *,
    tolerance: float | None = None,
    replace: bool = True,
    source_url: str | None = None,
) -> int:
    settings = get_settings()
    shapefile_url = shapefile_url or settings.london_borough_shape_url
    source_url = source_url or shapefile_url
    if tolerance is None:
        tolerance = settings.london_borough_bounds_tolerance
    shape_source_path: str | None
    if shape_file_path:
        shape_source_path = shape_file_path
    else:
        parsed = urlparse(shapefile_url)
        if not parsed.scheme.startswith("http"):
            raise RuntimeError("Shapefile URL must be http or https.")
        shape_source_path = None

    with TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir) / "boroughs.zip"
        extracted_dir = Path(temp_dir) / "extracted"
        extracted_dir.mkdir()
        shape_hash: str
        if shape_source_path:
            source_path = Path(shape_source_path)
            if not source_path.exists():
                raise RuntimeError(f"Local shape source not found: {shape_source_path}")
            if source_path.suffix.lower() != ".zip":
                if source_path.suffix.lower() == ".shp":
                    source_shapefile = source_path
                    shapefiles = [source_shapefile]
                    shape_hash = _source_hash(source_shapefile)
                else:
                    raise RuntimeError("Local shape source must be a .zip archive or .shp file.")
            else:
                _copy_file(source_path, zip_path)
                with zipfile.ZipFile(zip_path, "r") as archive:
                    archive.extractall(extracted_dir)
                shapefiles = sorted(extracted_dir.rglob("*.shp"))
                if not shapefiles:
                    raise RuntimeError("The local zip archive does not contain a .shp file.")
                shape_hash = _source_hash(zip_path)
        else:
            _download_shape_file(shapefile_url, zip_path)
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(extracted_dir)
            shapefiles = sorted(extracted_dir.rglob("*.shp"))
            if not shapefiles:
                raise RuntimeError("The downloaded archive does not contain a .shp file.")
            shape_hash = _source_hash(zip_path)

        if not shapefiles:
            raise RuntimeError("No borough boundary records were parsed.")
        total_upserted = 0
        with connect() as connection:
            init_db()
            if replace:
                clear_london_borough_boundaries(connection)
            for shapefile_path in shapefiles:
                coordinate_system = _read_projection(shapefile_path)
                geometry = shapefile.Reader(str(shapefile_path)).shapeTypeName
                boundaries = _load_records_from_shapefile(shapefile_path, tolerance=tolerance)
                for record in boundaries:
                    upsert_london_borough_boundary(
                        connection=connection,
                        borough={
                            "borough_name": record["borough_name"],
                            "borough_code": record.get("borough_code"),
                            "source_url": source_url,
                            "source_file_name": shapefile_path.name,
                            "coordinate_system": coordinate_system,
                            "geometry_type": geometry,
                            "source_file_hash": shape_hash,
                            "borders": record["borders"],
                        },
                    )
                    total_upserted += 1
        return total_upserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync London borough boundaries into SQLite.")
    parser.add_argument("--url", default=None, help="Shapefile download URL.")
    parser.add_argument(
        "--shape-path",
        default=None,
        help="Optional local path to .zip archive or .shp file.",
    )
    parser.add_argument("--source-url", default=None, help="Data source URL to store in DB.")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        help="Simplification tolerance for corner extraction.",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        default=False,
        help="Keep existing records and only upsert matching boroughs.",
    )
    args = parser.parse_args()
    count = sync_london_borough_boundaries(
        shapefile_url=args.url,
        shape_file_path=args.shape_path,
        tolerance=args.tolerance,
        replace=not args.no_replace,
        source_url=args.source_url,
    )
    print(json.dumps({"upserted": count}, indent=2))


if __name__ == "__main__":
    main()

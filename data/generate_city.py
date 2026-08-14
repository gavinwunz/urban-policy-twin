#!/usr/bin/env python3
"""Deterministic generator for the GOV SIM analysis grid.

Produces the *shared dataset* consumed by the baseline digital twin, the
synthetic population, the policy simulation and the 3D map.

Geography: the grid is anchored on the real centre of **Auckland, New Zealand**
(-36.8485, 174.7633), so it lines up with the OpenStreetMap basemap the frontend
draws underneath it. The zone system itself is a synthetic regular grid — the
same kind of abstraction a real transport model uses in place of raw parcels —
and the population, jobs and trip figures in it are modelled, not measured. No
real person or administrative record is represented.

Guardrail note (SPEC §34): this is *input world state*, not a simulation result.
Every record is tagged ``provenance: "Synthetic"`` in the manifest. Nothing here
is an LLM-generated numeric effect.

Run::

    python data/generate_city.py

Output (overwritten each run, deterministic for a fixed --seed)::

    data/city/manifest.json   dataset provenance + summary counts
    data/city/zones.geojson   zone polygons + attributes (pop, jobs, land use)
    data/city/roads.geojson   road network links (capacity, speed, cordon flag)
    data/city/od_pairs.json   origin→destination daily person-trips (gravity)

The generator uses only the Python standard library so it runs anywhere without
installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# City configuration
# ---------------------------------------------------------------------------

CITY_NAME = "Auckland"
CITY_REGION = "Auckland, New Zealand"
GRID = 9  # GRID x GRID zones
CELL_KM = 0.75  # size of one zone cell, km
# Real anchor: Auckland CBD (Queen Street / Britomart). The analysis grid is
# centred here so it registers against the OpenStreetMap basemap.
CENTER_LAT = -36.8485
CENTER_LON = 174.7633

# Category assignment by Chebyshev ring distance from the centre cell.
#   ring 0-1 -> CBD (central 3x3), 2 -> inner, 3 -> residential, 4 -> outer
CBD_RING = 1
INNER_RING = 2
RESIDENTIAL_RING = 3

# Per-category base residents / jobs per zone (before deterministic jitter).
CATEGORY_PROFILE = {
    # category      residents  jobs   land_use
    "cbd": (900, 6200, "commercial"),
    "inner": (3200, 2600, "mixed"),
    "residential": (4600, 900, "residential"),
    "industrial": (1400, 2400, "industrial"),
    "green": (350, 180, "green_space"),
}

# Destination-constrained gravity parameters. Each zone's jobs are the control
# total; origins supply commuters ~ population / distance^gamma.
GRAVITY_K = 1.0  # shared scale constant (cancels in the destination normalisation)
GRAVITY_ALPHA = 1.0  # origin (population) exponent
GRAVITY_GAMMA = 2.0  # distance decay exponent
MIN_OD_TRIPS = 8  # drop OD pairs below this many daily trips to keep file lean


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _deg_per_km_lat() -> float:
    return 1.0 / 111.32


def _deg_per_km_lon(lat: float) -> float:
    return 1.0 / (111.32 * math.cos(math.radians(lat)))


def _centroid(row: int, col: int) -> tuple[float, float]:
    """Return (lon, lat) for the centre of the given grid cell.

    Row 0 is the northern edge; column 0 is the western edge.
    """
    mid = (GRID - 1) / 2.0
    dlat = _deg_per_km_lat() * CELL_KM
    dlon = _deg_per_km_lon(CENTER_LAT) * CELL_KM
    lon = CENTER_LON + (col - mid) * dlon
    lat = CENTER_LAT + (mid - row) * dlat
    return round(lon, 6), round(lat, 6)


def _cell_polygon(row: int, col: int) -> list[list[float]]:
    """Square polygon ring (closed) for a grid cell, GeoJSON winding order."""
    lon, lat = _centroid(row, col)
    dlat = _deg_per_km_lat() * CELL_KM / 2.0
    dlon = _deg_per_km_lon(CENTER_LAT) * CELL_KM / 2.0
    ring = [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]
    return [[round(x, 6), round(y, 6)] for x, y in ring]


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# ---------------------------------------------------------------------------
# Zone / category logic
# ---------------------------------------------------------------------------

def _ring(row: int, col: int) -> int:
    mid = (GRID - 1) // 2
    return max(abs(row - mid), abs(col - mid))


def _category(rng: random.Random, row: int, col: int) -> str:
    ring = _ring(row, col)
    if ring <= CBD_RING:
        return "cbd"
    if ring == INNER_RING:
        return "inner"
    if ring == RESIDENTIAL_RING:
        return "residential"
    # Outer ring: a mix of residential, industrial and green space.
    return rng.choices(
        ["residential", "industrial", "green"], weights=[0.5, 0.3, 0.2]
    )[0]


def _zone_id(row: int, col: int) -> str:
    return f"Z{row * GRID + col:03d}"


def build_zones(rng: random.Random) -> list[dict]:
    zones: list[dict] = []
    for row in range(GRID):
        for col in range(GRID):
            category = _category(rng, row, col)
            base_pop, base_jobs, land_use = CATEGORY_PROFILE[category]
            # deterministic +/-20% jitter so zones are heterogeneous
            pop = int(base_pop * rng.uniform(0.8, 1.2))
            jobs = int(base_jobs * rng.uniform(0.8, 1.2))
            households = max(1, int(pop / rng.uniform(2.1, 2.8)))
            lon, lat = _centroid(row, col)
            zones.append(
                {
                    "zone_id": _zone_id(row, col),
                    "row": row,
                    "col": col,
                    "category": category,
                    "land_use": land_use,
                    "is_cbd": category == "cbd",
                    "centroid": [lon, lat],
                    "area_km2": round(CELL_KM * CELL_KM, 4),
                    "population": pop,
                    "households": households,
                    "jobs": jobs,
                    "polygon": _cell_polygon(row, col),
                }
            )
    return zones


def zones_to_geojson(zones: list[dict]) -> dict:
    features = []
    for z in zones:
        props = {k: v for k, v in z.items() if k not in ("polygon", "centroid")}
        props["centroid_lon"] = z["centroid"][0]
        props["centroid_lat"] = z["centroid"][1]
        features.append(
            {
                "type": "Feature",
                "id": z["zone_id"],
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [z["polygon"]]},
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "auckland_zones",
        "features": features,
    }


# ---------------------------------------------------------------------------
# Road network
# ---------------------------------------------------------------------------

def build_roads(zones: list[dict]) -> list[dict]:
    """Undirected links between orthogonally adjacent zones (grid network).

    Links with exactly one CBD endpoint form the congestion-charge cordon.
    """
    by_rc = {(z["row"], z["col"]): z for z in zones}
    roads: list[dict] = []
    link_idx = 0
    for row in range(GRID):
        for col in range(GRID):
            here = by_rc[(row, col)]
            # east and south neighbours only -> each undirected link once
            for drow, dcol in ((0, 1), (1, 0)):
                nrow, ncol = row + drow, col + dcol
                if nrow >= GRID or ncol >= GRID:
                    continue
                nb = by_rc[(nrow, ncol)]
                a = tuple(here["centroid"])
                b = tuple(nb["centroid"])
                length_km = round(_haversine_km(a, b), 4)
                cbd_count = int(here["is_cbd"]) + int(nb["is_cbd"])
                crosses_cordon = cbd_count == 1
                interior_cbd = cbd_count == 2
                if interior_cbd or crosses_cordon:
                    road_class = "arterial"
                    lanes = 2
                    capacity = 1800  # veh/hr/direction
                    free_flow_kmh = 40
                else:
                    road_class = "local"
                    lanes = 1
                    capacity = 900
                    free_flow_kmh = 50
                roads.append(
                    {
                        "link_id": f"L{link_idx:03d}",
                        "from_zone": here["zone_id"],
                        "to_zone": nb["zone_id"],
                        "road_class": road_class,
                        "lanes": lanes,
                        "length_km": length_km,
                        "capacity_veh_per_hr": capacity,
                        "free_flow_speed_kmh": free_flow_kmh,
                        "crosses_cordon": crosses_cordon,
                        "interior_cbd": interior_cbd,
                        "geometry": [
                            [round(a[0], 6), round(a[1], 6)],
                            [round(b[0], 6), round(b[1], 6)],
                        ],
                    }
                )
                link_idx += 1
    return roads


def roads_to_geojson(roads: list[dict]) -> dict:
    features = []
    for r in roads:
        props = {k: v for k, v in r.items() if k != "geometry"}
        features.append(
            {
                "type": "Feature",
                "id": r["link_id"],
                "properties": props,
                "geometry": {"type": "LineString", "coordinates": r["geometry"]},
            }
        )
    return {
        "type": "FeatureCollection",
        "name": "auckland_roads",
        "features": features,
    }


def cbd_polygon(zones: list[dict]) -> dict:
    """Bounding polygon around the CBD block — the priced/pedestrianised cordon."""
    cbd = [z for z in zones if z["is_cbd"]]
    rows = [z["row"] for z in cbd]
    cols = [z["col"] for z in cbd]
    r0, r1 = min(rows), max(rows)
    c0, c1 = min(cols), max(cols)
    # corners of the CBD block (outer edges of the boundary cells)
    dlat = _deg_per_km_lat() * CELL_KM / 2.0
    dlon = _deg_per_km_lon(CENTER_LAT) * CELL_KM / 2.0
    lon_nw, lat_nw = _centroid(r0, c0)
    lon_se, lat_se = _centroid(r1, c1)
    west, east = lon_nw - dlon, lon_se + dlon
    north, south = lat_nw + dlat, lat_se - dlat
    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    ring = [[round(x, 6), round(y, 6)] for x, y in ring]
    return {
        "type": "Feature",
        "id": "cbd_polygon",
        "properties": {
            "name": "Central district cordon",
            "zone_ids": sorted(z["zone_id"] for z in cbd),
            "description": (
                "Congestion-charge / pedestrianisation boundary for the demo "
                "policy. Vehicles crossing into this polygon are priced."
            ),
        },
        "geometry": {"type": "Polygon", "coordinates": [ring]},
    }


# ---------------------------------------------------------------------------
# Origin -> destination trip table (gravity model)
# ---------------------------------------------------------------------------

def build_od_pairs(zones: list[dict]) -> list[dict]:
    """Destination-constrained gravity: distribute each zone's jobs among origins.

    For destination ``j`` with ``jobs_j`` positions, an origin ``i`` supplies
    commuters in proportion to ``P_i / d_ij^gamma`` (population weighted, distance
    decayed). Total inflow to ``j`` therefore ≈ ``jobs_j`` and the whole matrix
    sums to the city's jobs — a realistic home→work commute interpretation, so
    trips into the CBD ≈ CBD jobs.
    """
    pairs: list[dict] = []
    for dz in zones:
        if dz["jobs"] <= 0:
            continue
        # weight for every candidate origin
        weights: list[tuple[dict, float]] = []
        total_w = 0.0
        for oz in zones:
            if oz["zone_id"] == dz["zone_id"] or oz["population"] <= 0:
                continue
            dist = _haversine_km(tuple(oz["centroid"]), tuple(dz["centroid"]))
            dist = max(dist, CELL_KM / 2.0)
            w = (
                GRAVITY_K
                * (oz["population"] ** GRAVITY_ALPHA)
                / (dist ** GRAVITY_GAMMA)
            )
            weights.append((oz, w))
            total_w += w
        if total_w <= 0:
            continue
        for oz, w in weights:
            trips = int(round(dz["jobs"] * (w / total_w)))
            if trips < MIN_OD_TRIPS:
                continue
            dist = _haversine_km(tuple(oz["centroid"]), tuple(dz["centroid"]))
            dist = max(dist, CELL_KM / 2.0)
            pairs.append(
                {
                    "origin": oz["zone_id"],
                    "destination": dz["zone_id"],
                    "daily_person_trips": trips,
                    "distance_km": round(dist, 3),
                    "dest_is_cbd": dz["is_cbd"],
                }
            )
    return pairs


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def _write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def generate(out_dir: Path, seed: int) -> dict:
    rng = random.Random(seed)
    zones = build_zones(rng)
    roads = build_roads(zones)
    od_pairs = build_od_pairs(zones)
    cordon = cbd_polygon(zones)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "zones.geojson", zones_to_geojson(zones))
    _write_json(out_dir / "roads.geojson", roads_to_geojson(roads))
    _write_json(
        out_dir / "od_pairs.json",
        {
            "name": "auckland_od_pairs",
            "units": "daily_person_trips",
            "model": "destination_constrained_gravity",
            "interpretation": "home->work commute flows; inflow to zone j ~= jobs_j",
            "params": {
                "origin_pop_exponent": GRAVITY_ALPHA,
                "distance_decay_exponent": GRAVITY_GAMMA,
                "min_trips": MIN_OD_TRIPS,
            },
            "pairs": od_pairs,
        },
    )
    _write_json(out_dir / "cbd_polygon.geojson", cordon)

    total_pop = sum(z["population"] for z in zones)
    total_jobs = sum(z["jobs"] for z in zones)
    total_trips = sum(p["daily_person_trips"] for p in od_pairs)
    cordon_trips = sum(p["daily_person_trips"] for p in od_pairs if p["dest_is_cbd"])

    manifest = {
        "title": f"{CITY_NAME} policy analysis grid",
        "city": CITY_NAME,
        "region": CITY_REGION,
        "provenance": "Synthetic",
        "generated_by": "data/generate_city.py",
        "seed": seed,
        "geographic_scope": (
            f"{CITY_REGION} — real coordinates, modelled zone system"
        ),
        "spatial_resolution": f"{CELL_KM} km grid cells",
        "crs": "EPSG:4326 (WGS84 lon/lat)",
        "license": "CC0 (generated demo data)",
        "notes": (
            "Input world state for GOV SIM. The grid is anchored on Auckland's "
            "real centre so it registers against the OpenStreetMap basemap, but "
            "the zone system, population, jobs and trip figures are modelled — "
            "not measured, and not drawn from any administrative record. Numeric "
            "effects are produced later by the simulation engine, never by an "
            "LLM (SPEC §34)."
        ),
        "grid": {"rows": GRID, "cols": GRID, "cell_km": CELL_KM},
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "counts": {
            "zones": len(zones),
            "cbd_zones": sum(1 for z in zones if z["is_cbd"]),
            "roads": len(roads),
            "cordon_crossing_links": sum(1 for r in roads if r["crosses_cordon"]),
            "od_pairs": len(od_pairs),
        },
        "totals": {
            "population": total_pop,
            "jobs": total_jobs,
            "daily_person_trips": total_trips,
            "daily_trips_into_cbd": cordon_trips,
        },
        "files": {
            "zones": "zones.geojson",
            "roads": "roads.geojson",
            "od_pairs": "od_pairs.json",
            "cbd_polygon": "cbd_polygon.geojson",
        },
    }
    _write_json(out_dir / "manifest.json", manifest)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the GOV SIM demo city grid.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42).")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "city",
        help="Output directory (default data/city).",
    )
    args = parser.parse_args()
    manifest = generate(args.out, args.seed)
    print(f"Wrote {CITY_NAME} dataset to {args.out}")
    for key, value in manifest["counts"].items():
        print(f"  {key}: {value}")
    for key, value in manifest["totals"].items():
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()

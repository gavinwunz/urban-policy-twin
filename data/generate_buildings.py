#!/usr/bin/env python3
"""Deterministic generator for the GOV SIM built-environment layer (Auckland).

`generate_city.py` produces the analytical world state (zones, roads, OD matrix).
This script produces the **visual** world state that the 3D scene renders:

    data/city/buildings.geojson   ~1.3k building footprints with heights and a
                                  10-year redevelopment pipeline baked in
    data/city/water.geojson       the river that runs through the city
    data/city/sources.json        data lineage for the 3D model + OD model

Design notes
------------

*Blocks and streets.* Roads in `roads.geojson` connect zone centroids, so every
zone has one road running through the middle horizontally and one vertically.
Each zone is therefore carved into four blocks around a central street cross,
and each block into a 2x2 lot grid. Buildings sit inside the lots with a random
setback, which is what produces readable street canyons rather than a blob.

*Skyline.* Height falls off smoothly with distance from the centre
(a Gaussian-ish dome), modulated by the zone's land use and a per-building
jitter. This reads as a real downtown core tapering into mid-rise and then
suburbs, instead of the "flat extruded choropleth" look.

*Time.* Each building carries the fields the 10-year scrubber needs:

    h    height in metres today (t = 0)
    dh   metres added by year 10 under the do-nothing baseline
    td   *extra* metres added by year 10 if the scenario invests in transit
         (transit-oriented development near the core / cordon)
    t0   the year this building appears (0 = it already exists); buildings with
         t0 > 0 are the development pipeline and rise out of the ground
    g    1 if this lot is a candidate to become a green plaza under
         pedestrianisation (CBD kerbside / surface-parking lots)

The frontend interpolates those fields, so dragging the timeline morphs the city
without a single network round-trip. Nothing here is a simulation *result*:
these are input assumptions about the built environment (SPEC §34), and the
policy response that reads them is a documented mechanistic model, never an LLM.

The footprints are modelled, not surveyed: they are anchored on Auckland's real
coordinates so they register against the OpenStreetMap basemap, but the building
layer itself is generated. See `sources.json` for the real-world datasets this
layer and the demand model are shaped like.

Run::

    python data/generate_buildings.py

Standard library only, deterministic for a fixed --seed.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

# ---------------------------------------------------------------------------
# Config — kept in sync with generate_city.py
# ---------------------------------------------------------------------------

CITY_NAME = "Auckland"
CITY_REGION = "Auckland, New Zealand"
GRID = 9
CELL_KM = 0.75
CENTER_LAT = -36.8485
CENTER_LON = 174.7633

DEG_LAT_PER_KM = 1.0 / 111.32
DEG_LON_PER_KM = 1.0 / (111.32 * math.cos(math.radians(CENTER_LAT)))

# Street cross through each zone, in normalised zone coordinates [0, 1].
STREET_LO, STREET_HI = 0.42, 0.58
BLOCK_MARGIN = 0.045  # gap at the zone edge so neighbouring blocks don't fuse

# Skyline shape: a tall core decaying to a mid-rise "urban fabric" floor, so the
# suburbs stay varied instead of collapsing onto the minimum height.
PEAK_HEIGHT_M = 150.0
FABRIC_HEIGHT_M = 22.0
DECAY_KM = 1.15
DECAY_POWER = 1.9
LANDMARK_HEIGHT_M = 238.0

# Height multiplier per land-use category.
CATEGORY_HEIGHT_FACTOR = {
    "cbd": 1.00,
    "inner": 0.80,
    "residential": 0.62,
    "industrial": 0.55,
    "green": 0.30,
}

# Probability a lot is left as a park / square rather than built on.
PARK_PROB = {
    "cbd": 0.07,
    "inner": 0.11,
    "residential": 0.17,
    "industrial": 0.12,
    "green": 0.72,
}

MIN_BUILDING_M = 7.0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def zone_origin(row: int, col: int) -> tuple[float, float, float, float]:
    """Return (lon_min, lat_min, dlon, dlat) for a zone cell."""
    mid = (GRID - 1) / 2.0
    dlat = DEG_LAT_PER_KM * CELL_KM
    dlon = DEG_LON_PER_KM * CELL_KM
    lon_c = CENTER_LON + (col - mid) * dlon
    lat_c = CENTER_LAT + (mid - row) * dlat
    return lon_c - dlon / 2, lat_c - dlat / 2, dlon, dlat


def ring(row: int, col: int) -> int:
    mid = (GRID - 1) // 2
    return max(abs(row - mid), abs(col - mid))


def km_from_centre(lon: float, lat: float) -> float:
    dx = (lon - CENTER_LON) / DEG_LON_PER_KM
    dy = (lat - CENTER_LAT) / DEG_LAT_PER_KM
    return math.hypot(dx, dy)


def rect(lon0: float, lat0: float, lon1: float, lat1: float) -> list[list[float]]:
    """Closed GeoJSON ring for an axis-aligned rectangle."""
    return [
        [round(lon0, 7), round(lat0, 7)],
        [round(lon1, 7), round(lat0, 7)],
        [round(lon1, 7), round(lat1, 7)],
        [round(lon0, 7), round(lat1, 7)],
        [round(lon0, 7), round(lat0, 7)],
    ]


# ---------------------------------------------------------------------------
# The river
# ---------------------------------------------------------------------------

def river_polygon() -> dict:
    """A meandering river sweeping NNE→SSW, grazing the eastern CBD edge."""
    lat_span = DEG_LAT_PER_KM * CELL_KM * GRID
    lat_min = CENTER_LAT - lat_span / 2 - 0.004
    lat_max = CENTER_LAT + lat_span / 2 + 0.004

    left: list[list[float]] = []
    right: list[list[float]] = []
    steps = 90
    for i in range(steps + 1):
        t = i / steps
        lat = lat_min + t * (lat_max - lat_min)
        # Centreline: a slow diagonal drift plus two gentle meanders.
        lon = (
            CENTER_LON
            + 0.0068
            + 0.0165 * (t - 0.5)
            + 0.0052 * math.sin(2 * math.pi * (t * 1.15 + 0.18))
        )
        # Width breathes a little; ~200-320 m across.
        half = (0.00135 + 0.00045 * math.sin(2 * math.pi * (t * 1.7 + 0.4)))
        left.append([round(lon - half, 7), round(lat, 7)])
        right.append([round(lon + half, 7), round(lat, 7)])

    ring_coords = left + list(reversed(right))
    ring_coords.append(ring_coords[0])
    return {
        "type": "Feature",
        "id": "W000",
        "properties": {"name": "Waitematā Harbour (schematic)", "kind": "water"},
        "geometry": {"type": "Polygon", "coordinates": [ring_coords]},
    }


def river_centre_lon(lat: float) -> float:
    lat_span = DEG_LAT_PER_KM * CELL_KM * GRID
    lat_min = CENTER_LAT - lat_span / 2 - 0.004
    lat_max = CENTER_LAT + lat_span / 2 + 0.004
    t = (lat - lat_min) / (lat_max - lat_min)
    return (
        CENTER_LON
        + 0.0068
        + 0.0165 * (t - 0.5)
        + 0.0052 * math.sin(2 * math.pi * (t * 1.15 + 0.18))
    )


def in_river(lon: float, lat: float, pad: float = 0.0009) -> bool:
    return abs(lon - river_centre_lon(lat)) < (0.0018 + pad)


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

def lot_boxes() -> list[tuple[float, float, float, float]]:
    """The 16 lots of one zone in normalised [0,1] coords (4 blocks × 2×2)."""
    lo, hi = BLOCK_MARGIN, 1.0 - BLOCK_MARGIN
    blocks = [
        (lo, STREET_LO, lo, STREET_LO),
        (STREET_HI, hi, lo, STREET_LO),
        (lo, STREET_LO, STREET_HI, hi),
        (STREET_HI, hi, STREET_HI, hi),
    ]
    lots: list[tuple[float, float, float, float]] = []
    for x0, x1, y0, y1 in blocks:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        gap = 0.012  # alley between the four lots of a block
        lots.extend(
            [
                (x0, mx - gap, y0, my - gap),
                (mx + gap, x1, y0, my - gap),
                (x0, mx - gap, my + gap, y1),
                (mx + gap, x1, my + gap, y1),
            ]
        )
    return lots


def building_kind(category: str, height: float) -> str:
    if category == "industrial":
        return "industrial"
    if height >= 90:
        return "tower"
    if height >= 45:
        return "office"
    if category in ("cbd", "inner"):
        return "mixed"
    return "residential"


def build_buildings(zones: list[dict], rng: random.Random) -> list[dict]:
    features: list[dict] = []
    lots = lot_boxes()
    counter = 0
    landmark_done = False

    # Centre zone gets the landmark tower.
    mid = (GRID - 1) // 2
    centre_zone_id = f"Z{mid * GRID + mid:03d}"

    for z in zones:
        p = z["properties"]
        row, col = p["row"], p["col"]
        category = p["category"]
        is_cbd = bool(p["is_cbd"])
        lon0, lat0, dlon, dlat = zone_origin(row, col)
        r = ring(row, col)

        for li, (u0, u1, v0, v1) in enumerate(lots):
            # Random setback inside the lot — this is what makes the block read
            # as individual buildings rather than one extruded slab.
            su = (u1 - u0) * rng.uniform(0.06, 0.20)
            sv = (v1 - v0) * rng.uniform(0.06, 0.20)
            a0 = lon0 + (u0 + su) * dlon
            a1 = lon0 + (u1 - su) * dlon
            b0 = lat0 + (v0 + sv) * dlat
            b1 = lat0 + (v1 - sv) * dlat
            clon, clat = (a0 + a1) / 2, (b0 + b1) / 2

            if in_river(clon, clat):
                continue  # the river wins

            dist = km_from_centre(clon, clat)
            is_park = rng.random() < PARK_PROB[category]

            if is_park:
                features.append(
                    {
                        "type": "Feature",
                        "id": f"B{counter:04d}",
                        "properties": {
                            "z": p["zone_id"],
                            "k": "park",
                            "h": 0.0,
                            "dh": 0.0,
                            "td": 0.0,
                            "t0": 0.0,
                            "g": 0,
                            "cbd": 1 if is_cbd else 0,
                            "d": round(dist, 3),
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [rect(a0, b0, a1, b1)],
                        },
                    }
                )
                counter += 1
                continue

            # --- height today -------------------------------------------------
            dome = FABRIC_HEIGHT_M + (PEAK_HEIGHT_M - FABRIC_HEIGHT_M) * math.exp(
                -((dist / DECAY_KM) ** DECAY_POWER)
            )
            h = dome * CATEGORY_HEIGHT_FACTOR[category] * rng.uniform(0.55, 1.45)
            h = max(MIN_BUILDING_M, h)

            # A share of central lots are surface parking, service yards and
            # single-storey retail sheds rather than towers. They break up the
            # skyline, and they are exactly the kerbside space that
            # pedestrianisation converts into public realm.
            low_rise_prob = 0.40 if is_cbd else (0.24 if r == 2 else 0.0)
            is_low_rise = rng.random() < low_rise_prob
            if is_low_rise:
                h = rng.uniform(5.0, 13.5)

            if (
                not landmark_done
                and p["zone_id"] == centre_zone_id
                and li == 0
            ):
                h = LANDMARK_HEIGHT_M
                landmark_done = True

            # --- the 10-year pipeline ----------------------------------------
            # A minority of lots are the development pipeline: either an
            # existing building that gets replaced/extended, or an empty lot
            # that gets built on part-way through the horizon.
            t0 = 0.0
            dh = 0.0
            td = 0.0

            new_build = rng.random() < (0.10 if r <= 2 else 0.06)
            if new_build:
                t0 = round(rng.uniform(1.0, 8.5), 2)
                h = max(MIN_BUILDING_M, h * rng.uniform(1.05, 1.9))
            elif rng.random() < 0.16:
                # Existing building densifies over the horizon.
                dh = h * rng.uniform(0.15, 0.75)

            # Transit-oriented development potential: strongest near the core
            # and along the cordon, where better transit unlocks height.
            tod_pot = math.exp(-((dist / 2.1) ** 2))
            if rng.random() < 0.34:
                td = (h + dh) * 0.55 * tod_pot * rng.uniform(0.4, 1.3)

            # --- greening candidate ------------------------------------------
            # The low-rise central lots are what pedestrianisation converts into
            # plazas and pocket parks. Nothing tall is ever demolished for it.
            greenable = 1 if (is_low_rise and rng.random() < 0.9) else 0
            if greenable:
                # A lot earmarked for public realm is not also a growth site.
                dh = td = 0.0

            kind = "lowrise" if is_low_rise else building_kind(category, h)
            features.append(
                {
                    "type": "Feature",
                    "id": f"B{counter:04d}",
                    "properties": {
                        "z": p["zone_id"],
                        "k": kind,
                        "h": round(h, 1),
                        "dh": round(dh, 1),
                        "td": round(td, 1),
                        "t0": t0,
                        "g": greenable,
                        "cbd": 1 if is_cbd else 0,
                        "d": round(dist, 3),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [rect(a0, b0, a1, b1)],
                    },
                }
            )
            counter += 1

            # Tower-on-podium: a wider, low base under the tallest towers.
            # Purely visual, and it is what makes the skyline read as a city.
            if h >= 85:
                pu = (u1 - u0) * 0.02
                pv = (v1 - v0) * 0.02
                features.append(
                    {
                        "type": "Feature",
                        "id": f"B{counter:04d}",
                        "properties": {
                            "z": p["zone_id"],
                            "k": "podium",
                            "h": round(rng.uniform(11.0, 21.0), 1),
                            "dh": 0.0,
                            "td": 0.0,
                            "t0": t0,
                            "g": 0,
                            "cbd": 1 if is_cbd else 0,
                            "d": round(dist, 3),
                        },
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                rect(
                                    lon0 + (u0 + pu) * dlon,
                                    lat0 + (v0 + pv) * dlat,
                                    lon0 + (u1 - pu) * dlon,
                                    lat0 + (v1 - pv) * dlat,
                                )
                            ],
                        },
                    }
                )
                counter += 1

    return features


# ---------------------------------------------------------------------------
# Data lineage
# ---------------------------------------------------------------------------

def sources_doc(counts: dict) -> dict:
    return {
        "title": "GOV SIM — data lineage",
        "note": (
            "GOV SIM is anchored on Auckland, New Zealand — real coordinates, real "
            "basemap geography. The zone system, building footprints and trip "
            "matrix on top of it are modelled, not measured, and contain no real "
            "administrative record. The entries below are the real datasets this "
            "model is shaped like, plus the corpus the traffic model is actually "
            "fitted on."
        ),
        "sources": [
            {
                "id": "3dcitydb-web-map",
                "role": "3D city geometry",
                "name": "3DCityDB Web Map Client",
                "publisher": "3D City Database project (TU Munich / virtualcitysystems)",
                "url": "https://github.com/3dcitydb/3dcitydb-web-map",
                "docs": "https://www.3dcitydb.org/3dcitydb/documentation/",
                "license": "Apache-2.0",
                "formats": [
                    "CityGML",
                    "Cesium 3D Tiles",
                    "COLLADA/KML/glTF",
                    "CZML",
                    "GeoJSON",
                    "I3S",
                ],
                "how_used": (
                    "The building layer follows the same semantic model a "
                    "3DCityDB export uses at LOD1: one footprint polygon per "
                    "building with a measured height attribute, grouped by zone. "
                    "Swapping in a real city means replacing buildings.geojson "
                    "with a CityGML/3D-Tiles export from a 3DCityDB instance — "
                    "the scene reads footprint + height and nothing else."
                ),
            },
            {
                "id": "uk-census-wu03ew",
                "role": "origin-destination travel demand",
                "name": "2011 Census origin-destination flows, table WU03EW",
                "full_name": (
                    "Location of usual residence and place of work by method of "
                    "travel to work (WU03EW)"
                ),
                "publisher": "Office for National Statistics (UK)",
                "country": "United Kingdom",
                "url": "https://www.nomisweb.co.uk/census/2011/wu03ew",
                "license": "Open Government Licence v3.0",
                "how_used": (
                    "The shape of the demand model: home-zone → work-zone daily "
                    "commuter flows split by mode (car, public transport, walk). "
                    "od_pairs.json is a destination-constrained gravity "
                    "model fitted to the same schema, so a real WU03EW extract "
                    "drops straight into the same pipeline."
                ),
            },
            {
                "id": "metr-la",
                "role": "traffic speed model — training corpus",
                "name": "METR-LA",
                "full_name": (
                    "Loop-detector speeds, Los Angeles County freeway network"
                ),
                "publisher": "Jagadeesh et al. / DCRNN benchmark, via Hugging Face",
                "country": "United States",
                "url": "https://huggingface.co/datasets/witgaw/METR-LA",
                "license": "Research use, per dataset card",
                "formats": ["Parquet", "CSV sensor graph"],
                "how_used": (
                    "This one is not a shape — it is the corpus the traffic "
                    "model is actually fitted on. 207 loop detectors at "
                    "5-minute resolution, 1 Mar – 30 Jun 2012, with real sensor "
                    "coordinates. GOV SIM trains nine classical regressors and "
                    "an LSTM on it to predict link speed from a 12-step history, "
                    "then transfers that speed-response relationship onto the "
                    "Auckland network. Reported R² and MAE are measured on the "
                    "held-out METR-LA test split, not asserted."
                ),
            },
        ],
        "model": {
            "name": "Cordon demand-response model",
            "class": "reduced-form mechanistic (deterministic, no LLM)",
            "inputs": [
                "od_pairs.json — daily person-trips per origin→destination pair",
                "zones.geojson — population, jobs, land use",
                "roads.geojson — capacity, free-flow speed, cordon-crossing flag",
                "buildings.geojson — footprints, heights, 10-year pipeline",
            ],
            "mechanism": (
                "Trips crossing the cordon respond to the generalised cost of the "
                "charge with a constant-elasticity demand curve; suppressed car "
                "trips are reallocated to transit, walking and rerouting in fixed "
                "proportions, subject to transit capacity. Effects ramp in over "
                "roughly two years (behavioural adjustment), then land-use "
                "responds: transit-oriented development near the core, and "
                "pedestrianised kerbside converting to public realm."
            ),
            "counts": counts,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "city",
        help="output directory (default: data/city)",
    )
    ap.add_argument(
        "--mirror",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "frontend" / "public" / "city",
        help="also write a copy here so the frontend can serve it statically",
    )
    args = ap.parse_args()

    out: Path = args.out
    zones_path = out / "zones.geojson"
    if not zones_path.exists():
        raise SystemExit(
            f"{zones_path} not found — run `python data/generate_city.py` first."
        )
    zones = json.loads(zones_path.read_text())["features"]

    rng = random.Random(args.seed)
    buildings = build_buildings(zones, rng)
    water = river_polygon()

    built = [f for f in buildings if f["properties"]["k"] != "park"]
    tallest = max((f["properties"]["h"] for f in built), default=0.0)
    counts = {
        "buildings": len(built),
        "parks": len(buildings) - len(built),
        "pipeline_buildings": sum(1 for f in built if f["properties"]["t0"] > 0),
        "greenable_lots": sum(1 for f in built if f["properties"]["g"] == 1),
        "tallest_m": tallest,
    }

    buildings_fc = {
        "type": "FeatureCollection",
        "name": "auckland_buildings",
        "provenance": "Synthetic",
        "generated_by": "data/generate_buildings.py",
        "seed": args.seed,
        "schema": {
            "z": "zone id",
            "k": (
                "kind (tower|office|podium|mixed|residential|industrial"
                "|lowrise|park)"
            ),
            "h": "height in metres at t=0",
            "dh": "metres added by year 10 under the do-nothing baseline",
            "td": "extra metres by year 10 under transit investment (TOD)",
            "t0": "year the building appears (0 = already standing)",
            "g": "1 = lot can become public realm under pedestrianisation",
            "cbd": "1 = inside the charge cordon",
            "d": "km from city centre",
        },
        "features": buildings,
    }
    water_fc = {
        "type": "FeatureCollection",
        "name": "auckland_water",
        "provenance": "Synthetic",
        "features": [water],
    }
    sources = sources_doc(counts)

    targets = [out] + ([args.mirror] if args.mirror else [])
    for d in targets:
        d.mkdir(parents=True, exist_ok=True)
        (d / "buildings.geojson").write_text(
            json.dumps(buildings_fc, separators=(",", ":"))
        )
        (d / "water.geojson").write_text(json.dumps(water_fc, separators=(",", ":")))
        (d / "sources.json").write_text(json.dumps(sources, indent=2))

    size_kb = (out / "buildings.geojson").stat().st_size / 1024
    print(
        f"{CITY_NAME}: {counts['buildings']} buildings "
        f"({counts['pipeline_buildings']} in the 10-year pipeline), "
        f"{counts['parks']} parks, {counts['greenable_lots']} greenable lots, "
        f"tallest {tallest:.0f} m — {size_kb:.0f} KB"
    )
    for d in targets:
        print(f"  wrote {d}/buildings.geojson, water.geojson, sources.json")


if __name__ == "__main__":
    main()

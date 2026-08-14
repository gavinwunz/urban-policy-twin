#!/usr/bin/env python3
"""Compact the raw OpenStreetMap extract into something a browser can load.

`fetch_osm_auckland.py` writes 11 MB of faithful OSM geometry. That is the right
thing to keep on disk and the wrong thing to send over the wire on page load, so
this step trims it without changing what it *is*:

  * coordinates rounded to 5 decimal places (~1.1 m — finer than the survey
    accuracy of most of the source data, so nothing visible is lost)
  * buildings below a floor area threshold dropped (garden sheds and garages,
    which read as noise at city zoom and trebled the file)
  * null and redundant properties stripped
  * road links below a length threshold dropped, except named ones

Nothing is invented and nothing is reclassified. The output is a subset of the
input at lower precision, and `osm_manifest.json` records both counts so the
reduction is visible rather than silent.

Usage::

    python data/prepare_frontend_city.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "city"
FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend" / "public" / "city"

COORD_DP = 5
MIN_BUILDING_AREA_M2 = 55
MIN_ROAD_LENGTH_KM = 0.02

# Building extent. 16.9k extruded polygons animating alongside the traffic layer
# drops the frame rate on modest hardware, and most of the count is low-rise
# suburbia at the edge of the extract that is never legible at city zoom. Keep
# everything within the central 2 km, plus every building of 25 m or more
# anywhere in the extract — so the skyline is complete and the fringe is not.
BUILDING_CORE_RADIUS_KM = 2.0
BUILDING_TALL_M = 25.0


def round_ring(ring: list, dp: int = COORD_DP) -> list:
    out = []
    prev = None
    for x, y in ring:
        p = [round(x, dp), round(y, dp)]
        # Rounding can collapse neighbouring vertices onto each other.
        if p != prev:
            out.append(p)
            prev = p
    return out


def compact_buildings() -> dict:
    src = json.loads((DATA_DIR / "osm_buildings.geojson").read_text())
    kept = []
    for f in src["features"]:
        p = f["properties"]
        if p["area_m2"] < MIN_BUILDING_AREA_M2:
            continue
        if p["d"] >= BUILDING_CORE_RADIUS_KM and p["h"] < BUILDING_TALL_M:
            continue
        ring = round_ring(f["geometry"]["coordinates"][0])
        if len(ring) < 4:
            continue
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        props = {"h": p["h"], "hsrc": p["hsrc"], "b": p["b"], "d": p["d"]}
        if p.get("name"):
            props["name"] = p["name"]
        kept.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Polygon", "coordinates": [ring]},
        })

    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_buildings",
        "provenance": "Observed",
        "source": src["source"],
        "license": src["license"],
        "height_note": src["height_note"],
        "source_feature_count": len(src["features"]),
        "kept_feature_count": len(kept),
        "min_area_m2": MIN_BUILDING_AREA_M2,
        "extent_note": (
            f"Kept: everything within {BUILDING_CORE_RADIUS_KM} km of the centre, "
            f"plus every building of {BUILDING_TALL_M:.0f} m or more anywhere in "
            "the extract. Dropped: low-rise beyond that radius, for frame rate."
        ),
        "features": kept,
    }


def compact_roads() -> dict:
    src = json.loads((DATA_DIR / "osm_roads.geojson").read_text())
    kept = []
    for f in src["features"]:
        p = f["properties"]
        if p["length_km"] < MIN_ROAD_LENGTH_KM and not p.get("name"):
            continue
        coords = round_ring(f["geometry"]["coordinates"])
        if len(coords) < 2:
            continue
        props = {
            "c": p["road_class"],
            "l": p["lanes"],
            "s": p["free_flow_speed_kmh"],
            "km": p["length_km"],
            "d": p["km_from_centre"],
        }
        if p.get("name"):
            props["name"] = p["name"]
        if p.get("oneway"):
            props["ow"] = 1
        kept.append({
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_roads",
        "provenance": "Observed",
        "source": src["source"],
        "license": src["license"],
        "source_feature_count": len(src["features"]),
        "kept_feature_count": len(kept),
        "features": kept,
    }


def compact_simple(filename: str, min_area: int = 0) -> dict:
    src = json.loads((DATA_DIR / filename).read_text())
    kept = []
    for f in src["features"]:
        g = f["geometry"]
        p = f["properties"]
        if min_area and p.get("area_m2", 0) < min_area:
            continue
        if g["type"] == "Polygon":
            ring = round_ring(g["coordinates"][0])
            if len(ring) < 4:
                continue
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            geom = {"type": "Polygon", "coordinates": [ring]}
        else:
            coords = round_ring(g["coordinates"])
            if len(coords) < 2:
                continue
            geom = {"type": "LineString", "coordinates": coords}
        props = {k: v for k, v in p.items() if v is not None and k != "area_m2"}
        kept.append({"type": "Feature", "properties": props, "geometry": geom})

    return {
        "type": "FeatureCollection",
        "name": src["name"],
        "provenance": "Observed",
        "source": src["source"],
        "license": src["license"],
        "source_feature_count": len(src["features"]),
        "kept_feature_count": len(kept),
        "features": kept,
    }


def main() -> int:
    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

    outputs = {
        "osm_buildings.geojson": compact_buildings(),
        "osm_roads.geojson": compact_roads(),
        "osm_landuse.geojson": compact_simple("osm_landuse.geojson", min_area=600),
        "osm_water.geojson": compact_simple("osm_water.geojson"),
    }

    print("Compacting OpenStreetMap extract for the browser\n")
    total_before = 0
    total_after = 0
    for name, fc in outputs.items():
        before = (DATA_DIR / name).stat().st_size
        path = FRONTEND_DIR / name
        path.write_text(json.dumps(fc, separators=(",", ":")))
        after = path.stat().st_size
        total_before += before
        total_after += after
        print(
            f"  {name:<26} {fc['source_feature_count']:>6} → "
            f"{fc['kept_feature_count']:>6} features   "
            f"{before / 1e6:>5.2f} → {after / 1e6:>5.2f} MB"
        )

    # The manifest travels with the data so the UI can state the provenance.
    manifest = json.loads((DATA_DIR / "osm_manifest.json").read_text())
    manifest["frontend"] = {
        "coord_decimal_places": COORD_DP,
        "min_building_area_m2": MIN_BUILDING_AREA_M2,
        "counts": {n.replace("osm_", "").replace(".geojson", ""): fc["kept_feature_count"]
                   for n, fc in outputs.items()},
        "bytes": {n: (FRONTEND_DIR / n).stat().st_size for n in outputs},
        "reduction_note": (
            "A precision-reduced subset of the full extract, for load time. "
            "Nothing is reclassified or invented; both counts are recorded."
        ),
    }
    (FRONTEND_DIR / "osm_manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"\n  total {total_before / 1e6:.2f} → {total_after / 1e6:.2f} MB "
          f"({100 * (1 - total_after / total_before):.0f}% smaller)")
    print(f"  {FRONTEND_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

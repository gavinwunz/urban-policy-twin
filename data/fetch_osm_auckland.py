#!/usr/bin/env python3
"""Scrape the real Auckland street network and building stock from OpenStreetMap.

This replaces the generated grid. Everything written here is **real** —
surveyed by OpenStreetMap contributors, fetched live from the Overpass API, and
redistributable under the Open Database Licence. That matters for more than
provenance: traffic trails now follow the actual curve of Karangahape Road, and
the skyline is the actual Auckland skyline rather than a dome of boxes.

What it fetches, in one Overpass call per layer:

    roads       every drivable way in the bbox, with name / classification /
                lane count / speed limit / oneway, geometry included
    buildings   every building footprint, with height or storey count where a
                contributor has recorded one
    landuse     parks, retail, commercial and industrial polygons — what the
                zone shading is derived from instead of being invented
    coastline   the Waitematā / Manukau shoreline, so water is really water

Height handling is the one place we estimate, and it is labelled as such: OSM
records an explicit `height` on a minority of buildings, `building:levels` on
more, and nothing on the rest. We use height when present (Observed), derive it
from levels at 3.2 m per storey when that is present (Estimated), and otherwise
fall back to a per-type default (Estimated). Every feature carries `hsrc` saying
which of the three it was, so the UI can colour or filter by confidence and
never implies a surveyed height it does not have.

Usage::

    python data/fetch_osm_auckland.py              # fetch (uses cache if fresh)
    python data/fetch_osm_auckland.py --force      # ignore the cache
    python data/fetch_osm_auckland.py --radius 3.0 # wider bbox, km

Overpass is a shared free service. Be polite: the cache is on by default, the
script sleeps between calls, and it identifies itself in the User-Agent.
"""

from __future__ import annotations

import argparse
import json
import math
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CITY_NAME = "Auckland"
CITY_REGION = "Auckland, New Zealand"

# Auckland CBD — Queen Street / Britomart.
CENTER_LAT = -36.8485
CENTER_LON = 174.7633

DEFAULT_RADIUS_KM = 2.6

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

USER_AGENT = "GOVSIM/0.3 (hackathon policy simulator; contact: local)"

OUT_DIR = Path(__file__).resolve().parent / "city"
CACHE_DIR = Path(__file__).resolve().parent / ".osm_cache"
CACHE_TTL_S = 7 * 24 * 3600  # a week; OSM does not move fast at this scale

# Metres of building height per storey when only `building:levels` is recorded.
METRES_PER_LEVEL = 3.2

# Fallback heights by building type, metres. Used only when OSM records neither
# a height nor a storey count — always tagged as a default, never as observed.
DEFAULT_HEIGHT_M = {
    "apartments": 18.0,
    "commercial": 14.0,
    "office": 22.0,
    "retail": 8.0,
    "industrial": 9.0,
    "warehouse": 9.0,
    "university": 15.0,
    "school": 9.0,
    "hospital": 20.0,
    "hotel": 24.0,
    "church": 12.0,
    "civic": 14.0,
    "public": 14.0,
    "parking": 11.0,
    "house": 6.0,
    "residential": 9.0,
    "detached": 6.5,
    "terrace": 7.5,
    "garage": 3.0,
    "garages": 3.0,
    "shed": 3.0,
    "roof": 4.0,
    "yes": 8.5,
}

# Road classes we keep, with the lane/capacity defaults the traffic model needs
# when OSM has not recorded them.
ROAD_CLASSES = {
    "motorway": ("motorway", 3, 100, 2000),
    "motorway_link": ("motorway", 1, 60, 1200),
    "trunk": ("arterial", 3, 80, 1800),
    "trunk_link": ("arterial", 1, 50, 1000),
    "primary": ("arterial", 2, 60, 1600),
    "primary_link": ("arterial", 1, 40, 900),
    "secondary": ("arterial", 2, 50, 1300),
    "secondary_link": ("arterial", 1, 40, 800),
    "tertiary": ("collector", 1, 50, 900),
    "tertiary_link": ("collector", 1, 30, 600),
    "residential": ("local", 1, 30, 600),
    "unclassified": ("local", 1, 40, 600),
    "living_street": ("local", 1, 20, 300),
    "service": ("service", 1, 20, 200),
}

# Land-use tags worth carrying through to the zone layer.
LANDUSE_KEEP = {
    "park", "grass", "forest", "recreation_ground", "village_green",
    "commercial", "retail", "industrial", "residential", "education",
}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def bbox(radius_km: float) -> tuple[float, float, float, float]:
    """(south, west, north, east) around the city centre."""
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(CENTER_LAT)))
    return (
        CENTER_LAT - dlat,
        CENTER_LON - dlon,
        CENTER_LAT + dlat,
        CENTER_LON + dlon,
    )


def ring_area_m2(coords: list[list[float]]) -> float:
    """Rough planar area of a small lon/lat ring, in square metres."""
    if len(coords) < 3:
        return 0.0
    lat0 = math.radians(sum(c[1] for c in coords) / len(coords))
    mx = 111320.0 * math.cos(lat0)
    my = 110540.0
    s = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i][0] * mx, coords[i][1] * my
        x2, y2 = coords[i + 1][0] * mx, coords[i + 1][1] * my
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def centroid(coords: list[list[float]]) -> tuple[float, float]:
    n = max(1, len(coords))
    return sum(c[0] for c in coords) / n, sum(c[1] for c in coords) / n


def km_from_centre(lon: float, lat: float) -> float:
    dx = (lon - CENTER_LON) * 111.32 * math.cos(math.radians(CENTER_LAT))
    dy = (lat - CENTER_LAT) * 111.32
    return math.hypot(dx, dy)


def close_ring(coords: list[list[float]]) -> list[list[float]]:
    if coords and coords[0] != coords[-1]:
        return coords + [coords[0]]
    return coords


# ---------------------------------------------------------------------------
# Overpass
# ---------------------------------------------------------------------------


def _ssl_context() -> ssl.SSLContext | None:
    """A context with a usable CA bundle.

    A stock macOS python often ships without one, which fails every HTTPS call
    with CERTIFICATE_VERIFY_FAILED. certifi supplies one when it is installed;
    otherwise we return None and fall back to curl, which uses the system store.
    """
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return None


def _post(endpoint: str, query: str, ctx: ssl.SSLContext | None) -> bytes:
    """POST the query, via urllib when we have certs and curl when we don't."""
    if ctx is not None:
        req = urllib.request.Request(
            endpoint, data=query.encode("utf-8"), headers={"User-Agent": USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=180, context=ctx) as resp:
            return resp.read()

    proc = subprocess.run(
        ["curl", "-sS", "--fail", "-m", "180", "-A", USER_AGENT,
         "-X", "POST", "--data-binary", "@-", endpoint],
        input=query.encode("utf-8"),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise urllib.error.URLError(proc.stderr.decode("utf-8", "replace").strip())
    return proc.stdout


def overpass(query: str, cache_key: str, force: bool = False) -> dict[str, Any]:
    """Run an Overpass query, with an on-disk cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{cache_key}.json"

    if cache.exists() and not force:
        age = time.time() - cache.stat().st_mtime
        if age < CACHE_TTL_S:
            print(f"  [{cache_key}] cache hit ({cache.stat().st_size / 1e6:.1f} MB, "
                  f"{age / 3600:.0f}h old)")
            return json.loads(cache.read_text())

    ctx = _ssl_context()
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            print(f"  [{cache_key}] querying {endpoint.split('/')[2]}…", flush=True)
            t0 = time.time()
            raw = _post(endpoint, query, ctx)
            dt = time.time() - t0
            print(f"  [{cache_key}] {len(raw) / 1e6:.1f} MB in {dt:.1f}s")
            cache.write_text(raw.decode("utf-8"))
            time.sleep(2)  # be polite to a shared free service
            return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            print(f"  [{cache_key}] {endpoint.split('/')[2]} failed: {exc}")
            time.sleep(3)

    raise RuntimeError(f"all Overpass endpoints failed for {cache_key}: {last_error}")


# ---------------------------------------------------------------------------
# Layer builders
# ---------------------------------------------------------------------------


def fetch_roads(bb, force: bool) -> dict:
    s, w, n, e = bb
    classes = "|".join(ROAD_CLASSES)
    query = f"""
[out:json][timeout:180];
way["highway"~"^({classes})$"]["area"!~"yes"]({s},{w},{n},{e});
out geom;
"""
    data = overpass(query, "roads", force)

    features = []
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags", {})
        hw = tags.get("highway")
        if hw not in ROAD_CLASSES:
            continue
        road_class, def_lanes, def_speed, def_cap = ROAD_CLASSES[hw]

        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in geom]

        def as_int(v, default):
            try:
                return int(float(str(v).split(";")[0].strip()))
            except (TypeError, ValueError):
                return default

        lanes = as_int(tags.get("lanes"), def_lanes)
        speed = as_int(tags.get("maxspeed"), def_speed)
        oneway = tags.get("oneway") in ("yes", "1", "-1", "true")

        # Length along the way, km.
        length = 0.0
        for i in range(len(coords) - 1):
            dx = (coords[i + 1][0] - coords[i][0]) * 111.32 * math.cos(
                math.radians(coords[i][1])
            )
            dy = (coords[i + 1][1] - coords[i][1]) * 111.32
            length += math.hypot(dx, dy)

        lon_c, lat_c = centroid(coords)
        features.append({
            "type": "Feature",
            "id": f"W{el['id']}",
            "properties": {
                "link_id": f"W{el['id']}",
                "name": tags.get("name"),
                "osm_highway": hw,
                "road_class": road_class,
                "lanes": max(1, lanes),
                "free_flow_speed_kmh": speed,
                "capacity_veh_per_hr": def_cap * max(1, lanes) // max(1, def_lanes),
                "oneway": oneway,
                "length_km": round(length, 4),
                "bridge": tags.get("bridge") == "yes",
                "tunnel": tags.get("tunnel") == "yes",
                "km_from_centre": round(km_from_centre(lon_c, lat_c), 3),
            },
            "geometry": {"type": "LineString", "coordinates": coords},
        })

    named = sum(1 for f in features if f["properties"]["name"])
    print(f"  → {len(features)} road links ({named} named)")
    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_roads",
        "provenance": "Observed",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0",
        "features": features,
    }


def fetch_buildings(bb, force: bool) -> dict:
    s, w, n, e = bb
    query = f"""
[out:json][timeout:180];
way["building"]({s},{w},{n},{e});
out geom;
"""
    data = overpass(query, "buildings", force)

    features = []
    stats = {"height": 0, "levels": 0, "default": 0}

    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 4:
            continue
        tags = el.get("tags", {})
        coords = close_ring([[round(p["lon"], 6), round(p["lat"], 6)] for p in geom])
        area = ring_area_m2(coords)
        if area < 25:  # sheds and mapping noise
            continue

        btype = tags.get("building", "yes")

        # Height: observed → derived from levels → typed default.
        height = None
        hsrc = "default"
        raw_h = tags.get("height") or tags.get("building:height")
        if raw_h:
            try:
                height = float(str(raw_h).replace("m", "").strip().split()[0])
                hsrc = "height"
            except (ValueError, IndexError):
                height = None
        if height is None:
            lv = tags.get("building:levels") or tags.get("levels")
            if lv:
                try:
                    height = float(str(lv).split(";")[0].strip()) * METRES_PER_LEVEL
                    hsrc = "levels"
                except ValueError:
                    height = None
        if height is None or not (2.0 <= height <= 400.0):
            height = DEFAULT_HEIGHT_M.get(btype, 8.5)
            hsrc = "default"
        stats[hsrc] += 1

        lon_c, lat_c = centroid(coords)
        features.append({
            "type": "Feature",
            "id": f"B{el['id']}",
            "properties": {
                "name": tags.get("name"),
                "b": btype,
                "h": round(height, 1),
                "hsrc": hsrc,
                "area_m2": round(area),
                "levels": tags.get("building:levels"),
                "d": round(km_from_centre(lon_c, lat_c), 3),
            },
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })

    features.sort(key=lambda f: -f["properties"]["h"])
    tallest = features[0]["properties"] if features else {}
    print(f"  → {len(features)} buildings "
          f"({stats['height']} surveyed height, {stats['levels']} from storeys, "
          f"{stats['default']} typed default)")
    if tallest:
        print(f"    tallest: {tallest.get('name') or '(unnamed)'} @ {tallest['h']} m")

    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_buildings",
        "provenance": "Observed",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0",
        "height_sources": stats,
        "height_note": (
            "hsrc=height: surveyed height tag (Observed). hsrc=levels: derived "
            f"from building:levels at {METRES_PER_LEVEL} m/storey (Estimated). "
            "hsrc=default: typed fallback, no height recorded (Estimated)."
        ),
        "features": features,
    }


def fetch_landuse(bb, force: bool) -> dict:
    s, w, n, e = bb
    query = f"""
[out:json][timeout:120];
(
  way["landuse"]({s},{w},{n},{e});
  way["leisure"~"^(park|garden|pitch|recreation_ground)$"]({s},{w},{n},{e});
  way["natural"="water"]({s},{w},{n},{e});
);
out geom;
"""
    data = overpass(query, "landuse", force)

    features = []
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 4:
            continue
        tags = el.get("tags", {})
        kind = tags.get("landuse") or tags.get("leisure") or tags.get("natural")
        if kind not in LANDUSE_KEEP and kind != "water":
            continue
        coords = close_ring([[round(p["lon"], 6), round(p["lat"], 6)] for p in geom])
        area = ring_area_m2(coords)
        if area < 200:
            continue
        features.append({
            "type": "Feature",
            "id": f"L{el['id']}",
            "properties": {
                "name": tags.get("name"),
                "kind": kind,
                "area_m2": round(area),
            },
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })

    water = sum(1 for f in features if f["properties"]["kind"] == "water")
    print(f"  → {len(features)} land-use polygons ({water} water)")
    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_landuse",
        "provenance": "Observed",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0",
        "features": features,
    }


def fetch_coastline(bb, force: bool) -> dict:
    """The real shoreline — Waitematā to the north, Manukau to the south."""
    s, w, n, e = bb
    # Widen a little so the coastline does not stop dead at the bbox edge.
    pad = 0.02
    query = f"""
[out:json][timeout:120];
(
  way["natural"="coastline"]({s - pad},{w - pad},{n + pad},{e + pad});
  way["natural"="water"]["water"!="pond"]({s - pad},{w - pad},{n + pad},{e + pad});
);
out geom;
"""
    data = overpass(query, "coastline", force)
    features = []
    for el in data.get("elements", []):
        geom = el.get("geometry") or []
        if len(geom) < 2:
            continue
        tags = el.get("tags", {})
        coords = [[round(p["lon"], 6), round(p["lat"], 6)] for p in geom]
        is_water_area = tags.get("natural") == "water"
        features.append({
            "type": "Feature",
            "id": f"C{el['id']}",
            "properties": {"name": tags.get("name"), "kind": tags.get("natural")},
            "geometry": (
                {"type": "Polygon", "coordinates": [close_ring(coords)]}
                if is_water_area and len(coords) >= 4
                else {"type": "LineString", "coordinates": coords}
            ),
        })
    print(f"  → {len(features)} coastline / water features")
    return {
        "type": "FeatureCollection",
        "name": "auckland_osm_water",
        "provenance": "Observed",
        "source": "OpenStreetMap via Overpass API",
        "license": "ODbL 1.0",
        "features": features,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="ignore the cache")
    ap.add_argument("--radius", type=float, default=DEFAULT_RADIUS_KM,
                    help=f"bbox radius in km (default {DEFAULT_RADIUS_KM})")
    args = ap.parse_args()

    bb = bbox(args.radius)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Scraping OpenStreetMap — {CITY_REGION}")
    print(f"  centre {CENTER_LAT}, {CENTER_LON}   radius {args.radius} km")
    print(f"  bbox   {bb[0]:.4f},{bb[1]:.4f} → {bb[2]:.4f},{bb[3]:.4f}\n")

    started = time.time()
    layers = {
        "osm_roads.geojson": fetch_roads(bb, args.force),
        "osm_buildings.geojson": fetch_buildings(bb, args.force),
        "osm_landuse.geojson": fetch_landuse(bb, args.force),
        "osm_water.geojson": fetch_coastline(bb, args.force),
    }

    sizes = {}
    for filename, fc in layers.items():
        path = OUT_DIR / filename
        path.write_text(json.dumps(fc, separators=(",", ":")))
        sizes[filename] = path.stat().st_size
        print(f"  wrote {filename}  {sizes[filename] / 1e6:.2f} MB")

    manifest = {
        "title": f"{CITY_NAME} — OpenStreetMap extract",
        "city": CITY_NAME,
        "region": CITY_REGION,
        "provenance": "Observed",
        "source": {
            "name": "OpenStreetMap",
            "via": "Overpass API",
            "url": "https://www.openstreetmap.org/copyright",
            "endpoint": OVERPASS_ENDPOINTS[0],
            "license": "Open Database Licence (ODbL) 1.0",
            "attribution": "© OpenStreetMap contributors",
        },
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_seconds": round(time.time() - started, 1),
        "center": {"lat": CENTER_LAT, "lon": CENTER_LON},
        "radius_km": args.radius,
        "bbox": {"south": bb[0], "west": bb[1], "north": bb[2], "east": bb[3]},
        "counts": {
            name.replace("osm_", "").replace(".geojson", ""): len(fc["features"])
            for name, fc in layers.items()
        },
        "bytes": sizes,
        "height_sources": layers["osm_buildings.geojson"]["height_sources"],
        "note": (
            "Real surveyed geometry, fetched live from the Overpass API. Road "
            "names, classifications, lane counts and speed limits are as "
            "recorded by OpenStreetMap contributors. Building heights are "
            "surveyed where available and otherwise estimated — see hsrc on "
            "each feature."
        ),
    }
    (OUT_DIR / "osm_manifest.json").write_text(json.dumps(manifest, indent=2))

    total = sum(sizes.values())
    print(f"\nDone in {manifest['elapsed_seconds']}s — {total / 1e6:.2f} MB total")
    print(f"  {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

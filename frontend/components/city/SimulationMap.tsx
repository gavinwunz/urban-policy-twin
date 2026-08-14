"use client";

/**
 * The operational map: real Auckland, drawn from real OpenStreetMap geometry.
 *
 * Every line on this map is surveyed. The street network is 5,960 real links
 * with their real names, classifications, lane counts and speed limits; the
 * skyline is 14,776 real building footprints; the water is the actual
 * Waitematā shoreline. All of it scraped from the Overpass API by
 * `data/fetch_osm_auckland.py` and licensed ODbL.
 *
 * That matters for the simulation, not just for looks. Traffic trails follow
 * the real curve of Karangahape Road because they are laid on the real
 * polyline, so "where does the queue form" is a question about Auckland rather
 * than about a synthetic grid.
 *
 * Building heights are the one place the data is uneven, and the map says so:
 * OSM records a surveyed height on ~2% of footprints and a storey count on
 * ~7%, so the rest fall back to a typed default. `hsrc` carries which, the
 * legend explains it, and the confidence view colours by it — a skyline that
 * shows you how much of itself is measured.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import DeckGL from "@deck.gl/react";
import { AmbientLight, DirectionalLight, LightingEffect, MapView } from "@deck.gl/core";
import type { Color, PickingInfo } from "@deck.gl/core";
import { PathLayer, PolygonLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
// Aliased: a bare `Map` import shadows the global Map constructor used below.
import BaseMap from "react-map-gl/maplibre";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

import type { OdMatrix } from "../../lib/city";
import type {
  BuildingFeature,
  BuildingProps,
  LanduseProps,
  OsmManifest,
  OsmRoadFeature,
} from "../../lib/osm";
import { loadOsmBuildings } from "../../lib/osm";
import type { CityState, Scenario } from "../../lib/cityModel";
import type { Feature, FeatureCollection, LineString, Polygon } from "geojson";

const BASEMAP_STYLE = {
  version: 8 as const,
  sources: {
    carto: {
      type: "raster" as const,
      tiles: [
        "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [{ id: "carto", type: "raster" as const, source: "carto" }],
};

const LOOP = 1000;
const CORDON: Color = [120, 170, 255];

/** Vertical exaggeration. Stated in the legend so nobody reads it as a survey. */
const HEIGHT_EXAGGERATION = 1.35;

// ---------------------------------------------------------------------------
// Palettes
// ---------------------------------------------------------------------------

function trafficColor(pressure: number): Color {
  const stops: Array<[number, Color]> = [
    [0.45, [58, 167, 104]],
    [0.85, [192, 131, 39]],
    [1.15, [217, 100, 82]],
    [1.45, [185, 59, 94]],
  ];
  const x = Math.max(stops[0][0], Math.min(stops[stops.length - 1][0], pressure));
  for (let i = 1; i < stops.length; i++) {
    const [t1, c1] = stops[i];
    if (x <= t1) {
      const [t0, c0] = stops[i - 1];
      const f = (x - t0) / (t1 - t0 || 1);
      return [
        Math.round(c0[0] + f * (c1[0] - c0[0])),
        Math.round(c0[1] + f * (c1[1] - c0[1])),
        Math.round(c0[2] + f * (c1[2] - c0[2])),
      ];
    }
  }
  return stops[stops.length - 1][1];
}

const rgba = (c: Color, a: number): Color => [c[0], c[1], c[2], a];

function mix(a: Color, b: Color, f: number): Color {
  const t = Math.max(0, Math.min(1, f));
  return [
    Math.round(a[0] + t * (b[0] - a[0])),
    Math.round(a[1] + t * (b[1] - a[1])),
    Math.round(a[2] + t * (b[2] - a[2])),
  ];
}

/** Building colour by height — a cool base warming toward the towers. */
function buildingColor(h: number): Color {
  const t = Math.min(1, h / 120);
  return mix([76, 94, 118], [186, 198, 214], t);
}

/** Building colour by how trustworthy its height is. */
const CONFIDENCE_COLOR: Record<string, Color> = {
  height: [47, 165, 184],
  levels: [140, 122, 200],
  default: [92, 104, 122],
};

const LANDUSE_COLOR: Record<string, Color> = {
  park: [34, 96, 62, 120],
  grass: [34, 96, 62, 90],
  forest: [28, 82, 54, 110],
  recreation_ground: [34, 96, 62, 90],
  village_green: [34, 96, 62, 90],
  pitch: [40, 104, 68, 90],
  garden: [34, 96, 62, 80],
  commercial: [70, 74, 110, 70],
  retail: [104, 70, 96, 70],
  industrial: [86, 78, 62, 70],
  residential: [56, 68, 86, 55],
  education: [64, 86, 112, 70],
  water: [18, 44, 76, 210],
};

const ROAD_WIDTH: Record<string, number> = {
  motorway: 22,
  arterial: 14,
  collector: 9,
  local: 5.5,
  service: 3.5,
};

// ---------------------------------------------------------------------------
// Commute arcs
// ---------------------------------------------------------------------------

const ARC_SEGMENTS = 24;
const ARC_RISE = 0.16;

function arcPath(
  from: [number, number],
  to: [number, number],
): [number, number, number][] {
  const midLat = ((from[1] + to[1]) / 2) * (Math.PI / 180);
  const dx = (to[0] - from[0]) * 111320 * Math.cos(midLat);
  const dy = (to[1] - from[1]) * 110540;
  const apex = Math.hypot(dx, dy) * ARC_RISE;
  const path: [number, number, number][] = [];
  for (let i = 0; i <= ARC_SEGMENTS; i++) {
    const t = i / ARC_SEGMENTS;
    path.push([
      from[0] + (to[0] - from[0]) * t,
      from[1] + (to[1] - from[1]) * t,
      apex * 4 * t * (1 - t),
    ]);
  }
  return path;
}

// ---------------------------------------------------------------------------
// Traffic trails, laid on real street geometry
// ---------------------------------------------------------------------------

interface Trip {
  path: [number, number][];
  timestamps: [number, number];
  color: Color;
}

function jitter(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Turn the real network into animated vehicle trails.
 *
 * Only the classes that carry through-traffic get trails, and the count per
 * link tracks the model's congestion index — so emptying the cordon visibly
 * empties the streets inside it while the motorways keep running.
 */
function buildTrips(
  roads: OsmRoadFeature[],
  state: CityState,
  scenario: Scenario,
  cordonRadiusKm: number,
): Trip[] {
  const trips: Trip[] = [];
  const cordonFactor = Math.max(0.05, state.congestion);
  const cityFactor = 0.85 + 0.15 * state.congestion;

  for (let i = 0; i < roads.length; i++) {
    const r = roads[i];
    const p = r.properties;
    if (p.c === "service" || p.c === "local") continue; // too fine to read
    if (p.km < 0.05) continue;

    const inCordon = p.d < cordonRadiusKm;
    const factor = inCordon ? cordonFactor : cityFactor;
    // Pedestrianisation removes through-traffic from central streets.
    const closed = inCordon && p.c !== "motorway"
      ? 1 - scenario.pedestrianise * 0.85
      : 1;
    const base = p.c === "motorway" ? 3 : p.c === "arterial" ? 2 : 1;
    const n = Math.round(base * factor * closed);
    if (n <= 0) continue;

    const coords = r.geometry.coordinates as [number, number][];
    if (coords.length < 2) continue;

    const pressure = inCordon ? state.congestion : cityFactor;
    const color = trafficColor(pressure);
    const duration = LOOP * 0.16 * (0.55 + 0.75 * Math.min(1.5, pressure));

    for (let k = 0; k < n; k++) {
      const forward = (i + k) % 2 === 0;
      const path = forward ? coords : [...coords].slice().reverse();
      const start = ((k / n + jitter(i * 31 + k)) % 1) * Math.max(1, LOOP - duration);
      trips.push({ path, timestamps: [start, start + duration], color });
    }
  }
  return trips;
}

// ---------------------------------------------------------------------------
// Static deck config
// ---------------------------------------------------------------------------

const MAP_VIEW = new MapView({ repeat: false });
const CONTROLLER = {
  dragRotate: true,
  dragPan: true,
  scrollZoom: false,
  doubleClickZoom: true,
  touchZoom: true,
  keyboard: true,
};

const ambientLight = new AmbientLight({ color: [255, 255, 255], intensity: 1.35 });
const sunLight = new DirectionalLight({
  color: [255, 244, 226],
  intensity: 1.9,
  direction: [-1.1, -2.4, -1.5],
});
const fillLight = new DirectionalLight({
  color: [150, 180, 255],
  intensity: 0.9,
  direction: [1.4, 1.0, -0.9],
});

export type ZoneMetric = "none" | "landuse" | "confidence" | "height";

export interface SimulationMapProps {
  osm: {
    manifest: OsmManifest;
    roads: FeatureCollection<LineString, OsmRoadFeature["properties"]>;
    water: FeatureCollection<Polygon | LineString, { kind: string; name?: string }>;
    landuse: FeatureCollection<Polygon, LanduseProps>;
  };
  od: OdMatrix;
  zoneCentroids: Map<string, [number, number]>;
  cbdCentre: [number, number];
  cordonPolygon: number[][];
  state: CityState;
  scenario: Scenario;
  showFlows: boolean;
  /** Draw the 3D building stock. Loads ~5 MB on first enable. */
  show3D: boolean;
  zoneMetric: ZoneMetric;
  /** Larger, more legible framing for the lower-page instances. */
  variant?: "deck" | "full";
  pitch?: number;
  zoom?: number;
}

export default function SimulationMap({
  osm,
  od,
  zoneCentroids,
  cbdCentre,
  cordonPolygon,
  state,
  scenario,
  showFlows,
  show3D,
  zoneMetric,
  variant = "deck",
  pitch = 48,
  zoom = 13.1,
}: SimulationMapProps) {
  const [time, setTime] = useState(0);
  const raf = useRef<number | null>(null);
  const [buildings, setBuildings] =
    useState<FeatureCollection<Polygon, BuildingProps> | null>(null);
  const [loadingBuildings, setLoadingBuildings] = useState(false);

  // ~30fps: smooth enough for headlight trails, half the React work of 60.
  useEffect(() => {
    let mounted = true;
    let last = 0;
    const step = (now: number) => {
      if (!mounted) return;
      if (now - last > 33) {
        last = now;
        setTime((now / 26) % LOOP);
      }
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      mounted = false;
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    };
  }, []);

  // The building layer is the heaviest file in the app, so it is fetched the
  // first time the 3D view is asked for and then kept.
  useEffect(() => {
    if (!show3D || buildings || loadingBuildings) return;
    const ctrl = new AbortController();
    setLoadingBuildings(true);
    loadOsmBuildings(ctrl.signal)
      .then(setBuildings)
      .catch(() => undefined)
      .finally(() => setLoadingBuildings(false));
    return () => ctrl.abort();
  }, [show3D, buildings, loadingBuildings]);

  const cordonRadiusKm = useMemo(() => {
    // Radius of the charge cordon from its polygon, for the in/out test.
    let max = 0;
    for (const [lon, lat] of cordonPolygon) {
      const dx = (lon - cbdCentre[0]) * 111.32 * Math.cos((cbdCentre[1] * Math.PI) / 180);
      const dy = (lat - cbdCentre[1]) * 111.32;
      max = Math.max(max, Math.hypot(dx, dy));
    }
    return max || 1.2;
  }, [cordonPolygon, cbdCentre]);

  const flows = useMemo(() => {
    const byOrigin = new Map<string, number>();
    for (const p of od.pairs) {
      if (!p.dest_is_cbd) continue;
      byOrigin.set(p.origin, (byOrigin.get(p.origin) ?? 0) + p.daily_person_trips);
    }
    const out: Array<{ path: [number, number, number][]; trips: number }> = [];
    for (const [zone, trips] of byOrigin) {
      const from = zoneCentroids.get(zone);
      if (!from || trips <= 200) continue;
      out.push({ path: arcPath(from, cbdCentre), trips });
    }
    return out;
  }, [od, zoneCentroids, cbdCentre]);

  const roadFeatures = osm.roads.features as unknown as OsmRoadFeature[];

  const trips = useMemo(
    () => buildTrips(roadFeatures, state, scenario, cordonRadiusKm),
    [roadFeatures, state, scenario, cordonRadiusKm],
  );

  const layers = useMemo(() => {
    const shiftToTransit = 1 - state.carShareIntoCbd / 0.62;
    const flowColor = mix([224, 163, 62], [74, 134, 232], shiftToTransit);

    return [
      // --- land use, from real OSM polygons ---------------------------------
      zoneMetric === "landuse" &&
        new PolygonLayer({
          id: "landuse",
          data: osm.landuse.features as Array<Feature<Polygon, LanduseProps>>,
          getPolygon: (f) => f.geometry.coordinates as never,
          getFillColor: (f) =>
            (LANDUSE_COLOR[f.properties.kind] ?? [70, 80, 96, 45]) as Color,
          stroked: false,
          filled: true,
          extruded: false,
          pickable: true,
        }),

      // --- water: the actual shoreline --------------------------------------
      new PolygonLayer({
        id: "water",
        data: osm.water.features.filter(
          (f) => f.geometry.type === "Polygon",
        ) as Array<Feature<Polygon, { kind: string }>>,
        getPolygon: (f) => f.geometry.coordinates as never,
        getFillColor: LANDUSE_COLOR.water,
        stroked: false,
        filled: true,
        extruded: false,
      }),

      // --- the real street network ------------------------------------------
      new PathLayer({
        id: "network",
        data: roadFeatures,
        getPath: (f: OsmRoadFeature) => f.geometry.coordinates as [number, number][],
        getColor: (f: OsmRoadFeature) => {
          const p = f.properties;
          const inCordon = p.d < cordonRadiusKm;
          if (!inCordon) {
            return (p.c === "motorway"
              ? [126, 146, 172, 190]
              : [92, 110, 134, 150]) as Color;
          }
          return rgba(trafficColor(state.congestion), 235);
        },
        getWidth: (f: OsmRoadFeature) => ROAD_WIDTH[f.properties.c] ?? 5,
        widthUnits: "meters",
        widthMinPixels: 0.8,
        capRounded: true,
        jointRounded: true,
        pickable: true,
        updateTriggers: { getColor: [state.congestion, cordonRadiusKm] },
      }),

      // --- 3D building stock -------------------------------------------------
      show3D &&
        buildings &&
        new PolygonLayer({
          id: "buildings",
          data: buildings.features as BuildingFeature[],
          getPolygon: (f: BuildingFeature) => f.geometry.coordinates as never,
          extruded: true,
          filled: true,
          stroked: false,
          wireframe: false,
          pickable: true,
          getElevation: (f: BuildingFeature) => f.properties.h,
          elevationScale: HEIGHT_EXAGGERATION,
          getFillColor: (f: BuildingFeature) =>
            zoneMetric === "confidence"
              ? (CONFIDENCE_COLOR[f.properties.hsrc] ?? CONFIDENCE_COLOR.default)
              : buildingColor(f.properties.h),
          material: {
            ambient: 0.45,
            diffuse: 0.72,
            shininess: 28,
            specularColor: [70, 90, 120],
          },
          updateTriggers: { getFillColor: [zoneMetric] },
        }),

      // --- charge cordon -----------------------------------------------------
      new PolygonLayer({
        id: "cordon",
        data: [{ polygon: cordonPolygon }],
        getPolygon: (d: { polygon: number[][] }) => d.polygon as never,
        stroked: true,
        filled: true,
        extruded: false,
        getFillColor: rgba(CORDON, scenario.charge > 0 ? 22 : 8),
        getLineColor: rgba(CORDON, 235),
        getLineWidth: 26,
        widthUnits: "meters",
        lineWidthMinPixels: 2,
        updateTriggers: { getFillColor: [scenario.charge] },
      }),

      // --- commute arcs ------------------------------------------------------
      showFlows &&
        new PathLayer({
          id: "od-flows",
          data: flows,
          getPath: (d: { path: [number, number, number][] }) => d.path,
          getColor: rgba(flowColor, 105),
          getWidth: (d: { trips: number }) => Math.max(1.1, Math.sqrt(d.trips) / 9),
          widthUnits: "pixels",
          widthMinPixels: 1,
          capRounded: true,
          jointRounded: true,
          updateTriggers: { getColor: [flowColor] },
        }),

      // --- animated traffic --------------------------------------------------
      new TripsLayer({
        id: "traffic",
        data: trips,
        getPath: (d: Trip) => d.path,
        getTimestamps: (d: Trip) => d.timestamps,
        getColor: (d: Trip) => d.color,
        currentTime: time,
        trailLength: 60,
        fadeTrail: true,
        widthMinPixels: 2.2,
        capRounded: true,
        jointRounded: true,
        opacity: 0.95,
      }),
    ].filter(Boolean);
  }, [
    osm, roadFeatures, buildings, show3D, state, scenario, flows, showFlows,
    trips, time, zoneMetric, cordonPolygon, cordonRadiusKm,
  ]);

  const effects = useMemo(() => {
    const e = new LightingEffect({ ambientLight, sunLight, fillLight });
    return [e];
  }, []);

  const counts = osm.manifest.frontend.counts;

  return (
    <div className={`sim-map sim-map-${variant}`}>
      <DeckGL
        views={MAP_VIEW}
        initialViewState={{
          longitude: osm.manifest.center.lon,
          latitude: osm.manifest.center.lat,
          zoom,
          pitch,
          bearing: -18,
          maxPitch: 70,
          minZoom: 10,
          maxZoom: 17,
        }}
        controller={CONTROLLER}
        effects={effects}
        layers={layers as never}
        getTooltip={getTooltip}
        style={{ position: "absolute", inset: "0" }}
      >
        <BaseMap reuseMaps mapLib={maplibregl} mapStyle={BASEMAP_STYLE as never} />
      </DeckGL>

      <div className="map-locale">
        <strong>Auckland</strong>
        <span>New Zealand · 36.85°S 174.76°E</span>
      </div>

      {show3D && loadingBuildings && (
        <div className="map-loading">
          Loading {counts.buildings.toLocaleString()} building footprints…
        </div>
      )}

      <div className="map-attribution">
        Geometry © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>{" "}
        contributors (ODbL) · tiles <a href="https://carto.com/attributions" target="_blank" rel="noreferrer">CARTO</a>
      </div>

      <div className="map-key" aria-hidden>
        {zoneMetric === "confidence" ? (
          <>
            <span><i className="sw" style={{ background: "#2fa5b8" }} /> surveyed height</span>
            <span><i className="sw" style={{ background: "#8c7ac8" }} /> from storey count</span>
            <span><i className="sw" style={{ background: "#5c687a" }} /> typed default</span>
          </>
        ) : (
          <>
            <span><i className="sw" style={{ background: "#3aa768" }} /> free-flowing</span>
            <span><i className="sw" style={{ background: "#c08327" }} /> busy</span>
            <span><i className="sw" style={{ background: "#b93b5e" }} /> jammed</span>
            <span><i className="sw" style={{ background: "#78aaff" }} /> charge cordon</span>
          </>
        )}
        {show3D && <span className="map-key-note">heights ×{HEIGHT_EXAGGERATION}</span>}
      </div>
    </div>
  );
}

function getTooltip(info: PickingInfo): string | null {
  const f = info.object as
    | Feature<Polygon, BuildingProps>
    | OsmRoadFeature
    | Feature<Polygon, LanduseProps>
    | undefined;
  if (!f?.properties) return null;
  const p = f.properties as unknown as Record<string, unknown>;

  if ("h" in p) {
    const b = p as unknown as BuildingProps;
    const src =
      b.hsrc === "height"
        ? "surveyed height (Observed)"
        : b.hsrc === "levels"
          ? "derived from storey count (Estimated)"
          : "typed default, no height recorded (Estimated)";
    return [b.name ?? `${b.b} building`, `${b.h.toFixed(0)} m — ${src}`].join("\n");
  }
  if ("c" in p) {
    const r = p as unknown as OsmRoadFeature["properties"];
    return [
      r.name ?? `${r.c} road`,
      `${r.c} · ${r.l} lane${r.l === 1 ? "" : "s"} · ${r.s} km/h`,
      `${(r.km * 1000).toFixed(0)} m`,
    ].join("\n");
  }
  if ("kind" in p) {
    const l = p as unknown as LanduseProps;
    return l.name ? `${l.name}\n${l.kind}` : String(l.kind);
  }
  return null;
}

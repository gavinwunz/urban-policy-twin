/**
 * Loader for the OpenStreetMap extract.
 *
 * These are the real surveyed geometry of central Auckland — 14,776 building
 * footprints, 5,960 road links with their real names and classifications, land
 * use and the actual shoreline — scraped from the Overpass API by
 * `data/fetch_osm_auckland.py` and compacted for the browser.
 *
 * Loaded lazily and separately from the analysis grid, because buildings are
 * ~5 MB and only the 3D view needs them. The map renders roads and water first
 * and drops the building layer in when it arrives, so the first paint is not
 * held up by the heaviest file.
 */

import type { Feature, FeatureCollection, LineString, Polygon } from "geojson";

const BASE = process.env.NEXT_PUBLIC_CITY_BASE_URL ?? "/city";

/** Where a building's height came from — surveyed, derived, or a typed guess. */
export type HeightSource = "height" | "levels" | "default";

export interface BuildingProps {
  /** Height in metres. */
  h: number;
  /** Provenance of `h`. Only "height" is a surveyed measurement. */
  hsrc: HeightSource;
  /** OSM `building=*` value. */
  b: string;
  /** Kilometres from the city centre. */
  d: number;
  name?: string;
}

export interface RoadProps {
  /** Road class: motorway | arterial | collector | local | service. */
  c: string;
  /** Lane count. */
  l: number;
  /** Free-flow speed, km/h. */
  s: number;
  /** Length, km. */
  km: number;
  /** Kilometres from the city centre. */
  d: number;
  name?: string;
  /** 1 when one-way. */
  ow?: number;
}

export interface LanduseProps {
  kind: string;
  name?: string;
}

export type BuildingFeature = Feature<Polygon, BuildingProps>;
export type OsmRoadFeature = Feature<LineString, RoadProps>;

export interface OsmSource {
  name: string;
  via: string;
  url: string;
  endpoint: string;
  license: string;
  attribution: string;
}

export interface OsmManifest {
  title: string;
  city: string;
  region: string;
  provenance: string;
  source: OsmSource;
  fetched_at: string;
  elapsed_seconds: number;
  center: { lat: number; lon: number };
  radius_km: number;
  bbox: { south: number; west: number; north: number; east: number };
  counts: Record<string, number>;
  bytes: Record<string, number>;
  height_sources: { height: number; levels: number; default: number };
  note: string;
  frontend: {
    coord_decimal_places: number;
    min_building_area_m2: number;
    counts: Record<string, number>;
    bytes: Record<string, number>;
    reduction_note: string;
  };
}

async function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${BASE}/${path}`, { signal, cache: "force-cache" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

export const loadOsmManifest = (s?: AbortSignal) =>
  get<OsmManifest>("osm_manifest.json", s);

export const loadOsmRoads = (s?: AbortSignal) =>
  get<FeatureCollection<LineString, RoadProps>>("osm_roads.geojson", s);

export const loadOsmWater = (s?: AbortSignal) =>
  get<FeatureCollection<Polygon | LineString, { kind: string; name?: string }>>(
    "osm_water.geojson",
    s,
  );

export const loadOsmLanduse = (s?: AbortSignal) =>
  get<FeatureCollection<Polygon, LanduseProps>>("osm_landuse.geojson", s);

/** ~5 MB — load only when the 3D layer is actually shown. */
export const loadOsmBuildings = (s?: AbortSignal) =>
  get<FeatureCollection<Polygon, BuildingProps>>("osm_buildings.geojson", s);

/** The base map layers, in parallel. Buildings are deliberately excluded. */
export async function loadOsmBase(signal?: AbortSignal) {
  const [manifest, roads, water, landuse] = await Promise.all([
    loadOsmManifest(signal),
    loadOsmRoads(signal),
    loadOsmWater(signal),
    loadOsmLanduse(signal),
  ]);
  return { manifest, roads, water, landuse };
}

/**
 * Colour a building by what its height claim is worth. Surveyed heights read
 * brightest; typed defaults are dimmest. A reader can therefore see at a glance
 * how much of the skyline is measured and how much is inferred — which is the
 * difference between a model and a picture.
 */
export const HEIGHT_SOURCE_LABEL: Record<HeightSource, string> = {
  height: "Surveyed height",
  levels: "Derived from storeys",
  default: "Typed default",
};

export const HEIGHT_SOURCE_TAG: Record<HeightSource, string> = {
  height: "Observed",
  levels: "Estimated",
  default: "Estimated",
};

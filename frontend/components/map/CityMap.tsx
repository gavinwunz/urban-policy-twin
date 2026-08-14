"use client";

/**
 * The 3D city map (SPEC §17/§27) — the visual centerpiece.
 *
 * MapLibre GL renders a tile-free dark base (no API key, works offline); a
 * deck.gl overlay draws the Auckland world on top:
 *   - zones as an extruded choropleth (height + colour encode a chosen metric),
 *   - the road network as lines (cordon-crossing links highlighted),
 *   - the CBD cordon polygon (the congestion-charge / pedestrianisation boundary).
 *
 * All geometry is synthetic world *input* (SPEC §34) — never a simulation result.
 * Optional data-driven overlays (traffic / transit / support) are layered in by
 * later milestones through the `overlays` prop and are clearly labelled where
 * they are placeholders until the backend `/simulate` is live.
 */

import { useMemo } from "react";
import Map, { NavigationControl, useControl } from "react-map-gl/maplibre";
import type { StyleSpecification } from "maplibre-gl";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer } from "@deck.gl/layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import "maplibre-gl/dist/maplibre-gl.css";

import type {
  CbdProps,
  CityGeometry,
  OdMatrix,
  RoadProps,
  ZoneProps,
} from "../../lib/city";
import { OVERLAY_META } from "./overlayMeta";
import type { OverlayMode } from "./overlayMeta";
import { buildOverlayLayers } from "./overlays";

/** A tile-free MapLibre style — a single dark background, no external sources. */
const BASE_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#070b17" },
    },
  ],
};

export type ChoroplethMetric = "population" | "jobs" | "job_density";

const METRIC_LABEL: Record<ChoroplethMetric, string> = {
  population: "Residents per zone",
  jobs: "Jobs per zone",
  job_density: "Jobs per km²",
};

function metricValue(p: ZoneProps, metric: ChoroplethMetric): number {
  switch (metric) {
    case "population":
      return p.population;
    case "jobs":
      return p.jobs;
    case "job_density":
      return p.area_km2 > 0 ? p.jobs / p.area_km2 : 0;
  }
}

/** Sequential blue→amber ramp (dark-mode safe), returned as deck RGBA. */
function ramp(t: number): [number, number, number] {
  const stops: Array<[number, [number, number, number]]> = [
    [0.0, [23, 42, 84]],
    [0.4, [40, 90, 160]],
    [0.7, [90, 150, 210]],
    [1.0, [246, 190, 96]],
  ];
  const x = Math.max(0, Math.min(1, t));
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

/**
 * Overlay layers supplied by later milestones (traffic flow, transit demand,
 * support/opposition heatmap). Kept as raw deck.gl layers so the map component
 * stays agnostic about their data source.
 */
export interface CityMapProps {
  geometry: CityGeometry;
  colorMetric?: ChoroplethMetric;
  /** Extrude zones by the chosen metric for a genuine 3D read. */
  extruded?: boolean;
  /** Which data-driven overlay to draw above the base city. */
  overlayMode?: OverlayMode;
  /** Synthetic OD matrix (lazy-loaded); required for the transit overlay. */
  od?: OdMatrix | null;
  /** Current Time Machine checkpoint label, shown as a badge. */
  timeLabel?: string;
}

/** deck.gl overlay wired into the MapLibre map instance via a custom control. */
function DeckOverlay(props: { layers: Layer[] }) {
  const overlay = useControl<MapboxOverlay>(
    () =>
      new MapboxOverlay({
        interleaved: true,
        layers: props.layers,
        getTooltip,
      }),
  );
  overlay.setProps({ layers: props.layers });
  return null;
}

function getTooltip(info: PickingInfo): string | null {
  const obj = info.object as { properties?: Record<string, unknown> } | undefined;
  const props = obj?.properties;
  if (!props) return null;
  if ("zone_id" in props) {
    const z = props as unknown as ZoneProps;
    return [
      `Zone ${z.zone_id}${z.is_cbd ? " · CBD" : ""}`,
      `${z.land_use}`,
      `Residents: ${z.population.toLocaleString()}`,
      `Jobs: ${z.jobs.toLocaleString()}`,
    ].join("\n");
  }
  if ("link_id" in props) {
    const r = props as unknown as RoadProps;
    return [
      `Link ${r.link_id} · ${r.road_class}`,
      `${r.lanes} lane(s), ${r.length_km.toFixed(2)} km`,
      r.crosses_cordon ? "Crosses CBD cordon" : "",
    ]
      .filter(Boolean)
      .join("\n");
  }
  return null;
}

export default function CityMap({
  geometry,
  colorMetric = "population",
  extruded = true,
  overlayMode = "none",
  od = null,
  timeLabel,
}: CityMapProps) {
  const { zones, roads, cbd, manifest } = geometry;
  const showBaseZones = !OVERLAY_META[overlayMode].hideBaseZones;

  const maxMetric = useMemo(() => {
    let m = 0;
    for (const f of zones.features) {
      m = Math.max(m, metricValue(f.properties, colorMetric));
    }
    return m || 1;
  }, [zones, colorMetric]);

  const layers = useMemo<Layer[]>(() => {
    const base: Layer[] = [];

    if (showBaseZones) {
      base.push(
        new GeoJsonLayer<ZoneProps>({
          id: "zones",
          data: zones,
          pickable: true,
          stroked: true,
          filled: true,
          extruded,
          wireframe: false,
          getLineColor: [12, 18, 33, 180],
          lineWidthMinPixels: 0.5,
          getFillColor: (f) => {
            const v = metricValue(f.properties as ZoneProps, colorMetric);
            const [r, g, b] = ramp(v / maxMetric);
            return [r, g, b, 205];
          },
          getElevation: (f) => {
            if (!extruded) return 0;
            const v = metricValue(f.properties as ZoneProps, colorMetric);
            return (v / maxMetric) * 900;
          },
          elevationScale: 1,
          material: {
            ambient: 0.6,
            diffuse: 0.6,
            shininess: 20,
            specularColor: [40, 60, 90],
          },
          updateTriggers: {
            getFillColor: [colorMetric, maxMetric],
            getElevation: [colorMetric, maxMetric, extruded],
          },
        }),
        new GeoJsonLayer<RoadProps>({
          id: "roads",
          data: roads,
          pickable: true,
          stroked: false,
          filled: false,
          getLineColor: (f) => {
            const p = f.properties as RoadProps;
            if (p.crosses_cordon) return [246, 190, 96, 230];
            if (p.road_class === "arterial") return [147, 160, 189, 200];
            return [90, 102, 130, 150];
          },
          getLineWidth: (f) => {
            const p = f.properties as RoadProps;
            if (p.crosses_cordon) return 3.2;
            return p.road_class === "arterial" ? 2.2 : 1.2;
          },
          lineWidthUnits: "pixels",
          lineWidthMinPixels: 1,
        }),
      );
    }

    // CBD cordon boundary — always drawn so the policy target is legible.
    base.push(
      new GeoJsonLayer<CbdProps>({
        id: "cbd-cordon",
        data: [cbd],
        pickable: false,
        stroked: true,
        filled: true,
        getFillColor: [79, 140, 255, 28],
        getLineColor: [120, 170, 255, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 3,
        lineWidthMinPixels: 2,
      }),
    );

    const overlayLayers = buildOverlayLayers(overlayMode, geometry, od);
    return [...base, ...overlayLayers];
  }, [
    zones,
    roads,
    cbd,
    geometry,
    colorMetric,
    maxMetric,
    extruded,
    overlayMode,
    od,
    showBaseZones,
  ]);

  return (
    <Map
      initialViewState={{
        longitude: manifest.center.lon,
        latitude: manifest.center.lat,
        zoom: 12.3,
        pitch: 48,
        bearing: -18,
      }}
      mapStyle={BASE_STYLE}
      maxPitch={70}
      attributionControl={false}
      dragRotate
      style={{ width: "100%", height: "100%" }}
    >
      <NavigationControl position="top-right" visualizePitch />
      <DeckOverlay layers={layers} />
      {timeLabel && (
        <div className="map-time-badge" aria-hidden>
          {timeLabel}
        </div>
      )}
      {showBaseZones && (
        <div className="map-metric-badge" aria-hidden>
          {METRIC_LABEL[colorMetric]}
        </div>
      )}
    </Map>
  );
}

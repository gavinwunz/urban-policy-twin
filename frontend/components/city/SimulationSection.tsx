"use client";

/**
 * The simulation deck: map on the left, instrumentation on the right.
 *
 * The old layout gave the whole screen to a 3D city and pushed every number
 * below the fold, which is backwards — the map shows *where*, and the charts
 * show *how much*, and a policy argument is almost always about how much. So
 * the map is one panel of a working dashboard, sized to be read alongside the
 * series rather than admired on its own.
 *
 * The projection still runs in the browser (`lib/cityModel.ts`) so scrubbing is
 * instant and the deck survives the backend being down. It is a closed-form
 * summary of the same mechanism the FastAPI engine runs step-wise, off the same
 * OD matrix and the same documented assumptions.
 */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import { loadCityScene, type SceneData, type ZoneFeature } from "../../lib/city";
import { loadOsmBase, type LanduseProps, type OsmManifest, type RoadProps } from "../../lib/osm";
import {
  BASELINE_SCENARIO,
  SCENARIOS,
  cityConstants,
  deltaPct,
  predict,
  type CityState,
  type Scenario,
} from "../../lib/cityModel";
import LineChart from "../charts/LineChart";
import { CATEGORICAL, SERIES, STATUS } from "../charts/palette";
import { Block, Grid } from "../shell/Section";
import type { ZoneMetric } from "./SimulationMap";

const SimulationMap = dynamic(() => import("./SimulationMap"), {
  ssr: false,
  loading: () => <div className="scene-message">Initialising map…</div>,
});

const YEARS = Array.from({ length: 41 }, (_, i) => i * 0.25);

function fmt(n: number, digits = 0): string {
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function yearLabel(y: number): string {
  if (y < 0.05) return "Today";
  if (y < 1) return `${Math.round(y * 12)} months`;
  return `Year ${y.toFixed(1).replace(/\.0$/, "")}`;
}

type OsmBase = Awaited<ReturnType<typeof loadOsmBase>>;

export default function SimulationSection() {
  const [scene, setScene] = useState<SceneData | null>(null);
  const [osm, setOsm] = useState<OsmBase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scenario, setScenario] = useState<Scenario>(BASELINE_SCENARIO);
  const [year, setYear] = useState(0);
  const [showFlows, setShowFlows] = useState(true);
  const [playing, setPlaying] = useState(false);
  const [zoneMetric, setZoneMetric] = useState<ZoneMetric>("landuse");
  const [show3D, setShow3D] = useState(true);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    Promise.all([loadCityScene(ctrl.signal), loadOsmBase(ctrl.signal)])
      .then(([s, o]) => {
        setScene(s);
        setOsm(o);
      })
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Failed to load the city");
      });
    return () => ctrl.abort();
  }, []);

  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    const step = (now: number) => {
      const dt = (now - last) / 1000;
      last = now;
      setYear((y) => {
        const next = y + dt * (10 / 14);
        if (next >= 10) {
          setPlaying(false);
          return 10;
        }
        return next;
      });
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    };
  }, [playing]);

  const constants = useMemo(() => (scene ? cityConstants(scene.od) : null), [scene]);
  const state = useMemo(
    () => (constants ? predict(year, scenario, constants) : null),
    [constants, scenario, year],
  );
  const reference = useMemo(
    () => (constants ? predict(year, BASELINE_SCENARIO, constants) : null),
    [constants, year],
  );

  /** The full ten-year trace for both worlds — what every chart reads. */
  const trace = useMemo(() => {
    if (!constants) return null;
    const policy = YEARS.map((y) => predict(y, scenario, constants));
    const base = YEARS.map((y) => predict(y, BASELINE_SCENARIO, constants));
    return { policy, base };
  }, [constants, scenario]);

  if (error) {
    return (
      <div className="scene-message">City data unavailable — {error}</div>
    );
  }

  if (!scene || !osm || !state || !reference || !trace) {
    return (
      <div className="scene-message">
        Loading the Auckland street network from OpenStreetMap…
      </div>
    );
  }

  const isBaseline = scenario.id === BASELINE_SCENARIO.id;

  // The analysis grid still supplies the zone centroids the commute arcs are
  // drawn between, and the cordon polygon. The rest of the map is OSM.
  const zoneCentroids = new Map<string, [number, number]>();
  let cbdLon = 0;
  let cbdLat = 0;
  let cbdCount = 0;
  for (const f of scene.geometry.zones.features as ZoneFeature[]) {
    const zp = f.properties;
    zoneCentroids.set(zp.zone_id, [zp.centroid_lon, zp.centroid_lat]);
    if (zp.is_cbd) {
      cbdLon += zp.centroid_lon;
      cbdLat += zp.centroid_lat;
      cbdCount += 1;
    }
  }
  const cbdCentre: [number, number] = cbdCount
    ? [cbdLon / cbdCount, cbdLat / cbdCount]
    : [osm.manifest.center.lon, osm.manifest.center.lat];
  const cordonPolygon = (scene.geometry.cbd.geometry.coordinates as number[][][])[0];

  const series = (pick: (s: CityState) => number) => [
    ...(isBaseline
      ? []
      : [
          {
            label: "Do nothing",
            color: SERIES.baseline,
            dashed: true,
            points: trace.base.map((s, i) => ({ x: YEARS[i], y: pick(s) })),
          },
        ]),
    {
      label: isBaseline ? "Do nothing" : scenario.label,
      color: SERIES.policy,
      points: trace.policy.map((s, i) => ({ x: YEARS[i], y: pick(s) })),
    },
  ];

  return (
    <>
      <div className="scenario-row" role="group" aria-label="Policy lever">
        {SCENARIOS.map((s) => (
          <button
            key={s.id}
            type="button"
            className={`scenario-btn${scenario.id === s.id ? " active" : ""}`}
            onClick={() => setScenario(s)}
          >
            <span className="scenario-label">{s.label}</span>
            <span className="scenario-blurb">{s.blurb}</span>
          </button>
        ))}
      </div>

      <OsmProvenance manifest={osm.manifest} />

      <div className="sim-deck">
        <div className="sim-map-col">
          <div className="sim-map-frame">
            <SimulationMap
              osm={osm}
              od={scene.od}
              zoneCentroids={zoneCentroids}
              cbdCentre={cbdCentre}
              cordonPolygon={cordonPolygon}
              state={state}
              scenario={scenario}
              showFlows={showFlows}
              show3D={show3D}
              zoneMetric={zoneMetric}
            />
            <div className="scene-badge">
              <strong>{yearLabel(year)}</strong>
              <span>{scenario.label}</span>
            </div>
          </div>

          <div className="map-controls">
            <div className="map-control-group">
              <span className="map-control-label">Overlay</span>
              {(
                [
                  ["landuse", "Land use"],
                  ["confidence", "Height source"],
                  ["none", "Off"],
                ] as Array<[ZoneMetric, string]>
              ).map(([k, label]) => (
                <button
                  key={k}
                  type="button"
                  className={`chip${zoneMetric === k ? " on" : ""}`}
                  onClick={() => setZoneMetric(k)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="map-control-group">
              <label className="switch">
                <input
                  type="checkbox"
                  checked={show3D}
                  onChange={(e) => setShow3D(e.target.checked)}
                />
                3D buildings
              </label>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={showFlows}
                  onChange={(e) => setShowFlows(e.target.checked)}
                />
                Commute flows
              </label>
            </div>
          </div>

          <div className="scrubber">
            <button
              type="button"
              className="play"
              onClick={() => {
                if (year >= 10) setYear(0);
                setPlaying((p) => !p);
              }}
              aria-label={playing ? "Pause" : "Play ten years"}
            >
              {playing ? "❚❚" : "▶"}
            </button>
            <input
              className="scrub-range"
              type="range"
              min={0}
              max={10}
              step={0.05}
              value={year}
              onChange={(e) => {
                setPlaying(false);
                setYear(Number(e.target.value));
              }}
              aria-label="Years after implementation"
            />
            <span className="scrub-readout">{yearLabel(year)}</span>
          </div>
        </div>

        <div className="sim-stats-col">
          <div className="kpi-grid">
            <Kpi
              label="Cars into the centre"
              value={fmt(state.carTripsIntoCbd)}
              unit="/day"
              delta={deltaPct(state.carTripsIntoCbd, reference.carTripsIntoCbd)}
              goodWhenDown
              muted={isBaseline}
            />
            <Kpi
              label="Traffic CO₂"
              value={fmt(state.co2TonnesPerDay, 1)}
              unit="t/day"
              delta={deltaPct(state.co2TonnesPerDay, reference.co2TonnesPerDay)}
              goodWhenDown
              muted={isBaseline}
            />
            <Kpi
              label="Public transport"
              value={fmt(state.transitTrips)}
              unit="trips/day"
              delta={deltaPct(state.transitTrips, reference.transitTrips)}
              goodWhenDown={false}
              muted={isBaseline}
            />
            <Kpi
              label="Public support"
              value={fmt(state.support * 100)}
              unit="%"
              delta={deltaPct(state.support, reference.support)}
              goodWhenDown={false}
              muted={isBaseline}
            />
          </div>

          <div className="mini-chart">
            <h4>Cars entering the cordon</h4>
            <LineChart
              height={168}
              xLabel="years"
              yLabel="trips/day"
              formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
              format={(v) => `${(v / 1000).toFixed(0)}k`}
              series={series((s) => s.carTripsIntoCbd)}
            />
          </div>

          <div className="mini-chart">
            <h4>Mode split into the centre</h4>
            <LineChart
              height={168}
              xLabel="years"
              yLabel="car share"
              formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
              format={(v) => `${(v * 100).toFixed(0)}%`}
              series={series((s) => s.carShareIntoCbd)}
            />
          </div>
        </div>
      </div>

      <Grid>
        <Block
          title="Emissions trajectory"
          hint="Tailpipe CO₂ from traffic, tonnes per day. The gap between the two lines is the policy's actual climate contribution."
        >
          <LineChart
            height={210}
            zeroBased
            xLabel="years after implementation"
            yLabel="t CO₂/day"
            formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
            format={(v) => v.toFixed(0)}
            series={series((s) => s.co2TonnesPerDay)}
          />
        </Block>

        <Block
          title="Central traffic pressure"
          hint="Indexed to today = 1.0. Above 1 the centre is more congested than it is now; pedestrianisation holds this flat by removing road capacity as fast as it removes cars."
        >
          <LineChart
            height={210}
            xLabel="years after implementation"
            yLabel="index"
            formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
            format={(v) => v.toFixed(2)}
            marker={{ x: 0, label: "today" }}
            series={series((s) => s.congestion)}
          />
        </Block>

        <Block
          title="Public transport uptake"
          hint="Daily transit trips citywide. Where the suppressed car trips actually go — subject to whether there is capacity to carry them."
        >
          <LineChart
            height={210}
            xLabel="years after implementation"
            yLabel="trips/day"
            formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
            format={(v) => `${(v / 1000).toFixed(0)}k`}
            series={series((s) => s.transitTrips)}
          />
        </Block>

        <Block
          title="Street space returned to people"
          hint="Share of central kerbside converted to plazas, wider footways and pocket parks. Zero under every scenario that does not explicitly reallocate street space."
        >
          <LineChart
            height={210}
            zeroBased
            xLabel="years after implementation"
            yLabel="% of kerbside"
            formatX={(v) => (v < 0.1 ? "now" : `${v.toFixed(0)}y`)}
            format={(v) => `${(v * 100).toFixed(0)}%`}
            series={[
              {
                label: scenario.label,
                color: CATEGORICAL[3],
                points: trace.policy.map((s, i) => ({
                  x: YEARS[i],
                  y: s.publicRealm,
                })),
              },
            ]}
          />
        </Block>
      </Grid>

      <p className="studio-note">
        <span className="tag simulated">Simulated</span> Projected by the
        in-browser cordon demand-response model from the bundled
        origin–destination matrix and the same documented input assumptions the
        backend engine uses. Not an observation, and no language model produced
        any number on this page.
      </p>
    </>
  );
}

function Kpi({
  label,
  value,
  unit,
  delta,
  goodWhenDown,
  muted,
}: {
  label: string;
  value: string;
  unit: string;
  delta: number | null;
  goodWhenDown: boolean;
  muted: boolean;
}) {
  const flat = muted || delta === null || Math.abs(delta) < 0.05;
  const good = delta !== null && (goodWhenDown ? delta < 0 : delta > 0);
  return (
    <div className="kpi">
      <span className="kpi-label">{label}</span>
      <span className="kpi-value">
        {value}
        <em>{unit}</em>
      </span>
      {flat ? (
        <span className="kpi-delta flat">
          {muted ? "reference case" : "— vs do nothing"}
        </span>
      ) : (
        <span
          className="kpi-delta"
          style={{ color: good ? STATUS.good : STATUS.serious }}
        >
          {delta! > 0 ? "▲" : "▼"} {Math.abs(delta!).toFixed(1)}% vs do nothing
        </span>
      )}
    </div>
  );
}


/**
 * States, on screen, exactly what the map is made of and where it came from.
 *
 * The counts are read from the scraper's own manifest rather than typed in, so
 * they cannot drift away from the data actually being drawn.
 */
function OsmProvenance({ manifest }: { manifest: OsmManifest }) {
  const c = manifest.frontend.counts;
  const hs = manifest.height_sources;
  const surveyed = hs.height;
  const total = hs.height + hs.levels + hs.default;
  const fetched = new Date(manifest.fetched_at);

  return (
    <div className="osm-strip">
      <div className="osm-strip-head">
        <span className="tag observed">Observed</span>
        <strong>Scraped from OpenStreetMap</strong>
        <span className="osm-strip-sub">
          via the Overpass API · {fetched.toISOString().slice(0, 10)} ·{" "}
          Open Database Licence
        </span>
      </div>
      <dl className="osm-strip-facts">
        <div>
          <dt>Street links</dt>
          <dd>{c.roads.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Buildings</dt>
          <dd>{c.buildings.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Land use</dt>
          <dd>{c.landuse.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Coast &amp; water</dt>
          <dd>{c.water.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Surveyed heights</dt>
          <dd>
            {surveyed.toLocaleString()}{" "}
            <em>of {total.toLocaleString()}</em>
          </dd>
        </div>
      </dl>
      <p className="osm-strip-note">
        Real surveyed geometry — road names, classifications, lane counts and
        speed limits are as recorded by OpenStreetMap contributors. Traffic
        trails follow the actual street polylines. Building heights are
        surveyed on {((surveyed / total) * 100).toFixed(0)}% of footprints and
        estimated from storey counts or building type on the rest; switch the
        overlay to <strong>Height source</strong> to see which is which.
      </p>
    </div>
  );
}

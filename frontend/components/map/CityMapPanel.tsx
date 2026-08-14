"use client";

/**
 * Client wrapper for the 3D city map.
 *
 * The map (MapLibre + deck.gl) touches `window` at import, so it is dynamically
 * imported with SSR disabled. This wrapper owns geometry + OD loading, the
 * choropleth-metric switcher, the overlay switcher (Traffic / Transit / Support),
 * loading/empty/error states, the legend, and the provenance stamp — every
 * overlay is labelled with its provenance class so no placeholder reads as real
 * (SPEC §34).
 */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { loadCityGeometry, loadOdMatrix } from "../../lib/city";
import type { CityGeometry, OdMatrix } from "../../lib/city";
import type { ChoroplethMetric } from "./CityMap";
import { OVERLAY_META } from "./overlayMeta";
import type { OverlayMode } from "./overlayMeta";

const CityMap = dynamic(() => import("./CityMap"), {
  ssr: false,
  loading: () => <MapPlaceholder label="Loading map engine…" />,
});

const METRICS: Array<{ key: ChoroplethMetric; label: string }> = [
  { key: "population", label: "Residents" },
  { key: "jobs", label: "Jobs" },
  { key: "job_density", label: "Job density" },
];

const OVERLAYS: OverlayMode[] = ["none", "traffic", "transit", "support"];

function MapPlaceholder({ label }: { label: string }) {
  return (
    <div className="map-placeholder">
      <span className="dot" />
      <span>{label}</span>
    </div>
  );
}

export interface CityMapPanelProps {
  /** Current Time Machine checkpoint label from the parent workspace. */
  timeLabel?: string;
}

export default function CityMapPanel({ timeLabel }: CityMapPanelProps) {
  const [geometry, setGeometry] = useState<CityGeometry | null>(null);
  const [od, setOd] = useState<OdMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [metric, setMetric] = useState<ChoroplethMetric>("population");
  const [extruded, setExtruded] = useState(true);
  const [overlay, setOverlay] = useState<OverlayMode>("none");

  useEffect(() => {
    const ctrl = new AbortController();
    loadCityGeometry(ctrl.signal)
      .then(setGeometry)
      .catch((e: unknown) => {
        if (ctrl.signal.aborted) return;
        setError(e instanceof Error ? e.message : "Failed to load city geometry");
      });
    return () => ctrl.abort();
  }, []);

  // Lazily fetch the (~0.4 MB) OD matrix the first time the transit overlay is used.
  useEffect(() => {
    if (overlay !== "transit" || od) return;
    const ctrl = new AbortController();
    loadOdMatrix(ctrl.signal)
      .then(setOd)
      .catch(() => {
        /* transit overlay stays empty; caption notes it. */
      });
    return () => ctrl.abort();
  }, [overlay, od]);

  const totals = useMemo(() => geometry?.manifest.totals ?? {}, [geometry]);
  const meta = OVERLAY_META[overlay];
  const showChoroplethControls = !meta.hideBaseZones;
  const transitLoading = overlay === "transit" && !od;

  return (
    <section className="map-section card" data-tour="map">
      <div className="map-header">
        <div>
          <h2>Auckland — 3D world</h2>
          <p className="map-sub">
            {geometry
              ? `${geometry.manifest.counts.zones} zones · ${geometry.manifest.counts.roads} links · CBD cordon`
              : "Synthetic city grid"}
          </p>
        </div>
        <div className="map-controls">
          <div className="seg" role="group" aria-label="Overlay">
            {OVERLAYS.map((o) => (
              <button
                key={o}
                className={`seg-btn${overlay === o ? " active" : ""}`}
                onClick={() => setOverlay(o)}
                type="button"
              >
                {OVERLAY_META[o].label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {showChoroplethControls && (
        <div className="map-subcontrols">
          <span className="ctrl-label">Colour zones by</span>
          <div className="seg" role="group" aria-label="Colour zones by">
            {METRICS.map((m) => (
              <button
                key={m.key}
                className={`seg-btn${metric === m.key ? " active" : ""}`}
                onClick={() => setMetric(m.key)}
                type="button"
              >
                {m.label}
              </button>
            ))}
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={extruded}
              onChange={(e) => setExtruded(e.target.checked)}
            />
            3D
          </label>
        </div>
      )}

      <div className="map-canvas">
        {error ? (
          <MapPlaceholder label={`Map unavailable — ${error}`} />
        ) : !geometry ? (
          <MapPlaceholder label="Loading Auckland…" />
        ) : (
          <CityMap
            geometry={geometry}
            colorMetric={metric}
            extruded={extruded}
            overlayMode={overlay}
            od={od}
            timeLabel={timeLabel}
          />
        )}
      </div>

      {overlay !== "none" && (
        <div className={`overlay-banner prov-${meta.provenance.toLowerCase()}`}>
          <span className={`tag ${meta.provenance.toLowerCase()}`}>
            {meta.provenance}
          </span>
          <span className="overlay-caption">
            {transitLoading ? "Loading synthetic origin–destination demand…" : meta.caption}
          </span>
          {meta.legend.length > 0 && !transitLoading && (
            <span className="overlay-legend">
              {meta.legend.map((l) => (
                <span key={l.label} className="legend-item">
                  <span
                    className="swatch"
                    style={{ background: l.color }}
                    aria-hidden
                  />
                  {l.label}
                </span>
              ))}
            </span>
          )}
        </div>
      )}

      <div className="map-footer">
        {overlay === "none" && (
          <div className="map-legend">
            <span className="legend-label">Low</span>
            <span className="legend-ramp" aria-hidden />
            <span className="legend-label">High</span>
            <span className="legend-item">
              <span className="swatch cordon" /> CBD cordon
            </span>
            <span className="legend-item">
              <span className="swatch cross" /> Cordon-crossing road
            </span>
          </div>
        )}
        <div className="map-provenance">
          <span className="tag muted">Synthetic</span>
          <span>
            World input — not a simulation result. Policy effects come from{" "}
            <code>/simulate</code>.
          </span>
        </div>
      </div>

      {geometry && (
        <dl className="kv map-totals">
          <dt>Population</dt>
          <dd>{(totals.population ?? 0).toLocaleString()}</dd>
          <dt>Jobs</dt>
          <dd>{(totals.jobs ?? 0).toLocaleString()}</dd>
          <dt>Daily trips into CBD</dt>
          <dd>{(totals.daily_trips_into_cbd ?? 0).toLocaleString()}</dd>
        </dl>
      )}
    </section>
  );
}

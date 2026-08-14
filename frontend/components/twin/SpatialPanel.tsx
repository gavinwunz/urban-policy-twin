"use client";

/**
 * Spatial traffic-assignment view (SPEC §7.7): where the policy's traffic
 * actually goes on the road grid — built by `POST /spatial` from a peak-hour
 * static user-equilibrium assignment (MSA + BPR volume-delay) over the real
 * Auckland network. Car demand is the subset of the same deterministic
 * mode-choice agents (`/simulate`) who still choose to drive.
 *
 * Honesty story (SPEC §7.7/§34): every number here is Simulated by a
 * deterministic assignment model — no LLM. Bottlenecks, cordon inflow,
 * accessibility and the CO₂ dispersion proxy are surfaced as World A (baseline)
 * vs World B (policy) so displacement is visible, not hidden. The spatial
 * assumptions live in an auditable `params` block, and `not_modelled` is explicit
 * about what a static peak-hour assignment can't capture. When the backend is
 * down we show a clear waiting/error state; we never invent link flows.
 */

import { useEffect, useState } from "react";

import { runSpatial } from "../../lib/api";
import type {
  ArcLoad,
  NetworkState,
  SpatialReport,
  ZoneChange,
} from "../../lib/api";
import { formatNumber } from "../../lib/format";
import { useTwin } from "./TwinStore";

type Status = "idle" | "loading" | "ready" | "error";

/**
 * Format a value that is ALREADY in percent units (the backend's `_pct_change`
 * returns e.g. `-12.5` for −12.5%), signed. Distinct from `formatSignedPct`,
 * which expects a 0..1 fraction.
 */
function deltaPct(percentValue: number): string {
  const sign = percentValue > 0 ? "+" : percentValue < 0 ? "−" : "";
  return `${sign}${Math.abs(percentValue).toFixed(1)}%`;
}

function num(v: number): string {
  return formatNumber(v);
}

export default function SpatialPanel() {
  const { policy } = useTwin();
  const [status, setStatus] = useState<Status>("idle");
  const [report, setReport] = useState<SpatialReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setReport(null);
    setStatus("idle");
    setError(null);
  }, [policy]);

  async function run() {
    if (!policy) return;
    setStatus("loading");
    setError(null);
    try {
      const r = await runSpatial(policy);
      setReport(r);
      setStatus("ready");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Spatial assignment failed");
      setStatus("error");
    }
  }

  return (
    <section className="card spatial">
      <div className="dashboard-head">
        <h2>Spatial traffic assignment</h2>
        <span className="dashboard-sub">
          Peak-hour user-equilibrium over the road grid · where traffic goes (SPEC §7.7)
        </span>
      </div>

      {!policy ? (
        <div className="waiting">
          <span className="tag muted">No policy yet</span>
          <p>
            Compile a policy above to load its driving demand onto the Auckland
            road network — congested link flows, cordon inflow, bottlenecks, job
            accessibility and a road-CO₂ dispersion proxy, each as baseline vs policy.
          </p>
        </div>
      ) : (
        <>
          <div className="policy-actions" style={{ marginTop: 0 }}>
            <button
              type="button"
              className="btn primary"
              onClick={run}
              disabled={status === "loading"}
            >
              {status === "loading"
                ? "Assigning to network…"
                : report
                  ? "Re-run assignment"
                  : "Run assignment"}
            </button>
            {report && (
              <span className={`tag ${report.provenance.toLowerCase()}`}>
                {report.provenance}
              </span>
            )}
          </div>

          {status === "error" && (
            <p className="hint error-text">Couldn&rsquo;t run assignment: {error}</p>
          )}

          {status === "idle" && !report && (
            <p className="hint">
              Routes the driving subset of the deterministic mode-choice agents to an
              approximate user equilibrium (method of successive averages + BPR
              volume-delay) over the real road grid. Every number is Simulated; no
              LLM. Click to run.
            </p>
          )}

          {report && status !== "loading" && (
            <div className="sp-body">
              <NetworkHeadline r={report} />

              <div className="sp-worlds">
                <WorldCard label="World A · baseline" s={report.world_a} />
                <WorldCard label="World B · policy" s={report.world_b} accent />
              </div>

              {report.notable_arcs.length > 0 && (
                <ArcSection
                  title="Notable link loads"
                  note="cordon-crossing & most-changed arcs, World A → B"
                  arcs={report.notable_arcs}
                />
              )}

              {(report.bottlenecks_b.length > 0 ||
                report.bottlenecks_a.length > 0) && (
                <div className="sp-bottlenecks">
                  <ArcSection
                    title="Bottlenecks · World B (policy)"
                    note="arcs over capacity (v/c ≥ 1.0)"
                    arcs={report.bottlenecks_b}
                    emptyLabel="No arc over capacity under the policy."
                  />
                  <ArcSection
                    title="Bottlenecks · World A (baseline)"
                    note="arcs over capacity (v/c ≥ 1.0)"
                    arcs={report.bottlenecks_a}
                    emptyLabel="No arc over capacity at baseline."
                  />
                </div>
              )}

              <AccessibilityBlock r={report} />
              <PollutionBlock r={report} />

              {report.not_modelled.length > 0 && (
                <div className="eco-notmodelled">
                  <span className="eco-nm-title">Deliberately not modelled</span>
                  <ul>
                    {report.not_modelled.map((n, i) => (
                      <li key={i}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}

              <ParamsBlock params={report.params} />

              <p className="hint eco-note">{report.note}</p>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function NetworkHeadline({ r }: { r: SpatialReport }) {
  // Falling cordon inflow / vehicle-hours is the good direction.
  const cordonGood = r.cordon_inflow_delta_pct <= 0;
  const vhGood = r.vehicle_hours_delta_pct <= 0;
  return (
    <div className="sp-headline">
      <div className="sp-hl-item">
        <span className="sp-hl-label">Peak-hour car trips</span>
        <span className="sp-hl-value">
          {num(r.peak_hour_car_trips_a)} → {num(r.peak_hour_car_trips_b)}
        </span>
      </div>
      <div className="sp-hl-item">
        <span className="sp-hl-label">Cordon inflow</span>
        <span className={`sp-hl-value ${cordonGood ? "good" : "warn"}`}>
          {deltaPct(r.cordon_inflow_delta_pct)}
        </span>
      </div>
      <div className="sp-hl-item">
        <span className="sp-hl-label">Network vehicle-hours</span>
        <span className={`sp-hl-value ${vhGood ? "good" : "warn"}`}>
          {deltaPct(r.vehicle_hours_delta_pct)}
        </span>
      </div>
    </div>
  );
}

function WorldCard({
  label,
  s,
  accent = false,
}: {
  label: string;
  s: NetworkState;
  accent?: boolean;
}) {
  const rows: Array<[string, string, string?]> = [
    ["Vehicle-hours", `${num(s.total_vehicle_hours)}`, "veh-hr/peak"],
    ["Vehicle-km", `${num(s.total_vehicle_km)}`, "veh-km/peak"],
    ["Mean speed", `${s.mean_speed_kmh.toFixed(1)}`, "km/h"],
    ["Mean v/c", `${s.mean_vc.toFixed(2)}`],
    ["Max v/c", `${s.max_vc.toFixed(2)}`],
    ["Congested arcs", `${num(s.congested_arcs)}`, "v/c ≥ 0.9"],
    ["Over capacity", `${num(s.overcapacity_arcs)}`, "v/c ≥ 1.0"],
    ["Cordon inflow", `${num(s.cordon_inflow_veh_per_hr)}`, "veh/hr"],
  ];
  return (
    <div className={`sp-world${accent ? " accent" : ""}`}>
      <div className="sp-world-head">{label}</div>
      <dl className="sp-world-grid">
        {rows.map(([k, v, unit]) => (
          <div className="sp-world-row" key={k}>
            <dt>{k}</dt>
            <dd>
              {v}
              {unit && <span className="sp-unit"> {unit}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function ArcSection({
  title,
  note,
  arcs,
  emptyLabel,
}: {
  title: string;
  note?: string;
  arcs: ArcLoad[];
  emptyLabel?: string;
}) {
  return (
    <div className="sp-section">
      <h3 className="eco-sec-title">
        {title}
        {note && <span className="eco-sec-note">{note}</span>}
      </h3>
      {arcs.length === 0 ? (
        <p className="hint">{emptyLabel ?? "None."}</p>
      ) : (
        <div className="sp-arc-table" role="table" aria-label={title}>
          <div className="sp-arc-row sp-arc-head" role="row">
            <span role="columnheader">Arc</span>
            <span role="columnheader" title="Road class">class</span>
            <span role="columnheader" title="Peak vehicles World A → World B">flow A→B</span>
            <span role="columnheader" title="Volume/capacity World A → World B">v/c A→B</span>
            <span role="columnheader" title="Congested speed km/h A → B">km/h A→B</span>
          </div>
          {arcs.map((a) => {
            const worse = a.delta_flow > 0;
            return (
              <div className="sp-arc-row" role="row" key={a.arc_id}>
                <span className="sp-arc-id" role="cell">
                  <span className="sp-arc-od" title={`${a.from_zone} → ${a.to_zone}`}>
                    {a.from_zone}→{a.to_zone}
                  </span>
                  {a.crosses_cordon && (
                    <span className="sp-cordon-chip" title="Crosses the CBD cordon">
                      cordon
                    </span>
                  )}
                </span>
                <span className="sp-arc-class" role="cell">
                  {a.road_class}
                </span>
                <span className="sp-arc-flow" role="cell">
                  {num(a.flow_a)} → {num(a.flow_b)}{" "}
                  <span className={worse ? "warn" : "good"}>
                    ({worse ? "+" : "−"}
                    {num(Math.abs(a.delta_flow))})
                  </span>
                </span>
                <span className="sp-arc-vc" role="cell">
                  <VcPill v={a.vc_a} /> → <VcPill v={a.vc_b} />
                </span>
                <span className="sp-arc-speed" role="cell">
                  {a.speed_a_kmh.toFixed(0)} → {a.speed_b_kmh.toFixed(0)}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function VcPill({ v }: { v: number }) {
  const cls = v >= 1.0 ? "warn" : v >= 0.9 ? "mid" : "good";
  return <span className={`sp-vc ${cls}`}>{v.toFixed(2)}</span>;
}

function AccessibilityBlock({ r }: { r: SpatialReport }) {
  const a = r.accessibility;
  const good = a.mean_delta_pct >= 0; // more jobs reachable is good
  return (
    <div className="sp-section">
      <h3 className="eco-sec-title">
        Job accessibility
        <span className="eco-sec-note">
          gravity reach by congested car network{" "}
          <span className={`tag ${a.tag.toLowerCase()}`}>{a.tag}</span>
        </span>
      </h3>
      <div className="sp-access-head">
        <span>
          mean {num(a.mean_a)} → {num(a.mean_b)}
        </span>
        <span className={`sp-access-delta ${good ? "good" : "warn"}`}>
          {deltaPct(a.mean_delta_pct)} population-weighted
        </span>
      </div>
      <div className="sp-zone-cols">
        <ZoneList title="Top gainers" zones={a.top_gainers} goodDir />
        <ZoneList title="Top losers" zones={a.top_losers} />
      </div>
    </div>
  );
}

function PollutionBlock({ r }: { r: SpatialReport }) {
  const p = r.pollution;
  const cbdGood = p.cbd_delta_pct <= 0; // less CBD CO₂ is good
  return (
    <div className="sp-section">
      <h3 className="eco-sec-title">
        Road-CO₂ dispersion proxy
        <span className="eco-sec-note">
          per-zone, peak hour{" "}
          <span className={`tag ${p.tag.toLowerCase()}`}>{p.tag}</span>
        </span>
      </h3>
      <div className="sp-access-head">
        <span>
          CBD {num(p.cbd_a)} → {num(p.cbd_b)}
        </span>
        <span className={`sp-access-delta ${cbdGood ? "good" : "warn"}`}>
          {deltaPct(p.cbd_delta_pct)} CBD
        </span>
        <span className="sp-network-total">
          network {num(p.network_total_a)} → {num(p.network_total_b)}
        </span>
      </div>
      <div className="sp-zone-cols">
        <ZoneList title="Biggest drops" zones={p.biggest_drops} goodDir />
        <ZoneList
          title="Biggest rises (displacement)"
          zones={p.biggest_rises}
        />
      </div>
      {p.displacement_note && (
        <p className="sp-displacement">{p.displacement_note}</p>
      )}
    </div>
  );
}

function ZoneList({
  title,
  zones,
  goodDir = false,
}: {
  title: string;
  zones: ZoneChange[];
  goodDir?: boolean;
}) {
  return (
    <div className="sp-zonelist">
      <span className="sp-zonelist-title">{title}</span>
      {zones.length === 0 ? (
        <p className="hint">None.</p>
      ) : (
        <ul>
          {zones.map((z) => (
            <li key={z.zone_id}>
              <span className="sp-zone-id">
                {z.zone_id}
                {z.is_cbd && <span className="sp-cbd-chip">CBD</span>}
              </span>
              <span className={`sp-zone-delta ${goodDir ? "good" : "warn"}`}>
                {deltaPct(z.delta_pct)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ParamsBlock({ params }: { params: Record<string, unknown> }) {
  const entries = Object.entries(params ?? {});
  if (entries.length === 0) return null;
  return (
    <details className="eco-assumptions">
      <summary>
        Spatial assumptions <span className="eco-assum-count">({entries.length})</span>
      </summary>
      <dl>
        {entries.map(([k, v]) => (
          <div key={k} className="eco-assum-row">
            <dt>{k.replace(/_/g, " ")}</dt>
            <dd>{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

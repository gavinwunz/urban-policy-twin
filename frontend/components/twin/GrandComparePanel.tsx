"use client";

/**
 * Grand counterfactual (SPEC §21/§22): the canonical four-way comparison via
 * `POST /compare/grand`. Where the plain Compare tab spins up arbitrary caller
 * amendment worlds, this tab composes the *named* quartet the spec defines by
 * role:
 *
 *   • World A — baseline (no policy),
 *   • World B — the compiled policy (the intervention),
 *   • World C — the opposition amendment (auto-derived when none supplied),
 *   • World D — the GOV SIM-optimised best-balanced pick from the §22 optimiser.
 *
 * The distinct value here isn't a new number — it's the *derivation* audit: the
 * panel shows exactly how World C and World D were composed (amendment source +
 * rationale; optimiser objective/constraints, which recommendation slot was
 * picked, the chosen config, feasibility, candidate counts) so the quartet is
 * legible rather than magic.
 *
 * Honesty (SPEC §21/§22/§34): World A is always present and never omitted; C/D
 * are re-simulated through the *same* deterministic path as B, so every number
 * is Simulated and no LLM touches the numeric path. When the backend is down we
 * show a waiting/error state instead of inventing a comparison.
 */

import { useEffect, useState } from "react";

import { getCompareExample, runGrandCompare } from "../../lib/api";
import type {
  ComparisonRow,
  CounterfactualComparison,
  CounterfactualWorld,
  GrandWorldC,
  GrandWorldD,
} from "../../lib/api";
import { formatNumber } from "../../lib/format";
import { useTwin } from "./TwinStore";

type Status = "idle" | "loading" | "ready" | "error";

const HORIZONS: Array<{ label: string; months: number }> = [
  { label: "Year 1", months: 12 },
  { label: "Year 2", months: 24 },
  { label: "Year 5", months: 60 },
  { label: "Year 10", months: 120 },
];

/**
 * World-D optimiser targets. Each is a transparent (objective, constraints) pair
 * handed to the §22 optimiser; the backend still picks the *best-balanced*
 * feasible policy — these only steer what "balanced" optimises toward.
 */
const D_TARGETS: Array<{
  key: string;
  label: string;
  objective: Record<string, number>;
  constraints: Record<string, number>;
}> = [
  { key: "balanced", label: "Best balanced (default)", objective: {}, constraints: {} },
  {
    key: "emissions",
    label: "Cut transport emissions 20%",
    objective: { reduce_transport_emissions_pct: 20 },
    constraints: {},
  },
  {
    key: "equity",
    label: "Protect low-income (≤2% burden)",
    objective: {},
    constraints: { max_low_income_burden_increase_pct: 2 },
  },
];

export default function GrandComparePanel() {
  const { policy } = useTwin();
  const [status, setStatus] = useState<Status>("idle");
  const [result, setResult] = useState<CounterfactualComparison | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [horizon, setHorizon] = useState(60);
  const [target, setTarget] = useState("balanced");
  // True when the shown quartet is the canonical §28 demo (GET /compare/example),
  // not the user's compiled policy — kept explicit so a judge is never shown the
  // demo comparison as if it were the policy compiled above (honest, SPEC §34).
  const [isExample, setIsExample] = useState(false);

  // A fresh/edited policy invalidates any prior comparison (including an example).
  useEffect(() => {
    setResult(null);
    setStatus("idle");
    setError(null);
    setIsExample(false);
  }, [policy]);

  async function compare() {
    if (!policy) return;
    setStatus("loading");
    setError(null);
    setIsExample(false);
    const t = D_TARGETS.find((d) => d.key === target) ?? D_TARGETS[0];
    try {
      const r = await runGrandCompare({
        policy,
        objective: t.objective,
        constraints: t.constraints,
        horizon_months: horizon,
      });
      setResult(r);
      setStatus("ready");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Comparison failed");
      setStatus("error");
    }
  }

  // Compose the canonical §28 demo quartet (GET /compare/example) — a body-less
  // call so the tab is usable with no compiled policy in the store. Flagged as
  // the example rather than the policy above (honest, SPEC §21/§34). The horizon
  // and World-D target selectors don't apply here: the keyless endpoint fixes
  // both to the demo defaults, so the surface can never disagree with the POST.
  async function compareExample() {
    setStatus("loading");
    setError(null);
    setIsExample(true);
    try {
      const r = await getCompareExample();
      setResult(r);
      setStatus("ready");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Example comparison failed");
      setStatus("error");
    }
  }

  const derivation = result?.derivation ?? null;

  return (
    <section className="card compare grand">
      <div className="dashboard-head">
        <h2>Grand counterfactual · A / B / C / D</h2>
        <span className="dashboard-sub">
          Baseline vs policy vs opposition amendment vs GOV SIM-optimised (SPEC §21/§22)
        </span>
      </div>

      <>
          <div className="grand-controls">
            <label className="asm-horizon">
              <span className="asm-ctl-label">Horizon</span>
              <select
                value={horizon}
                onChange={(e) => setHorizon(Number(e.target.value))}
                disabled={status === "loading" || !policy}
              >
                {HORIZONS.map((h) => (
                  <option key={h.months} value={h.months}>
                    {h.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="asm-horizon">
              <span className="asm-ctl-label">World D optimiser target</span>
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                disabled={status === "loading" || !policy}
              >
                {D_TARGETS.map((d) => (
                  <option key={d.key} value={d.key}>
                    {d.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="btn primary"
              onClick={compare}
              disabled={status === "loading" || !policy}
              title={
                policy
                  ? "Compose the four-way comparison for the policy compiled above"
                  : "Compile a policy above first, or load the demo example →"
              }
            >
              {status === "loading" && !isExample
                ? "Composing worlds…"
                : result && !isExample
                  ? "Re-compose A/B/C/D"
                  : "Compose A/B/C/D"}
            </button>
            <button
              type="button"
              className="btn"
              onClick={compareExample}
              disabled={status === "loading"}
              title="Compose the §21 quartet for the canonical demo congestion charge — no policy needed"
            >
              {status === "loading" && isExample
                ? "Loading example…"
                : "Load example comparison"}
            </button>
            {result && <span className="tag simulated">Simulated</span>}
          </div>

          {!policy && !result && (
            <p className="hint">
              Compile a policy above to compose your own four-way comparison — the
              baseline, your policy, the opposition&rsquo;s amendment, and the
              GOV SIM-optimised alternative — or{" "}
              <em>Load example comparison</em> to read the canonical §28 demo
              quartet with no policy in the store.
            </p>
          )}

          <p className="hint grand-banner">
            One deterministic model, four worlds. World C (opposition amendment)
            and World D (optimiser pick) are re-simulated through the same path as
            World B — no new numeric model, no LLM (SPEC §34).
          </p>

          {status === "error" && (
            <p className="hint error-text">Couldn&rsquo;t compose: {error}</p>
          )}

          {result && status !== "loading" && isExample && (
            <p className="hint brief-example-note">
              <span className="tag generated">example</span>
              The canonical §28 demo congestion charge (from{" "}
              <code>/compare/example</code>) at the endpoint&rsquo;s fixed demo
              horizon and best-balanced World&nbsp;D — <strong>not</strong> the
              policy compiled above. Compile a policy and use{" "}
              <em>Compose A/B/C/D</em> for your own quartet.
            </p>
          )}

          {result && status !== "loading" && (
            <div className="cmp-body">
              <div className="cmp-worlds">
                <span className="cmp-world base" title="Always present (SPEC §21)">
                  A · Baseline
                </span>
                {result.worlds.map((w) => (
                  <WorldChip key={w.id} w={w} />
                ))}
              </div>

              <p className="cmp-horizon">Headline table quoted at {result.horizon.label}</p>

              <div
                className="cmp-table"
                role="table"
                aria-label="Metric by world at the headline horizon"
                style={{ ["--cols" as string]: result.worlds.length }}
              >
                <div className="cmp-row cmp-row-head" role="row">
                  <span role="columnheader">Metric</span>
                  <span role="columnheader" className="cmp-num">
                    A · Baseline
                  </span>
                  {result.worlds.map((w) => (
                    <span role="columnheader" className="cmp-num" key={w.id}>
                      {w.id} · {shortLabel(w.label)}
                    </span>
                  ))}
                </div>
                {result.headline_table.map((row) => (
                  <MetricRow key={row.key} row={row} worlds={result.worlds} />
                ))}
              </div>

              {derivation && (
                <div className="grand-derivation">
                  <h3>How C &amp; D were derived</h3>
                  <div className="grand-deriv-grid">
                    {derivation.world_c && <WorldCCard c={derivation.world_c} />}
                    {derivation.world_d && <WorldDCard d={derivation.world_d} />}
                  </div>
                </div>
              )}

              <p className="hint cmp-note">{result.note}</p>
            </div>
          )}
        </>
    </section>
  );
}

/** Trim the "World X — " prefix the backend puts on grand-world labels. */
function shortLabel(label: string): string {
  const m = label.match(/^World [A-Z]\s*[—-]\s*(.+)$/);
  return m ? m[1] : label;
}

function WorldChip({ w }: { w: CounterfactualWorld }) {
  const roleClass = w.role === "optimised" ? "optimised" : w.role.includes("amendment") ? "amendment" : "intervention";
  return (
    <span className={`cmp-world ${roleClass}`} title={w.changes.join("; ") || w.label}>
      {w.id} · {shortLabel(w.label)}
      {w.changes.length > 0 && (
        <span className="cmp-world-changes">{w.changes.length} edit(s)</span>
      )}
    </span>
  );
}

function MetricRow({ row, worlds }: { row: ComparisonRow; worlds: CounterfactualWorld[] }) {
  const byWorld = new Map(row.cells.map((c) => [c.world_id, c]));
  return (
    <div className="cmp-row" role="row">
      <span role="cell" className="cmp-metric">
        <span className="cmp-metric-label" title={row.key}>
          {row.label}
        </span>
        {row.unit && <span className="cmp-metric-unit">{row.unit}</span>}
      </span>
      <span role="cell" className="cmp-num cmp-baseline">
        {formatNumber(row.baseline_value)}
      </span>
      {worlds.map((w) => {
        const cell = byWorld.get(w.id);
        if (!cell) {
          return (
            <span role="cell" className="cmp-num" key={w.id}>
              —
            </span>
          );
        }
        const d = cell.delta_vs_baseline;
        const dir = d > 0 ? "up" : d < 0 ? "down" : "flat";
        return (
          <span role="cell" className="cmp-num" key={w.id}>
            <span className="cmp-val">{formatNumber(cell.value)}</span>
            <span className={`cmp-delta ${dir}`}>
              {d > 0 ? "▲" : d < 0 ? "▼" : "—"} {d > 0 ? "+" : ""}
              {formatNumber(d)}
              {cell.delta_pct != null
                ? ` (${cell.delta_pct > 0 ? "+" : ""}${cell.delta_pct.toFixed(1)}%)`
                : ""}
            </span>
          </span>
        );
      })}
    </div>
  );
}

function WorldCCard({ c }: { c: GrandWorldC }) {
  const edits = c.amendment ? describeAmendment(c.amendment) : [];
  return (
    <div className="grand-deriv-card">
      <div className="grand-deriv-head">
        <span className="cmp-world amendment">C</span>
        <span className="grand-deriv-role">{c.role}</span>
        <span className="tag estimated" title="Rule over the policy DSL, not an LLM">
          {c.source === "caller" ? "caller-supplied" : "auto-derived"}
        </span>
      </div>
      {c.proposed && c.amendment ? (
        <>
          <p className="grand-deriv-name">{c.amendment.label}</p>
          {edits.length > 0 && (
            <ul className="grand-deriv-list">
              {edits.map((e, i) => (
                <li key={i}>{e}</li>
              ))}
            </ul>
          )}
        </>
      ) : (
        <p className="grand-deriv-name muted">No opposition amendment applies to this policy.</p>
      )}
      <p className="grand-deriv-rationale">{c.rationale}</p>
    </div>
  );
}

function WorldDCard({ d }: { d: GrandWorldD }) {
  const cfg = d.config;
  return (
    <div className="grand-deriv-card">
      <div className="grand-deriv-head">
        <span className="cmp-world optimised">D</span>
        <span className="grand-deriv-role">{d.role}</span>
        <span
          className={`tag ${d.constraints_satisfiable ? "estimated" : "muted"}`}
          title="Whether the optimiser found a feasible policy under the constraints"
        >
          {d.constraints_satisfiable ? "feasible set found" : "constraints unsatisfiable"}
        </span>
      </div>
      <dl className="grand-deriv-kv">
        <div>
          <dt>Selected via</dt>
          <dd>{prettySelection(d.selection)}</dd>
        </div>
        <div>
          <dt>Objective</dt>
          <dd>{formatKV(d.objective) || "best balanced (default)"}</dd>
        </div>
        <div>
          <dt>Constraints</dt>
          <dd>{formatKV(d.constraints) || "none"}</dd>
        </div>
        <div>
          <dt>Candidates</dt>
          <dd>
            {d.n_feasible}/{d.n_candidates} feasible
          </dd>
        </div>
      </dl>
      {cfg ? (
        <ul className="grand-deriv-list">
          <li>Intervention: {cfg.intervention_type.replace(/_/g, " ")}</li>
          {cfg.charge_amount != null && <li>Charge: {formatNumber(cfg.charge_amount)}/day</li>}
          {cfg.pedestrianised && <li>Pedestrianised cordon (car ban)</li>}
          <li>Reinvest {Math.round(cfg.public_transport_share * 100)}% of revenue in transit</li>
          <li>{cfg.exempt_low_income ? "Exempt low-income commuters" : "No exemptions"}</li>
        </ul>
      ) : (
        <p className="grand-deriv-name muted">
          Optimiser returned no candidate — World D omitted.
        </p>
      )}
      {cfg && d.feasible != null && (
        <p className="grand-deriv-rationale">
          Chosen policy {d.feasible ? "meets" : "does not meet"} all supplied constraints.
        </p>
      )}
    </div>
  );
}

/** Human summary of an Amendment's structured edits (no free text). */
function describeAmendment(a: {
  exempt_low_income?: boolean;
  exempt_residents?: boolean;
  set_charge_amount?: number | null;
  charge_multiplier?: number | null;
  set_public_transport_share?: number | null;
}): string[] {
  const out: string[] = [];
  if (a.exempt_low_income) out.push("Exempt low-income commuters");
  if (a.exempt_residents) out.push("Exempt residents");
  if (a.set_charge_amount != null) out.push(`Set charge to ${formatNumber(a.set_charge_amount)}/day`);
  if (a.charge_multiplier != null) out.push(`Scale charge ×${a.charge_multiplier}`);
  if (a.set_public_transport_share != null)
    out.push(`Reinvest ${Math.round(a.set_public_transport_share * 100)}% in transit`);
  return out;
}

function prettySelection(slot: string): string {
  const map: Record<string, string> = {
    best_balanced: "best-balanced recommendation",
    largest_emissions_reduction: "largest emissions cut",
    most_equitable: "most equitable",
    cheapest: "cheapest",
    pareto_front: "Pareto frontier (fallback)",
    first_candidate: "first candidate (fallback)",
    none: "no selection",
  };
  return map[slot] ?? slot.replace(/_/g, " ");
}

function formatKV(obj: Record<string, number>): string {
  const entries = Object.entries(obj);
  if (entries.length === 0) return "";
  return entries.map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(", ");
}

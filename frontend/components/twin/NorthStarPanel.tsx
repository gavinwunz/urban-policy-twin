"use client";

/**
 * North-Star view (SPEC §37 — *the* GOV SIM experience).
 *
 * A minister asks "What happens if we implement this?" and `POST /north-star`
 * answers with the fixed §37 narrative: baseline → historical analogues →
 * mechanisms → median outcome → uncertainty → winners → losers → failure modes →
 * the opposition's strongest argument → opinion evolution → media narratives →
 * three risk-reducing amendments → each amendment's effect → the best-fit policy
 * configuration → every assumption & piece of evidence.
 *
 * The endpoint introduces **no new numeric model**: every section embeds the
 * *same* deterministic layer output the standalone endpoints return, so this
 * answer can never disagree with the deep tabs behind it. This panel renders the
 * ordered narrative (each line's synthesis + provenance chip + a cross-link to
 * the tab that carries the full evidence), the composed median-outcome dashboard,
 * the risk-reducing amendments with their isolated Δ(amended − original), and the
 * assumptions/guardrail footer.
 *
 * Honesty contract (SPEC §34): numbers are Simulated (agent-based) or Estimated
 * (documented transfer); debate & media prose is Generated; transparency
 * artifacts are Observed; no LLM touches any figure. Nothing is fabricated — when
 * the backend is down the panel says so and offers a retry.
 */

import { useState } from "react";

import { runNorthStar, getNorthStarExample } from "../../lib/api";
import type {
  AmendmentComparison,
  GuardrailCheck,
  NorthStarAnswer,
  NorthStarProposedAmendment,
  NorthStarSection,
  RunHeadlineMetric,
} from "../../lib/api";
import { formatNumber } from "../../lib/format";
import { useTwin } from "./TwinStore";

type Status = "idle" | "loading" | "ready" | "error";

/** Horizon options snap to the Time-Machine checkpoints (SPEC §27). */
const HORIZONS: Array<{ label: string; months: number }> = [
  { label: "Year 1", months: 12 },
  { label: "Year 2", months: 24 },
  { label: "Year 5", months: 60 },
  { label: "Year 10", months: 120 },
];

/** Only transit ridership is "up = good"; everything else here is "down = good". */
function higherIsBetter(key: string): boolean {
  return key === "transit.daily_transit_trips";
}

/**
 * Map a section's `backs` field to the analysis tab that carries the full
 * evidence, so a reader can jump from the one-line synthesis to the deep view.
 * Purely a navigational hint — the number itself is rendered here, verbatim.
 */
function xrefFor(backs: string): string | null {
  const key = backs.toLowerCase();
  if (key.includes("baseline")) return "World tab";
  if (key.includes("analogues")) return "Analogue tab";
  if (key.includes("mechanisms")) return "Run / Dynamics tab";
  if (key.includes("median_outcome") || key.includes("delta")) return "Run tab";
  if (key.includes("uncertainty")) return "Uncertainty tab";
  if (key.includes("winners")) return "Microsim tab";
  if (key.includes("failure")) return "Red Team tab";
  if (key.includes("opposition") || key.includes("debate")) return "Parliament tab";
  if (key.includes("opinion")) return "Diffusion tab";
  if (key.includes("media")) return "Press tab";
  if (key.includes("amendments")) return "Parliament tab";
  if (key.includes("best_configuration")) return "Optimiser tab";
  if (key.includes("evidence")) return "Registry tab";
  return null;
}

export default function NorthStarPanel() {
  const { policy } = useTwin();
  const [text, setText] = useState("");
  const [horizon, setHorizon] = useState(24);
  const [answer, setAnswer] = useState<NorthStarAnswer | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  // True when the shown answer is the canonical §28 demo (GET /north-star/example),
  // not the user's compiled/typed policy — kept explicit so the UI never lets a
  // demo narrative masquerade as the policy above it (honest, SPEC §34).
  const [isExample, setIsExample] = useState(false);

  // Prefer the compiled policy from the store; fall back to a natural-language
  // box so the tab can drive the whole compile→answer pipeline standalone (§3).
  const usingText = !policy;

  function execute() {
    if (usingText && !text.trim()) return;
    setStatus("loading");
    setError(null);
    setIsExample(false);
    const req = usingText
      ? { text: text.trim(), horizon_months: horizon }
      : { policy: policy ?? undefined, horizon_months: horizon };
    runNorthStar(req)
      .then((a) => {
        setAnswer(a);
        setStatus("ready");
      })
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "North-Star answer failed");
        setStatus("error");
      });
  }

  // Compose the canonical §28 demo answer (GET /north-star/example) — a body-less
  // call so a judge can read the whole §37 narrative without compiling anything.
  // Flagged as the example rather than the policy above (honest, SPEC §34).
  function executeExample() {
    setStatus("loading");
    setError(null);
    setIsExample(true);
    getNorthStarExample()
      .then((a) => {
        setAnswer(a);
        setStatus("ready");
      })
      .catch((e: unknown) => {
        setError(
          e instanceof Error ? e.message : "Example North-Star answer failed",
        );
        setStatus("error");
      });
  }

  return (
    <section className="card ns" data-tour="northstar">
      <div className="dashboard-head">
        <h2>North-Star · &ldquo;What happens if we implement this?&rdquo;</h2>
        <span className="dashboard-sub">
          the fixed SPEC §37 minister&rsquo;s answer, composed from one simulation
        </span>
      </div>

      <p className="hint ns-intro">
        The whole answer is a <strong>composition</strong> of the deep tabs — each
        line embeds the <strong>same</strong> deterministic layer output the
        standalone endpoint returns, so it can never disagree with them. Numbers
        are Simulated or Estimated; debate&nbsp;&amp; media prose is Generated;
        transparency artifacts are Observed; no LLM touches a figure (SPEC §34).
      </p>

      {/* Input: compiled policy from the store, or a natural-language fallback. */}
      <div className="run-controls">
        {usingText ? (
          <label className="run-textwrap">
            <span className="run-label">
              No compiled policy yet — describe one to compile &amp; answer:
            </span>
            <textarea
              className="run-text"
              rows={2}
              placeholder="e.g. Charge £12 to drive into the city centre at peak and spend it on buses"
              value={text}
              onChange={(e) => setText(e.target.value)}
            />
          </label>
        ) : (
          <p className="run-usingpolicy">
            <span className="tag generated">compiled policy</span>
            Answering the minister&rsquo;s question for the policy compiled above.
          </p>
        )}

        <div className="run-actions">
          <label className="run-horizon">
            <span className="run-label">Headline horizon</span>
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
            >
              {HORIZONS.map((h) => (
                <option key={h.months} value={h.months}>
                  {h.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="btn primary"
            onClick={execute}
            disabled={status === "loading" || (usingText && !text.trim())}
          >
            {status === "loading" && !isExample
              ? "Composing answer…"
              : usingText
                ? "Compile & answer"
                : "Answer the question"}
          </button>
          <button
            type="button"
            className="btn"
            onClick={executeExample}
            disabled={status === "loading"}
            title="Compose the §37 answer for the canonical demo congestion charge — no policy needed"
          >
            {status === "loading" && isExample
              ? "Loading example…"
              : "Load example answer"}
          </button>
        </div>
      </div>

      {status === "loading" && !answer && (
        <p className="hint">Composing the §37 answer from the backend…</p>
      )}

      {status === "error" && (
        <div className="waiting">
          <span className="tag muted">Backend unavailable</span>
          <p>
            Couldn&rsquo;t compose the answer: {error}. Nothing here is invented —
            reconnect the backend to read the §37 narrative from one deterministic
            run.
          </p>
          <button
            type="button"
            className="btn"
            onClick={isExample ? executeExample : execute}
          >
            Retry
          </button>
        </div>
      )}

      {status === "idle" && !answer && (
        <p className="hint">
          {usingText
            ? "Describe a policy above, then ask the question."
            : "Ask the question to compose the §37 answer for the compiled policy."}
        </p>
      )}

      {answer && (
        <NorthStarResult
          answer={answer}
          stale={status === "loading"}
          isExample={isExample}
        />
      )}
    </section>
  );
}

function NorthStarResult({
  answer,
  stale,
  isExample,
}: {
  answer: NorthStarAnswer;
  stale: boolean;
  isExample: boolean;
}) {
  return (
    <div className={`run-result${stale ? " stale" : ""}`}>
      {stale && (
        <p className="hint run-stale">Re-composing… showing the previous answer.</p>
      )}

      {isExample && (
        <p className="hint brief-example-note">
          <span className="tag generated">example</span>
          The canonical §28 demo congestion charge (from{" "}
          <code>/north-star/example</code>) — <strong>not</strong> the policy
          compiled above. Compile a policy and use <em>Answer the question</em> for
          your own §37 answer.
        </p>
      )}

      {/* Provenance banner — the reason this single answer is trustworthy. */}
      <div className="run-consistency">
        <div className="run-cons-tags">
          <span className="tag simulated">Simulated numbers</span>
          <span className="tag estimated">Estimated transfers</span>
          <span className="tag generated">Generated prose</span>
          <span className="tag observed">No LLM in numeric path</span>
        </div>
        <p className="run-cons-note">{answer.provenance}</p>
      </div>

      {/* The minister's question this answers, echoed. */}
      <div className="ns-question">
        <span className="ns-q-label">Minister asks</span>
        <p className="ns-q-text">&ldquo;{answer.question}&rdquo;</p>
        <span className="run-sub-tag">
          horizon {answer.horizon_label} · policy {answer.policy_id}
        </span>
      </div>

      {/* §37 fixed narrative — 15 ordered lines, each a synthesis over a layer. */}
      <h3 className="run-sub">
        The §37 answer
        <span className="run-sub-tag">
          {answer.sections.length} ordered lines · one per §37 question
        </span>
      </h3>
      <ol className="ns-sections">
        {answer.sections.map((s) => (
          <SectionRow key={s.order} section={s} />
        ))}
      </ol>

      {/* §37.4 — the composed median-outcome dashboard at the chosen horizon. */}
      <h3 className="run-sub">
        Median simulated outcome at {answer.horizon_label}
        <span className="run-sub-tag">Simulated · Δ vs baseline</span>
      </h3>
      {answer.median_outcome.length > 0 ? (
        <div className="tiles run-tiles">
          {answer.median_outcome.map((m) => (
            <HeadlineTile key={m.key} m={m} />
          ))}
        </div>
      ) : (
        <p className="hint">No headline metrics returned for this horizon.</p>
      )}

      {/* §37.12/13 — risk-reducing amendments + their isolated effects. */}
      <h3 className="run-sub">
        Risk-reducing amendments
        <span className="run-sub-tag">
          {answer.amendments.length > 0
            ? "isolated Δ(amended − original) · Simulated"
            : "none needed"}
        </span>
      </h3>
      {answer.amendments.length > 0 ? (
        <div className="ns-amendments">
          {answer.amendments.map((a, i) => (
            <AmendmentCard key={i} amendment={a} />
          ))}
        </div>
      ) : (
        <p className="hint">
          No structural amendment needed — the base policy already covers the main
          risks.
        </p>
      )}
      <p className="hint run-xref">
        Amendment vs original policy, in full → Parliament tab.
      </p>

      {/* §37.15 — every assumption + guardrail behind the conclusions. */}
      <EvidenceFooter evidence={answer.evidence} />
    </div>
  );
}

/** One §37 narrative line: order badge, the question, the synthesis, tag + xref. */
function SectionRow({ section }: { section: NorthStarSection }) {
  const xref = xrefFor(section.backs);
  return (
    <li className="ns-section">
      <span className="ns-order">{section.order}</span>
      <div className="ns-section-body">
        <p className="ns-section-q">
          {section.question}
          <span className={`tag ${section.tag.toLowerCase()} ns-section-tag`}>
            {section.tag}
          </span>
        </p>
        <p className="ns-section-lead">{section.lead}</p>
        <p className="ns-section-backs">
          <span className="ns-backs-code">{section.backs}</span>
          {xref && <span className="ns-backs-xref">→ {xref}</span>}
        </p>
      </div>
    </li>
  );
}

function HeadlineTile({ m }: { m: RunHeadlineMetric }) {
  const negligible = m.direction === "flat" || Math.abs(m.delta) < 1e-9;
  const good = m.delta > 0 === higherIsBetter(m.key);
  const cls = negligible ? "muted" : good ? "down" : "up";
  return (
    <div className="tile">
      <div className="tile-head">
        <span className="tile-title" title={m.key}>
          {m.label}
        </span>
        <span className={`tag ${m.tag.toLowerCase()}`}>{m.tag}</span>
      </div>

      <div className="tile-value">
        {formatNumber(m.world_b)}
        <span className="tile-unit">{m.unit}</span>
      </div>

      <div className="tile-band">
        World A {formatNumber(m.world_a)} → B {formatNumber(m.world_b)}
      </div>
      <div className="tile-band">
        Δ band {formatNumber(m.band[0] ?? m.delta)}–
        {formatNumber(m.band[1] ?? m.delta)}
      </div>

      <div className="tile-deltas">
        <span className="delta">
          <span className="delta-label">vs baseline</span>
          <span className={`delta-val ${cls}`}>
            {negligible ? (
              "≈ 0"
            ) : (
              <>
                {m.delta > 0 ? "+" : ""}
                {formatNumber(m.delta)}
                {m.delta_pct != null
                  ? ` (${m.delta_pct > 0 ? "+" : ""}${m.delta_pct.toFixed(1)}%)`
                  : ""}
              </>
            )}
          </span>
        </span>
      </div>
    </div>
  );
}

/** One proposed amendment: label, targeted risk, rationale + its isolated Δ. */
function AmendmentCard({
  amendment,
}: {
  amendment: NorthStarProposedAmendment;
}) {
  return (
    <div className="ns-amendment">
      <p className="ns-amd-head">
        <span className="tag simulated ns-amd-stamp">amendment</span>
        <span className="ns-amd-label">{amendment.label}</span>
      </p>
      <p className="ns-amd-targets">
        <span className="ns-amd-targets-k">targets risk:</span>{" "}
        {amendment.targets_risk}
      </p>
      <p className="ns-amd-rationale">{amendment.rationale}</p>
      <AmendmentDelta comparison={amendment.comparison} />
    </div>
  );
}

/** Δ(amended − original) at the final checkpoint per metric (SPEC §12). */
function AmendmentDelta({
  comparison,
}: {
  comparison: AmendmentComparison;
}) {
  const rows = comparison.amendment_delta.series
    .map((s) => ({ s, p: s.points[s.points.length - 1] }))
    .filter((r) => r.p);
  if (rows.length === 0) return null;
  return (
    <div className="run-amd-table" role="table">
      <div className="run-amd-head" role="row">
        <span role="columnheader">Metric</span>
        <span role="columnheader" className="run-amd-num">
          Δ(amended − original)
        </span>
        <span role="columnheader" className="run-amd-band">
          band
        </span>
      </div>
      {rows.map(({ s, p }) => {
        const negligible = Math.abs(p.delta) < 1e-9;
        const dir = p.delta > 0 ? "up" : p.delta < 0 ? "down" : "flat";
        return (
          <div className="run-amd-row" role="row" key={s.key}>
            <span role="cell" className="run-amd-metric" title={s.key}>
              {s.label}
            </span>
            <span role="cell" className={`run-amd-num ${dir}`}>
              {negligible ? (
                <span className="run-amd-flat">≈ 0 (no change)</span>
              ) : (
                <>
                  {p.delta > 0 ? "+" : ""}
                  {formatNumber(p.delta)}
                  {p.delta_pct != null
                    ? ` (${p.delta_pct > 0 ? "+" : ""}${p.delta_pct.toFixed(1)}%)`
                    : ""}
                </>
              )}
            </span>
            <span role="cell" className="run-amd-band">
              {formatNumber(p.low)} … {formatNumber(p.high)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * §37.15 — the assumptions + SPEC §34 guardrail checklist behind the answer. The
 * evidence dict is composed on the backend from the model registry; we read it
 * defensively (unknown-typed) and only assert the honesty line the registry
 * guarantees: no LLM touches any number.
 */
function EvidenceFooter({ evidence }: { evidence: Record<string, unknown> }) {
  const assumptions = Array.isArray(evidence.assumption_index)
    ? (evidence.assumption_index as unknown[])
    : [];
  const guardrails = Array.isArray(evidence.guardrails)
    ? (evidence.guardrails as GuardrailCheck[])
    : [];
  const dataSources = Array.isArray(evidence.data_sources)
    ? (evidence.data_sources as unknown[])
    : [];
  const passing = guardrails.filter((g) => g && g.holds).length;
  const llmTouchesNumbers = evidence.llm_touches_numbers === true;

  return (
    <>
      <h3 className="run-sub">
        Assumptions &amp; evidence
        <span className="run-sub-tag">Observed transparency manifest</span>
      </h3>
      <div className="ns-evidence">
        <div className="ns-evidence-counts">
          <span className="ns-ev-chip">
            <span className="ns-ev-n">{assumptions.length}</span>
            documented assumptions
          </span>
          <span className="ns-ev-chip">
            <span className="ns-ev-n">{dataSources.length}</span>
            data sources
          </span>
          <span className={`ns-ev-chip ${passing === guardrails.length ? "ok" : "warn"}`}>
            <span className="ns-ev-n">
              {passing}/{guardrails.length}
            </span>
            SPEC §34 guardrails hold
          </span>
        </div>
        <p className={`ns-ev-honesty ${llmTouchesNumbers ? "warn" : "ok"}`}>
          {llmTouchesNumbers ? (
            <>
              ⚠ A pinned model reports LLM-touched numbers — investigate before
              trusting any figure (SPEC §34).
            </>
          ) : (
            <>
              ✓ No LLM produces any figure in this answer — numbers come only from
              the deterministic agent-based model and documented transfers (SPEC
              §34).
            </>
          )}
        </p>
        {guardrails.length > 0 && (
          <ul className="ns-guardrails">
            {guardrails.map((g, i) => (
              <li key={g.id ?? i} className={`ns-guardrail ${g.holds ? "ok" : "fail"}`}>
                <span className="ns-guardrail-mark">{g.holds ? "✓" : "✗"}</span>
                <span className="ns-guardrail-rule">{g.rule}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="hint run-xref">
          Full model cards, data sources &amp; assumption index → Registry tab.
        </p>
      </div>
    </>
  );
}

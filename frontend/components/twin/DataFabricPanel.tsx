"use client";

/**
 * Data Fabric view (SPEC §4): the dataset-level answer to "where did every number
 * ultimately come from?". `GET /data-fabric` returns a machine-readable catalogue
 * of every dataset the engine reads — each carrying the full §4 provenance record
 * (publisher, source, variables, missingness, a content-hash revision and its
 * transformation history) built *live* from the file bytes so it can never drift
 * from what the engine actually runs — plus the supported-format contract and the
 * harmonisation-pipeline lineage.
 *
 * This tab is policy-independent (it describes the data, not a run) and loads on
 * mount. It is itself Observed — it describes files on disk, it doesn't simulate.
 * The Auckland zone system is modelled, so the datasets themselves are tagged
 * Simulated/assumption-set and real-world sources are listed as the *schemas* the
 * data is shaped like, never claimed as live feeds (SPEC §4/§34). If the backend
 * is down we say so rather than inventing a catalogue.
 */

import { useEffect, useState } from "react";

import { getDataFabric } from "../../lib/api";
import type {
  DataFabric,
  DatasetCard,
  FormatSupport,
  HarmonisationStep,
} from "../../lib/api";

type Status = "idle" | "loading" | "ready" | "error";

/** Short, human label for the content-hash revision (drop the `sha256:` prefix). */
function shortRev(rev: string): string {
  return rev.replace(/^sha256:/, "");
}

export default function DataFabricPanel() {
  const [fabric, setFabric] = useState<DataFabric | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);

  function load(signal?: AbortSignal) {
    setStatus("loading");
    setError(null);
    getDataFabric(signal)
      .then((f) => {
        setFabric(f);
        // Open the first dataset by default so the panel isn't a wall of headers.
        setOpenId((prev) => prev ?? f.datasets[0]?.id ?? null);
        setStatus("ready");
      })
      .catch((e: unknown) => {
        if (signal?.aborted) return;
        setError(e instanceof Error ? e.message : "Data Fabric unavailable");
        setStatus("error");
      });
  }

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, []);

  return (
    <section className="card fabric">
      <div className="dashboard-head">
        <h2>Data Fabric</h2>
        <span className="dashboard-sub">
          Dataset ingestion &amp; provenance · where every number comes from (SPEC §4)
        </span>
      </div>

      {status === "loading" && !fabric && (
        <p className="hint">Loading the dataset provenance manifest from the backend…</p>
      )}

      {status === "error" && (
        <div className="waiting">
          <span className="tag muted">Backend unavailable</span>
          <p>
            Couldn&rsquo;t load the Data Fabric: {error}. Nothing here is invented —
            reconnect the backend to read the live catalogue (record counts,
            missingness and content hashes are computed on disk).
          </p>
          <button type="button" className="btn" onClick={() => load()}>
            Retry
          </button>
        </div>
      )}

      {fabric && (
        <div className="fabric-body">
          <div className="fabric-topline">
            <span className={`tag ${fabric.provenance.toLowerCase()}`}>
              {fabric.provenance}
            </span>
            <span className="fabric-ver">v{fabric.app_version}</span>
            <span className="fabric-gen">{fabric.generated_from}</span>
          </div>
          <p className="hint fabric-note">{fabric.note}</p>

          {/* The §4 lineage contract, front and centre. */}
          <div className="fabric-lineage" title="SPEC §4: no model output exists without a traceable path back to source">
            {fabric.lineage_contract.split("→").map((seg, i, arr) => (
              <span key={i} className="fabric-lineage-seg">
                {seg.trim()}
                {i < arr.length - 1 && <span className="fabric-arrow" aria-hidden>→</span>}
              </span>
            ))}
          </div>

          {/* Summary counts */}
          {Object.keys(fabric.counts).length > 0 && (
            <div className="fabric-counts">
              {Object.entries(fabric.counts).map(([k, v]) => (
                <div className="fabric-count" key={k}>
                  <span className="fabric-count-val">{v.toLocaleString()}</span>
                  <span className="fabric-count-label">{k.replace(/_/g, " ")}</span>
                </div>
              ))}
            </div>
          )}

          {/* Dataset catalogue — the core of the tab. */}
          <h3 className="fabric-sub">Datasets · {fabric.datasets.length}</h3>
          <div className="fabric-datasets">
            {fabric.datasets.map((d) => (
              <DatasetView
                key={d.id}
                d={d}
                open={openId === d.id}
                onToggle={() =>
                  setOpenId((cur) => (cur === d.id ? null : d.id))
                }
              />
            ))}
          </div>

          {/* Supported-format contract */}
          {fabric.format_support.length > 0 && (
            <>
              <h3 className="fabric-sub">
                Ingestion formats · {fabric.format_support.length}
              </h3>
              <div className="fabric-formats">
                {fabric.format_support.map((f) => (
                  <FormatView key={f.format} f={f} />
                ))}
              </div>
            </>
          )}

          {/* Harmonisation pipeline lineage */}
          {fabric.harmonisation.length > 0 && (
            <>
              <h3 className="fabric-sub">
                Harmonisation pipeline · {fabric.harmonisation.filter((h) => h.implemented).length}
                /{fabric.harmonisation.length} implemented
              </h3>
              <div className="fabric-harm">
                {fabric.harmonisation.map((h) => (
                  <HarmView key={h.step} h={h} />
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}

function DatasetView({
  d,
  open,
  onToggle,
}: {
  d: DatasetCard;
  open: boolean;
  onToggle: () => void;
}) {
  const period =
    d.time_start || d.time_end
      ? `${d.time_start ?? "…"} → ${d.time_end ?? "…"}`
      : null;
  return (
    <div className={`fabric-ds${open ? " open" : ""}`}>
      <button
        type="button"
        className="fabric-ds-head"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="fabric-ds-caret" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
        <span className="fabric-ds-title">{d.title}</span>
        <span className="fabric-ds-meta">
          <span className={`fabric-kind ${d.kind}`}>{d.kind}</span>
          <span className="fabric-ds-count">
            {d.record_count.toLocaleString()} {d.format === "assumption set" ? "params" : "records"}
          </span>
          <span className={`tag ${d.tag.toLowerCase()}`}>{d.tag}</span>
        </span>
      </button>

      {open && (
        <div className="fabric-ds-body">
          <p className="fabric-ds-pub">
            <span className="fabric-ds-publisher">{d.publisher}</span>
            {" · "}
            {d.source_url && <span className="fabric-ds-src">{d.source_url}</span>}
          </p>

          {/* Auditable file-level facts, built live from the bytes. */}
          <div className="fabric-facts">
            <Fact label="format" value={d.format} />
            <Fact label="records" value={d.record_count.toLocaleString()} />
            <Fact
              label="missingness"
              value={`${d.missingness.toFixed(1)}%`}
              tone={d.missingness > 0 ? "warn" : "ok"}
            />
            <Fact label="revision" value={shortRev(d.revision)} mono title={d.revision} />
            {d.geographic_scope && <Fact label="scope" value={d.geographic_scope} />}
            {d.spatial_resolution && (
              <Fact label="resolution" value={d.spatial_resolution} />
            )}
            {d.frequency && <Fact label="frequency" value={d.frequency} />}
            {period && <Fact label="period" value={period} />}
            {d.units && <Fact label="units" value={d.units} />}
            {d.license && <Fact label="license" value={d.license} />}
            {d.retrieved_at && <Fact label="retrieved" value={d.retrieved_at} />}
          </div>

          <p className="fabric-conf">
            <span className="fabric-conf-label">confidence</span> {d.confidence}
          </p>

          {/* Variables (the §4 variable list). */}
          {d.variables.length > 0 && (
            <div className="fabric-vars">
              <div className="fabric-var fabric-var-head" role="row">
                <span>Variable</span>
                <span>Type</span>
                <span>Description</span>
                <span>Missing</span>
              </div>
              {d.variables.map((v) => (
                <div className="fabric-var" key={v.name} role="row">
                  <span className="fabric-var-name" title={v.name}>
                    {v.name}
                    {v.unit ? <span className="fabric-var-unit"> {v.unit}</span> : null}
                  </span>
                  <span className="fabric-var-type">{v.dtype}</span>
                  <span className="fabric-var-desc">{v.description}</span>
                  <span
                    className={`fabric-var-miss${v.missing_pct > 0 ? " warn" : ""}`}
                  >
                    {v.missing_pct.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          )}

          {/* Transformation history — the lineage trace for this dataset. */}
          {d.transformation_history.length > 0 && (
            <div className="fabric-trans">
              <span className="fabric-trans-title">Transformation history</span>
              <ol className="fabric-trans-list">
                {d.transformation_history.map((t, i) => (
                  <li key={i} className="fabric-trans-step">
                    <span className="fabric-trans-what">{t.step}</span>
                    <span className="fabric-trans-by">{t.by}</span>
                    <span className={`tag ${t.tag.toLowerCase()}`}>{t.tag}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* Real-world analogues: schemas, NOT live sources (honesty). */}
          {d.real_world_analogues.length > 0 && (
            <div className="fabric-analogues">
              <span className="fabric-analogues-label">
                schema-compatible with (not a live source)
              </span>
              <ul className="fabric-analogues-list">
                {d.real_world_analogues.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Fact({
  label,
  value,
  tone,
  mono,
  title,
}: {
  label: string;
  value: string;
  tone?: "ok" | "warn";
  mono?: boolean;
  title?: string;
}) {
  return (
    <div className="fabric-fact" title={title}>
      <span className="fabric-fact-label">{label}</span>
      <span
        className={`fabric-fact-val${mono ? " mono" : ""}${
          tone ? ` ${tone}` : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

function FormatView({ f }: { f: FormatSupport }) {
  return (
    <div className={`fabric-fmt ${f.status}`} title={f.note}>
      <span className="fabric-fmt-name">{f.format}</span>
      <span className={`fabric-fmt-status ${f.status}`}>{f.status}</span>
    </div>
  );
}

function HarmView({ h }: { h: HarmonisationStep }) {
  return (
    <div className={`fabric-hstep ${h.implemented ? "on" : "off"}`}>
      <span className="fabric-hstep-mark" aria-hidden>
        {h.implemented ? "✓" : "○"}
      </span>
      <div className="fabric-hstep-text">
        <p className="fabric-hstep-step">
          {h.step}
          <span className="fabric-hstep-flag">
            {h.implemented ? "implemented" : "declared"}
          </span>
        </p>
        <p className="fabric-hstep-where">{h.where}</p>
        {h.note && <p className="fabric-hstep-note">{h.note}</p>}
      </div>
    </div>
  );
}

"use client";

/**
 * The run console: the whole pipeline executing, one stage at a time.
 *
 * This is the view that answers "how does it actually work". Each row is a real
 * call — the byte counts are what came over the wire, the milliseconds are
 * measured at the call site, and the artefacts under each row are pulled out of
 * the real response. Nothing is on a timer pretending to be work.
 *
 * It takes several seconds, and that is honest rather than theatrical: eight
 * dependent stages across a compiler, a model registry, an LSTM, an
 * agent-based simulation, an opinion model, a division and a media generator.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { PolicyDSL, SimulateResponse } from "../../lib/api";
import {
  formatBytes,
  initialStages,
  runPipeline,
  type PipelineResult,
  type Stage,
} from "../../lib/pipeline";
import { STATUS } from "../charts/palette";
import { useTwin } from "../twin/TwinStore";

const DEMO_POLICY =
  "Introduce a charge of 12 credits on private vehicles entering the central " +
  "business district between 7am and 7pm on weekdays, starting 2026-01-01. " +
  "Exempt buses, taxis, and blue-badge holders. Spend 70% of the revenue on " +
  "public transport and 20% on cycling and walking. The aim is to cut " +
  "congestion and emissions without raising costs for low-income residents by " +
  "more than 5%.";

export interface PipelineRunProps {
  /** Called with the finished results so sibling panels can render them. */
  onComplete?: (result: PipelineResult) => void;
}

export default function PipelineRun({ onComplete }: PipelineRunProps) {
  const { setPolicy, setSim } = useTwin();
  const [text, setText] = useState(DEMO_POLICY);
  const [stages, setStages] = useState<Stage[]>(initialStages);
  const [running, setRunning] = useState(false);
  const [totalMs, setTotalMs] = useState<number | null>(null);
  const ctrlRef = useRef<AbortController | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => () => ctrlRef.current?.abort(), []);

  const start = useCallback(async () => {
    ctrlRef.current?.abort();
    const ctrl = new AbortController();
    ctrlRef.current = ctrl;

    setRunning(true);
    setTotalMs(null);
    setStages(initialStages());

    const t0 = performance.now();
    const result = await runPipeline(text, setStages, ctrl.signal);
    if (ctrl.signal.aborted) return;

    // Publish into the shared twin store so every downstream panel — the
    // newsroom, the referendum, the division, the stress tests — is looking at
    // the policy that was just run, rather than waiting for a second compile.
    if (result.policy) {
      setPolicy(result.policy as PolicyDSL);
      if (result.simulation) {
        setSim(result.simulation as SimulateResponse, {
          label: "Pipeline run",
          amended: false,
        });
      }
    }

    setTotalMs(Math.round(performance.now() - t0));
    setRunning(false);
    onComplete?.(result);
  }, [text, onComplete, setPolicy, setSim]);

  // Keep the newest running stage in view without yanking the whole page.
  useEffect(() => {
    const el = logRef.current?.querySelector(".stage.running");
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [stages]);

  const done = stages.filter((s) => s.status === "done").length;
  const failed = stages.filter((s) => s.status === "failed").length;
  const totalBytes = stages.reduce((n, s) => n + (s.bytes ?? 0), 0);
  const progress = (done / stages.length) * 100;

  return (
    <div className="pipeline">
      <div className="pipeline-input">
        <label htmlFor="pipeline-policy" className="pipeline-label">
          Policy prompt
        </label>
        <textarea
          id="pipeline-policy"
          className="policy-input"
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={running}
          spellCheck={false}
        />
        <div className="pipeline-actions">
          <button
            type="button"
            className="btn primary"
            onClick={start}
            disabled={running || text.trim().length < 20}
          >
            {running ? "Running…" : "Run full simulation"}
          </button>
          {running && (
            <button
              type="button"
              className="btn"
              onClick={() => {
                ctrlRef.current?.abort();
                setRunning(false);
              }}
            >
              Stop
            </button>
          )}
          <span className="pipeline-meta">
            {done}/{stages.length} stages
            {totalBytes > 0 && ` · ${formatBytes(totalBytes)} transferred`}
            {totalMs !== null && ` · ${(totalMs / 1000).toFixed(1)}s total`}
            {failed > 0 && ` · ${failed} failed`}
          </span>
        </div>
        <div className="pipeline-progress" aria-hidden>
          <span style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className="pipeline-log" ref={logRef}>
        {stages.map((s, i) => (
          <StageRow key={s.id} stage={s} index={i} />
        ))}
      </div>

      <p className="pipeline-note">
        Every row is a real request. Byte counts are what came over the wire and
        timings are measured at the call site — open the network tab and the
        numbers will match. The compiled policy is written to MongoDB{" "}
        <code>policies</code> and the simulation to <code>runs</code>, so any
        result here can be traced back afterwards.
      </p>
    </div>
  );
}

function StageRow({ stage, index }: { stage: Stage; index: number }) {
  const s = stage;
  const label = s.status === "done" ? s.doneLabel : s.activeLabel;

  return (
    <div className={`stage ${s.status}`}>
      <div className="stage-gutter" aria-hidden>
        <span className="stage-marker">
          {s.status === "done"
            ? "✓"
            : s.status === "failed"
              ? "✕"
              : s.status === "running"
                ? ""
                : "○"}
        </span>
        {index < 7 && <span className="stage-rail" />}
      </div>

      <div className="stage-body">
        <div className="stage-head">
          <span className="stage-label">{label}</span>
          {s.elapsedMs !== undefined && (
            <span className="stage-timing">
              {s.elapsedMs >= 1000
                ? `${(s.elapsedMs / 1000).toFixed(2)}s`
                : `${s.elapsedMs} ms`}
              {s.bytes ? ` · ${formatBytes(s.bytes)}` : ""}
            </span>
          )}
        </div>

        <p className="stage-detail">{s.detail}</p>

        {s.status === "failed" && (
          <p className="stage-error" style={{ color: STATUS.serious }}>
            {s.error}
          </p>
        )}

        {s.artifacts && s.artifacts.length > 0 && (
          <dl className="stage-artifacts">
            {s.artifacts.map((a) => (
              <div key={a.label}>
                <dt>{a.label}</dt>
                <dd>{a.value}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
    </div>
  );
}

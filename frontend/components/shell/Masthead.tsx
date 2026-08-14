"use client";

/**
 * The masthead: brand, live system status, and the positioning statement.
 *
 * Designed to read as an instrument's title bar rather than a landing page. The
 * status strip is real — it polls /health and the model registry, so the row of
 * indicators is telling you the state of the running system, not decorating the
 * page with plausible-looking chrome. A status light that cannot go red is a
 * lie, so these do.
 */

import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../lib/api";
import { getLeaderboard, type Leaderboard } from "../../lib/ml";

interface Health {
  status: string;
  service?: string;
  version?: string;
}

type Probe = "checking" | "up" | "down";

export default function Masthead() {
  const [engine, setEngine] = useState<Probe>("checking");
  const [health, setHealth] = useState<Health | null>(null);
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [models, setModels] = useState<Probe>("checking");

  useEffect(() => {
    const ctrl = new AbortController();

    fetch(`${API_BASE_URL}/health`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((h: Health) => {
        setHealth(h);
        setEngine("up");
      })
      .catch(() => !ctrl.signal.aborted && setEngine("down"));

    getLeaderboard(ctrl.signal)
      .then((b) => {
        setBoard(b);
        setModels("up");
      })
      .catch(() => !ctrl.signal.aborted && setModels("down"));

    return () => ctrl.abort();
  }, []);

  const best = board?.models?.[0];

  return (
    <header className="masthead">
      <div className="masthead-brand">
        <span className="wordmark">
          GOV<span className="wordmark-sim">SIM</span>
        </span>
        <span className="masthead-rule" aria-hidden />
        <span className="masthead-sub">Policy Simulation Environment</span>
      </div>

      <div className="masthead-status" role="status" aria-live="polite">
        <Indicator
          state={engine}
          label="Engine"
          detail={
            engine === "up"
              ? `v${health?.version ?? "—"}`
              : engine === "down"
                ? "offline"
                : "…"
          }
        />
        <Indicator
          state={models}
          label="Models"
          detail={
            models === "up" && best
              ? `${best.name} · R² ${best.r2.toFixed(3)}`
              : models === "down"
                ? "not trained"
                : "…"
          }
        />
        <Indicator
          state={board?.registry_source === "mongodb" ? "up" : models === "checking" ? "checking" : "down"}
          label="Registry"
          detail={board?.registry_source === "mongodb" ? "MongoDB" : "local files"}
        />
        <div className="masthead-locale">
          <span className="masthead-locale-label">Study area</span>
          <strong>Auckland, NZ</strong>
        </div>
      </div>
    </header>
  );
}

function Indicator({
  state,
  label,
  detail,
}: {
  state: Probe;
  label: string;
  detail: string;
}) {
  return (
    <div className={`indicator ${state}`}>
      <span className="indicator-dot" aria-hidden />
      <span className="indicator-label">{label}</span>
      <span className="indicator-detail">{detail}</span>
    </div>
  );
}

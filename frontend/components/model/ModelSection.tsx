"use client";

/**
 * The machine-learning layer, on screen.
 *
 * This section exists because a simulator that will not show its model is a
 * rhetorical device, not an instrument. Everything here is measured: the
 * leaderboard is nine regressors scored on a held-out split, the horizon curve
 * is where the LSTM's accuracy actually decays, and the congestion clock is
 * fitted from the corpus rather than drawn by hand.
 *
 * Provenance is stated rather than implied. The models are fitted on a
 * loop-detector speed corpus and run on the local Auckland network, and the
 * section says so in the header rather than letting a reader assume the
 * numbers were measured on Queen Street.
 */

import { useEffect, useState } from "react";

import {
  getAnomalyProfile,
  getCongestionClock,
  getExampleForecast,
  getLeaderboard,
  type AnomalyProfile,
  type CongestionClock,
  type ForecastResult,
  type Leaderboard,
} from "../../lib/ml";
import BarChart from "../charts/BarChart";
import Heatmap from "../charts/Heatmap";
import LineChart from "../charts/LineChart";
import { CATEGORICAL, SERIES, STATUS } from "../charts/palette";
import { Block, Grid } from "../shell/Section";

export default function ModelSection() {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [clock, setClock] = useState<CongestionClock | null>(null);
  const [fc, setFc] = useState<ForecastResult | null>(null);
  const [anom, setAnom] = useState<AnomalyProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    const s = ctrl.signal;
    Promise.allSettled([
      getLeaderboard(s),
      getCongestionClock(s),
      getExampleForecast(s),
      getAnomalyProfile(s),
    ]).then(([b, c, f, a]) => {
      if (s.aborted) return;
      if (b.status === "fulfilled") setBoard(b.value);
      else setError(b.reason?.message ?? "leaderboard unavailable");
      if (c.status === "fulfilled") setClock(c.value);
      if (f.status === "fulfilled") setFc(f.value);
      if (a.status === "fulfilled") setAnom(a.value);
    });
    return () => ctrl.abort();
  }, []);

  if (error && !board) {
    return (
      <div className="model-empty">
        <p>
          <strong>The model layer is not available.</strong> {error}
        </p>
        <p className="muted">
          The rest of the dashboard runs without it — the projection is
          mechanistic and does not depend on these models.
        </p>
      </div>
    );
  }

  return (
    <>
      {board && <ProvenanceStrip board={board} />}

      <Grid>
        <Block
          title="Algorithm bake-off"
          hint={
            board
              ? `Nine regressors predicting link speed ${board.horizon_minutes} minutes ahead, scored on the held-out test split. Higher R² is better.`
              : "Loading…"
          }
          span={1}
        >
          {board ? (
            <BarChart
              max={1}
              unit="R²"
              bars={board.models.map((m, i) => ({
                label: m.name,
                value: m.r2,
                display: m.r2.toFixed(4),
                color: m.best ? CATEGORICAL[0] : CATEGORICAL[4],
                highlight: m.best,
                sub: `MAE ${m.mae_mph.toFixed(2)} mph · ${m.fit_seconds < 1 ? "<1" : Math.round(m.fit_seconds)}s`,
              }))}
            />
          ) : (
            <Skeleton rows={9} />
          )}
        </Block>

        <Block
          title="Where accuracy decays"
          hint="The LSTM predicts twelve five-minute steps at once. Skill falls off with distance — this is the honest limit of the forecast, not a detail to bury."
          span={1}
        >
          {board?.sequence?.by_horizon ? (
            <LineChart
              height={230}
              zeroBased
              xLabel="minutes ahead"
              yLabel="R²"
              formatX={(v) => `${Math.round(v)}m`}
              format={(v) => v.toFixed(2)}
              series={[
                {
                  label: "R² by horizon",
                  color: SERIES.policy,
                  points: board.sequence.by_horizon.map((h) => ({
                    x: h.horizon_min,
                    y: h.r2,
                  })),
                },
              ]}
            />
          ) : (
            <Skeleton rows={5} />
          )}
          {board?.sequence?.architecture && (
            <p className="model-note">
              {board.sequence.architecture.type}, {board.sequence.architecture.layers}{" "}
              layers × {board.sequence.architecture.hidden_size} hidden,{" "}
              {board.sequence.architecture.params.toLocaleString()} parameters.
              Overall R² {board.sequence.overall.r2.toFixed(4)}, MAE{" "}
              {board.sequence.overall.mae.toFixed(2)} mph.
            </p>
          )}
        </Block>

        <Block
          title="Congestion clock"
          hint="Fitted speed by hour and day of week. The two dark bands are the weekday peaks; the weekend rows show they are a commuting artefact, not a road-capacity one."
          span={1}
        >
          {clock ? (
            <Heatmap
              values={clock.fitted}
              rowLabels={clock.days}
              colLabels={clock.hours}
              min={clock.speed_min}
              max={clock.speed_max}
              unit=" mph"
            />
          ) : (
            <Skeleton rows={7} />
          )}
        </Block>

        <Block
          title="Live forecast"
          hint={
            fc?.scenario ??
            "Twelve observed steps in, twelve predicted steps out."
          }
          span={1}
        >
          {fc ? (
            <>
              <LineChart
                height={230}
                xLabel="minutes"
                yLabel="mph"
                formatX={(v) => (v <= 0 ? `${Math.round(v)}` : `+${Math.round(v)}`)}
                format={(v) => v.toFixed(0)}
                marker={{ x: 0, label: "now" }}
                series={[
                  {
                    label: "Observed",
                    color: SERIES.baseline,
                    points: fc.history.map((y, i) => ({
                      x: (i - (fc.history.length - 1)) * 5,
                      y,
                    })),
                  },
                  {
                    label: "Predicted",
                    color: SERIES.policy,
                    dashed: true,
                    points: [
                      { x: 0, y: fc.history[fc.history.length - 1] },
                      ...fc.forecast.map((f) => ({
                        x: f.horizon_min,
                        y: f.speed_mph,
                      })),
                    ],
                  },
                ]}
              />
              {fc.cross_check && (
                <p className="model-note">
                  Cross-check — {fc.cross_check.model} independently puts the +
                  {fc.cross_check.horizon_min} min step at{" "}
                  <strong>{fc.cross_check.speed_mph.toFixed(1)} mph</strong>.
                  Two model families agreeing is weak evidence; disagreeing is
                  strong evidence something is wrong.
                </p>
              )}
            </>
          ) : (
            <Skeleton rows={5} />
          )}
        </Block>

        <Block
          title="Anomaly detection"
          hint="An isolation forest flags windows that do not look like ordinary traffic — the signature of an incident or a closure rather than a peak."
          span={2}
        >
          {anom ? (
            <>
              <div className="stat-row">
                <Stat
                  label="Windows scored"
                  value={anom.n_scored.toLocaleString()}
                />
                <Stat
                  label="Flagged anomalous"
                  value={anom.n_anomalies.toLocaleString()}
                  tone="warning"
                />
                <Stat
                  label="Rate"
                  value={`${(anom.anomaly_rate * 100).toFixed(1)}%`}
                />
                <Stat
                  label="Contamination prior"
                  value={`${(anom.contamination * 100).toFixed(0)}%`}
                />
              </div>
              <LineChart
                height={190}
                zeroBased
                xLabel="hour of day"
                yLabel="anomaly rate"
                formatX={(v) => `${String(Math.round(v)).padStart(2, "0")}:00`}
                format={(v) => `${(v * 100).toFixed(1)}%`}
                series={[
                  {
                    label: "Anomaly rate by hour",
                    color: CATEGORICAL[5],
                    points: anom.rate_by_hour.map((y, h) => ({ x: h, y })),
                  },
                ]}
              />
            </>
          ) : (
            <Skeleton rows={4} />
          )}
        </Block>
      </Grid>
    </>
  );
}

function ProvenanceStrip({ board }: { board: Leaderboard }) {
  const d = board.dataset;
  return (
    <div className="provenance-strip">
      <div className="provenance-main">
        <span className="tag observed">Observed</span>
        <div>
          <strong>{d.name}</strong> — {d.description}
        </div>
      </div>
      <dl className="provenance-facts">
        <div>
          <dt>Sensors</dt>
          <dd>{d.sensors}</dd>
        </div>
        <div>
          <dt>Training windows</dt>
          <dd>{d.train_rows_sampled.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Held-out test</dt>
          <dd>{d.test_rows_sampled.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Resolution</dt>
          <dd>{d.step_minutes} min</dd>
        </div>
        <div>
          <dt>Registry</dt>
          <dd>{board.registry_source}</dd>
        </div>
      </dl>
      <p className="provenance-transfer">
        <span className="tag simulated">Simulated</span>
        {board.provenance.transfer_note}{" "}
        <a href={board.provenance.source_url} target="_blank" rel="noreferrer">
          Dataset ↗
        </a>
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "warning";
}) {
  return (
    <div className="stat-tile">
      <span className="stat-label">{label}</span>
      <span
        className="stat-value"
        style={tone === "warning" ? { color: STATUS.warning } : undefined}
      >
        {value}
      </span>
    </div>
  );
}

function Skeleton({ rows }: { rows: number }) {
  return (
    <div className="skeleton" aria-hidden>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" style={{ opacity: 1 - i * 0.09 }} />
      ))}
    </div>
  );
}

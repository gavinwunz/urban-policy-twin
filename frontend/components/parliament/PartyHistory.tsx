"use client";

/**
 * Eighteen years of New Zealand general elections.
 *
 * This is the historical record, not a model output: the Electoral Commission's
 * official party-vote shares for 2005 through 2023. It earns its place because
 * the chamber above is only meaningful if you can see how the House got to look
 * the way it does — Labour's 2020 majority and its collapse in 2023, the
 * Greens' slow climb, NZ First falling below the threshold twice and coming
 * back both times.
 *
 * Colours are each party's own, which is the one case where a categorical
 * palette should be overridden: readers already know what colour Labour is, and
 * a "correct" palette that recoloured them would be harder to read, not easier.
 */

import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../lib/api";
import LineChart from "../charts/LineChart";

interface PartyMeta {
  id: string;
  name: string;
  short: string;
  colour: string;
  active: boolean;
}

interface ElectionRow {
  year: number;
  total_seats: number;
  note: string;
  results: Array<{ party: string; party_vote_pct: number; seats: number }>;
}

interface History {
  provenance: string;
  source: { name: string; url: string; note: string };
  parties: PartyMeta[];
  elections: ElectionRow[];
  span_years: number;
  election_count: number;
}

/** Parties with enough presence across the span to be worth a line. */
const HEADLINE = ["labour", "national", "green", "act", "nzfirst", "maori"];

export default function PartyHistory() {
  const [data, setData] = useState<History | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"vote" | "seats">("vote");

  useEffect(() => {
    const ctrl = new AbortController();
    fetch(`${API_BASE_URL}/parliament/nz/history`, { signal: ctrl.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : "unavailable");
        }
      });
    return () => ctrl.abort();
  }, []);

  if (error) return <p className="muted">Election history unavailable — {error}</p>;
  if (!data) return <p className="muted">Loading election history…</p>;

  const byId = new Map(data.parties.map((p) => [p.id, p]));

  const series = HEADLINE.map((pid) => {
    const meta = byId.get(pid);
    return {
      label: meta?.short ?? pid,
      // NZ First's official colour is black, which is invisible on this
      // surface — lifted to a readable grey and noted in the legend.
      color: meta?.colour === "#000000" ? "#8895a6" : (meta?.colour ?? "#8895a6"),
      points: data.elections.map((e) => {
        const row = e.results.find((r) => r.party === pid);
        return {
          x: e.year,
          y: row ? (mode === "vote" ? row.party_vote_pct : row.seats) : 0,
        };
      }),
    };
  });

  const latest = data.elections[data.elections.length - 1];

  return (
    <div className="party-history">
      <div className="party-history-controls">
        <div className="map-control-group">
          <span className="map-control-label">Show</span>
          <button
            type="button"
            className={`chip${mode === "vote" ? " on" : ""}`}
            onClick={() => setMode("vote")}
          >
            Party vote %
          </button>
          <button
            type="button"
            className={`chip${mode === "seats" ? " on" : ""}`}
            onClick={() => setMode("seats")}
          >
            Seats
          </button>
        </div>
        <span className="party-history-span">
          {data.election_count} elections · {data.span_years} years
        </span>
      </div>

      <LineChart
        height={250}
        zeroBased
        xLabel="general election"
        yLabel={mode === "vote" ? "party vote %" : "seats"}
        formatX={(v) => String(Math.round(v))}
        format={(v) => (mode === "vote" ? `${v.toFixed(0)}%` : v.toFixed(0))}
        series={series}
      />

      <table className="election-table">
        <caption>
          {latest.year} result — {latest.note}
        </caption>
        <thead>
          <tr>
            <th scope="col">Party</th>
            <th scope="col">Party vote</th>
            <th scope="col">Seats</th>
          </tr>
        </thead>
        <tbody>
          {latest.results.map((r) => {
            const meta = byId.get(r.party);
            return (
              <tr key={r.party}>
                <th scope="row">
                  <span
                    className="bench-swatch"
                    style={{
                      background:
                        meta?.colour === "#000000" ? "#8895a6" : meta?.colour,
                    }}
                  />
                  {meta?.name ?? r.party}
                </th>
                <td>{r.party_vote_pct.toFixed(2)}%</td>
                <td>{r.seats}</td>
              </tr>
            );
          })}
        </tbody>
      </table>

      <p className="party-history-source">
        <span className="tag observed">Observed</span> {data.source.name}.{" "}
        {data.source.note}{" "}
        <a href={data.source.url} target="_blank" rel="noreferrer">
          electionresults.govt.nz ↗
        </a>
      </p>
    </div>
  );
}

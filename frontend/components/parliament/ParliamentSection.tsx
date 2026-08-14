"use client";

/**
 * Parliament: the chamber, the division, and how the House got this shape.
 *
 * Three things stacked, in the order a briefing would take them. The 3D chamber
 * shows the room and the vote. The division table shows each party's position
 * and the reasoning behind it. The history shows eighteen years of real
 * election results underneath, because the current benches are only meaningful
 * against how they were won.
 *
 * The debate transcript (five adversarial personas arguing with citations) sits
 * below as its own block — it answers a different question from the division:
 * not "does this pass" but "what is the argument".
 */

import { useEffect, useState } from "react";

import { API_BASE_URL } from "../../lib/api";
import { Block, Grid } from "../shell/Section";
import ParliamentPanel from "../twin/ParliamentPanel";
import { useTwin } from "../twin/TwinStore";
import Chamber3D, { type Division } from "./Chamber3D";
import PartyHistory from "./PartyHistory";

interface DivisionResponse {
  house: { year: number; total_seats: number; majority: number; note: string };
  result: {
    ayes: number;
    noes: number;
    abstentions: number;
    passed: boolean;
    majority_needed: number;
    margin: number;
  };
  divisions: Division[];
  levers: Array<{ lever: string; weight: number }>;
  outcome_signal: { effectiveness: number; equity_harm: number };
  method: string;
  method_reference: { title: string; org: string; url: string; licence: string };
  caveat: string;
}

export default function ParliamentSection() {
  const { policy, sim } = useTwin();
  const [division, setDivision] = useState<DivisionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setError(null);

    // Pull the headline percentage changes out of the active simulation so the
    // House is reacting to this policy's actual projected result, not a
    // generic one. Falls back to the keyless example when nothing has run.
    const outcome: Record<string, number> = {};
    const series = (sim as { delta?: { series?: Array<{ key: string; points?: Array<{ delta_pct: number }> }> } } | null)
      ?.delta?.series;
    if (series) {
      for (const s of series) {
        const p = s.points?.[s.points.length - 1];
        if (!p) continue;
        if (s.key.includes("cbd")) outcome.car_trips_into_cbd_pct = p.delta_pct;
        if (s.key.includes("co2")) outcome.co2_pct = p.delta_pct;
        if (s.key.includes("transit")) outcome.transit_trips_pct = p.delta_pct;
        if (s.key.includes("congestion")) outcome.congestion_pct = p.delta_pct;
      }
    }

    const request = policy
      ? fetch(`${API_BASE_URL}/parliament/nz/division`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ policy, outcome }),
          signal: ctrl.signal,
        })
      : fetch(`${API_BASE_URL}/parliament/nz/division/example`, {
          signal: ctrl.signal,
        });

    request
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setDivision)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : "division unavailable");
        }
      });

    return () => ctrl.abort();
  }, [policy, sim]);

  return (
    <Grid>
      <Block
        title="The House divides"
        hint={
          division
            ? `${division.house.total_seats} seats as returned at the ${division.house.year} general election. ${policy ? "Voting on your compiled policy." : "Showing the canonical demo charge until you compile one."}`
            : "Loading the chamber…"
        }
        span={2}
      >
        {error ? (
          <p className="muted">Division unavailable — {error}</p>
        ) : division ? (
          <>
            <Chamber3D
              divisions={division.divisions}
              totalSeats={division.house.total_seats}
              result={division.result}
              year={division.house.year}
            />
            <details className="division-method">
              <summary>How this division was computed</summary>
              <p>{division.method}</p>
              <dl className="division-signals">
                <div>
                  <dt>Levers pulled</dt>
                  <dd>
                    {division.levers
                      .map((l) => `${l.lever.replace(/_/g, " ")} ${(l.weight * 100).toFixed(0)}%`)
                      .join(" · ")}
                  </dd>
                </div>
                <div>
                  <dt>Effectiveness signal</dt>
                  <dd>{division.outcome_signal.effectiveness >= 0 ? "+" : ""}{division.outcome_signal.effectiveness.toFixed(2)}</dd>
                </div>
                <div>
                  <dt>Equity harm signal</dt>
                  <dd>{division.outcome_signal.equity_harm.toFixed(2)}</dd>
                </div>
              </dl>
              <p className="division-caveat">{division.caveat}</p>
              <p className="division-ref">
                Method after{" "}
                <a href={division.method_reference.url} target="_blank" rel="noreferrer">
                  {division.method_reference.org} — {division.method_reference.title}
                </a>{" "}
                ({division.method_reference.licence}), computed rather than
                language-model generated.
              </p>
            </details>
          </>
        ) : (
          <p className="muted">Convening the House…</p>
        )}
      </Block>

      <Block
        title="How the House got this shape"
        hint="Seven general elections, 2005–2023. Official Electoral Commission results — the record the benches above are drawn from."
        span={2}
      >
        <PartyHistory />
      </Block>

      <Block
        title="Debate transcript"
        hint="Five adversarial personas argue the policy with citations, and the House can amend it — every amendment re-runs the simulation."
        span={2}
      >
        <ParliamentPanel />
      </Block>
    </Grid>
  );
}

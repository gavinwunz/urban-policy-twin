"use client";

/**
 * A binding referendum on the policy, run over the modelled electorate.
 *
 * New Zealand runs citizens-initiated referenda, so "would this survive a
 * public vote" is a real question about a real mechanism rather than a
 * hypothetical. The result here is computed from the same cohort opinion model
 * that drives the public-reaction panel — the same numbers, asked a different
 * question.
 *
 * The modelling choice worth stating: turnout is not uniform. People who feel
 * strongly vote more than people who are indifferent, which is why a policy
 * with mild broad support can lose to a motivated minority. The turnout weights
 * below encode that, and the panel shows the result both raw and
 * turnout-weighted so the gap between them is visible rather than buried.
 */

import { useEffect, useMemo, useState } from "react";

import { API_BASE_URL } from "../../lib/api";
import { STATUS } from "../charts/palette";
import { useTwin } from "../twin/TwinStore";

interface Distribution {
  strong_support: number;
  support: number;
  neutral: number;
  oppose: number;
  strong_oppose: number;
  uncertain: number;
  net_support: number;
}

interface Cohort {
  key: string;
  income_band: string;
  geography: string;
  travel_mode: string;
  size: number;
  distribution: Distribution;
}

interface PublicResponse {
  population: number;
  overall: Distribution;
  cohorts: Cohort[];
}

/**
 * Propensity to turn out, by strength of feeling. Referendum turnout skews
 * hard toward the committed; the indifferent mostly stay home.
 */
const TURNOUT = {
  strong_support: 0.88,
  support: 0.62,
  neutral: 0.28,
  oppose: 0.66,
  strong_oppose: 0.9,
  uncertain: 0.22,
};

export default function Referendum() {
  const { policy } = useTwin();
  const [data, setData] = useState<PublicResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [weighted, setWeighted] = useState(true);

  useEffect(() => {
    if (!policy) {
      setData(null);
      return;
    }
    const ctrl = new AbortController();
    fetch(`${API_BASE_URL}/public`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ policy }),
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setData)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : "unavailable");
        }
      });
    return () => ctrl.abort();
  }, [policy]);

  const result = useMemo(() => {
    if (!data) return null;

    let yes = 0;
    let no = 0;
    let didNotVote = 0;

    for (const c of data.cohorts) {
      const d = c.distribution;
      const bucket = (share: number, key: keyof typeof TURNOUT) => {
        const people = share * c.size;
        const voting = weighted ? people * TURNOUT[key] : people;
        didNotVote += people - voting;
        return voting;
      };
      // "Uncertain" and "neutral" voters who do turn out split evenly — a
      // referendum forces a binary answer out of an ambivalent voter.
      const neutralVoting =
        bucket(d.neutral, "neutral") + bucket(d.uncertain, "uncertain");
      yes += bucket(d.strong_support, "strong_support") + bucket(d.support, "support") + neutralVoting / 2;
      no += bucket(d.strong_oppose, "strong_oppose") + bucket(d.oppose, "oppose") + neutralVoting / 2;
    }

    const cast = yes + no;
    const yesPct = cast > 0 ? (yes / cast) * 100 : 0;
    const turnoutPct =
      data.population > 0 ? (cast / data.population) * 100 : 0;

    return {
      yes: Math.round(yes),
      no: Math.round(no),
      yesPct,
      noPct: 100 - yesPct,
      turnoutPct,
      passed: yesPct > 50,
      didNotVote: Math.round(didNotVote),
    };
  }, [data, weighted]);

  if (!policy) {
    return (
      <p className="muted">
        Compile a policy to put it to a citizens-initiated referendum over the
        modelled electorate.
      </p>
    );
  }
  if (error) return <p className="muted">Referendum unavailable — {error}</p>;
  if (!data || !result) return <p className="muted">Counting…</p>;

  return (
    <div className="referendum">
      <div className="referendum-question">
        <span className="referendum-label">The question put to voters</span>
        <p>
          “Should the proposed policy be brought into force in Auckland?”
        </p>
      </div>

      <div className={`referendum-result ${result.passed ? "yes" : "no"}`}>
        <div className="referendum-verdict">
          <strong>{result.passed ? "YES" : "NO"}</strong>
          <span>{result.yesPct.toFixed(1)}% in favour</span>
        </div>
        <div className="referendum-bar" role="img"
          aria-label={`${result.yesPct.toFixed(1)} per cent yes, ${result.noPct.toFixed(1)} per cent no`}>
          <span
            className="referendum-yes"
            style={{ width: `${result.yesPct}%`, background: STATUS.good }}
          />
          <span
            className="referendum-no"
            style={{ width: `${result.noPct}%`, background: STATUS.serious }}
          />
          <span className="referendum-threshold" style={{ left: "50%" }} />
        </div>
        <div className="referendum-tally">
          <span>
            <i style={{ background: STATUS.good }} /> Yes{" "}
            <b>{result.yes.toLocaleString()}</b>
          </span>
          <span>
            <i style={{ background: STATUS.serious }} /> No{" "}
            <b>{result.no.toLocaleString()}</b>
          </span>
          <span className="referendum-turnout">
            Turnout {result.turnoutPct.toFixed(0)}%
          </span>
        </div>
      </div>

      <label className="switch referendum-toggle">
        <input
          type="checkbox"
          checked={weighted}
          onChange={(e) => setWeighted(e.target.checked)}
        />
        Weight by turnout propensity
      </label>

      <p className="referendum-note">
        {weighted ? (
          <>
            Weighted for turnout: strongly-held positions vote at up to 90%,
            indifference at under 30%. This is why a policy with broad mild
            support can still lose — turn the weighting off to see the raw
            electorate, and the gap between the two is the size of the
            mobilisation problem.
          </>
        ) : (
          <>
            Raw electorate, every modelled person voting. Compare against the
            turnout-weighted result: the difference is how much this policy
            depends on getting its supporters to the booth.
          </>
        )}
      </p>

      <p className="referendum-provenance">
        <span className="tag simulated">Simulated</span> Computed from the same
        cohort opinion model as the public-reaction panel over{" "}
        {data.population.toLocaleString()} modelled residents in{" "}
        {data.cohorts.length} cohorts. Turnout propensities are{" "}
        <span className="tag estimated">Estimated</span>. Not a poll, and not a
        forecast of an actual referendum.
      </p>
    </div>
  );
}

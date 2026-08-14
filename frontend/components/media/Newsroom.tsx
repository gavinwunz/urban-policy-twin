"use client";

/**
 * The press, as a newsroom front page.
 *
 * Media coverage is one of the outputs a minister most wants to see, and a
 * bullet list does not convey it — the shape of a front page (a lead story, a
 * column of secondary pieces, mastheads, standfirsts) is itself information
 * about how a policy will land.
 *
 * The one hard rule: this must never be mistakable for real journalism. Every
 * outlet is an archetype rather than a real masthead, the backend labels each
 * item SIMULATED, and that label is rendered on the card rather than tucked in
 * a footnote. The tone is a real newspaper; the claim is never that it is one.
 *
 * Headline prose is Generated. Every figure a headline cites is a Simulated
 * metric the engine produced, listed under the card as citations.
 */

import { useEffect, useMemo, useState } from "react";

import { API_BASE_URL } from "../../lib/api";
import { useTwin } from "../twin/TwinStore";

interface Headline {
  archetype: string;
  outlet_label: string;
  headline: string;
  standfirst: string;
  angle: string;
  sentiment: string;
  cited_refs: string[];
  label: string;
  provenance: string;
}

interface ScenarioBlock {
  label: string;
  scenario_month: number;
  headlines: Headline[];
}

interface MediaResponse {
  provenance: string;
  disclaimer: string;
  note: string;
  method: string;
  scenarios: ScenarioBlock[];
}

const SENTIMENT_CLASS: Record<string, string> = {
  positive: "pos",
  supportive: "pos",
  negative: "neg",
  critical: "neg",
  mixed: "mix",
  neutral: "mix",
};

/** A masthead style per archetype, so outlets read as distinct publications. */
const MASTHEAD_STYLE: Record<string, string> = {
  public_broadcaster: "broadcaster",
  business_press: "business",
  tabloid: "tabloid",
  local_paper: "local",
  opposition_local: "local",
  broadsheet: "broadsheet",
  specialist: "specialist",
};

export default function Newsroom() {
  const { policy } = useTwin();
  const [data, setData] = useState<MediaResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [scenarioIdx, setScenarioIdx] = useState(0);

  useEffect(() => {
    if (!policy) {
      setData(null);
      return;
    }
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    fetch(`${API_BASE_URL}/media`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ policy }),
      signal: ctrl.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: MediaResponse) => {
        setData(d);
        setScenarioIdx(0);
      })
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) {
          setError(e instanceof Error ? e.message : "media unavailable");
        }
      })
      .finally(() => !ctrl.signal.aborted && setLoading(false));
    return () => ctrl.abort();
  }, [policy]);

  const scenario = data?.scenarios?.[scenarioIdx];
  const [lead, ...rest] = useMemo(
    () => scenario?.headlines ?? [],
    [scenario],
  );

  if (!policy) {
    return (
      <p className="muted">
        Compile a policy and the press reacts to it — one front page per
        Time-Machine checkpoint.
      </p>
    );
  }
  if (loading) return <p className="muted">Filing copy…</p>;
  if (error) return <p className="muted">Press feed unavailable — {error}</p>;
  if (!scenario) return <p className="muted">No coverage generated.</p>;

  return (
    <div className="newsroom">
      <div className="newsroom-bar">
        <div className="map-control-group">
          <span className="map-control-label">Front page at</span>
          {data!.scenarios.map((s, i) => (
            <button
              key={s.label}
              type="button"
              className={`chip${i === scenarioIdx ? " on" : ""}`}
              onClick={() => setScenarioIdx(i)}
            >
              {s.label}
            </button>
          ))}
        </div>
        <span className="newsroom-stamp">SIMULATED — not real journalism</span>
      </div>

      {lead && <LeadStory item={lead} />}

      <div className="newsroom-grid">
        {rest.map((h, i) => (
          <Story key={`${h.archetype}-${i}`} item={h} />
        ))}
      </div>

      <p className="newsroom-note">
        <span className="tag generated">Generated</span> {data!.note}
      </p>
    </div>
  );
}

function LeadStory({ item }: { item: Headline }) {
  return (
    <article className={`news-lead sentiment-${SENTIMENT_CLASS[item.sentiment] ?? "mix"}`}>
      <div className={`news-masthead ${MASTHEAD_STYLE[item.archetype] ?? "broadsheet"}`}>
        <span className="news-outlet">{item.outlet_label.replace(" (SIMULATED)", "")}</span>
        <span className="news-sim">SIMULATED</span>
      </div>
      <h4 className="news-headline lead">{item.headline}</h4>
      <p className="news-standfirst">{item.standfirst}</p>
      <div className="news-foot">
        <span className="news-angle">{item.angle}</span>
        <Citations refs={item.cited_refs} />
      </div>
    </article>
  );
}

function Story({ item }: { item: Headline }) {
  return (
    <article className={`news-card sentiment-${SENTIMENT_CLASS[item.sentiment] ?? "mix"}`}>
      <div className={`news-masthead ${MASTHEAD_STYLE[item.archetype] ?? "broadsheet"}`}>
        <span className="news-outlet">{item.outlet_label.replace(" (SIMULATED)", "")}</span>
        <span className="news-sim">SIM</span>
      </div>
      <h4 className="news-headline">{item.headline}</h4>
      <p className="news-standfirst">{item.standfirst}</p>
      <Citations refs={item.cited_refs} />
    </article>
  );
}

/**
 * Every figure a headline leans on, named. This is the difference between
 * simulated media and invented media: the copy is generated, but it can only
 * lean on metrics the engine actually produced, and here they are.
 */
function Citations({ refs }: { refs: string[] }) {
  if (!refs?.length) return null;
  return (
    <div className="news-citations">
      {refs.map((r) => (
        <span key={r} className="news-cite" title={`Cites simulated metric ${r}`}>
          {r}
        </span>
      ))}
    </div>
  );
}

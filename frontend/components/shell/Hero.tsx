"use client";

/**
 * The opening statement.
 *
 * One claim, stated plainly, and then the control that acts on it. A person
 * landing here should be able to say what GOV SIM does in one sentence,
 * because that sentence is the first thing on the page.
 *
 * Behind it sits a photograph of a debating chamber, pushed far back under a
 * gradient wash so it reads as context rather than decoration — this is a tool
 * for the room where policy is argued, and the fold should say so before a
 * word is read. The image is credited in the corner because a page that
 * lectures about provenance cannot use an uncredited photograph.
 *
 * The numbers in the strip are read from the live engine and the trained model
 * registry, so they are facts about this deployment rather than marketing.
 */

import { useEffect, useState } from "react";

import { getLeaderboard, type Leaderboard } from "../../lib/ml";

export default function Hero() {
  const [board, setBoard] = useState<Leaderboard | null>(null);

  useEffect(() => {
    const ctrl = new AbortController();
    getLeaderboard(ctrl.signal)
      .then(setBoard)
      .catch(() => undefined);
    return () => ctrl.abort();
  }, []);

  function scrollTo(id: string) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <section className="hero">
      <div className="hero-backdrop" aria-hidden="true">
        <div className="hero-photo" />
        <div className="hero-wash" />
        <div className="hero-mesh" />
      </div>

      <div className="hero-inner">
        <div className="hero-content">
          <p className="hero-eyebrow">
            <span className="hero-dot" />
            Policy simulation environment
          </p>

          <h1 className="hero-statement">
            <strong>GOV SIM</strong> lets governments test, stress-test, debate,
            amend and explore policies <em>before</em> they are deployed in the
            real world — based on{" "}
            <span className="hero-basis">
              local datasets and ML prediction models
            </span>
            .
          </h1>

          <div className="hero-actions">
            <button
              type="button"
              className="btn primary"
              onClick={() => scrollTo("compiler")}
            >
              Generate simulation from policy
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => scrollTo("model")}
            >
              Inspect the model
            </button>
          </div>

          <dl className="hero-facts">
            <div>
              <dt>Study area</dt>
              <dd>Auckland, New Zealand</dd>
            </div>
            <div>
              <dt>Horizon</dt>
              <dd>10 years</dd>
            </div>
            <div>
              <dt>Local network</dt>
              <dd>Auckland OSM</dd>
            </div>
            <div>
              <dt>Traffic model</dt>
              <dd>
                {board
                  ? `${board.models[0]?.name ?? "—"} · R² ${board.models[0]?.r2.toFixed(3) ?? "—"}`
                  : "loading…"}
              </dd>
            </div>
            <div>
              <dt>Fitted on</dt>
              <dd>
                {board
                  ? `${board.dataset.name} · ${board.dataset.sensors} sensors`
                  : "loading…"}
              </dd>
            </div>
          </dl>

          <p className="hero-epistemic">
            Every quantitative output is tagged{" "}
            <span className="tag observed">Observed</span>
            <span className="tag estimated">Estimated</span>
            <span className="tag simulated">Simulated</span>
            <span className="tag generated">Generated</span> — and language
            models never produce a numeric effect.
          </p>
        </div>
      </div>

      <p className="hero-credit">
        Debating chamber, New Zealand House of Representatives · Office of the
        Clerk ·{" "}
        <a
          href="https://creativecommons.org/licenses/by/4.0"
          target="_blank"
          rel="noreferrer"
        >
          CC BY 4.0
        </a>
      </p>
    </section>
  );
}

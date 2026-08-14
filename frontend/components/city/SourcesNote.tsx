"use client";

/**
 * Where the model comes from.
 *
 * The zone system is modelled, and saying so is not enough — a policy tool has to show
 * which real data models it is shaped like, so that swapping in a real city is
 * an obvious operation rather than a rewrite. Two lineages are cited, loaded
 * from `public/city/sources.json`:
 *
 *   3D geometry     3DCityDB Web Map Client (CityGML / 3D Tiles, Apache-2.0)
 *   travel demand   ONS 2011 Census origin–destination table WU03EW (OGL v3.0)
 *
 * The mechanism block underneath states, in plain language, what the prediction
 * model actually does with those inputs.
 */

import type { SourcesDoc } from "../../lib/city";

export default function SourcesNote({ sources }: { sources: SourcesDoc }) {
  return (
    <details className="sources">
      <summary>
        Data sources &amp; how the prediction model works
        <span className="sources-chips">
          {sources.sources.map((s) => (
            <span key={s.id} className="chip">
              {s.id === "3dcitydb-web-map" ? "3DCityDB" : s.country ?? s.name}
            </span>
          ))}
        </span>
      </summary>

      <p className="sources-note">{sources.note}</p>

      <ul className="source-list">
        {sources.sources.map((s) => (
          <li key={s.id}>
            <div className="source-head">
              <span className="source-role">{s.role}</span>
              <a href={s.url} target="_blank" rel="noreferrer noopener">
                {s.full_name ?? s.name}
              </a>
            </div>
            <div className="source-meta">
              {s.publisher}
              {s.country ? ` · ${s.country}` : ""} · {s.license}
              {s.formats ? ` · ${s.formats.join(", ")}` : ""}
            </div>
            <p className="source-use">{s.how_used}</p>
            {s.docs && (
              <a
                className="source-docs"
                href={s.docs}
                target="_blank"
                rel="noreferrer noopener"
              >
                Documentation ↗
              </a>
            )}
          </li>
        ))}
      </ul>

      <div className="model-card">
        <h4>
          {sources.model.name}{" "}
          <span className="model-class">{sources.model.class}</span>
        </h4>
        <p>{sources.model.mechanism}</p>
        <ul className="model-inputs">
          {sources.model.inputs.map((i) => (
            <li key={i}>
              <code>{i.split("—")[0].trim()}</code>
              <span>{i.split("—").slice(1).join("—").trim()}</span>
            </li>
          ))}
        </ul>
      </div>
    </details>
  );
}

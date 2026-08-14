"use client";

/**
 * One numbered section of the single-page dashboard, plus the sub-block used
 * inside it.
 *
 * `Section` carries the scroll anchor and the framing question. `Block` wraps a
 * former tab-panel so a stack of them reads as a document rather than a pile of
 * cards — each one keeps a title and a one-line "what am I looking at", which
 * the tab bar used to supply implicitly via the tab label.
 */

import type { ReactNode } from "react";

import { SECTIONS } from "./sections";

export function Section({
  id,
  children,
}: {
  id: string;
  children: ReactNode;
}) {
  const def = SECTIONS.find((s) => s.id === id);
  const index = SECTIONS.findIndex((s) => s.id === id) + 1;

  return (
    <section id={id} className="dash-section">
      <header className="dash-section-head">
        <span className="dash-section-num">{String(index).padStart(2, "0")}</span>
        <div>
          <h2>{def?.question ?? id}</h2>
          <p className="dash-section-blurb">{def?.blurb}</p>
        </div>
        <span className="dash-section-tag">{def?.label}</span>
      </header>
      {children}
    </section>
  );
}

export function Block({
  title,
  hint,
  span = 1,
  children,
}: {
  title: string;
  hint?: string;
  /** 1 = half width on wide screens, 2 = full width. */
  span?: 1 | 2;
  children: ReactNode;
}) {
  return (
    <article className={`dash-block span-${span}`}>
      <header className="dash-block-head">
        <h3>{title}</h3>
        {hint && <p>{hint}</p>}
      </header>
      <div className="dash-block-body">{children}</div>
    </article>
  );
}

export function Grid({ children }: { children: ReactNode }) {
  return <div className="dash-grid">{children}</div>;
}

"use client";

/**
 * Sticky scroll-spy rail. Replaces the old tab bar.
 *
 * The distinction matters: a tab bar *hides* everything you are not looking at,
 * so the page has no shape and you cannot tell how much instrument there is.
 * This rail is a table of contents over content that is all present — it moves
 * you around the page rather than swapping what the page contains.
 *
 * Uses IntersectionObserver rather than scroll maths so it stays correct when
 * sections change height (panels loading, charts resizing) without recomputing
 * offsets on every frame.
 */

import { useEffect, useState } from "react";

import { SECTIONS } from "./sections";

export default function SectionNav() {
  const [active, setActive] = useState<string>(SECTIONS[0].id);

  useEffect(() => {
    const targets = SECTIONS.map((s) => document.getElementById(s.id)).filter(
      (el): el is HTMLElement => el !== null,
    );
    if (!targets.length) return;

    // Bias the "active" band toward the upper third of the viewport: the
    // heading you are reading is normally near the top, not the middle.
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-12% 0px -70% 0px", threshold: 0 },
    );

    targets.forEach((t) => observer.observe(t));
    return () => observer.disconnect();
  }, []);

  return (
    <nav className="section-nav" aria-label="Sections">
      <ol>
        {SECTIONS.map((s, i) => {
          // A category heading appears the first time that category is used,
          // so the rail reads as grouped work rather than a flat list.
          const isNewCategory = i === 0 || SECTIONS[i - 1].category !== s.category;
          return (
            <li key={s.id}>
              {isNewCategory && (
                <span className="section-nav-category">{s.category}</span>
              )}
              <a
                href={`#${s.id}`}
                className={active === s.id ? "active" : undefined}
                aria-current={active === s.id ? "true" : undefined}
              >
                <span className="section-nav-num">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="section-nav-label">{s.label}</span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

"use client";

/**
 * The debating chamber, in 3D, seated with the real House.
 *
 * 123 seats laid out on the tiered horseshoe a Westminster-derived chamber
 * actually uses, benches coloured by party, each seat lit or dimmed by how its
 * party voted in the simulated division. The camera orbits slowly so the tiers
 * read as tiers.
 *
 * Built with CSS 3D transforms rather than WebGL on purpose. The scene is a few
 * hundred flat quads with no lighting model, a second WebGL context beside the
 * map would cost more than it returns, and this way every seat stays a real DOM
 * node — so it is hoverable, focusable, and legible to a screen reader as text.
 *
 * The seat counts are the official 2023 results. Which way each bench votes is
 * simulated; the chamber says so under the model.
 */

import { useEffect, useMemo, useRef, useState } from "react";

export interface Division {
  party: string;
  name: string;
  short: string;
  colour: string;
  seats: number;
  stance: string;
  ayes: number;
  noes: number;
  abstentions: number;
  reasoning: string;
  position: number;
}

export interface Chamber3DProps {
  divisions: Division[];
  totalSeats: number;
  result: {
    ayes: number;
    noes: number;
    abstentions: number;
    passed: boolean;
    majority_needed: number;
  };
  year: number;
}

interface Seat {
  x: number;
  y: number;
  z: number;
  rot: number;
  party: Division;
  vote: "aye" | "no" | "abstain";
}

/** Seats per tier, innermost first. Sums to 126 — enough for a 123-seat House. */
const TIERS = [16, 20, 24, 30, 36];

/**
 * Lay the House out on a tiered horseshoe.
 *
 * Parties are seated as contiguous blocs in the order given, sweeping from one
 * side of the chamber to the other — which is how a real chamber seats them,
 * and why the picture reads as a balance of forces rather than a scatter.
 */
function layout(divisions: Division[], totalSeats: number): Seat[] {
  // Build every seat position first, carrying the angle it sits at.
  const slots: Array<{ x: number; y: number; z: number; rot: number; angle: number }> = [];

  TIERS.forEach((count, tier) => {
    const radius = 120 + tier * 46;
    for (let i = 0; i < count; i++) {
      const t = count === 1 ? 0.5 : i / (count - 1);
      // 180° of arc, opening toward the Speaker at the front of the chamber.
      const angle = Math.PI * (1.0 + t);
      slots.push({
        x: Math.cos(angle) * radius,
        z: Math.sin(angle) * radius * 0.82,
        // Back tiers sit higher, as they do in a real raked chamber.
        y: tier * 13,
        rot: (angle * 180) / Math.PI + 90,
        angle: t,
      });
    }
  });

  // Sorting by angle before assigning is what makes a party a *wedge* rather
  // than a stripe: consecutive slots in this order are radially adjacent
  // across all five tiers, which is how a chamber actually seats a caucus.
  slots.sort((a, b) => a.angle - b.angle);

  const seats: Seat[] = [];
  let cursor = 0;
  const scale = Math.min(1, slots.length / Math.max(1, totalSeats));

  for (const party of divisions) {
    const n = Math.max(1, Math.round(party.seats * scale));
    for (let i = 0; i < n && cursor < slots.length; i++, cursor++) {
      const share = i / Math.max(1, n);
      const ayeShare = party.ayes / Math.max(1, party.seats);
      const noShare = party.noes / Math.max(1, party.seats);
      const vote: Seat["vote"] =
        share < ayeShare
          ? "aye"
          : share < ayeShare + noShare
            ? "no"
            : "abstain";
      seats.push({ ...slots[cursor], party, vote });
    }
  }
  return seats;
}

export default function Chamber3D({
  divisions,
  totalSeats,
  result,
  year,
}: Chamber3DProps) {
  const seats = useMemo(() => layout(divisions, totalSeats), [divisions, totalSeats]);
  const [spin, setSpin] = useState(0);
  const [hover, setHover] = useState<Division | null>(null);
  const [paused, setPaused] = useState(false);
  const raf = useRef<number | null>(null);

  // A slow orbit. Stops on hover so a seat can actually be inspected, and
  // never runs at all for a reader who has asked for reduced motion.
  useEffect(() => {
    const reduced =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced || paused) return;

    let mounted = true;
    let last = performance.now();
    const step = (now: number) => {
      if (!mounted) return;
      const dt = (now - last) / 1000;
      last = now;
      setSpin((s) => (s + dt * 3.2) % 360);
      raf.current = requestAnimationFrame(step);
    };
    raf.current = requestAnimationFrame(step);
    return () => {
      mounted = false;
      if (raf.current !== null) cancelAnimationFrame(raf.current);
    };
  }, [paused]);

  // A gentle sway rather than a full rotation — a chamber viewed from the
  // gallery, not a turntable.
  const yaw = Math.sin((spin * Math.PI) / 180) * 16;

  return (
    <div className="chamber3d">
      <div
        className="chamber3d-stage"
        onMouseEnter={() => setPaused(true)}
        onMouseLeave={() => {
          setPaused(false);
          setHover(null);
        }}
      >
        <div
          className="chamber3d-world"
          style={{ transform: `rotateX(64deg) rotateZ(${yaw}deg)` }}
        >
          <div className="chamber3d-floor" />

          {seats.map((s, i) => (
            <div
              key={i}
              className={`chamber3d-seat vote-${s.vote}${
                hover && hover.party !== s.party.party ? " dim" : ""
              }`}
              style={{
                transform: `translate3d(${s.x}px, ${s.z}px, ${s.y}px) rotateZ(${s.rot}deg)`,
                background: s.party.colour,
              }}
              onMouseEnter={() => setHover(s.party)}
              title={`${s.party.name} — ${s.vote}`}
            />
          ))}

          <div className="chamber3d-speaker">
            <span>SPEAKER</span>
          </div>
          <div className="chamber3d-table" aria-hidden />
        </div>
      </div>

      <div className="chamber3d-readout">
        <div className={`division-result ${result.passed ? "carried" : "lost"}`}>
          <span className="division-verdict">
            {result.passed ? "Carried" : "Lost"}
          </span>
          <span className="division-tally">
            <b>{result.ayes}</b> ayes · <b>{result.noes}</b> noes ·{" "}
            {result.abstentions} abstentions
          </span>
          <span className="division-majority">
            {result.majority_needed} needed for a majority of {totalSeats}
          </span>
        </div>

        <ul className="bench-list">
          {divisions.map((d) => (
            <li
              key={d.party}
              className={`bench${hover && hover.party !== d.party ? " dim" : ""}`}
              onMouseEnter={() => setHover(d)}
              onMouseLeave={() => setHover(null)}
            >
              <span className="bench-swatch" style={{ background: d.colour }} />
              <span className="bench-name">{d.short}</span>
              <span className="bench-seats">{d.seats}</span>
              <span className={`bench-stance ${d.stance}`}>
                {d.stance === "for"
                  ? "Aye"
                  : d.stance === "against"
                    ? "No"
                    : "Split"}
              </span>
            </li>
          ))}
        </ul>

        {hover && <p className="bench-reasoning">{hover.reasoning}</p>}
      </div>

      <p className="chamber3d-note">
        {totalSeats} seats as returned at the <strong>{year} general
        election</strong> <span className="tag observed">Observed</span> — the
        division itself is <span className="tag simulated">Simulated</span> from
        party stance priors and the projected outcome, not a prediction of how
        any real member would vote.
      </p>
    </div>
  );
}

"use client";

/**
 * The debating chamber, drawn as a chamber.
 *
 * A stance table tells you the count; a horseshoe tells you the *shape* of the
 * room — where the weight sits, whether the middle is holding, how isolated a
 * position is. That is the thing a minister reads a whip's report for, and it
 * survives being glanced at from across a room during a briefing.
 *
 * Geometry: seats are laid out on concentric arcs of a horseshoe, filled from
 * the government benches round to the opposition, which is how Westminster-
 * derived chambers (including New Zealand's) are actually arranged. Seat colour
 * is stance, and stance is *also* written in the legend and the roll-call below,
 * so identity never rests on colour alone.
 */

import { useMemo, useState } from "react";

import type { Argument, Stance } from "../../lib/api";
import { STATUS, INK } from "../charts/palette";

const STANCE_COLOR: Record<Stance, string> = {
  support: STATUS.good,
  oppose: STATUS.serious,
  conditional: STATUS.warning,
  challenge: "#8b6fe8",
};

const STANCE_LABEL: Record<Stance, string> = {
  support: "Support",
  oppose: "Oppose",
  conditional: "Conditional",
  challenge: "Challenge",
};

/** Seats per arc, innermost first — 120 seats, near NZ's House of 120. */
const ARCS = [14, 18, 22, 26, 40];
const TOTAL_SEATS = ARCS.reduce((a, b) => a + b, 0);

interface Seat {
  x: number;
  y: number;
  arc: number;
  index: number;
}

function layout(): Seat[] {
  const seats: Seat[] = [];
  const cx = 200;
  const cy = 178;
  ARCS.forEach((count, arcIdx) => {
    const r = 52 + arcIdx * 26;
    // A horseshoe: 200° of arc, opening toward the speaker at the bottom.
    const start = Math.PI * 1.0;
    const sweep = Math.PI * 1.0;
    for (let i = 0; i < count; i++) {
      const t = count === 1 ? 0.5 : i / (count - 1);
      const a = start + t * sweep;
      seats.push({
        x: cx + r * Math.cos(a),
        y: cy + r * Math.sin(a) * 0.82,
        arc: arcIdx,
        index: seats.length,
      });
    }
  });
  return seats;
}

export interface ChamberProps {
  /** One argument per persona, as returned by /parliament/debate. */
  args: Argument[];
}

export default function Chamber({ args }: ChamberProps) {
  const seats = useMemo(layout, []);
  const [hover, setHover] = useState<Stance | null>(null);

  /**
   * Seats are apportioned to stances in proportion to how many personas hold
   * them. This is a representation of the debate's balance, not a prediction of
   * a division — the label under the chamber says so.
   */
  const blocs = useMemo(() => {
    const counts = new Map<Stance, number>();
    for (const a of args) counts.set(a.stance, (counts.get(a.stance) ?? 0) + 1);

    const order: Stance[] = ["support", "conditional", "challenge", "oppose"];
    const present = order.filter((s) => counts.has(s));
    const totalPersonas = args.length || 1;

    let assigned = 0;
    return present.map((stance, i) => {
      const share = (counts.get(stance) ?? 0) / totalPersonas;
      const n =
        i === present.length - 1
          ? TOTAL_SEATS - assigned
          : Math.round(share * TOTAL_SEATS);
      const from = assigned;
      assigned += n;
      return {
        stance,
        seats: n,
        from,
        to: assigned,
        personas: args.filter((a) => a.stance === stance).map((a) => a.persona),
      };
    });
  }, [args]);

  const stanceOf = (seatIndex: number): Stance | null => {
    const bloc = blocs.find((b) => seatIndex >= b.from && seatIndex < b.to);
    return bloc?.stance ?? null;
  };

  return (
    <div className="chamber">
      {/* Cropped to the occupied band — the seats start around y=44, so a
          0-origin viewBox leaves a quarter of the box empty above the arc. */}
      <svg viewBox="0 34 400 178" className="chamber-svg" role="img"
        aria-label="Debating chamber, seats coloured by stance">
        <defs>
          <radialGradient id="chamber-floor" cx="50%" cy="88%" r="70%">
            <stop offset="0%" stopColor="rgba(47,165,184,0.16)" />
            <stop offset="100%" stopColor="rgba(47,165,184,0)" />
          </radialGradient>
        </defs>

        <ellipse cx={200} cy={182} rx={168} ry={62} fill="url(#chamber-floor)" />

        {/* the despatch box / speaker's chair */}
        <rect x={186} y={176} width={28} height={9} rx={2}
          fill="rgba(133,160,171,0.35)" />
        <text x={200} y={200} textAnchor="middle" className="chamber-speaker">
          SPEAKER
        </text>

        {seats.map((s) => {
          const stance = stanceOf(s.index);
          const dim = hover !== null && stance !== hover;
          return (
            <circle
              key={s.index}
              cx={s.x}
              cy={s.y}
              r={5.4}
              fill={stance ? STANCE_COLOR[stance] : "rgba(133,160,171,0.25)"}
              stroke={INK.surface}
              strokeWidth={1.6}
              opacity={dim ? 0.22 : 1}
            />
          );
        })}
      </svg>

      <div className="chamber-legend">
        {blocs.map((b) => (
          <button
            key={b.stance}
            type="button"
            className="chamber-bloc"
            onMouseEnter={() => setHover(b.stance)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(b.stance)}
            onBlur={() => setHover(null)}
          >
            <i style={{ background: STANCE_COLOR[b.stance] }} />
            <span className="chamber-bloc-label">{STANCE_LABEL[b.stance]}</span>
            <span className="chamber-bloc-count">{b.seats}</span>
            <span className="chamber-bloc-who">{b.personas.join(", ")}</span>
          </button>
        ))}
      </div>

      <p className="chamber-note">
        Seats are apportioned in proportion to the positions taken in the
        debate — a picture of where the argument sits, not a forecast of a
        division. <span className="tag generated">Generated</span> prose,{" "}
        <span className="tag simulated">Simulated</span> evidence.
      </p>
    </div>
  );
}

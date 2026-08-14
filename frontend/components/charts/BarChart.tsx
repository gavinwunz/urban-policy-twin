"use client";

/**
 * Horizontal bar chart for ranked magnitude — the model leaderboard, effect
 * sizes, anything where the reader's question is "which is biggest".
 *
 * Horizontal because the labels are model names, not dates: a vertical bar
 * chart would need rotated labels, which are measurably slower to read.
 * Data-ends are rounded 4px and anchored to the baseline, so length stays
 * proportional to value.
 */

import { INK } from "./palette";

export interface Bar {
  label: string;
  value: number;
  color: string;
  /** Shown at the end of the bar instead of the raw value. */
  display?: string;
  /** Emphasise this row (the winner). */
  highlight?: boolean;
  /** Extra context under the label. */
  sub?: string;
}

interface Props {
  bars: Bar[];
  /** Force the scale maximum, e.g. 1.0 for an R² chart. */
  max?: number;
  /** Force the scale minimum. */
  min?: number;
  unit?: string;
  barHeight?: number;
}

export default function BarChart({
  bars,
  max,
  min = 0,
  unit = "",
  barHeight = 26,
}: Props) {
  const hi = max ?? Math.max(...bars.map((b) => b.value), 0);
  const lo = min;
  const span = hi - lo || 1;

  return (
    <div className="bar-chart" role="img" aria-label={`Ranked comparison${unit ? ` in ${unit}` : ""}`}>
      {bars.map((b) => {
        const pct = Math.max(0, Math.min(100, ((b.value - lo) / span) * 100));
        return (
          <div
            key={b.label}
            className={`bar-row${b.highlight ? " highlight" : ""}`}
            style={{ ["--bar-h" as string]: `${barHeight}px` }}
          >
            <div className="bar-label">
              <span>{b.label}</span>
              {b.sub && <em>{b.sub}</em>}
            </div>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{ width: `${pct}%`, background: b.color }}
                title={`${b.label}: ${b.display ?? b.value}`}
              />
            </div>
            <div className="bar-value" style={{ color: INK.primary }}>
              {b.display ?? b.value.toFixed(3)}
            </div>
          </div>
        );
      })}
    </div>
  );
}

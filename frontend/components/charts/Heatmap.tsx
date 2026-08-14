"use client";

/**
 * Hour × day-of-week heatmap — the congestion clock.
 *
 * Sequential single-hue ramp: the value is a magnitude (speed), so a rainbow
 * would invent category boundaries that are not in the data. Cells carry a 2px
 * surface gap so adjacent values stay separable without a stroke, and hovering
 * gives the exact number because a colour cannot be read to two decimal places.
 */

import { Fragment, useState } from "react";

import { sequentialAt, SEQUENTIAL, INK } from "./palette";

interface Props {
  /** Rows = days, columns = hours. */
  values: Array<Array<number | null>>;
  rowLabels: string[];
  colLabels: number[];
  min: number;
  max: number;
  unit?: string;
  format?: (v: number) => string;
}

export default function Heatmap({
  values,
  rowLabels,
  colLabels,
  min,
  max,
  unit = "",
  format = (v) => v.toFixed(1),
}: Props) {
  const [hover, setHover] = useState<{ r: number; c: number } | null>(null);
  const span = max - min || 1;

  return (
    <div className="heatmap">
      <div className="heatmap-grid">
        <div />
        {colLabels.map((h) => (
          <div key={h} className="heatmap-col-label">
            {h % 3 === 0 ? String(h).padStart(2, "0") : ""}
          </div>
        ))}

        {values.map((row, r) => (
          <Fragment key={`row-${r}`}>
            <div className="heatmap-row-label">{rowLabels[r]}</div>
            {row.map((v, c) => (
              <div
                key={`${r}-${c}`}
                className={`heatmap-cell${hover?.r === r && hover?.c === c ? " on" : ""}`}
                style={{
                  background:
                    v === null ? "transparent" : sequentialAt((v - min) / span),
                }}
                onMouseEnter={() => setHover({ r, c })}
                onMouseLeave={() => setHover(null)}
                title={
                  v === null
                    ? "no data"
                    : `${rowLabels[r]} ${String(colLabels[c]).padStart(2, "0")}:00 — ${format(v)}${unit}`
                }
              />
            ))}
          </Fragment>
        ))}
      </div>

      <div className="heatmap-foot">
        <div className="heatmap-scale">
          <span>{format(min)}{unit}</span>
          <div className="heatmap-ramp">
            {SEQUENTIAL.map((c) => (
              <i key={c} style={{ background: c }} />
            ))}
          </div>
          <span>{format(max)}{unit}</span>
        </div>
        <div className="heatmap-readout" style={{ color: INK.secondary }}>
          {hover && values[hover.r]?.[hover.c] != null ? (
            <>
              <strong>
                {rowLabels[hover.r]} {String(colLabels[hover.c]).padStart(2, "0")}:00
              </strong>{" "}
              {format(values[hover.r][hover.c] as number)}
              {unit}
            </>
          ) : (
            <span className="muted">Hover a cell for the exact value</span>
          )}
        </div>
      </div>
    </div>
  );
}

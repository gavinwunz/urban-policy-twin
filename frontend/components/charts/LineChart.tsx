"use client";

/**
 * Multi-series line chart with an optional uncertainty band and a crosshair
 * tooltip.
 *
 * Inline SVG rather than a charting library: the whole dashboard needs perhaps
 * five chart forms, and a library would cost more bytes than the forms do while
 * making the mark specs (2px strokes, recessive grid, selective direct labels)
 * harder to hold consistent.
 *
 * Deliberately single-axis. Two measures on different scales become two charts
 * or an indexed series — never a second y-axis, which makes crossings look
 * meaningful when they are an artefact of the scaling.
 */

import { useEffect, useId, useRef, useState } from "react";

import { INK } from "./palette";

export interface Series {
  label: string;
  color: string;
  points: Array<{ x: number; y: number }>;
  /** Draw dashed — the secondary encoding for a CVD-adjacent colour pair. */
  dashed?: boolean;
  /** Optional ±band drawn behind the line (uncertainty, p05–p95, …). */
  band?: Array<{ x: number; lo: number; hi: number }>;
}

interface Props {
  series: Series[];
  height?: number;
  xLabel?: string;
  yLabel?: string;
  /** Formats the y value in the tooltip and axis. */
  format?: (v: number) => string;
  formatX?: (v: number) => string;
  /** Force the y-axis to include zero. */
  zeroBased?: boolean;
  /** Vertical reference line, e.g. "policy takes effect here". */
  marker?: { x: number; label: string };
}

const PAD = { top: 22, right: 16, bottom: 30, left: 46 };

export default function LineChart({
  series,
  height = 220,
  xLabel,
  yLabel,
  format = (v) => v.toFixed(1),
  formatX = (v) => String(v),
  zeroBased = false,
  marker,
}: Props) {
  const uid = useId().replace(/:/g, "");
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; px: number } | null>(null);
  const [width, setWidth] = useState(640);

  // Track the container width so the SVG viewBox matches the rendered box and
  // the crosshair maths stay in the same coordinate space.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      const w = entry.contentRect.width;
      if (w > 0) setWidth(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const all = series.flatMap((s) => s.points);
  const bandPts = series.flatMap((s) => s.band ?? []);

  const xs = all.map((p) => p.x);
  const ys = [
    ...all.map((p) => p.y),
    ...bandPts.map((b) => b.lo),
    ...bandPts.map((b) => b.hi),
  ];

  const xMin = xs.length ? Math.min(...xs) : 0;
  const xMax = xs.length ? Math.max(...xs) : 1;
  let yMin = ys.length ? Math.min(...ys) : 0;
  let yMax = ys.length ? Math.max(...ys) : 1;
  if (zeroBased) yMin = Math.min(0, yMin);
  // A flat series has no range to pad, so pad *relative to its own value*.
  // Padding by a fixed ±1 would put a constant 0.62 on a −0.38…1.62 axis and
  // render "62%" as an axis running from −54% to 178%.
  if (yMax - yMin < Math.abs(yMax) * 1e-6 + 1e-12) {
    const eps = Math.max(Math.abs(yMax) * 0.1, 1e-6);
    yMin = yMax - eps;
    yMax += eps;
  } else {
    const pad = (yMax - yMin) * 0.08;
    yMin -= pad;
    yMax += pad;
  }

  const innerW = Math.max(1, width - PAD.left - PAD.right);
  const innerH = Math.max(1, height - PAD.top - PAD.bottom);
  const sx = (x: number) => PAD.left + ((x - xMin) / (xMax - xMin || 1)) * innerW;
  const sy = (y: number) => PAD.top + innerH - ((y - yMin) / (yMax - yMin || 1)) * innerH;

  const ticks = 4;
  const yTicks = Array.from({ length: ticks + 1 }, (_, i) => yMin + ((yMax - yMin) * i) / ticks);
  const xTicks = Array.from({ length: 5 }, (_, i) => xMin + ((xMax - xMin) * i) / 4);

  const path = (pts: Array<{ x: number; y: number }>) =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.y).toFixed(2)}`).join(" ");

  const bandPath = (b: Array<{ x: number; lo: number; hi: number }>) => {
    const top = b.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(2)},${sy(p.hi).toFixed(2)}`);
    const bottom = [...b]
      .reverse()
      .map((p) => `L${sx(p.x).toFixed(2)},${sy(p.lo).toFixed(2)}`);
    return `${top.join(" ")} ${bottom.join(" ")} Z`;
  };

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    if (px < PAD.left || px > width - PAD.right) return setHover(null);
    const xVal = xMin + ((px - PAD.left) / innerW) * (xMax - xMin);
    setHover({ x: xVal, px });
  }

  // Snap the readout to the nearest actual sample of each series.
  const readout = hover
    ? series.map((s) => {
        const nearest = s.points.reduce(
          (best, p) => (Math.abs(p.x - hover.x) < Math.abs(best.x - hover.x) ? p : best),
          s.points[0] ?? { x: 0, y: 0 },
        );
        return { label: s.label, color: s.color, point: nearest };
      })
    : [];
  const snapX = readout.length ? readout[0].point.x : 0;

  return (
    <div className="chart-wrap" ref={wrapRef}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={height}
        role="img"
        aria-label={`${yLabel ?? "value"} against ${xLabel ?? "x"}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {/* grid — recessive, behind everything */}
        {yTicks.map((t, i) => (
          <g key={`y${i}`}>
            <line
              x1={PAD.left}
              x2={width - PAD.right}
              y1={sy(t)}
              y2={sy(t)}
              stroke={INK.grid}
              strokeWidth={1}
            />
            <text x={PAD.left - 8} y={sy(t) + 3.5} textAnchor="end" className="chart-tick">
              {format(t)}
            </text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={`x${i}`} x={sx(t)} y={height - 10} textAnchor="middle" className="chart-tick">
            {formatX(t)}
          </text>
        ))}

        {/* uncertainty bands sit behind their lines */}
        {series.map(
          (s, i) =>
            s.band &&
            s.band.length > 1 && (
              <path key={`b${i}`} d={bandPath(s.band)} fill={s.color} opacity={0.14} />
            ),
        )}

        {marker && (
          <g>
            <line
              x1={sx(marker.x)}
              x2={sx(marker.x)}
              y1={PAD.top}
              y2={PAD.top + innerH}
              stroke={INK.axis}
              strokeWidth={1}
              strokeDasharray="3 3"
            />
            <text x={sx(marker.x) + 5} y={PAD.top + 10} className="chart-marker-label">
              {marker.label}
            </text>
          </g>
        )}

        {series.map((s, i) => (
          <path
            key={`l${i}`}
            d={path(s.points)}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={s.dashed ? "6 4" : undefined}
          />
        ))}

        {hover && (
          <g>
            <line
              x1={sx(snapX)}
              x2={sx(snapX)}
              y1={PAD.top}
              y2={PAD.top + innerH}
              stroke={INK.axis}
              strokeWidth={1}
            />
            {readout.map((r, i) => (
              <circle
                key={i}
                cx={sx(r.point.x)}
                cy={sy(r.point.y)}
                r={4}
                fill={r.color}
                stroke={INK.surface}
                strokeWidth={2}
              />
            ))}
          </g>
        )}

        {/* The unit sits as a caption above the plot rather than as rotated
            text beside it: rotated labels are slower to read and, at this
            padding, collide with the tick values. */}
        {yLabel && (
          <text x={PAD.left} y={9} textAnchor="start" className="chart-axis-label">
            {yLabel}
          </text>
        )}
      </svg>

      {hover && readout.length > 0 && (
        <div
          className="chart-tip"
          style={{
            left: Math.min(Math.max(hover.px, 60), width - 60),
          }}
        >
          <strong>{formatX(snapX)}</strong>
          {readout.map((r, i) => (
            <span key={i}>
              <i style={{ background: r.color }} />
              {r.label} <b>{format(r.point.y)}</b>
            </span>
          ))}
        </div>
      )}

      {series.length > 1 && (
        <div className="chart-legend">
          {series.map((s) => (
            <span key={s.label}>
              <i
                style={{
                  background: s.dashed
                    ? `repeating-linear-gradient(90deg, ${s.color} 0 5px, transparent 5px 9px)`
                    : s.color,
                }}
              />
              {s.label}
            </span>
          ))}
        </div>
      )}
      <span className="sr-only" id={`${uid}-desc`}>
        {series
          .map((s) => `${s.label}: ${s.points.map((p) => format(p.y)).join(", ")}`)
          .join(". ")}
      </span>
    </div>
  );
}

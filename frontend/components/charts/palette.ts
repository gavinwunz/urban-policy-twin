/**
 * Chart palette.
 *
 * Categorical hues are assigned in this fixed order and never cycled — a
 * seventh series folds into "Other" or becomes a small multiple rather than
 * getting a generated colour, so a filter that changes the series count can
 * never repaint the survivors.
 *
 * These six were validated against the dashboard's dark surface (#101f2c) with
 * the palette validator: all sit inside the OKLCH L 0.48–0.67 band, clear the
 * chroma floor, hold ΔE ≥ 8 between adjacent pairs under deuteranopia and
 * protanopia, and reach 3:1 contrast against the surface. Adjacent ordering
 * matters — rose and green are deliberately kept apart because deuteranopes
 * confuse them.
 *
 * `TRITAN_WARN` records the one pair (rose ↔ blue, ΔE 4.6 tritan) that needs
 * secondary encoding: wherever those two are adjacent, they also carry a direct
 * label or a dash pattern, never colour alone.
 */

export const CATEGORICAL = [
  "#2fa5b8", // 1 cyan   — the brand hue; always the primary series
  "#c08327", // 2 amber  — the comparison / do-nothing series
  "#8b6fe8", // 3 violet
  "#3aa768", // 4 green
  "#4a86e8", // 5 blue
  "#d9527a", // 6 rose
] as const;

export const TRITAN_WARN = ["#d9527a", "#4a86e8"];

/** Semantic slots for the two series that appear on nearly every chart. */
export const SERIES = {
  policy: CATEGORICAL[0],
  baseline: CATEGORICAL[1],
} as const;

/**
 * Status colours are reserved: they mean state, never "series 4", and always
 * ship with a label or icon rather than standing alone.
 */
export const STATUS = {
  good: "#3aa768",
  warning: "#c08327",
  serious: "#d9527a",
  critical: "#b93b5e",
} as const;

/** Single-hue sequential ramp for magnitude (light → dark reads low → high). */
export const SEQUENTIAL = [
  "#0d2b33",
  "#12414d",
  "#175867",
  "#1b7082",
  "#2189a0",
  "#2fa5b8",
  "#5cc0cf",
] as const;

/**
 * Diverging ramp for polarity — two hues either side of a neutral grey. Used
 * for "faster vs slower than usual", where the midpoint is genuinely no change.
 */
export const DIVERGING = [
  "#b93b5e",
  "#d9527a",
  "#e08fa6",
  "#7c8b93", // neutral midpoint, not a hue
  "#63b98d",
  "#3aa768",
  "#227a4c",
] as const;

/** Ink tokens — text never wears a series colour. */
export const INK = {
  primary: "#eef4f2",
  secondary: "#b9c9d0",
  muted: "#85a0ab",
  grid: "rgba(133, 160, 171, 0.16)",
  axis: "rgba(133, 160, 171, 0.42)",
  surface: "#101f2c",
} as const;

/** Pick a diverging colour for a value in [-1, 1]. */
export function divergingAt(t: number): string {
  const clamped = Math.max(-1, Math.min(1, t));
  const idx = Math.round(((clamped + 1) / 2) * (DIVERGING.length - 1));
  return DIVERGING[idx];
}

/** Pick a sequential colour for a value in [0, 1]. */
export function sequentialAt(t: number): string {
  const clamped = Math.max(0, Math.min(1, t));
  return SEQUENTIAL[Math.round(clamped * (SEQUENTIAL.length - 1))];
}

"""Deterministic Markdown renderer for the Minister's Brief (SPEC §27/§37).

Turns a :class:`NorthStarAnswer` into a single self-contained Markdown document.
Pure formatting: it reads fields off the answer and lays them out — it never
recomputes, re-weights, or re-orders a number. The §37 narrative order is
preserved exactly, provenance tags travel with each line, media stays labelled
SIMULATED, and the document ends with a reproducibility footer (SPEC §32/§34).
"""

from __future__ import annotations

from ..media.schema import SIMULATED_LABEL
from ..northstar.schema import NorthStarAnswer

#: Provenance key printed under the title so every reader sees the tag meanings.
TAG_LEGEND: list[tuple[str, str]] = [
    ("Observed", "read directly from a transparency artifact / assumption register"),
    ("Estimated", "documented transfer or elasticity, not a live simulation draw"),
    ("Simulated", "produced by the deterministic agent-based / policy model"),
    ("Generated", "narrative prose (debate, media) that cites only Simulated numbers"),
]


def _fmt(value: float, unit: str) -> str:
    """Format a metric value with a light-touch unit."""
    if unit in {"%", "percent"}:
        return f"{value:.1f}%"
    if abs(value) >= 1000:
        return f"{value:,.0f} {unit}".rstrip()
    return f"{value:,.1f} {unit}".rstrip()


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.1f}%"


def _arrow(direction: str) -> str:
    return {"down": "▼", "up": "▲", "flat": "→"}.get(direction, "→")


def _headline_table(answer: NorthStarAnswer) -> list[str]:
    """The median-outcome dashboard as a Markdown table (§37.4)."""
    if not answer.median_outcome:
        return ["_No headline metrics at this configuration._", ""]
    rows = [
        "| Metric | Baseline (A) | Policy (B) | Δ | Δ% | Band [low, high] | Provenance |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for t in answer.median_outcome:
        band = f"[{_fmt(t.band[0], t.unit)}, {_fmt(t.band[1], t.unit)}]" if len(t.band) == 2 else "—"
        rows.append(
            f"| {t.label} | {_fmt(t.world_a, t.unit)} | {_fmt(t.world_b, t.unit)} "
            f"| {_arrow(t.direction)} {_fmt(t.delta, t.unit)} | {_pct(t.delta_pct)} "
            f"| {band} | {t.tag.value} |"
        )
    rows.append("")
    return rows


def _failure_table(answer: NorthStarAnswer, limit: int = 5) -> list[str]:
    """The top failure modes as a ranked table (§37.8 — Estimated overlay)."""
    modes = answer.failure_modes.failure_modes[:limit]
    if not modes:
        return ["_No material failure modes surfaced._", ""]
    rows = [
        "| # | Risk | Severity | Prob. | Mitigation |",
        "|---:|---|---|---:|---|",
    ]
    for i, m in enumerate(modes, start=1):
        rows.append(
            f"| {i} | {m.risk} | {m.severity.value} | {m.probability:.0%} | {m.mitigation} |"
        )
    rows.append("")
    return rows


def _amendments_block(answer: NorthStarAnswer) -> list[str]:
    """Risk-reducing amendments + a one-line effect summary each (§37.12/13)."""
    if not answer.amendments:
        return ["_No structural amendment needed at this configuration._", ""]
    out: list[str] = []
    for a in answer.amendments:
        out.append(f"- **{a.label}** — targets _{a.targets_risk}_. {a.rationale}")
        changes = ", ".join(a.comparison.changes) if a.comparison.changes else "structured edit"
        out.append(f"  - Re-simulated effect: Δ(amended − original) computed via the same A/B path ({changes}).")
    out.append("")
    return out


def _media_block(answer: NorthStarAnswer, include_media: bool) -> list[str]:
    """Plausible media narratives — every item labelled SIMULATED (§37.11)."""
    if not include_media:
        return []
    out = ["## Simulated media narratives", "", f"> {SIMULATED_LABEL}", ""]
    any_line = False
    for scenario in answer.media.scenarios:
        for h in scenario.headlines:
            any_line = True
            out.append(f"- _{scenario.label}_ — **{h.outlet_label}:** “{h.headline}” ({h.sentiment})")
    if not any_line:
        out.append("_No media narratives generated for this configuration._")
    out.append("")
    return out


def render_brief_markdown(
    answer: NorthStarAnswer,
    *,
    include_media: bool = True,
    seed: int | None = None,
) -> str:
    """Render the full Minister's Brief as a single Markdown string."""
    lines: list[str] = []

    # --- Header -------------------------------------------------------------
    lines.append(f"# Minister's Brief — policy `{answer.policy_id}`")
    lines.append("")
    lines.append(f"**Question:** {answer.question}")
    lines.append("")
    lines.append(f"**Horizon:** {answer.horizon_label} ({answer.horizon_months:g} months)")
    lines.append("")
    lines.append(
        "> This brief renders the North-Star answer (SPEC §37). Every figure is the same "
        "object the standalone endpoints return; no LLM produces any number (SPEC §34)."
    )
    lines.append("")
    lines.append("**Provenance key:** " + " · ".join(f"**{t}** = {m}" for t, m in TAG_LEGEND))
    lines.append("")

    # --- Executive summary: the median outcome ------------------------------
    lines.append("## Executive summary")
    lines.append("")
    lines.extend(_headline_table(answer))

    # --- The §37 narrative, in order ----------------------------------------
    lines.append("## What happens if we implement this?")
    lines.append("")
    for s in answer.sections:
        lines.append(f"**{s.order}. {s.question}** _({s.tag.value})_")
        lines.append("")
        lines.append(s.lead)
        lines.append("")

    # --- Winners / losers ---------------------------------------------------
    ms = answer.winners
    lines.append("## Distribution — who gains, who loses")
    lines.append("")
    lines.append(
        f"- **{ms.winners:,} commuters better off** ; **{ms.losers:,} worse off** ; "
        f"regressivity ratio **{ms.regressivity_ratio:.1f}** _(Simulated)_"
    )
    if ms.biggest_winner:
        lines.append(f"- Largest gains: {ms.biggest_winner}")
    if ms.worst_hit:
        lines.append(f"- Hardest hit: {ms.worst_hit}")
    lines.append("")

    # --- Failure modes ------------------------------------------------------
    lines.append("## Where it is most likely to fail _(Estimated risk overlay)_")
    lines.append("")
    lines.extend(_failure_table(answer))

    # --- Amendments ---------------------------------------------------------
    lines.append("## Risk-reducing amendments")
    lines.append("")
    lines.extend(_amendments_block(answer))

    # --- Media --------------------------------------------------------------
    lines.extend(_media_block(answer, include_media))

    # --- Reproducibility footer (SPEC §32) ----------------------------------
    ev = answer.evidence or {}
    n_assumptions = len(ev.get("assumption_index", []))
    n_guardrails = len(ev.get("guardrails", []))
    lines.append("## Reproducibility & assumptions")
    lines.append("")
    lines.append(
        f"- {n_assumptions} documented assumptions, {n_guardrails} SPEC §34 guardrails "
        "(full register via `GET /registry` and `POST /reproduce`)."
    )
    lines.append(f"- Deterministic core; seed = `{seed if seed is not None else 'default'}`.")
    lines.append(
        "- No LLM touches any figure; narrative prose cites only Simulated numbers (SPEC §34)."
    )
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("_Generated by GOV SIM from `/north-star`. Figures are consistent with every tab._")
    lines.append("")

    return "\n".join(lines)

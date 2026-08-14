"""Build a causal provenance trace for one metric (ROADMAP M7, SPEC §26).

Given a compiled policy and a metric key, :func:`run_evidence` re-runs the
deterministic World-A / World-B simulation, locates the metric's Δ trajectory,
and assembles the ``input-data → transform → model → assumptions → result``
ladder the Evidence Drawer renders — plus the equations/parameters (behavioural
levers), the named assumptions, illustrative real-world analogues and citations
required by SPEC §26.

The function performs NO numeric modelling of its own: every value it places on
the trace is copied from the simulation output. Analogues and citations are
static reference facts. The LLM never touches this path (SPEC §34).
"""

from __future__ import annotations

from ..baseline.model import compute_baseline
from ..baseline.schema import Checkpoint, MetricTag
from ..baseline.timeseries import build_timeseries
from ..policy.dsl import PolicyDSL
from ..simulation.compare import build_delta
from ..simulation.model import compute_world_b
from ..simulation.schema import BehaviouralRule, DeltaPoint, DeltaSeries
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .schema import (
    HistoricalAnalogue,
    ProvenanceTrace,
    TraceAssumption,
    TraceConfidence,
    TraceResult,
    TraceStep,
)


class MetricNotFound(LookupError):
    """Raised when the requested metric key is not in the simulation output."""

    def __init__(self, key: str, available: list[str]) -> None:
        self.key = key
        self.available = available
        super().__init__(f"Unknown metric key {key!r}. Available: {', '.join(available)}")


# Real congestion-pricing schemes offered as qualitative analogues (SPEC §26).
# Static reference facts (Observed), NOT a source of any simulated number.
_ANALOGUES: list[HistoricalAnalogue] = [
    HistoricalAnalogue(
        scheme="Congestion Charge",
        city="London",
        year=2003,
        mechanism="Flat daily cordon charge to drive into central London.",
        relevance="Canonical flat cordon charge — closest analogue to a road-pricing "
        "cordon; observed traffic fell and bus/transit use rose after introduction.",
    ),
    HistoricalAnalogue(
        scheme="Congestion Tax",
        city="Stockholm",
        year=2007,
        mechanism="Time-of-day cordon tax on entering/leaving the inner city.",
        relevance="Trial-then-permanent cordon with strong measured mode shift toward "
        "transit — an analogue for staged behavioural adaptation.",
    ),
    HistoricalAnalogue(
        scheme="Electronic Road Pricing (ERP)",
        city="Singapore",
        year=1998,
        mechanism="Dynamic gantry pricing that varies the charge to hold target speeds.",
        relevance="Long-running road pricing — evidence that charge level maps onto "
        "car generalized cost and demand, as this model assumes.",
    ),
    HistoricalAnalogue(
        scheme="Area C",
        city="Milan",
        year=2012,
        mechanism="Charge plus pollution-class access control for the central zone.",
        relevance="Combines pricing with access restriction — analogue for the "
        "car-ban / pedestrianisation lever.",
    ),
]

_CITATIONS: list[str] = [
    "data/city/manifest.json — Modelled Auckland input world state (not real administrative records).",
    "backend/app/baseline/model.py — deterministic agent-based mode-choice baseline (World A).",
    "backend/app/simulation/model.py — World-B mode re-choice under policy levers.",
    "backend/app/simulation/timeline.py — staged adaptation ramp + horizon-widening band.",
    "backend/app/simulation/compare.py — Δ(B−A) construction per checkpoint.",
    "SPEC §7.5 (behavioural-rule audit), §24 (uncertainty), §26 (explainability), §34 (guardrails).",
]


def _family(metric_key: str) -> str:
    return metric_key.split(".", 1)[0]


def _rules_for(metric_key: str, rules: list[BehaviouralRule], levers: dict) -> list[BehaviouralRule]:
    """Pick the behavioural levers that materially touch ``metric_key``.

    The charge/ban push commuters off the car (drives traffic, emissions, car
    share, and — via substitution — transit). Reinvestment pulls onto transit
    (drives transit metrics and public-transit share). Everything ultimately
    routes through the same mode-choice model, so we only prune levers that have
    no plausible path to the metric.
    """
    fam = _family(metric_key)
    picked: list[BehaviouralRule] = []
    for r in rules:
        if not r.active:
            continue
        if r.name == "transit_reinvestment":
            # Reinvestment only bites on transit demand and mode share.
            fare = levers.get("transit_fare_multiplier", 1.0)
            speed = levers.get("transit_speed_multiplier", 1.0)
            engaged = fare != 1.0 or speed != 1.0
            if engaged and (fam in {"transit", "mode_share"}):
                picked.append(r)
            continue
        # cordon_charge (and any future car-side lever) touches every family.
        picked.append(r)
    return picked


def _find_series(delta_series: list[DeltaSeries], metric_key: str) -> DeltaSeries:
    for s in delta_series:
        if s.key == metric_key:
            return s
    raise MetricNotFound(metric_key, [s.key for s in delta_series])


def _pick_point(series: DeltaSeries, horizon_months: float | None) -> DeltaPoint:
    """Snap the requested horizon to the nearest available checkpoint."""
    points = series.points
    if horizon_months is None:
        # Default to the 5-year checkpoint if present, else the last one.
        for p in points:
            if p.t_months == 60.0:
                return p
        return points[-1]
    return min(points, key=lambda p: abs(p.t_months - horizon_months))


def _confidence(point: DeltaPoint, adaptation: dict) -> TraceConfidence:
    """Confidence from the model's own horizon-widening band (SPEC §24)."""
    base = float(adaptation.get("uncertainty_base", 0.05))
    slope = float(adaptation.get("uncertainty_slope_per_year", 0.05))
    cap = float(adaptation.get("uncertainty_cap", 0.45))
    years = point.t_months / 12.0
    unc = min(base + slope * years, cap)
    half = (point.high - point.low) / 2.0
    rel = (half / abs(point.delta) * 100.0) if point.delta else None
    return TraceConfidence(
        value=round(max(0.0, 1.0 - unc), 4),
        band_half_width=round(half, 3),
        band_rel_pct=(round(rel, 2) if rel is not None else None),
        horizon_months=point.t_months,
    )


def _mechanism_step(rule: BehaviouralRule, metric_key: str) -> TraceStep:
    """Turn a behavioural lever into a transform node on the trace."""
    fam = _family(metric_key)
    if rule.name == "cordon_charge":
        detail = (
            f"Charge adds {rule.value:g} to car generalized cost per CBD-bound trip "
            f"({rule.source}) → car utility falls, some commuters re-choose mode."
        )
    elif rule.name == "transit_reinvestment":
        direction = "transit demand rises" if fam in {"transit"} else "public-transit share rises"
        detail = (
            f"Revenue-funded service uplift ({rule.source}) cuts effective transit "
            f"cost and raises effective speed → transit utility rises, {direction}."
        )
    else:  # pragma: no cover - defensive, future levers
        detail = f"{rule.label}: {rule.parameter} = {rule.value:g}."
    return TraceStep(
        stage="transform",
        label=rule.label,
        detail=detail,
        tag=MetricTag.simulated,
        value=rule.value,
        unit=rule.unit,
        refs=[rule.name],
    )


def _build_chain(
    metric_key: str,
    metric_label: str,
    unit: str,
    tag: MetricTag,
    point: DeltaPoint,
    rules: list[BehaviouralRule],
) -> list[TraceStep]:
    fam = _family(metric_key)
    steps: list[TraceStep] = [
        TraceStep(
            stage="input-data",
            label="Auckland analysis grid (modelled)",
            detail="Commuter population, origin/destination cohorts and baseline mode "
            "split — the World-A no-intervention reference.",
            tag=MetricTag.simulated,
            value=round(point.world_a, 3),
            unit=unit,
            refs=["dataset:auckland"],
        )
    ]
    steps.extend(_mechanism_step(r, metric_key) for r in rules)
    steps.append(
        TraceStep(
            stage="model",
            label="Mode-choice model",
            detail="Deterministic agent-based multinomial mode choice re-allocates "
            "commuters across car / transit / walk by generalized-cost utility, "
            "weighted by origin/destination cohort.",
            tag=MetricTag.simulated,
            refs=["backend/app/simulation/model.py"],
        )
    )
    if fam == "emissions":
        steps.append(
            TraceStep(
                stage="transform",
                label="Emissions factor",
                detail="Remaining vehicle-km × CO₂ intensity → commute CO₂; falls with "
                "traffic, so it inherits traffic's trace upstream.",
                tag=MetricTag.simulated,
                refs=["emissions.co2_kg_per_km"],
            )
        )
    steps.append(
        TraceStep(
            stage="model",
            label="Staged adaptation over horizon",
            detail="Short-run behavioural substitution then mid-run revenue-funded "
            "transit ramp move the metric from the no-intervention state toward the "
            "fully-adapted policy state; the band widens with the horizon.",
            tag=MetricTag.simulated,
            refs=["backend/app/simulation/timeline.py"],
        )
    )
    steps.append(
        TraceStep(
            stage="result",
            label=metric_label,
            detail=(
                f"World A {point.world_a:g} → World B {point.world_b:g}; "
                f"Δ {point.delta:+g} {unit}"
                + (f" ({point.delta_pct:+.1f}% vs baseline)" if point.delta_pct is not None else "")
                + f" at {point.t_months:g} months, band [{point.low:g}, {point.high:g}]."
            ),
            tag=tag,
            value=round(point.delta, 3),
            unit=unit,
            refs=[metric_key],
        )
    )
    return steps


def _ascii_trace(
    metric_label: str, unit: str, point: DeltaPoint, rules: list[BehaviouralRule]
) -> str:
    lines: list[str] = []
    lever_names = [r.label for r in rules] or ["Policy intervention"]
    lines.append(" + ".join(lever_names))
    lines.append("↓")
    lines.append("commuter generalized-cost change")
    lines.append("↓")
    lines.append("mode-choice model")
    lines.append("↓")
    lines.append("predicted mode switch, weighted by origin/destination cohort")
    lines.append("↓")
    lines.append("staged adaptation over the horizon")
    lines.append("↓")
    pct = f" ({point.delta_pct:+.1f}%)" if point.delta_pct is not None else ""
    lines.append(
        f"{point.delta:+g} {unit}{pct} at {point.t_months:g} months → {metric_label}"
    )
    return "\n".join(lines)


def _assumptions(adaptation: dict, metric_assumptions: list[str]) -> list[TraceAssumption]:
    out: list[TraceAssumption] = []
    labels = {
        "behaviour_tau_months": ("months", "Time-constant of short-run mode substitution."),
        "transit_lag_months": ("months", "Lead time before reinvested service comes online."),
        "transit_tau_months": ("months", "Time-constant of the transit capacity ramp."),
        "demand_growth_per_year": ("/yr", "Exogenous background travel-demand growth."),
        "uncertainty_base": ("frac", "Band half-width at T0."),
        "uncertainty_slope_per_year": ("frac/yr", "How fast the band widens with horizon."),
        "uncertainty_cap": ("frac", "Maximum band half-width."),
    }
    for key, val in adaptation.items():
        unit, detail = labels.get(key, ("", ""))
        out.append(TraceAssumption(name=key, value=val, unit=unit, detail=detail))
    # Named per-metric assumptions carried on the metric itself (SPEC §7.5).
    for name in metric_assumptions:
        out.append(
            TraceAssumption(
                name=name,
                value="see behavioural rule / calibration",
                detail="Named assumption this metric's baseline computation depends on.",
            )
        )
    return out


def run_evidence(
    policy: PolicyDSL,
    metric_key: str,
    *,
    shocks: Shocks | None = None,
    horizon_months: float | None = None,
) -> ProvenanceTrace:
    """Assemble the full causal trace for ``metric_key`` under ``policy``."""
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)
    b_full = compute_world_b(policy, params=params, reinvestment=True)
    b_behav = compute_world_b(policy, params=params, reinvestment=False)
    b_ts = build_world_b_timeline(
        policy,
        baseline=base,
        world_b_full=b_full,
        world_b_behaviour=b_behav,
        params=params,
        trend=trend,
    )
    delta = build_delta(base_ts, b_ts)

    series = _find_series(delta.series, metric_key)
    point = _pick_point(series, horizon_months)
    checkpoint = next(
        (c for c in delta.checkpoints if c.t_months == point.t_months),
        Checkpoint(label=f"{point.t_months:g}m", t_months=point.t_months, t_years=point.t_months / 12.0),
    )

    rules = _rules_for(metric_key, b_full.behavioural_rules, b_full.levers)
    # Metric-level named assumptions (from the World-B snapshot metric, if present).
    metric_assumptions: list[str] = []
    for m in b_full.metrics:
        if m.key == metric_key:
            metric_assumptions = list(m.assumptions)
            break

    return ProvenanceTrace(
        policy_id=policy.id,
        metric_key=metric_key,
        metric_label=series.label,
        unit=series.unit,
        tag=series.tag,
        horizon=checkpoint,
        available_horizons_months=[c.t_months for c in delta.checkpoints],
        result=TraceResult(
            world_a=round(point.world_a, 3),
            world_b=round(point.world_b, 3),
            delta=round(point.delta, 3),
            delta_pct=point.delta_pct,
            low=round(point.low, 3),
            high=round(point.high, 3),
        ),
        confidence=_confidence(point, b_ts.adaptation),
        ascii_trace=_ascii_trace(series.label, series.unit, point, rules),
        chain=_build_chain(metric_key, series.label, series.unit, series.tag, point, rules),
        rules=rules,
        assumptions=_assumptions(b_ts.adaptation, metric_assumptions),
        historical_analogues=list(_ANALOGUES),
        citations=list(_CITATIONS),
    )

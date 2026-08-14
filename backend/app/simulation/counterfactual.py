"""Counterfactual comparison: World A vs B vs amended C/D… (ROADMAP M7, SPEC §21).

SPEC §21 requires that intervention metrics are never shown without the
baseline, and that additional worlds (an opposition amendment, an optimised
policy) can be compared side by side against it. This module assembles one
payload holding:

* **World A** — the no-intervention baseline (snapshot + trajectory),
* **World B** — the compiled policy (intervention),
* **World C, D…** — one per supplied amendment,

each carrying its Δ-vs-baseline and Δ-vs-intervention, plus a compact headline
table (baseline + every world + Δ per metric at one horizon) the dashboard can
render directly.

Guardrail (SPEC §34): amendments only edit the *structured policy*; every number
comes from the same deterministic model, so all worlds/deltas are Simulated. No
LLM is on the numeric path.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.model import compute_baseline
from ..baseline.schema import BaselineMetrics, BaselineTimeSeries, Checkpoint, MetricTag
from ..baseline.timeseries import build_timeseries
from ..policy.dsl import (
    Intervention,
    InterventionType,
    PolicyDSL,
    RevenueAllocation,
)
from .amendment import (
    Amendment,
    apply_amendment,
    propose_opposition_amendment,
)
from .compare import build_delta
from .model import compute_world_b
from .schema import DeltaTimeSeries, WorldBMetrics, WorldBTimeSeries
from .shocks import Shocks, apply_shocks
from .timeline import build_world_b_timeline

# World ids beyond the baseline (A) and the intervention (B).
_WORLD_IDS = ["B", "C", "D", "E", "F", "G", "H"]


class WorldAResult(BaseModel):
    snapshot: BaselineMetrics
    timeseries: BaselineTimeSeries


class CounterfactualWorld(BaseModel):
    """One intervention world (B, C, D…) with its deltas."""

    id: str = Field(description="World id, e.g. 'B' (intervention) or 'C' (amendment).")
    role: str = Field(description="'intervention' | 'amendment'.")
    label: str = Field(description="Human name for the world.")
    policy_id: str
    changes: list[str] = Field(
        default_factory=list, description="Concrete edits vs the base policy (amendments)."
    )
    snapshot: WorldBMetrics
    timeseries: WorldBTimeSeries
    delta_vs_baseline: DeltaTimeSeries = Field(description="Δ(world − World A).")
    delta_vs_intervention: DeltaTimeSeries | None = Field(
        default=None, description="Δ(world − World B); None for World B itself."
    )


class ComparisonCell(BaseModel):
    """One world's value for one metric at the headline horizon."""

    world_id: str
    value: float
    delta_vs_baseline: float
    delta_pct: float | None = None


class ComparisonRow(BaseModel):
    """One metric across all worlds at the headline horizon."""

    key: str
    label: str
    unit: str
    tag: MetricTag = MetricTag.simulated
    baseline_value: float = Field(description="World-A value (never omitted, SPEC §21).")
    cells: list[ComparisonCell] = Field(default_factory=list)


class CounterfactualComparison(BaseModel):
    """World A vs B vs amended C/D… in one payload (SPEC §21)."""

    provenance: MetricTag = Field(MetricTag.simulated)
    note: str = Field(
        default=(
            "Counterfactual set: World A (baseline) vs World B (intervention) vs any "
            "amendment worlds, all from the same deterministic model. Δ outcome = "
            "world − World A; the baseline is always present (SPEC §21/§34)."
        )
    )
    base_policy_id: str
    horizon: Checkpoint = Field(description="Horizon the headline table is quoted at.")
    world_a: WorldAResult
    worlds: list[CounterfactualWorld] = Field(default_factory=list)
    headline_table: list[ComparisonRow] = Field(
        default_factory=list, description="Baseline + every world + Δ per metric (SPEC §21)."
    )
    derivation: dict | None = Field(
        default=None,
        description="How the C/D worlds were derived (present only for the "
        "grand A/B/C/D comparison; None for a plain amendment comparison).",
    )


def _pick_point(series, horizon_months: float | None):
    if horizon_months is None:
        for p in series.points:
            if p.t_months == 60.0:
                return p
        return series.points[-1]
    return min(series.points, key=lambda p: abs(p.t_months - horizon_months))


def compare_counterfactuals(
    policy: PolicyDSL,
    amendments: list[Amendment] | None = None,
    *,
    shocks: Shocks | None = None,
    horizon_months: float | None = None,
) -> CounterfactualComparison:
    """Build the A / B / C… counterfactual payload for ``policy``."""
    amendments = amendments or []
    params, trend = apply_shocks(shocks)

    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)

    # World B — the intervention itself.
    intervention_specs = [("B", "intervention", "Intervention", policy, [])]
    for i, amd in enumerate(amendments):
        wid = _WORLD_IDS[min(i + 1, len(_WORLD_IDS) - 1)]
        amended = apply_amendment(policy, amd)
        intervention_specs.append((wid, "amendment", amd.label, amended, amd.describe()))

    return _assemble_comparison(
        base_policy_id=policy.id,
        base=base,
        base_ts=base_ts,
        params=params,
        trend=trend,
        intervention_specs=intervention_specs,
        horizon_months=horizon_months,
    )


def _assemble_comparison(
    *,
    base_policy_id: str,
    base: BaselineMetrics,
    base_ts: BaselineTimeSeries,
    params,
    trend,
    intervention_specs,
    horizon_months: float | None,
    note: str | None = None,
    derivation: dict | None = None,
) -> CounterfactualComparison:
    """Simulate every world spec vs the shared baseline and build the payload.

    ``intervention_specs`` is a list of ``(world_id, role, label, policy, changes)``
    tuples; the first is always World B (the intervention). Shared by the plain
    amendment comparison and the grand A/B/C/D comparison so both produce
    byte-identical worlds/deltas from the same deterministic path (SPEC §34).
    """
    worlds: list[CounterfactualWorld] = []
    b_ts_ref: WorldBTimeSeries | None = None
    for wid, role, label, wpolicy, changes in intervention_specs:
        snapshot = compute_world_b(wpolicy, params=params, reinvestment=True)
        w_ts = build_world_b_timeline(wpolicy, baseline=base, params=params, trend=trend)
        delta_vs_baseline = build_delta(base_ts, w_ts)
        if wid == "B":
            b_ts_ref = w_ts
            delta_vs_intervention = None
        else:
            delta_vs_intervention = build_delta(b_ts_ref, w_ts) if b_ts_ref else None
        worlds.append(
            CounterfactualWorld(
                id=wid,
                role=role,
                label=label,
                policy_id=wpolicy.id,
                changes=changes,
                snapshot=snapshot,
                timeseries=w_ts,
                delta_vs_baseline=delta_vs_baseline,
                delta_vs_intervention=delta_vs_intervention,
            )
        )

    # Headline table: one row per metric, baseline + each world at the horizon.
    checkpoint: Checkpoint | None = None
    rows: list[ComparisonRow] = []
    ref_delta = worlds[0].delta_vs_baseline  # World B provides the metric list.
    for series in ref_delta.series:
        cells: list[ComparisonCell] = []
        baseline_value: float | None = None
        for w in worlds:
            w_series = next((s for s in w.delta_vs_baseline.series if s.key == series.key), None)
            if w_series is None:
                continue
            pt = _pick_point(w_series, horizon_months)
            if checkpoint is None:
                checkpoint = Checkpoint(
                    label=f"{pt.t_months:g}m",
                    t_months=pt.t_months,
                    t_years=round(pt.t_months / 12.0, 3),
                )
            baseline_value = pt.world_a
            cells.append(
                ComparisonCell(
                    world_id=w.id,
                    value=round(pt.world_b, 3),
                    delta_vs_baseline=round(pt.delta, 3),
                    delta_pct=pt.delta_pct,
                )
            )
        rows.append(
            ComparisonRow(
                key=series.key,
                label=series.label,
                unit=series.unit,
                tag=series.tag,
                baseline_value=round(baseline_value or 0.0, 3),
                cells=cells,
            )
        )

    if checkpoint is None:  # pragma: no cover - defensive (no metrics)
        checkpoint = Checkpoint(label="60m", t_months=60.0, t_years=5.0)

    kwargs = {}
    if note is not None:
        kwargs["note"] = note
    return CounterfactualComparison(
        base_policy_id=base_policy_id,
        horizon=checkpoint,
        world_a=WorldAResult(snapshot=base, timeseries=base_ts),
        worlds=worlds,
        headline_table=rows,
        derivation=derivation,
        **kwargs,
    )


def _policy_from_candidate_config(cfg, policy_id: str) -> PolicyDSL:
    """Rebuild a Policy DSL from an optimiser :class:`CandidateConfig`.

    Mirrors the optimiser's own grid builder so World D re-simulates through the
    identical deterministic path as every other world (SPEC §34) — the optimiser
    only *chooses* which policy; the numbers here come from the same model.
    """
    itype = InterventionType(cfg.intervention_type)
    exemptions = ["low-income"] if cfg.exempt_low_income else []
    pt = cfg.public_transport_share
    return PolicyDSL(
        id=policy_id,
        intervention=Intervention(type=itype, amount=cfg.charge_amount, currency="local"),
        exemptions=exemptions,
        revenue_allocation=RevenueAllocation(
            public_transport=pt, general_fund=round(1.0 - pt, 4)
        ),
    )


def _describe_optimised(cfg) -> list[str]:
    """Concise human description of the optimiser's chosen World-D policy."""
    out: list[str] = [f"intervention: {cfg.intervention_type}"]
    if cfg.charge_amount is not None:
        out.append(f"charge {cfg.charge_amount:g}/day")
    if cfg.pedestrianised:
        out.append("pedestrianised cordon (car ban)")
    out.append(f"reinvest {cfg.public_transport_share:.0%} of revenue in transit")
    if cfg.exempt_low_income:
        out.append("exempt low-income commuters")
    return out


def compare_grand(
    policy: PolicyDSL,
    *,
    amendment: Amendment | None = None,
    objective: dict | None = None,
    constraints: dict | None = None,
    shocks: Shocks | None = None,
    horizon_months: float | None = None,
) -> CounterfactualComparison:
    """Build the canonical §21 four-way A / B / C / D comparison.

    * **World A** — baseline (no policy).
    * **World B** — ``policy`` (the intervention).
    * **World C** — the opposition amendment: ``amendment`` if supplied, else the
      deterministic default from :func:`propose_opposition_amendment`.
    * **World D** — the GOV SIM-optimised policy: the §22 optimiser's *best-balanced*
      recommendation (given ``objective``/``constraints``), re-simulated here.

    World C/D are composed from existing deterministic services — no new numeric
    model, no LLM (SPEC §21/§22/§34).
    """
    # Import here to avoid any import-time coupling with the optimiser package.
    from ..optimiser import optimise_policy

    objective = objective or {}
    constraints = constraints or {}
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)

    specs = [("B", "intervention", "World B — Intervention", policy, [])]
    derivation: dict = {}

    # World C — opposition amendment (caller override or deterministic default).
    if amendment is not None:
        amd, c_source, c_rationale = amendment, "caller", "Caller-supplied amendment."
    else:
        amd, c_source, c_rationale = propose_opposition_amendment(policy)
    if amd is not None:
        amended = apply_amendment(policy, amd)
        specs.append(
            ("C", "opposition_amendment", f"World C — {amd.label}", amended, amd.describe())
        )
    derivation["world_c"] = {
        "role": "Opposition Amendment (SPEC §21)",
        "source": c_source,
        "proposed": amd is not None,
        "amendment": amd.model_dump() if amd is not None else None,
        "rationale": c_rationale,
    }

    # World D — GOV SIM-optimised policy (best-balanced pick from the §22 optimiser).
    opt = optimise_policy(objective, constraints, shocks=shocks)
    rec = opt.recommendations
    # Prefer the best-balanced pick (SPEC §22 "Policy D — best balanced"); fall
    # back through the other recommendations, then the frontier, then any candidate.
    which = "none"
    chosen_id = None
    for slot in ("best_balanced", "largest_emissions_reduction", "most_equitable", "cheapest"):
        pid = getattr(rec, slot)
        if pid:
            which, chosen_id = slot, pid
            break
    if chosen_id is None and opt.pareto_front:
        which, chosen_id = "pareto_front", opt.pareto_front[0].policy_id
    if chosen_id is None and opt.candidates:
        which, chosen_id = "first_candidate", opt.candidates[0].policy_id
    chosen = next((c for c in opt.candidates if c.policy_id == chosen_id), None)
    if chosen is not None:
        d_policy = _policy_from_candidate_config(chosen.config, "world_d_optimised")
        specs.append(
            ("D", "optimised", "World D — GOV SIM-optimised", d_policy, _describe_optimised(chosen.config))
        )
    derivation["world_d"] = {
        "role": "GOV SIM Optimised Policy (SPEC §21/§22)",
        "objective": objective,
        "constraints": constraints,
        "constraints_satisfiable": opt.constraints_satisfiable,
        "selection": which,
        "chosen_policy_id": chosen_id,
        "config": chosen.config.model_dump() if chosen is not None else None,
        "feasible": chosen.feasible if chosen is not None else None,
        "n_candidates": opt.n_candidates,
        "n_feasible": opt.n_feasible,
    }

    note = (
        "Grand counterfactual (SPEC §21): World A (baseline) vs World B "
        "(intervention) vs World C (opposition amendment) vs World D "
        "(GOV SIM-optimised). Δ outcome = world − World A; the baseline is always "
        "present. World C/D are composed from the deterministic amendment + "
        "optimiser services — all Simulated, no LLM (SPEC §34)."
    )
    return _assemble_comparison(
        base_policy_id=policy.id,
        base=base,
        base_ts=base_ts,
        params=params,
        trend=trend,
        intervention_specs=specs,
        horizon_months=horizon_months,
        note=note,
        derivation=derivation,
    )

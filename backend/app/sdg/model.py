"""Map simulation + opinion outcomes onto SDG targets (SPEC §23).

The core GOV SIM alignment is **SDG 11** (sustainable cities / transport) and
**SDG 16** (effective, transparent, evidence-informed institutions); the
secondary alignment is **SDG 10** (reduced inequalities) and **SDG 13** (climate
action). We map each to measurable indicators / transparent proxies rather than
inventing an arbitrary composite score (SPEC §23).

Numbers are pulled straight from the deterministic World-A/World-B model, the
cohort-opinion burden model, and the run's own audit artifacts (provenance-tagged
metrics + event ledger). No LLM touches the numeric path (SPEC §34).
"""

from __future__ import annotations

from typing import Optional

from ..baseline.model import compute_baseline, mode_options, pick_mode
from ..baseline.params import DEFAULT_PARAMS
from ..baseline.schema import Checkpoint, MetricTag
from ..baseline.timeseries import build_timeseries
from ..opinion.model import _LOW_BANDS, compute_public_opinion
from ..policy.dsl import PolicyDSL
from ..simulation.compare import build_delta
from ..simulation.events import build_event_ledger
from ..simulation.model import compute_world_b
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .. import dataset
from .schema import SdgGoal, SdgIndicator, SdgReport


def _pick(series, horizon_months: Optional[float]):
    """Nearest point to the requested horizon (default 5 years)."""
    target = 60.0 if horizon_months is None else horizon_months
    return min(series.points, key=lambda p: abs(p.t_months - target))


def _conf_label(c: float) -> str:
    if c >= 0.66:
        return "high"
    if c >= 0.4:
        return "medium"
    return "low"


def _horizon_decay(t_years: float) -> float:
    """Confidence falls with the horizon (SPEC §9/§24): 1.0 now → 0.5 at 10y+."""
    return max(0.5, 1.0 - 0.05 * t_years)


def _forecast_confidence(base_conf: float, t_years: float, dp) -> float:
    """Combine a mapping-directness prior, Δ-band width and horizon decay.

    ``dp`` is a :class:`~app.simulation.schema.DeltaPoint` (carries ``delta`` and
    a ``low``/``high`` Δ band). A wider band relative to the effect ⇒ less
    confident; confidence also decays with the horizon (SPEC §9/§24).
    """
    half = (dp.high - dp.low) / 2.0
    denom = max(abs(dp.delta), 1e-9)
    band_factor = max(0.3, 1.0 - min(1.0, half / denom * 0.5))
    return round(base_conf * band_factor * _horizon_decay(t_years), 3)


def _indicator(
    id_: str,
    target: str,
    name: str,
    proxy_for: str,
    unit: str,
    baseline: float,
    scenario: float,
    better_when: str,
    data_source: str,
    confidence: float,
    tag: MetricTag,
    note: str = "",
) -> SdgIndicator:
    change = round(scenario - baseline, 4)
    change_pct = round(100.0 * change / baseline, 2) if abs(baseline) > 1e-9 else None
    if abs(change) < 1e-9:
        improved = False
    elif better_when == "higher":
        improved = change > 0
    else:
        improved = change < 0
    return SdgIndicator(
        id=id_,
        sdg_target=target,
        indicator=name,
        proxy_for=proxy_for,
        unit=unit,
        baseline=round(baseline, 4),
        scenario=round(scenario, 4),
        change=change,
        change_pct=change_pct,
        better_when=better_when,
        improved=improved,
        data_source=data_source,
        confidence=confidence,
        confidence_label=_conf_label(confidence),
        tag=tag,
        note=note,
    )


def _distributional_burden(policy: PolicyDSL, params) -> tuple[float, float]:
    """(avg commuter cost increase %, low-income cost increase %) via opinion cohorts.

    Mirrors the optimiser's real generalized-cost burden: size-weighted mean
    material impact of the policy on all commuters vs the lowest income bands,
    normalised by the baseline generalized cost.
    """
    # Baseline reference generalized cost (all commuters, low-income commuters).
    tot = tot_n = low = low_n = 0.0
    for a in dataset.population_agents():
        opts = mode_options(a, DEFAULT_PARAMS)
        gc = opts[pick_mode(opts)]
        tot += gc
        tot_n += 1
        if a["income_band"] in _LOW_BANDS:
            low += gc
            low_n += 1
    ref_all = tot / max(1.0, tot_n)
    ref_low = low / max(1.0, low_n)

    op = compute_public_opinion(policy, params=params)
    all_w = all_n = lw = ln = 0.0
    for c in op.cohorts:
        all_w += c.mean_material_impact * c.size
        all_n += c.size
        if c.income_band in _LOW_BANDS:
            lw += c.mean_material_impact * c.size
            ln += c.size
    mean_all = all_w / max(1.0, all_n)
    mean_low = lw / max(1.0, ln)
    avg_pct = mean_all / ref_all * 100.0 if ref_all else 0.0
    low_pct = mean_low / ref_low * 100.0 if ref_low else 0.0
    return round(avg_pct, 3), round(low_pct, 3)


def build_sdg_report(
    policy: PolicyDSL,
    *,
    shocks: Optional[Shocks] = None,
    horizon_months: Optional[float] = None,
) -> SdgReport:
    """Assemble the SDG alignment report for a compiled policy (SPEC §23)."""
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

    by_key = {s.key: s for s in delta.series}

    # Resolve the horizon from any available series and echo it.
    any_series = delta.series[0]
    hp = _pick(any_series, horizon_months)
    horizon = Checkpoint(
        label=f"{hp.t_months:g}m",
        t_months=hp.t_months,
        t_years=round(hp.t_months / 12.0, 3),
    )
    t_years = horizon.t_years

    sim_src = "GOV SIM deterministic mode-choice simulation (World A vs World B)"

    def pt(key: str):
        s = by_key.get(key)
        return _pick(s, horizon_months) if s else None

    # ---- SDG 11 — Sustainable Cities and Communities (CORE) -------------------
    sdg11: list[SdgIndicator] = []

    transit_p = pt("mode_share.public_transit_pct")
    walk_p = pt("mode_share.walk_pct")
    if transit_p and walk_p:
        base_sust = transit_p.world_a + walk_p.world_a
        scen_sust = transit_p.world_b + walk_p.world_b
        conf = _forecast_confidence(0.8, t_years, transit_p)
        sdg11.append(
            _indicator(
                "sdg11.sustainable_mode_share",
                "11.2",
                "Share of commutes by sustainable modes (public transit + walking)",
                "Access to safe, affordable, sustainable transport systems",
                "% of commuters",
                base_sust,
                scen_sust,
                "higher",
                sim_src,
                conf,
                MetricTag.simulated,
                note="Sum of the public-transit and walking mode shares at this horizon.",
            )
        )

    trips = pt("traffic.vehicle_trips_into_cbd")
    if trips:
        conf = _forecast_confidence(0.8, t_years, trips)
        sdg11.append(
            _indicator(
                "sdg11.cbd_vehicle_trips",
                "11.2/11.6",
                "Daily private-vehicle trips into the city centre",
                "Congestion, road-safety exposure and per-capita environmental "
                "impact of cities",
                "vehicle trips/day",
                trips.world_a,
                trips.world_b,
                "lower",
                sim_src,
                conf,
                MetricTag.simulated,
            )
        )

    transit_trips = pt("transit.peak_into_cbd_transit_trips")
    if transit_trips:
        conf = _forecast_confidence(0.75, t_years, transit_trips)
        sdg11.append(
            _indicator(
                "sdg11.peak_transit_ridership",
                "11.2",
                "Peak public-transport trips into the city centre",
                "Provision and uptake of public transport capacity",
                "transit trips/peak",
                transit_trips.world_a,
                transit_trips.world_b,
                "higher",
                sim_src,
                conf,
                MetricTag.simulated,
            )
        )

    # ---- SDG 13 — Climate Action (SECONDARY) ----------------------------------
    sdg13: list[SdgIndicator] = []
    co2 = pt("emissions.daily_co2_tonnes")
    if co2:
        conf = _forecast_confidence(0.8, t_years, co2)
        sdg13.append(
            _indicator(
                "sdg13.transport_co2",
                "13.2",
                "Daily transport CO₂ emissions",
                "Integration of climate measures into transport policy",
                "tCO₂/day",
                co2.world_a,
                co2.world_b,
                "lower",
                sim_src + " (CO₂ = vehicle-km × emission factor)",
                conf,
                MetricTag.simulated,
            )
        )

    # ---- SDG 10 — Reduced Inequalities (SECONDARY) ----------------------------
    sdg10: list[SdgIndicator] = []
    avg_pct, low_pct = _distributional_burden(policy, params)
    # Excess burden on the lowest income bands vs the average commuter (pp).
    # Baseline = 0 (no policy ⇒ no differential burden). Regressive policies push
    # this positive; exemptions/reinvestment pull it toward or below zero.
    excess = round(low_pct - avg_pct, 3)
    sdg10.append(
        _indicator(
            "sdg10.excess_low_income_burden",
            "10.4",
            "Excess travel-cost burden on lowest-income commuters vs average",
            "Distributional fairness / unequal burden of policy on the worst-off",
            "percentage points of generalized cost",
            0.0,
            excess,
            "lower",
            "GOV SIM cohort-opinion generalized-cost burden model (income decile × "
            "geography × mode)",
            round(0.6 * _horizon_decay(t_years), 3),
            MetricTag.estimated,
            note="Positive = the charge falls harder on low-income commuters than "
            "on the average commuter (regressive); ≤0 = exemptions/reinvestment "
            "have neutralised the gap. Derived from modelled generalized-cost "
            "impacts, so Estimated.",
        )
    )

    # ---- SDG 16 — Strong, evidence-informed Institutions (CORE) ---------------
    # Transparent *process* proxies measured from the run's own audit artifacts —
    # not transport outcomes. This is what GOV SIM itself contributes to SDG 16.
    sdg16: list[SdgIndicator] = []
    headline_metrics = list(base.metrics) + list(b_full.metrics)
    n_metrics = len(headline_metrics)
    fully_documented = sum(
        1
        for m in headline_metrics
        if m.tag is not None and m.method and m.assumptions
    )
    completeness = 100.0 * fully_documented / n_metrics if n_metrics else 0.0
    sdg16.append(
        _indicator(
            "sdg16.evidence_provenance_completeness",
            "16.6/16.10",
            "Share of decision metrics published with full provenance + assumptions",
            "Transparent, accountable, evidence-informed institutions",
            "% of headline metrics",
            0.0,  # conventional opaque process publishes no model provenance
            round(completeness, 2),
            "higher",
            "GOV SIM provenance tags on the run's headline metrics (audit artifact)",
            round(0.9 * _horizon_decay(t_years), 3),
            MetricTag.estimated,
            note="Governance-process proxy, not a transport outcome: fraction of "
            "the policy's headline numbers that ship with an explicit "
            "Observed/Estimated/Simulated tag, a stated method and named "
            "assumptions. Baseline 0 = a conventional process that publishes no "
            "model. Estimated.",
        )
    )

    ledger = build_event_ledger(policy, base, delta)
    n_events = len(ledger.events)
    sdg16.append(
        _indicator(
            "sdg16.structured_reasoning_records",
            "16.7",
            "Structured cause→effect→confidence records produced for the decision",
            "Responsive, inclusive, evidence-based decision-making",
            "event-ledger entries",
            0.0,
            float(n_events),
            "higher",
            "GOV SIM event ledger (each entry carries cause / affected / confidence / "
            "downstream)",
            round(0.9 * _horizon_decay(t_years), 3),
            MetricTag.estimated,
            note="Governance-process proxy: count of auditable, cited reasoning "
            "records the twin generates for this policy. Baseline 0 = an "
            "undocumented decision.",
        )
    )

    goals = [
        SdgGoal(goal=11, title="Sustainable Cities and Communities", tier="core", indicators=sdg11),
        SdgGoal(goal=16, title="Peace, Justice and Strong Institutions", tier="core", indicators=sdg16),
        SdgGoal(goal=10, title="Reduced Inequalities", tier="secondary", indicators=sdg10),
        SdgGoal(goal=13, title="Climate Action", tier="secondary", indicators=sdg13),
    ]

    total_i = total_w = total_u = 0
    for g in goals:
        g.improved_count = sum(1 for i in g.indicators if i.improved)
        g.worsened_count = sum(
            1 for i in g.indicators if not i.improved and abs(i.change) > 1e-9
        )
        g.unchanged_count = sum(1 for i in g.indicators if abs(i.change) < 1e-9)
        total_i += g.improved_count
        total_w += g.worsened_count
        total_u += g.unchanged_count
        g.summary = (
            f"SDG {g.goal}: {g.improved_count} indicator(s) improve, "
            f"{g.worsened_count} worsen, {g.unchanged_count} unchanged."
        )

    n_ind = total_i + total_w + total_u
    headline = (
        f"Maps to {n_ind} indicators across SDGs 11, 16, 10, 13: "
        f"{total_i} improve, {total_w} worsen, {total_u} unchanged at "
        f"{horizon.label}. No composite SDG score is computed (SPEC §23)."
    )

    return SdgReport(
        policy_id=policy.id,
        horizon=horizon,
        goals=goals,
        total_improved=total_i,
        total_worsened=total_w,
        total_unchanged=total_u,
        headline=headline,
    )

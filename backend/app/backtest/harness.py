"""Backtesting harness scaffold: historical replay + scorecard (ROADMAP stretch, SPEC §25).

:func:`run_backtest` takes a :class:`HistoricalCase` (a policy plus its known
outcomes), replays it through the deterministic simulation using only
pre-implementation state, and scores the forecast against the actuals:

* forecast error (MAE / RMSE / MAPE),
* direction accuracy (did the metric move the right way vs baseline?),
* interval calibration (did actuals fall inside the forecast band?),
* event-timing error (how far off were predicted event months?).

Geographic and full distributional accuracy are out of scope for this scaffold
(the demo case carries no geographic actuals) and are flagged as such rather
than silently skipped. The forecast is Simulated; the scores are exact
arithmetic; no LLM is on the numeric path (SPEC §25/§34).
"""

from __future__ import annotations

from ..baseline.model import compute_baseline
from ..baseline.schema import MetricSeries, MetricTag
from ..baseline.timeseries import build_timeseries
from ..policy.dsl import (
    Intervention,
    InterventionType,
    PolicyDSL,
    RevenueAllocation,
)
from ..simulation.compare import build_delta
from ..simulation.events import build_event_ledger
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .schema import (
    ActualEvent,
    ActualObservation,
    EventTimingScore,
    HistoricalCase,
    MetricScore,
    Scorecard,
)


def _interp(series: MetricSeries, t: float) -> tuple[float, float | None, float | None]:
    """Linear-interpolate (value, low, high) of a metric series at month ``t``."""
    pts = series.points
    if not pts:
        return 0.0, None, None
    if t <= pts[0].t_months:
        p = pts[0]
        return p.value, p.low, p.high
    if t >= pts[-1].t_months:
        p = pts[-1]
        return p.value, p.low, p.high
    for a, b in zip(pts, pts[1:]):
        if a.t_months <= t <= b.t_months:
            span = b.t_months - a.t_months
            frac = (t - a.t_months) / span if span else 0.0
            val = a.value + frac * (b.value - a.value)
            low = a.low + frac * (b.low - a.low)
            high = a.high + frac * (b.high - a.high)
            return val, low, high
    p = pts[-1]
    return p.value, p.low, p.high


def _sign(x: float, tol: float = 1e-6) -> int:
    if x > tol:
        return 1
    if x < -tol:
        return -1
    return 0


def example_case() -> HistoricalCase:
    """A built-in synthetic benchmark case (Auckland 2018 cordon charge).

    The 'actuals' are a synthetic, illustrative benchmark near the model's own
    forecast — NOT real observations — so the scaffold produces a meaningful,
    non-trivial scorecard end-to-end. Clearly labelled Simulated.
    """
    policy = PolicyDSL(
        id="auckland_2018_cordon",
        intervention=Intervention(
            type=InterventionType.road_pricing, amount=10.0, currency="local"
        ),
        revenue_allocation=RevenueAllocation(public_transport=0.6, general_fund=0.4),
    )
    return HistoricalCase(
        id="auckland_2018_cordon",
        name="Auckland 2018 central cordon charge (synthetic benchmark)",
        description=(
            "Illustrative historical replay on the synthetic Auckland dataset: a 10/day "
            "central cordon charge with 60% of revenue reinvested in transit. Actuals are "
            "a synthetic benchmark, not real records."
        ),
        policy=policy,
        implementation_date="2018-01-01",
        horizon_months=60.0,
        observations=[
            # traffic (fewer CBD-bound car trips than baseline)
            ActualObservation(metric_key="traffic.vehicle_trips_into_cbd", t_months=12, value=250.0),
            ActualObservation(metric_key="traffic.vehicle_trips_into_cbd", t_months=60, value=240.0),
            # emissions (tonnes/day)
            ActualObservation(metric_key="emissions.daily_co2_tonnes", t_months=12, value=1.95),
            ActualObservation(metric_key="emissions.daily_co2_tonnes", t_months=60, value=2.10),
            # transit demand
            ActualObservation(metric_key="transit.peak_into_cbd_transit_trips", t_months=12, value=2750.0),
            ActualObservation(metric_key="transit.peak_into_cbd_transit_trips", t_months=60, value=3050.0),
        ],
        events=[
            ActualEvent(type="mode_shift", t_months=2.0),
            ActualEvent(type="transit_reinvestment", t_months=15.0),
            ActualEvent(type="transit_capacity", t_months=4.0),
        ],
        actuals_provenance=MetricTag.simulated,
        actuals_note=(
            "Synthetic illustrative benchmark on the Auckland dataset — NOT real "
            "observations. Replace with real outcomes for a genuine backtest."
        ),
    )


def run_backtest(case: HistoricalCase, *, shocks: Shocks | None = None) -> Scorecard:
    """Replay ``case`` through the model and score it against the actuals."""
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)
    b_ts = build_world_b_timeline(case.policy, baseline=base, params=params, trend=trend)
    delta = build_delta(base_ts, b_ts)
    ledger = build_event_ledger(case.policy, base, delta)

    fc_by_key = {s.key: s for s in b_ts.series}
    base_by_key = {s.key: s for s in base_ts.series}

    metric_scores: list[MetricScore] = []
    abs_errors: list[float] = []
    sq_errors: list[float] = []
    pct_errors: list[float] = []
    direction_hits = 0
    interval_hits = 0
    for obs in case.observations:
        fc_series = fc_by_key.get(obs.metric_key)
        base_series = base_by_key.get(obs.metric_key)
        if fc_series is None or base_series is None:
            continue
        forecast, f_low, f_high = _interp(fc_series, obs.t_months)
        baseline, _, _ = _interp(base_series, obs.t_months)
        error = forecast - obs.value
        abs_err = abs(error)
        pct = (abs_err / abs(obs.value) * 100.0) if abs(obs.value) > 1e-9 else None
        direction_correct = _sign(forecast - baseline) == _sign(obs.value - baseline)
        within = (
            f_low is not None
            and f_high is not None
            and f_low <= obs.value <= f_high
        )
        abs_errors.append(abs_err)
        sq_errors.append(error * error)
        if pct is not None:
            pct_errors.append(pct)
        direction_hits += int(direction_correct)
        interval_hits += int(bool(within))
        metric_scores.append(
            MetricScore(
                metric_key=obs.metric_key,
                t_months=obs.t_months,
                forecast=round(forecast, 3),
                forecast_low=(round(f_low, 3) if f_low is not None else None),
                forecast_high=(round(f_high, 3) if f_high is not None else None),
                actual=obs.value,
                baseline=round(baseline, 3),
                error=round(error, 3),
                abs_error=round(abs_err, 3),
                pct_error=(round(pct, 2) if pct is not None else None),
                direction_correct=direction_correct,
                within_interval=bool(within),
            )
        )

    n = len(metric_scores)
    mae = round(sum(abs_errors) / n, 3) if n else 0.0
    rmse = round((sum(sq_errors) / n) ** 0.5, 3) if n else 0.0
    mape = round(sum(pct_errors) / len(pct_errors), 2) if pct_errors else None
    direction_pct = round(direction_hits / n * 100.0, 1) if n else 0.0
    coverage_pct = round(interval_hits / n * 100.0, 1) if n else 0.0

    # Event-timing scoring: match actual events to the predicted ledger by type.
    predicted_month = {e.type: e.scenario_month for e in ledger.events}
    event_scores: list[EventTimingScore] = []
    timing_errors: list[float] = []
    for ev in case.events:
        pm = predicted_month.get(ev.type)
        if pm is None:
            event_scores.append(
                EventTimingScore(type=ev.type, predicted_month=None, actual_month=ev.t_months, matched=False)
            )
            continue
        err = abs(pm - ev.t_months)
        timing_errors.append(err)
        event_scores.append(
            EventTimingScore(
                type=ev.type,
                predicted_month=pm,
                actual_month=ev.t_months,
                timing_error_months=round(err, 2),
                matched=True,
            )
        )
    mean_timing = round(sum(timing_errors) / len(timing_errors), 2) if timing_errors else None

    summary = (
        f"{n} observations: MAE {mae}, direction {direction_pct}% correct, "
        f"{coverage_pct}% inside forecast band"
        + (f", mean event-timing error {mean_timing} months" if mean_timing is not None else "")
        + "."
    )

    return Scorecard(
        case_id=case.id,
        case_name=case.name,
        actuals_provenance=case.actuals_provenance,
        actuals_note=case.actuals_note,
        n_observations=n,
        mae=mae,
        rmse=rmse,
        mape_pct=mape,
        direction_accuracy_pct=direction_pct,
        interval_coverage_pct=coverage_pct,
        mean_event_timing_error_months=mean_timing,
        metric_scores=metric_scores,
        event_scores=event_scores,
        geographic_accuracy=(
            "Not scored in this scaffold — the demo case carries no geographic "
            "breakdown. Supply per-zone actuals to enable geographic accuracy."
        ),
        summary=summary,
    )

"""Pydantic schemas for the backtesting harness scaffold (ROADMAP stretch, SPEC §25).

Historical replay: give the model only pre-implementation data, simulate the
policy forward, and score the forecast against what actually occurred —
forecast error, direction accuracy, interval calibration and event-timing error
— producing a stored scorecard (SPEC §25).

Because the world here is the synthetic city *Auckland*, the built-in case's
"actuals" are a clearly-labelled synthetic benchmark, NOT real observations. The
harness itself is real and works on any supplied case with genuine outcomes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import MetricTag
from ..policy.dsl import PolicyDSL


class ActualObservation(BaseModel):
    """One observed outcome to score the forecast against."""

    metric_key: str = Field(description="Metric key, e.g. 'traffic.vehicle_trips_into_cbd'.")
    t_months: float = Field(description="Months after implementation the outcome was measured.")
    value: float = Field(description="The observed value.")
    low: float | None = Field(default=None, description="Observed lower bound (optional).")
    high: float | None = Field(default=None, description="Observed upper bound (optional).")


class ActualEvent(BaseModel):
    """One observed event, for event-timing scoring."""

    type: str = Field(description="Event family, matching the simulation ledger's type.")
    t_months: float = Field(description="Month the event was actually observed.")


class HistoricalCase(BaseModel):
    """A policy + its known outcomes, for historical replay (SPEC §25)."""

    id: str
    name: str
    description: str = ""
    policy: PolicyDSL
    implementation_date: str | None = Field(
        default=None, description="ISO date the policy took effect."
    )
    horizon_months: float = Field(default=60.0, description="Replay horizon.")
    observations: list[ActualObservation] = Field(default_factory=list)
    events: list[ActualEvent] = Field(default_factory=list)
    actuals_provenance: MetricTag = Field(
        MetricTag.observed,
        description="Provenance of the actuals (Observed for real cases; the built-in "
        "demo case overrides this to Simulated — a synthetic benchmark).",
    )
    actuals_note: str = Field(
        default="Actual outcomes supplied by the caller.",
    )


class MetricScore(BaseModel):
    """Forecast-vs-actual score for one metric at one checkpoint."""

    metric_key: str
    t_months: float
    forecast: float
    forecast_low: float | None = None
    forecast_high: float | None = None
    actual: float
    baseline: float = Field(description="No-intervention value (for direction accuracy).")
    error: float = Field(description="forecast − actual.")
    abs_error: float
    pct_error: float | None = Field(default=None, description="error / actual × 100 (None if actual≈0).")
    direction_correct: bool = Field(
        description="sign(forecast − baseline) matches sign(actual − baseline)."
    )
    within_interval: bool = Field(
        description="Whether the actual fell inside the forecast's uncertainty band."
    )


class EventTimingScore(BaseModel):
    """Predicted-vs-actual timing for one event type."""

    type: str
    predicted_month: float | None = None
    actual_month: float | None = None
    timing_error_months: float | None = None
    matched: bool = Field(description="Whether the event was both predicted and observed.")


class Scorecard(BaseModel):
    """Backtest scorecard for one case (SPEC §25)."""

    provenance: MetricTag = Field(MetricTag.simulated)
    note: str = Field(
        default=(
            "Historical replay: the deterministic model forecasts the policy from "
            "pre-implementation state only, scored against supplied actuals. Forecast "
            "is Simulated; scores are exact arithmetic. No LLM (SPEC §25/§34)."
        )
    )
    case_id: str
    case_name: str
    actuals_provenance: MetricTag
    actuals_note: str

    n_observations: int
    mae: float = Field(description="Mean absolute error across observations.")
    rmse: float = Field(description="Root-mean-square error across observations.")
    mape_pct: float | None = Field(
        default=None, description="Mean absolute percentage error (observations with actual≠0)."
    )
    direction_accuracy_pct: float = Field(description="% of observations with the right direction.")
    interval_coverage_pct: float = Field(
        description="% of observations inside the forecast band (calibration)."
    )
    mean_event_timing_error_months: float | None = Field(
        default=None, description="Mean |predicted − actual| month over matched events."
    )

    metric_scores: list[MetricScore] = Field(default_factory=list)
    event_scores: list[EventTimingScore] = Field(default_factory=list)
    geographic_accuracy: str | None = Field(
        default=None,
        description="Not scored in the scaffold — no geographic actuals in the demo case.",
    )
    summary: str = Field(default="")

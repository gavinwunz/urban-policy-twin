"""Pydantic schemas for the Historical Analogue / Causal Layer (SPEC §7.1).

This layer estimates a policy effect from *comparable real-world interventions*
rather than from the synthetic-city agent model. Its outputs follow the exact
shape SPEC §7.1 asks for:

    Estimated policy effect
    Confidence interval
    Historical analogue quality
    Parallel-trend / identification diagnostics
    Transferability score

Provenance (SPEC §34): each historical scheme's reported outcome is tagged
**Observed** (a real, published effect) but flagged *illustrative / approximate*
— these are reference figures assembled for the prototype, not a live causal-
inference pipeline over this city's microdata. The *transfer* of those effects
to the input policy is **Estimated** (a cross-scheme judgement). No LLM touches
any number.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import MetricTag


class HistoricalCase(BaseModel):
    """One real-world congestion-pricing / access-restriction scheme."""

    id: str = Field(description="Stable key, e.g. 'london_ccz'.")
    name: str
    city: str
    country: str
    year: int = Field(description="Year the scheme (or the studied phase) began.")
    intervention_family: str = Field(
        description="Which of our InterventionType families this scheme belongs to."
    )
    scheme: str = Field(description="One-line description of the mechanism.")

    # --- Reported outcome (the DiD 'treated' arm) --------------------------
    treated_change_pct: float = Field(
        description="Reported change in cordon/central car traffic, post vs pre (%, negative = fall)."
    )
    control_change_pct: float = Field(
        description="Background/untreated trend over the same window (%) — the DiD control arm."
    )
    charge_per_day_ref: float | None = Field(
        default=None,
        description="Approximate introductory daily charge in the scheme's own currency (None for a car ban).",
    )
    reinvested_in_transit: bool = Field(
        description="Whether scheme revenue was recycled into public transport."
    )

    # --- Identification / quality (SPEC §7.1 diagnostics) ------------------
    design: str = Field(
        description="Strongest available study design (natural experiment / DiD / event study / referendum)."
    )
    identification_strength: float = Field(
        ge=0.0, le=1.0, description="How credibly the effect is causally identified (0..1)."
    )
    parallel_trend_note: str = Field(description="Parallel-trends / confounding caveat for this case.")
    context_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description="Documented similarity of the scheme's city context to Auckland (0..1, Estimated).",
    )
    mode_shift_note: str = Field(default="", description="Where displaced trips went, if reported.")
    source_note: str = Field(
        default="Illustrative, approximate published figure — not a live data source."
    )
    tag: MetricTag = Field(
        MetricTag.observed,
        description="Historical outcomes are Observed (real), but flagged illustrative/approximate.",
    )


class CaseEstimate(BaseModel):
    """A single case's difference-in-differences effect and transfer weight."""

    case_id: str
    name: str
    year: int
    applicable: bool = Field(description="True when the scheme's family matches the input policy.")
    did_effect_pct: float = Field(
        description="Difference-in-differences effect = treated_change − control_change (%)."
    )
    identification_strength: float
    transferability_score: float = Field(
        ge=0.0, le=1.0, description="How transferable this case is to the input policy (0..1)."
    )
    analogue_quality: float = Field(
        ge=0.0, le=1.0, description="identification_strength × transferability_score."
    )
    pool_weight: float = Field(ge=0.0, description="Normalised weight this case carries in the pool.")
    transfer_factors: dict = Field(
        default_factory=dict, description="The components that built the transferability score."
    )
    note: str = Field(default="")
    tag: MetricTag = Field(MetricTag.observed)


class StructuralComparison(BaseModel):
    """Cross-checks the analogue estimate against the agent-based model (SPEC §8 honesty)."""

    structural_effect_pct: float = Field(
        description="The agent-based World-B model's own flagship cordon Δ% at this horizon (Simulated)."
    )
    analogue_effect_pct: float = Field(description="This layer's pooled analogue estimate (Estimated).")
    gap_pct_points: float = Field(description="structural − analogue (percentage points).")
    agreement: str = Field(description="'consistent' | 'moderate gap' | 'large gap'.")
    interpretation: str = Field(default="")
    tag: MetricTag = Field(MetricTag.estimated)


class AnalogueEstimate(BaseModel):
    """Full Historical Analogue / Causal Layer payload for one policy (SPEC §7.1)."""

    provenance: MetricTag = Field(
        MetricTag.estimated,
        description="Per-case outcomes are Observed; the transferred estimate for THIS policy is Estimated.",
    )
    note: str = Field(
        default=(
            "Historical Analogue / Causal Layer (SPEC §7.1): estimates the flagship "
            "cordon-traffic effect from comparable real-world schemes via a "
            "difference-in-differences read (treated change − background trend) "
            "transferred to this policy by an auditable similarity score. Historical "
            "outcomes are Observed but illustrative/approximate published figures, not "
            "this city's microdata; the transferred estimate is Estimated. No LLM "
            "touches any number (SPEC §7.1/§34)."
        )
    )
    policy_id: str
    intervention_family: str
    horizon_label: str
    metric_key: str = Field(default="traffic.vehicle_trips_into_cbd")
    metric_label: str = Field(default="Vehicle trips into the central cordon")

    estimated_effect_pct: float = Field(
        description="Transfer-weighted central estimate of the % reduction (negative = fall)."
    )
    ci_low_pct: float = Field(description="Low edge of the confidence interval (%).")
    ci_high_pct: float = Field(description="High edge of the confidence interval (%).")
    analogue_quality: str = Field(description="'strong' | 'moderate' | 'weak' overall analogue quality.")
    transferability_score: float = Field(
        ge=0.0, le=1.0, description="Pooled transferability across contributing cases (0..1)."
    )

    cases: list[CaseEstimate] = Field(default_factory=list)
    identification_diagnostics: list[str] = Field(
        default_factory=list, description="Parallel-trend / identification caveats (SPEC §7.1)."
    )
    structural_comparison: StructuralComparison | None = Field(
        default=None, description="Optional cross-check vs the agent-based model."
    )
    not_modelled: list[str] = Field(
        default_factory=list, description="Honest boundaries of this layer (SPEC §34)."
    )

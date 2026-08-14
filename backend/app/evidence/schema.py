"""Pydantic schemas for the evidence / provenance trace (ROADMAP M7, SPEC §26).

The Evidence Drawer lets a policymaker click any output number and walk the
causal trace all the way down to the underlying evidence:

    input-data → transform → model → assumptions → result (+ confidence)

Nothing here is an LLM-generated number. Every value on the trace is copied
straight from the deterministic simulation output (World A / World B / Δ) or is
a static, clearly-labelled reference fact (real-world analogues / citations).
Guardrail (SPEC §34): the LLM never produces or edits a number on this path.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import Checkpoint, MetricTag
from ..simulation.schema import BehaviouralRule


class TraceStep(BaseModel):
    """One node on the causal trace (SPEC §26).

    Ordered from raw inputs to the final number so the drawer can render the
    ``input-data → … → result`` ladder shown in the spec.
    """

    stage: str = Field(
        description="'input-data' | 'transform' | 'model' | 'assumption' | 'result'."
    )
    label: str = Field(description="Short node label, e.g. 'Mode-choice model'.")
    detail: str = Field(description="One-line explanation of what happens at this node.")
    tag: MetricTag = Field(description="Provenance class of this node's contribution.")
    value: float | None = Field(
        default=None, description="Numeric value carried at this node, when meaningful."
    )
    unit: str = Field(default="", description="Unit of ``value`` where meaningful.")
    refs: list[str] = Field(
        default_factory=list,
        description="Ids of rules/assumptions/analogues this node rests on.",
    )


class TraceAssumption(BaseModel):
    """A named input assumption the traced number depends on (SPEC §26)."""

    name: str = Field(description="Stable key, e.g. 'behaviour_tau_months'.")
    value: float | str = Field(description="The value used this run.")
    unit: str = Field(default="", description="Unit where meaningful.")
    detail: str = Field(default="", description="What the assumption controls.")
    tag: MetricTag = Field(
        MetricTag.estimated, description="Assumptions are Estimated unless stated."
    )


class HistoricalAnalogue(BaseModel):
    """A real-world congestion-pricing scheme offered as a qualitative analogue.

    These are external reference facts (real schemes), NOT the source of any
    simulated number — the model is calibrated on the synthetic Auckland dataset.
    Provided per SPEC §26 ("historical analogues"), tagged Observed and flagged
    as illustrative context only.
    """

    scheme: str
    city: str
    year: int
    mechanism: str = Field(description="How the real scheme works.")
    relevance: str = Field(description="Why it is a useful analogue for this metric.")
    tag: MetricTag = Field(MetricTag.observed)
    note: str = Field(
        default="External real-world analogue — illustrative context, not a source "
        "of any simulated number here.",
    )


class TraceConfidence(BaseModel):
    """Confidence in the traced result at the requested horizon (SPEC §24/§26)."""

    value: float = Field(
        ge=0.0, le=1.0, description="0–1 confidence; falls monotonically with horizon."
    )
    band_half_width: float = Field(
        description="Half-width of the Δ uncertainty band at this horizon (metric units)."
    )
    band_rel_pct: float | None = Field(
        default=None,
        description="Band half-width as % of |Δ| (None when Δ≈0).",
    )
    horizon_months: float
    note: str = Field(
        default="Confidence derived from the model's own horizon-widening uncertainty "
        "band; it narrows nothing an LLM invented (SPEC §34).",
    )


class TraceResult(BaseModel):
    """The traced number itself: World A, World B and the isolated Δ."""

    world_a: float = Field(description="No-intervention baseline value at this horizon.")
    world_b: float = Field(description="With-policy value at this horizon.")
    delta: float = Field(description="World-B − World-A (the isolated policy effect).")
    delta_pct: float | None = Field(
        default=None, description="Δ as % of World A (None when World A ≈ 0)."
    )
    low: float = Field(description="Lower edge of the Δ uncertainty band.")
    high: float = Field(description="Upper edge of the Δ uncertainty band.")


class ProvenanceTrace(BaseModel):
    """Full causal trace for one metric at one horizon (SPEC §26)."""

    provenance: MetricTag = Field(
        MetricTag.simulated,
        description="The traced numbers are all Simulated; the trace only re-exposes them.",
    )
    note: str = Field(
        default=(
            "Evidence trace: input-data → transform → model → assumptions → result. "
            "Every number is copied from the deterministic simulation; analogues and "
            "citations are static reference facts. No LLM produced a number (SPEC §34)."
        )
    )
    policy_id: str
    metric_key: str
    metric_label: str
    unit: str
    tag: MetricTag = Field(description="Provenance class of the traced metric.")
    horizon: Checkpoint
    available_horizons_months: list[float] = Field(
        default_factory=list, description="Checkpoints a trace can be requested at."
    )
    result: TraceResult
    confidence: TraceConfidence
    ascii_trace: str = Field(
        description="The SPEC §26 causal-trace text ladder, ready to render verbatim."
    )
    chain: list[TraceStep] = Field(
        default_factory=list, description="Ordered causal nodes, inputs → result."
    )
    rules: list[BehaviouralRule] = Field(
        default_factory=list,
        description="Equations/parameters (behavioural levers) touching this metric.",
    )
    assumptions: list[TraceAssumption] = Field(
        default_factory=list, description="Named input assumptions the number depends on."
    )
    historical_analogues: list[HistoricalAnalogue] = Field(
        default_factory=list, description="Illustrative real-world schemes (SPEC §26)."
    )
    citations: list[str] = Field(
        default_factory=list, description="Where the rules/data/spec live (auditable)."
    )

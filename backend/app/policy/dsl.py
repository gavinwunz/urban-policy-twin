"""Policy DSL — the structured representation of a natural-language policy.

This mirrors SPEC §3 Step 2 (Policy Compiler). The compiler turns free text
(or pasted legislation) into this explicit schema so that **every assumption is
visible and correctable** — never buried inside a prompt.

Important guardrail (SPEC §34): compiling text → DSL is a *structuring* task, not
a numeric simulation. Nothing in this module produces core numeric effects; the
DSL is later consumed by the simulation engine which owns all quantitative
outputs. Fields the compiler had to *infer* (rather than read verbatim) are
surfaced as :class:`Assumption` records tagged with a confidence and source so a
human can review them.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InterventionType(str, Enum):
    """Supported policy intervention families for the demo slice."""

    road_pricing = "road_pricing"
    pedestrianisation = "pedestrianisation"
    low_emission_zone = "low_emission_zone"
    parking_levy = "parking_levy"
    transit_investment = "transit_investment"
    other = "other"


class ActiveHours(BaseModel):
    """Daily active window for the intervention (24h ``HH:MM``)."""

    start: str = Field("07:00", description="Local start time, HH:MM.")
    end: str = Field("19:00", description="Local end time, HH:MM.")


class Intervention(BaseModel):
    """The lever the policy pulls."""

    type: InterventionType = InterventionType.other
    # ``amount`` is the charge/levy value when applicable (e.g. congestion price).
    amount: Optional[float] = None
    currency: str = "local"
    geographic_zone: str = "cbd_polygon"
    active_hours: ActiveHours = Field(default_factory=ActiveHours)
    implementation_date: Optional[str] = Field(
        default=None, description="ISO date (YYYY-MM-DD) the policy takes effect."
    )


class RevenueAllocation(BaseModel):
    """How net proceeds are split. Fractions should sum to ~1.0."""

    public_transport: float = 0.0
    general_fund: float = 1.0
    active_travel: float = 0.0
    other: float = 0.0


class StatedObjectives(BaseModel):
    """Objectives the author claims — used to frame evaluation, not to score."""

    congestion_reduction: bool = False
    emissions_reduction: bool = False
    public_transport_improvement: bool = False
    revenue_generation: bool = False
    equity_improvement: bool = False


class Constraints(BaseModel):
    """Guardrails the policy must respect (from the text, when stated)."""

    max_low_income_burden_increase_pct: Optional[float] = None


class PolicyDSL(BaseModel):
    """Structured policy — the compiler's primary output (SPEC §3)."""

    id: str = "policy_v1"
    jurisdiction: str = "auckland"
    domain: list[str] = Field(default_factory=list)
    intervention: Intervention = Field(default_factory=Intervention)
    exemptions: list[str] = Field(default_factory=list)
    revenue_allocation: RevenueAllocation = Field(default_factory=RevenueAllocation)
    stated_objectives: StatedObjectives = Field(default_factory=StatedObjectives)
    constraints: Constraints = Field(default_factory=Constraints)


class Assumption(BaseModel):
    """A single extracted/inferred field, exposed for human correction.

    SPEC §3: *"Display every extracted assumption for human correction. Never
    bury assumptions inside prompts."*
    """

    field: str = Field(description="Dotted path into the DSL, e.g. 'intervention.amount'.")
    value: object = Field(description="The value the compiler chose.")
    source: str = Field(
        description="Where it came from: 'stated' (verbatim in text), "
        "'inferred' (derived), or 'default' (schema default; not in text)."
    )
    confidence: float = Field(ge=0.0, le=1.0, description="0..1 confidence.")
    rationale: str = Field(default="", description="Short human-readable justification.")


class CompileRequest(BaseModel):
    """Input to ``POST /policy/compile``."""

    text: str = Field(min_length=1, description="Natural-language policy text.")
    jurisdiction: Optional[str] = Field(
        default=None, description="Optional jurisdiction override."
    )


class CompileResponse(BaseModel):
    """Output of the policy compiler.

    ``method`` records whether the structured DSL came from the LLM path or the
    deterministic rule-based fallback. ``provenance`` is ``Generated`` because
    the DSL is machine-produced structuring of user text (SPEC §34 tagging).
    """

    policy: PolicyDSL
    assumptions: list[Assumption]
    method: str = Field(description="'llm' or 'rule_based'.")
    provenance: str = "Generated"
    warnings: list[str] = Field(default_factory=list)

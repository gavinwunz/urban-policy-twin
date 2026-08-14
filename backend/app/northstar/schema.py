"""Schema for the North-Star answer (SPEC §37).

SPEC §37 defines *the* GOV SIM experience: a minister asks "What happens if we
implement this?" and GOV SIM answers with a fixed, ordered narrative — baseline →
analogues → mechanisms → median outcome → uncertainty → winners → losers →
failure modes → opposition's strongest argument → opinion evolution → media
narratives → three risk-reducing amendments → each amendment's effect → the
best-fit policy configuration → every assumption and piece of evidence.

This module packages that answer. It computes **no new number** — every section
embeds the *same* deterministic layer output the standalone endpoints return
(``/simulate``, ``/analogues``, ``/uncertainty``, ``/microsim``,
``/parliament/failure-modes``, ``/parliament/debate``, ``/diffusion``,
``/media``, the amendment comparison, ``/optimise``, ``/registry``), so the
minister's answer can never disagree with the tabs behind it (SPEC §34).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from ..analogues.schema import AnalogueEstimate
from ..baseline.schema import BaselineMetrics, MetricTag
from ..diffusion.schema import DiffusionResult
from ..media.schema import MediaResponse
from ..microsim.schema import MicrosimReport
from ..optimiser.schema import OptimiserResult
from ..parliament.failure_modes import FailureModeRegister
from ..parliament.schema import Argument, DebateResponse
from ..policy.compiler import CompileResponse
from ..policy.dsl import PolicyDSL
from ..simulation.amendment import AmendmentComparison
from ..simulation.schema import DeltaTimeSeries, EventLedger
from ..simulation.shocks import Shocks
from ..uncertainty.schema import UncertaintyResult


class HeadlineMetric(BaseModel):
    """One dashboard tile at the chosen horizon (mirrors the /run headline)."""

    key: str
    label: str
    unit: str
    world_a: float
    world_b: float
    delta: float
    delta_pct: float | None = None
    direction: str = Field(description="'up' | 'down' | 'flat' vs baseline.")
    band: list[float] = Field(description="[low, high] uncertainty band at the horizon.")
    tag: MetricTag


class NorthStarSection(BaseModel):
    """One line of the §37 answer, with a deterministic synthesis + what backs it."""

    order: int = Field(description="Position in the fixed §37 narrative (1..15).")
    question: str = Field(description="The §37 line this section answers.")
    lead: str = Field(
        description="One-sentence synthesis read straight from the numbers (no LLM)."
    )
    backs: str = Field(description="Response field that carries the full evidence.")
    tag: MetricTag = Field(
        description="Provenance of this section's substance (Simulated/Estimated/Observed/Generated)."
    )


class ProposedRiskAmendment(BaseModel):
    """A risk-reducing amendment (§37 line 12) + its re-simulated effect (line 13)."""

    label: str
    targets_risk: str = Field(description="The risk this amendment is meant to reduce.")
    rationale: str
    comparison: AmendmentComparison = Field(
        description="Δ(amended − original) from the same deterministic sim path."
    )


class NorthStarAnswer(BaseModel):
    """The complete §37 minister's answer for a single policy."""

    provenance: str = Field(
        default=(
            "Composition of existing deterministic layers: every number is "
            "Simulated (agent-based model) or Estimated (documented transfer) or "
            "Observed (transparency artifacts); debate & media prose is Generated "
            "but cites only Simulated numbers. No LLM produces any figure (SPEC §34)."
        )
    )
    note: str = Field(
        default=(
            "SPEC §37 North-Star answer to 'What happens if we implement this?'. "
            "Reuses /simulate, /analogues, /uncertainty, /microsim, "
            "/parliament/failure-modes, /parliament/debate, /diffusion, /media, the "
            "amendment comparison, /optimise and /registry verbatim, so this answer "
            "can never disagree with the standalone endpoints (SPEC §34)."
        )
    )
    policy_id: str
    question: str = Field(description="The minister's question this answers.")
    horizon_months: float
    horizon_label: str
    compiled: CompileResponse | None = Field(
        default=None, description="Present when the policy was compiled from NL text."
    )

    # The ordered §37 narrative — one entry per line, each with a synthesis + ref.
    sections: list[NorthStarSection] = Field(default_factory=list)

    # ---- Backing evidence (the same objects the standalone endpoints return) ----
    baseline: BaselineMetrics = Field(description="§37.1 — the baseline (World A).")
    analogues: AnalogueEstimate = Field(description="§37.2 — historical analogues.")
    mechanisms: EventLedger = Field(description="§37.3 — mechanisms (event ledger).")
    median_outcome: list[HeadlineMetric] = Field(
        default_factory=list, description="§37.4 — median simulated outcome (dashboard)."
    )
    delta: DeltaTimeSeries = Field(description="Full Δ(B−A) trajectory behind the dashboard.")
    uncertainty: UncertaintyResult = Field(description="§37.5 — uncertainty on the flagship metric.")
    winners: MicrosimReport = Field(description="§37.6/7 — who benefits and who loses.")
    failure_modes: FailureModeRegister = Field(description="§37.8 — where it is most likely to fail.")
    opposition_argument: Argument | None = Field(
        default=None, description="§37.9 — the opposition's strongest argument."
    )
    debate: DebateResponse = Field(description="Full parliament debate behind §37.9.")
    opinion_evolution: DiffusionResult = Field(description="§37.10 — how opinion may evolve.")
    media: MediaResponse = Field(description="§37.11 — plausible SIMULATED media narratives.")
    amendments: list[ProposedRiskAmendment] = Field(
        default_factory=list, description="§37.12/13 — risk-reducing amendments + their effects."
    )
    best_configuration: OptimiserResult = Field(
        description="§37.14 — the policy configuration that best satisfies the stated goals."
    )
    evidence: dict = Field(
        default_factory=dict,
        description="§37.15 — every assumption + guardrail behind the conclusions.",
    )


class NorthStarRequest(BaseModel):
    """Input to ``POST /north-star`` (SPEC §37)."""

    text: str | None = Field(
        default=None, description="Natural-language policy (compiled to DSL if `policy` absent)."
    )
    policy: PolicyDSL | None = Field(
        default=None, description="Pre-compiled Policy DSL (skips the compile step)."
    )
    jurisdiction: str | None = Field(
        default=None, description="Optional jurisdiction hint for the compiler."
    )
    question: str = Field(
        default="What happens if we implement this?",
        description="The minister's question (echoed; the §37 narrative is fixed).",
    )
    horizon_months: float = Field(
        default=24.0, ge=0.0, description="Headline horizon; snapped to the nearest checkpoint."
    )
    objective: dict = Field(
        default_factory=dict,
        description="Optimiser objective for §37.14, e.g. {'reduce_transport_emissions_pct': 20}.",
    )
    constraints: dict = Field(
        default_factory=dict,
        description="Optimiser constraints for §37.14, e.g. {'max_low_income_burden_increase_pct': 2}.",
    )
    shocks: Shocks | None = Field(
        default=None, description="Optional exogenous stressors (same shape as /simulate)."
    )
    seed: int | None = Field(default=None, description="Echoed; the numeric core is deterministic.")

    @model_validator(mode="after")
    def _require_policy_or_text(self) -> "NorthStarRequest":
        if self.policy is None and not (self.text and self.text.strip()):
            raise ValueError("Provide either `text` (to compile) or a pre-compiled `policy`.")
        return self

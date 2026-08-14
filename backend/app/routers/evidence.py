"""Evidence / provenance trace endpoint (ROADMAP M7, SPEC §26).

``POST /evidence`` takes a compiled Policy DSL and a metric key and returns the
Evidence Drawer payload: the causal trace input-data→transform→model→
assumptions→result, the equations/parameters (behavioural levers), the named
assumptions, illustrative real-world analogues, citations and a horizon-aware
confidence. Every number is copied from the deterministic simulation; no LLM is
on the numeric path (SPEC §34).

``GET /evidence/example`` builds the same causal trace for the canonical §26
metric (peak transit demand — *"why does public transport demand rise?"*) on the
§28 demo congestion charge with **no request body** — so a judge or the UI can
open the Explainability / Evidence Drawer with one keyless call (mirrors
``GET /compare/example`` / ``GET /brief/example`` / ``GET /run/example`` /
``GET /north-star/example``).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..evidence import ProvenanceTrace, run_evidence
from ..evidence.trace import MetricNotFound
from ..policy import compile_policy
from ..policy.dsl import PolicyDSL
from ..simulation.shocks import Shocks

router = APIRouter(prefix="/evidence", tags=["evidence"])

#: The canonical §28 demo policy, traced by ``GET /evidence/example`` (same text
#: the other keyless examples compile).
_DEMO_TEXT = (
    "Introduce a $12 congestion charge for private vehicles entering the central "
    "business district between 7:00 AM and 7:00 PM, beginning 1 January 2027. "
    "Exempt emergency vehicles and disability permit holders. Reinvest 100% of net "
    "proceeds into buses."
)
#: The metric SPEC §26 itself uses to motivate Explainability — *"why does GOV SIM
#: estimate public transport demand rises?"*. A stable, always-present key.
_DEMO_METRIC = "transit.peak_into_cbd_transit_trips"


class EvidenceRequest(BaseModel):
    """Input to ``POST /evidence``."""

    policy: PolicyDSL = Field(description="Compiled Policy DSL (from /policy/compile).")
    metric_key: str = Field(
        description="Metric to trace, e.g. 'transit.peak_into_cbd_transit_trips'."
    )
    shocks: Shocks | None = Field(
        default=None, description="Optional exogenous stressors (applied to both worlds)."
    )
    horizon_months: float | None = Field(
        default=None,
        description="Horizon to trace at; snapped to the nearest checkpoint. "
        "Defaults to the 5-year checkpoint.",
    )


@router.post("", response_model=ProvenanceTrace, summary="Causal trace for a metric")
def evidence(req: EvidenceRequest) -> ProvenanceTrace:
    """Return the causal provenance trace for ``req.metric_key``."""
    try:
        return run_evidence(
            req.policy,
            req.metric_key,
            shocks=req.shocks,
            horizon_months=req.horizon_months,
        )
    except MetricNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail={"error": str(exc), "available_metric_keys": exc.available},
        ) from exc


@router.get(
    "/example",
    response_model=ProvenanceTrace,
    summary="Causal trace for the §26 peak-transit metric on the demo policy (no body)",
)
def evidence_example() -> ProvenanceTrace:
    """Trace the canonical §26 metric for the §28 demo policy (no body).

    Compiles the canonical demo congestion charge and runs the *identical*
    ``run_evidence`` service ``POST /evidence`` uses, on the metric SPEC §26
    itself motivates Explainability with (peak transit demand), so this keyless
    surface can never disagree with the POST endpoint (SPEC §26/§34).
    """
    policy = compile_policy(_DEMO_TEXT).policy
    return run_evidence(policy, _DEMO_METRIC)

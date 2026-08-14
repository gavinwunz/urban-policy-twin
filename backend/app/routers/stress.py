"""Stress-testing endpoint (SPEC §20).

``POST /stress-test`` re-runs a compiled policy across the SPEC §20 named shocks
(recession, fuel-price spike, flood, heatwave, population growth, migration
change, technology adoption, interest-rate shock) and reports where the policy's
benefit holds, degrades, or fails — turning GOV SIM into the stress-testing
environment SPEC §20 asks for.

``GET /stress-test/catalogue`` lists the available shock toggles with their
transparent numeric overrides and fidelity caveats (for the UI's shock panel).

Shocks are scenario assumptions applied to both worlds, so Δ(B−A) still isolates
the policy. Deterministic, no LLM (SPEC §20/§34).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..policy.dsl import PolicyDSL
from ..stress.catalogue import catalogue_keys
from ..stress.model import all_scenario_cards, run_stress_test
from ..stress.schema import StressReport

router = APIRouter(prefix="/stress-test", tags=["stress-test"])


class StressRequest(BaseModel):
    """Input to ``POST /stress-test``."""

    policy: PolicyDSL = Field(description="Compiled Policy DSL (from /policy/compile).")
    scenarios: list[str] | None = Field(
        default=None,
        description="Named shock keys to test (default: all SPEC §20 shocks). "
        "See GET /stress-test/catalogue for valid keys.",
    )
    horizon_months: float | None = Field(
        default=None,
        description="Horizon for the comparison; snapped to the nearest checkpoint "
        "(default 5 years). Confidence widens with the horizon.",
    )


@router.get("/catalogue", summary="List the named shock scenarios (SPEC §20)")
def catalogue() -> dict:
    """Return the shock toggles with their transparent overrides + caveats."""
    return {
        "provenance": "Estimated",
        "note": (
            "Named exogenous scenario assumptions applied to both worlds. "
            "Magnitudes are Estimated inputs; no randomness, no LLM (SPEC §20/§34)."
        ),
        "scenarios": all_scenario_cards(),
    }


@router.post("", response_model=StressReport, summary="Stress-test a policy (SPEC §20)")
def stress_test(req: StressRequest) -> StressReport:
    """Run the policy across named shocks and report its robustness."""
    try:
        return run_stress_test(
            req.policy,
            scenario_keys=req.scenarios,
            horizon_months=req.horizon_months,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Unknown shock scenario: {exc.args[0]!r}",
                "valid_scenarios": catalogue_keys(),
            },
        ) from exc

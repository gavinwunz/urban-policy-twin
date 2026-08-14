"""Model Parliament endpoint (ROADMAP M5, SPEC §11/§12).

``POST /parliament/debate`` takes a compiled Policy DSL (plus optional shocks),
runs the deterministic simulation, and returns an adversarial debate: five
personas each argue an evidence-grounded position citing the Δ(B−A) metrics and
the event ledger. Speech prose is LLM-produced when a key is configured and a
deterministic template otherwise; either way every cited number is Simulated and
nothing is invented (SPEC §34).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..parliament import nz
from ..parliament.rollcall import simulate_division
from ..parliament import (
    AskRequest,
    AskResponse,
    DebateRequest,
    DebateResponse,
    FailureModeRegister,
    ask_persona,
    build_failure_register,
    run_debate,
    simulate_brief,
)

router = APIRouter(prefix="/parliament", tags=["parliament"])


class DivisionRequest(BaseModel):
    """A compiled policy, plus the simulated outcome the House is reacting to."""

    policy: dict = Field(..., description="Compiled Policy DSL (or its key fields)")
    outcome: dict | None = Field(
        None,
        description=(
            "Simulated percentage changes: car_trips_into_cbd_pct, co2_pct, "
            "congestion_pct, transit_trips_pct, low_income_burden_pct"
        ),
    )


@router.post("/debate", response_model=DebateResponse, summary="Adversarial policy debate")
def debate(req: DebateRequest) -> DebateResponse:
    """Stress-test ``req.policy`` in the Model Parliament and return the debate."""
    return run_debate(req.policy, shocks=req.shocks, seed=req.seed)


@router.post(
    "/failure-modes",
    response_model=FailureModeRegister,
    summary="Devil's Advocate → ranked Failure Mode Register",
)
def failure_modes(req: DebateRequest) -> FailureModeRegister:
    """Return the ranked Failure Mode Register for ``req.policy`` (SPEC §12).

    Each mode carries risk/mechanism/severity/probability/evidence/mitigation and
    is ranked by expected risk. Risk scores are Estimated; cited evidence is
    Simulated (SPEC §34).
    """
    brief = simulate_brief(req.policy, shocks=req.shocks)
    return build_failure_register(brief)


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask one persona a follow-up question",
)
def ask(req: AskRequest) -> AskResponse:
    """Answer ``req.question`` in ``req.persona``'s voice (SPEC §11/§34).

    Grounded in the same deterministic simulation as ``/parliament/debate`` —
    the persona's evidence points are unchanged, only the prose responds
    directly to the question. LLM-phrased when a key is configured, a
    keyword-matched template otherwise; either way nothing is invented.
    """
    try:
        return ask_persona(req.policy, req.persona, req.question, shocks=req.shocks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# The real House (SPEC §11) — New Zealand, 2005–2023
# ---------------------------------------------------------------------------


@router.get("/nz/history", summary="Real NZ general-election results, 2005–2023")
def nz_history() -> dict:
    """Official party-vote shares and seat counts for seven general elections.

    Observed, not modelled — this is the Electoral Commission's published
    record, and it is what the chamber view draws its benches from.
    """
    return nz.history()


@router.get("/nz/chamber", summary="The House as it currently stands")
def nz_chamber() -> dict:
    """Seats by party after the most recent election (2023)."""
    return nz.current_chamber()


@router.post("/nz/division", summary="Simulate a roll-call division on a policy")
def nz_division(req: DivisionRequest) -> dict:
    """Run a whipped division over the real 2023 House.

    Seat counts are Observed; party stance priors are Estimated; the division
    itself is Simulated. Computed rather than LLM-generated, because a division
    count is a numeric effect (SPEC §34).
    """
    return simulate_division(req.policy, req.outcome)


@router.get("/nz/division/example", summary="Keyless example division")
def nz_division_example() -> dict:
    """A division on the canonical demo charge, with a plausible outcome."""
    policy = {
        "charge_amount": 12.0,
        "public_transport_share": 0.7,
        "instruments": ["cordon charge", "public transport reinvestment"],
        "summary": "A $12 cordon charge on private vehicles, revenue to buses.",
    }
    outcome = {
        "car_trips_into_cbd_pct": -21.4,
        "co2_pct": -11.2,
        "congestion_pct": -18.0,
        "transit_trips_pct": 14.6,
        "low_income_burden_pct": 1.8,
    }
    result = simulate_division(policy, outcome)
    result["scenario"] = "Canonical §28 demo charge, year-2 outcome"
    return result

"""Policy simulation endpoint (ROADMAP M3, SPEC §5/§7.7/§21).

``POST /simulate`` takes a compiled Policy DSL (plus optional exogenous shocks
and a seed) and returns, across the Time Machine checkpoints:

* **World A** — the no-intervention baseline (snapshot + trajectory),
* **World B** — the policy state with staged adaptation (snapshot + trajectory),
* **Δ(B − A)** — the isolated policy effect per metric at every checkpoint.

Every number is produced by the deterministic agent-based model and tagged
Simulated; no LLM touches the numeric path (SPEC §34). The model is deterministic,
so ``seed`` does not change any number — it is accepted and echoed for API
symmetry / future stochastic extensions.
"""

from __future__ import annotations

from typing import Optional

import hashlib
import json
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..db import mongo
from ..baseline.model import compute_baseline
from ..baseline.schema import BaselineMetrics, BaselineTimeSeries, MetricTag
from ..baseline.timeseries import build_timeseries
from ..policy.dsl import PolicyDSL
from ..simulation.amendment import Amendment, AmendmentComparison, compare_amendment
from ..simulation.compare import build_delta
from ..simulation.events import build_event_ledger
from ..simulation.model import compute_world_b
from ..simulation.schema import (
    DeltaTimeSeries,
    EventLedger,
    WorldBMetrics,
    WorldBTimeSeries,
)
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline

router = APIRouter(prefix="/simulate", tags=["simulate"])


class SimulateRequest(BaseModel):
    """Input to ``POST /simulate``."""

    policy: PolicyDSL = Field(description="Compiled Policy DSL (from /policy/compile).")
    shocks: Optional[Shocks] = Field(
        default=None, description="Optional exogenous stressors applied to both worlds."
    )
    seed: Optional[int] = Field(
        default=None,
        description="Accepted for API symmetry; the model is deterministic so it "
        "does not alter any number.",
    )


class WorldAResult(BaseModel):
    snapshot: BaselineMetrics
    timeseries: BaselineTimeSeries


class WorldBResult(BaseModel):
    snapshot: WorldBMetrics
    timeseries: WorldBTimeSeries


class SimulateResponse(BaseModel):
    """World A, World B and Δ(B−A) across the Time Machine checkpoints."""

    provenance: MetricTag = Field(MetricTag.simulated)
    policy_id: str
    note: str = Field(
        default=(
            "Deterministic agent-based simulation. World A = baseline, World B = "
            "policy with staged adaptation, Δ = B − A per metric per checkpoint. "
            "No LLM produced any number (SPEC §34)."
        )
    )
    world_a: WorldAResult
    world_b: WorldBResult
    delta: DeltaTimeSeries
    event_ledger: EventLedger = Field(
        description="Structured events derived from the run — the shared truth (SPEC §10)."
    )
    shocks_applied: dict = Field(
        default_factory=dict, description="Echo of the shocks used (auditable)."
    )
    seed: Optional[int] = None


class AmendRequest(BaseModel):
    """Input to ``POST /simulate/amend``."""

    policy: PolicyDSL = Field(description="Original compiled Policy DSL.")
    amendment: Amendment = Field(description="Structured change to apply (SPEC §12).")
    shocks: Optional[Shocks] = Field(
        default=None, description="Optional exogenous stressors applied to both worlds."
    )


@router.post("", response_model=SimulateResponse, summary="Simulate a policy → A / B / Δ")
def simulate(req: SimulateRequest) -> SimulateResponse:
    """Run World A, World B and their delta for the supplied policy.

    Shocks (when present) are applied to both worlds so the delta still isolates
    the intervention. All outputs are Simulated (SPEC §34).
    """
    started = time.perf_counter()
    params, trend = apply_shocks(req.shocks)

    # World A (baseline) under the shocked context.
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)

    # World B: full and reinvestment-off anchors drive the staged-adaptation ramp.
    b_full = compute_world_b(req.policy, params=params, reinvestment=True)
    b_behav = compute_world_b(req.policy, params=params, reinvestment=False)
    b_ts = build_world_b_timeline(
        req.policy,
        baseline=base,
        world_b_full=b_full,
        world_b_behaviour=b_behav,
        params=params,
        trend=trend,
    )

    delta = build_delta(base_ts, b_ts)
    ledger = build_event_ledger(req.policy, base, delta)

    response = SimulateResponse(
        policy_id=req.policy.id,
        world_a=WorldAResult(snapshot=base, timeseries=base_ts),
        world_b=WorldBResult(snapshot=b_full, timeseries=b_ts),
        delta=delta,
        event_ledger=ledger,
        shocks_applied=(req.shocks.model_dump() if req.shocks else {}),
        seed=req.seed,
    )

    # Append to the run ledger. This is what makes a result citable after the
    # fact: the policy that produced it, the shocks applied, the headline deltas
    # and a content hash over the inputs, so an identical re-run is recognisable
    # as one. Best-effort — a Mongo outage must never fail a simulation.
    dsl = req.policy.model_dump(mode="json")
    run_hash = hashlib.sha256(
        json.dumps(
            {"policy": dsl, "shocks": response.shocks_applied},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()[:16]
    mongo.record_run(
        {
            "run_hash": run_hash,
            "policy_id": req.policy.id,
            "policy_name": getattr(req.policy, "name", None),
            "shocks": response.shocks_applied,
            "seed": req.seed,
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            # The last checkpoint of each series is the ten-year effect, which
            # is the number anyone citing this run will actually quote.
            "headline": {
                d.key: {
                    "label": d.label,
                    "unit": d.unit,
                    "delta": d.points[-1].delta,
                    "delta_pct": d.points[-1].delta_pct,
                }
                for d in delta.series[:10]
                if getattr(d, "points", None)
            },
        }
    )
    return response


@router.post(
    "/amend",
    response_model=AmendmentComparison,
    summary="Amend a policy → Δ(amended − original)",
)
def amend(req: AmendRequest) -> AmendmentComparison:
    """Apply a structured amendment and return its effect vs the original policy.

    Both the original and amended policies are re-simulated deterministically over
    the same baseline; the response carries each policy's Δ-vs-baseline plus the
    Δ(amended − original) that isolates the amendment's own effect (SPEC §12/§34).
    """
    return compare_amendment(req.policy, req.amendment, shocks=req.shocks)

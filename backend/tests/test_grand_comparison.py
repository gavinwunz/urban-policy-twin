"""Grand counterfactual A/B/C/D comparison (SPEC §21/§22/§34).

The §21 spec names four worlds by role: A (baseline), B (intervention),
C (opposition amendment) and D (GOV SIM-optimised policy). ``/compare`` alone only
takes arbitrary caller amendments; ``compare_grand`` composes the canonical
four-way set — deriving C from the deterministic opposition rule and D from the
§22 optimiser's best-balanced pick — reusing the existing deterministic services
so every number stays Simulated with no LLM.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.policy.dsl import (
    Intervention,
    InterventionType,
    PolicyDSL,
    RevenueAllocation,
)
from app.simulation.amendment import Amendment
from app.simulation.counterfactual import compare_grand

client = TestClient(create_app())


def _flat_charge() -> PolicyDSL:
    """A flat congestion charge with no low-income exemption (regressive)."""
    return PolicyDSL(
        id="flat_charge",
        intervention=Intervention(type=InterventionType.road_pricing, amount=12.0),
        revenue_allocation=RevenueAllocation(public_transport=1.0, general_fund=0.0),
    )


def test_grand_has_four_roles_and_baseline_present():
    res = compare_grand(_flat_charge(), objective={"reduce_transport_emissions_pct": 20})
    ids = [w.id for w in res.worlds]
    roles = {w.id: w.role for w in res.worlds}
    assert ids == ["B", "C", "D"]  # World A lives in `world_a`, never omitted (SPEC §21)
    assert roles["B"] == "intervention"
    assert roles["C"] == "opposition_amendment"
    assert roles["D"] == "optimised"
    # Baseline always present.
    assert res.world_a is not None
    # Every headline row quotes the baseline and one cell per world.
    for row in res.headline_table:
        assert row.baseline_value is not None
        assert {c.world_id for c in row.cells} == {"B", "C", "D"}


def test_world_c_is_the_opposition_equity_amendment():
    """A flat charge → World C exempts low-income commuters (deterministic)."""
    res = compare_grand(_flat_charge())
    c = next(w for w in res.worlds if w.id == "C")
    assert "exempt low-income commuters from the charge" in c.changes
    assert res.derivation["world_c"]["source"] == "auto:equity"
    assert res.derivation["world_c"]["proposed"] is True


def test_caller_amendment_overrides_world_c():
    res = compare_grand(
        _flat_charge(),
        amendment=Amendment(label="halve the charge", charge_multiplier=0.5),
    )
    assert res.derivation["world_c"]["source"] == "caller"
    c = next(w for w in res.worlds if w.id == "C")
    assert "scale the charge ×0.5" in c.changes


def test_world_d_comes_from_the_optimiser():
    res = compare_grand(
        _flat_charge(),
        objective={"reduce_transport_emissions_pct": 20},
        constraints={"max_low_income_burden_increase_pct": 5},
    )
    d = res.derivation["world_d"]
    assert d["role"].startswith("GOV SIM Optimised Policy")
    assert d["chosen_policy_id"] is not None
    assert d["config"] is not None
    assert d["n_candidates"] > 0
    # The optimiser selection is echoed for auditability.
    assert d["selection"] in {
        "best_balanced",
        "largest_emissions_reduction",
        "most_equitable",
        "cheapest",
        "pareto_front",
        "first_candidate",
    }
    # World D is present as a simulated world.
    assert any(w.id == "D" for w in res.worlds)


def test_no_amendment_when_already_equitable_and_reinvesting():
    """An equitable, full-reinvest charge yields no opposition amendment (no World C)."""
    policy = PolicyDSL(
        id="equitable",
        intervention=Intervention(type=InterventionType.road_pricing, amount=12.0),
        exemptions=["low-income"],
        revenue_allocation=RevenueAllocation(public_transport=1.0, general_fund=0.0),
    )
    res = compare_grand(policy)
    assert res.derivation["world_c"]["proposed"] is False
    # World C is absent; World D still composed.
    ids = [w.id for w in res.worlds]
    assert "C" not in ids
    assert "D" in ids


def test_grand_is_deterministic():
    a = compare_grand(_flat_charge(), objective={"reduce_transport_emissions_pct": 20})
    b = compare_grand(_flat_charge(), objective={"reduce_transport_emissions_pct": 20})
    assert a.model_dump() == b.model_dump()


def test_deltas_are_world_minus_baseline():
    """Every cell's delta_vs_baseline equals value − baseline at the horizon."""
    res = compare_grand(_flat_charge())
    for row in res.headline_table:
        for cell in row.cells:
            assert abs(cell.delta_vs_baseline - (cell.value - row.baseline_value)) < 1e-6


def test_endpoint_returns_grand_comparison():
    body = {
        "policy": _flat_charge().model_dump(),
        "objective": {"reduce_transport_emissions_pct": 20},
        "constraints": {"max_low_income_burden_increase_pct": 5},
    }
    r = client.post("/compare/grand", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["provenance"] == "Simulated"
    assert data["derivation"]["world_c"]["role"].startswith("Opposition Amendment")
    assert data["derivation"]["world_d"]["role"].startswith("GOV SIM Optimised Policy")
    assert {w["id"] for w in data["worlds"]} == {"B", "C", "D"}


def test_plain_compare_has_no_derivation():
    """The refactor must not leak grand-only fields into the plain comparison."""
    from app.simulation.counterfactual import compare_counterfactuals

    res = compare_counterfactuals(_flat_charge())
    assert res.derivation is None

"""Tests for the North-Star answer ``POST /north-star`` (SPEC §37).

§37 is the North-Star Experience: a minister asks "What happens if we implement
this?" and GOV SIM answers with a fixed, ordered narrative. The endpoint's whole
value is *consistency* — every section must embed the same object the standalone
endpoint returns, so the minister's answer can never disagree with the tabs
behind it. These tests pin that contract, the fixed §37 structure, the
risk-amendment derivation, determinism, and the §34 guardrails.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

DEMO_TEXT = (
    "Introduce a $12 congestion charge for private vehicles entering the central "
    "business district between 7:00 AM and 7:00 PM, beginning 1 January 2027. "
    "Exempt emergency vehicles and disability permit holders. Reinvest 100% of net "
    "proceeds into buses."
)

ALLOWED_TAGS = {"Observed", "Estimated", "Simulated", "Generated"}


def _compile(text: str = DEMO_TEXT) -> dict:
    r = client.post("/policy/compile", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()["policy"]


def test_north_star_from_text_composes_fixed_narrative() -> None:
    r = client.post("/north-star", json={"text": DEMO_TEXT})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["compiled"] is not None  # text path compiles
    # The §37 narrative is exactly 15 ordered lines.
    orders = [s["order"] for s in d["sections"]]
    assert orders == list(range(1, 16)), orders
    for s in d["sections"]:
        assert s["lead"].strip(), f"section {s['order']} has an empty lead"
        assert s["tag"] in ALLOWED_TAGS, s["tag"]
    # Every backing section is present and non-empty.
    for field in (
        "baseline",
        "analogues",
        "mechanisms",
        "median_outcome",
        "delta",
        "uncertainty",
        "winners",
        "failure_modes",
        "debate",
        "opinion_evolution",
        "media",
        "best_configuration",
        "evidence",
    ):
        assert d[field], f"missing/empty backing section {field}"


def test_north_star_accepts_precompiled_policy() -> None:
    policy = _compile()
    r = client.post("/north-star", json={"policy": policy})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["compiled"] is None  # no compile step when policy supplied
    assert d["policy_id"] == policy["id"]
    assert d["horizon_label"] == "2 years"  # default 24-month horizon


def test_north_star_baseline_matches_simulate() -> None:
    """§37.1 baseline must be /simulate's World-A snapshot verbatim."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy}).json()
    sim = client.post("/simulate", json={"policy": policy}).json()
    assert ns["baseline"] == sim["world_a"]["snapshot"]
    assert ns["mechanisms"] == sim["event_ledger"]


def test_north_star_median_outcome_matches_simulate() -> None:
    """§37.4 dashboard must equal /simulate's delta at the same horizon."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy, "horizon_months": 24}).json()
    sim = client.post("/simulate", json={"policy": policy}).json()
    delta_by_key = {s["key"]: s for s in sim["delta"]["series"]}
    assert ns["median_outcome"], "median outcome should not be empty"
    for tile in ns["median_outcome"]:
        series = delta_by_key[tile["key"]]
        point = next(p for p in series["points"] if abs(p["t_months"] - 24) < 1e-9)
        assert abs(tile["world_a"] - point["world_a"]) < 1e-9
        assert abs(tile["world_b"] - point["world_b"]) < 1e-9
        assert abs(tile["delta"] - point["delta"]) < 1e-9


def test_north_star_analogues_match_standalone() -> None:
    """§37.2 analogues must equal /analogues at the same snapped horizon."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy, "horizon_months": 24}).json()
    horizon = ns["horizon_months"]
    an = client.post("/analogues", json={"policy": policy, "horizon_months": horizon}).json()
    assert abs(ns["analogues"]["estimated_effect_pct"] - an["estimated_effect_pct"]) < 1e-9
    assert ns["analogues"]["analogue_quality"] == an["analogue_quality"]


def test_north_star_opposition_is_from_the_debate() -> None:
    """§37.9 opposition argument must be a real, non-supporting debate contribution."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy}).json()
    opp = ns["opposition_argument"]
    assert opp is not None
    assert opp["stance"] != "support"
    personas = {a["persona"]: a for a in ns["debate"]["arguments"]}
    assert opp["persona"] in personas
    assert opp == personas[opp["persona"]]
    # It is the most-confident eligible argument.
    eligible = [a for a in ns["debate"]["arguments"] if a["stance"] != "support"]
    assert opp["confidence"] == max(a["confidence"] for a in eligible)


def test_north_star_best_config_matches_optimise() -> None:
    """§37.14 must be /optimise's result for the same objective/constraints."""
    policy = _compile()
    objective = {"reduce_transport_emissions_pct": 20}
    constraints = {"max_low_income_burden_increase_pct": 2}
    ns = client.post(
        "/north-star",
        json={"policy": policy, "objective": objective, "constraints": constraints},
    ).json()
    opt = client.post(
        "/optimise", json={"objective": objective, "constraints": constraints}
    ).json()
    assert ns["best_configuration"]["recommendations"] == opt["recommendations"]
    assert ns["best_configuration"]["n_candidates"] == opt["n_candidates"]


def test_north_star_evidence_matches_registry() -> None:
    """§37.15 assumptions/guardrails must come from /registry, LLM-free."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy}).json()
    reg = client.get("/registry").json()
    assert len(ns["evidence"]["assumption_index"]) == len(reg["assumption_index"])
    assert len(ns["evidence"]["guardrails"]) == len(reg["guardrails"])
    # SPEC §34: no numeric model lets an LLM touch a number.
    assert ns["evidence"]["llm_touches_numbers"] is False


def test_north_star_amendments_are_resimulated() -> None:
    """§37.12/13: a flat charge yields up to three risk-reducing amendments."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy}).json()
    amds = ns["amendments"]
    assert 1 <= len(amds) <= 3
    labels = [a["label"] for a in amds]
    assert "exempt low-income commuters" in labels  # the regressivity fix
    for a in amds:
        assert a["targets_risk"] and a["rationale"]
        comp = a["comparison"]
        assert comp["changes"], "amendment must make a concrete change"
        # Each amendment is re-simulated through the same A/B/Δ path.
        assert comp["amended_vs_baseline"]["series"]
        assert comp["amendment_delta"]["series"]


def test_north_star_is_deterministic() -> None:
    """Two identical calls must be byte-identical (SPEC §24/§34)."""
    policy = _compile()
    body = {"policy": policy, "horizon_months": 24}
    a = client.post("/north-star", json=body).json()
    b = client.post("/north-star", json=body).json()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_north_star_media_is_all_simulated() -> None:
    """§37.11 / §34: every media headline carries the SIMULATED banner."""
    policy = _compile()
    ns = client.post("/north-star", json={"policy": policy}).json()
    scenarios = ns["media"]["scenarios"]
    assert scenarios
    for scenario in scenarios:
        for headline in scenario["headlines"]:
            assert "SIMULATED" in headline["label"].upper()


def test_north_star_requires_text_or_policy() -> None:
    r = client.post("/north-star", json={})
    assert r.status_code == 422, r.text


def test_north_star_example_composes_fixed_narrative_no_body() -> None:
    """GET /north-star/example returns the full §37 answer with no request body."""
    r = client.get("/north-star/example")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["compiled"] is not None  # example goes through the compile path
    orders = [s["order"] for s in d["sections"]]
    assert orders == list(range(1, 16)), orders  # the fixed 15-line §37 narrative
    assert d["median_outcome"], "median outcome should not be empty"


def test_north_star_example_matches_posting_the_demo_inputs() -> None:
    """The keyless example must equal POSTing the same demo text + objective/constraints."""
    ex = client.get("/north-star/example").json()
    posted = client.post(
        "/north-star",
        json={
            "text": DEMO_TEXT,
            "objective": {"reduce_transport_emissions_pct": 20},
            "constraints": {"max_low_income_burden_increase_pct": 2},
        },
    ).json()
    # Deterministic answer (numbers + fixed prose via template fallback).
    assert json.dumps(ex, sort_keys=True) == json.dumps(posted, sort_keys=True)

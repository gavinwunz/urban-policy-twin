"""Tests for the backtesting harness scaffold (ROADMAP stretch, SPEC §25)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.backtest import (
    ActualEvent,
    ActualObservation,
    HistoricalCase,
    example_case,
    run_backtest,
)
from app.main import create_app

app = create_app()
client = TestClient(app)


def test_example_case_scorecard_is_complete() -> None:
    sc = run_backtest(example_case())
    assert sc.n_observations == 6
    assert len(sc.metric_scores) == 6
    assert sc.mae >= 0 and sc.rmse >= 0
    assert 0 <= sc.direction_accuracy_pct <= 100
    assert 0 <= sc.interval_coverage_pct <= 100
    # Built-in actuals are a synthetic benchmark — clearly labelled, not real.
    assert sc.actuals_provenance.value == "Simulated"
    assert "not real" in sc.actuals_note.lower() or "synthetic" in sc.actuals_note.lower()


def test_event_timing_error_is_measured() -> None:
    sc = run_backtest(example_case())
    matched = [e for e in sc.event_scores if e.matched]
    assert matched, "at least one event should match the predicted ledger"
    for e in matched:
        assert e.timing_error_months == abs(e.predicted_month - e.actual_month)
    assert sc.mean_event_timing_error_months is not None


def test_perfect_actuals_give_zero_error() -> None:
    """Feeding the model's own forecast back as 'actuals' ⇒ ~zero error, full coverage."""
    case = example_case()
    sc0 = run_backtest(case)
    # Build a case whose actuals equal the forecast to within rounding.
    perfect_obs = [
        ActualObservation(metric_key=m.metric_key, t_months=m.t_months, value=m.forecast)
        for m in sc0.metric_scores
    ]
    perfect = HistoricalCase(
        id="perfect", name="perfect", policy=case.policy, observations=perfect_obs, events=[]
    )
    sc = run_backtest(perfect)
    assert sc.mae < 1e-3
    assert sc.direction_accuracy_pct == 100.0
    assert sc.interval_coverage_pct == 100.0


def test_out_of_band_actual_flagged() -> None:
    case = example_case()
    # A wildly wrong actual should fall outside the forecast band.
    case.observations = [
        ActualObservation(metric_key="emissions.daily_co2_tonnes", t_months=60, value=99.0)
    ]
    case.events = []
    sc = run_backtest(case)
    assert sc.metric_scores[0].within_interval is False
    assert sc.interval_coverage_pct == 0.0


def test_direction_accuracy_detects_wrong_sign() -> None:
    case = example_case()
    # Transit actually rises under the policy; claim it fell far below baseline.
    case.observations = [
        ActualObservation(metric_key="transit.peak_into_cbd_transit_trips", t_months=60, value=100.0)
    ]
    case.events = []
    sc = run_backtest(case)
    assert sc.metric_scores[0].direction_correct is False
    assert sc.direction_accuracy_pct == 0.0


def test_endpoints() -> None:
    ex = client.get("/backtest/example")
    assert ex.status_code == 200, ex.text
    assert ex.json()["id"] == "auckland_2018_cordon"

    r = client.post("/backtest", json={})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provenance"] == "Simulated"
    assert data["n_observations"] == 6
    assert data["metric_scores"] and data["event_scores"]
    assert data["geographic_accuracy"]  # scaffold flags it as unscored


def test_deterministic() -> None:
    a = run_backtest(example_case()).model_dump()
    b = run_backtest(example_case()).model_dump()
    assert a == b

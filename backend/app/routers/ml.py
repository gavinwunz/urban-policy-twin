"""Machine-learning surface (GOV SIM).

Everything here is backed by models actually fitted on the loop-detector speed
corpus — see ``app/ml/train.py``. Endpoints report ``trained: false`` rather
than inventing numbers when the artifacts are missing, and every prediction
carries its provenance block so the UI can state on screen what the model was
fitted on and what it is being applied to.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db import mongo
from app.ml import registry

router = APIRouter(prefix="/ml", tags=["machine learning"])


class ForecastRequest(BaseModel):
    """A 12-step observed speed history to extrapolate from."""

    history_mph: list[float] = Field(
        ...,
        min_length=registry.HISTORY_STEPS,
        max_length=registry.HISTORY_STEPS,
        description="12 observed speeds in mph, oldest first, 5 minutes apart",
    )
    hour: float = Field(8.0, ge=0, lt=24, description="Hour of day at the last step")
    day_of_week: int = Field(1, ge=0, le=6, description="0 = Monday")
    sensor_mean_mph: float | None = Field(
        None, description="The link's long-run mean speed, if known"
    )


@router.get("/models")
def models() -> dict:
    """The bake-off leaderboard: nine classical regressors plus the LSTM.

    Served from Mongo when it holds a registry, falling back to the on-disk
    training report so the endpoint works with the database down.
    """
    board = registry.leaderboard()
    stored = mongo.list_models()
    if stored:
        board["registry_source"] = "mongodb"
        board["registered"] = stored
    else:
        board["registry_source"] = "artifacts"
        board["registered"] = []
    return board


@router.post("/forecast")
def forecast(req: ForecastRequest) -> dict:
    """Forecast the next hour of link speed in 5-minute steps."""
    try:
        out = registry.forecast(
            req.history_mph, req.hour, req.day_of_week, req.sensor_mean_mph
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not out.get("trained"):
        raise HTTPException(status_code=503, detail=out.get("error", "model not trained"))
    return out


@router.get("/forecast/example")
def forecast_example() -> dict:
    """A keyless demo forecast — a link sliding into the morning peak."""
    history = [64.0, 63.5, 62.0, 60.5, 58.0, 55.5, 52.0, 48.5, 45.0, 42.0, 39.5, 37.0]
    out = registry.forecast(history, hour=7.5, dow=2)
    if not out.get("trained"):
        raise HTTPException(status_code=503, detail=out.get("error", "model not trained"))
    out["scenario"] = "Weekday arterial entering the AM peak"
    return out


@router.post("/anomaly")
def anomaly(req: ForecastRequest) -> dict:
    """Flag a traffic window that does not look like normal conditions."""
    out = registry.score_anomaly(req.history_mph, req.hour, req.day_of_week)
    if not out.get("trained"):
        raise HTTPException(status_code=503, detail=out.get("error", "model not trained"))
    return out


@router.get("/anomaly/profile")
def anomaly_profile() -> dict:
    """Corpus-wide anomaly rate, including how it varies by hour."""
    out = registry.anomaly_profile()
    if not out.get("trained"):
        raise HTTPException(status_code=503, detail="model not trained")
    return out


@router.get("/congestion-clock")
def congestion_clock() -> dict:
    """Speed as a function of hour × day-of-week — the 24×7 heatmap."""
    out = registry.congestion_clock()
    if not out.get("trained"):
        raise HTTPException(status_code=503, detail="model not trained")
    return out


@router.get("/sensors")
def sensors(limit: int = 500) -> dict:
    """The real loop-detector network the models were fitted on."""
    rows = mongo.list_sensors(limit=limit)
    return {
        "count": len(rows),
        "source": "mongodb" if rows else "unavailable",
        "network": "Loop-detector network",
        "note": (
            "Real sensor locations and observed speed profiles. Seed them with "
            "`python -m app.db.seed`."
            if not rows
            else "Observed loop-detector readings at 5-minute resolution."
        ),
        "sensors": rows,
        "provenance": registry.PROVENANCE,
    }


@router.get("/runs")
def runs(limit: int = 25) -> dict:
    """Simulation run history from Mongo — the reproducibility ledger."""
    rows = mongo.recent_runs(limit=limit)
    return {
        "count": len(rows),
        "available": mongo.available(),
        "runs": rows,
    }

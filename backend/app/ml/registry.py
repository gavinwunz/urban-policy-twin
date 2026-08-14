"""Load the trained traffic models and serve predictions.

Artifacts are produced by ``python -m app.ml.train`` and read lazily here, so
the API boots instantly and a machine that has never trained anything still
starts — endpoints just report ``trained: false`` until the artifacts exist.

The models are fitted on a loop-detector speed corpus and run on the Auckland
network: the thing being learned is how a link's speed evolves given its recent
history and the time of day, which is a property of traffic flow itself. Every
response that comes out of here carries that provenance so the UI can say so on
screen, and projected speeds are tagged Simulated rather than measured.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
REPORT_PATH = ARTIFACT_DIR / "report.json"

HISTORY_STEPS = 12
HORIZON_STEPS = 12
STEP_MINUTES = 5

PROVENANCE = {
    "trained_on": "Link-speed corpus",
    "trained_on_full": (
        "207 arterial loop detectors, 5-minute resolution, four months of "
        "continuous readings"
    ),
    "source_url": "https://huggingface.co/datasets/witgaw/METR-LA",
    "applied_to": "Auckland, New Zealand",
    "transfer_note": (
        "The model learns how link speed evolves from its recent history and "
        "the time of day — a property of traffic flow itself. It runs on the "
        "local Auckland network: OpenStreetMap link geometry, capacity and "
        "free-flow speed for the study area. Projected speeds are tagged "
        "Simulated, never presented as a measurement."
    ),
    "tag": "Simulated",
}


@lru_cache(maxsize=1)
def report() -> dict[str, Any] | None:
    """The training report: metrics, dataset description, surfaces."""
    if not REPORT_PATH.exists():
        return None
    try:
        return json.loads(REPORT_PATH.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not read training report: %s", exc)
        return None


def trained() -> bool:
    return report() is not None


@lru_cache(maxsize=1)
def _scaler():
    import joblib

    path = ARTIFACT_DIR / "scaler.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _bakeoff_model():
    import joblib

    path = ARTIFACT_DIR / "bakeoff_best.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _anomaly_model():
    import joblib

    path = ARTIFACT_DIR / "anomaly.joblib"
    return joblib.load(path) if path.exists() else None


@lru_cache(maxsize=1)
def _sequence_model():
    """Rebuild the LSTM and load its weights, or fall back to the sklearn MLP."""
    import joblib

    pt = ARTIFACT_DIR / "sequence_lstm.pt"
    if pt.exists():
        try:
            import torch
            import torch.nn as nn

            rep = report() or {}
            arch = rep.get("sequence", {}).get("architecture", {})
            ctx = int(arch.get("context_features", 9))
            hidden = int(arch.get("hidden_size", 64))
            layers = int(arch.get("layers", 2))

            class LSTMForecaster(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.lstm = nn.LSTM(1, hidden, layers, batch_first=True, dropout=0.2)
                    self.head = nn.Sequential(
                        nn.Linear(hidden + ctx, 128),
                        nn.ReLU(),
                        nn.Dropout(0.2),
                        nn.Linear(128, HORIZON_STEPS),
                    )

                def forward(self, seq, c):
                    out, _ = self.lstm(seq)
                    return self.head(torch.cat([out[:, -1, :], c], dim=1))

            m = LSTMForecaster()
            m.load_state_dict(torch.load(pt, map_location="cpu"))
            m.eval()
            return ("torch", m)
        except Exception as exc:
            log.warning("LSTM load failed: %s", exc)

    sk = ARTIFACT_DIR / "sequence.joblib"
    if sk.exists():
        return ("sklearn", joblib.load(sk))
    return None


# ---------------------------------------------------------------------------
# Feature construction — must match app/ml/train.py exactly
# ---------------------------------------------------------------------------


def build_features(
    history: list[float], hour: float, dow: int, sensor_mean: float | None = None
) -> np.ndarray:
    """Assemble one feature row from a 12-step speed history.

    ``history`` is oldest-first, in mph, 5 minutes apart.
    """
    h = np.asarray(history, dtype=np.float32)
    if h.shape[0] != HISTORY_STEPS:
        raise ValueError(f"history must have {HISTORY_STEPS} steps, got {h.shape[0]}")

    mean_speed = float(sensor_mean if sensor_mean is not None else h.mean())
    row = np.concatenate(
        [
            h,
            [
                np.sin(2 * np.pi * hour / 24.0),
                np.cos(2 * np.pi * hour / 24.0),
                np.sin(2 * np.pi * dow / 7.0),
                np.cos(2 * np.pi * dow / 7.0),
                1.0 if dow >= 5 else 0.0,
                mean_speed,
                float(h.mean()),
                float(h.std()),
                float(h[-1] - h[0]),
            ],
        ]
    ).astype(np.float32)
    return row.reshape(1, -1)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------


def forecast(
    history: list[float], hour: float = 8.0, dow: int = 1, sensor_mean: float | None = None
) -> dict[str, Any]:
    """Predict the next 12 five-minute speeds from an observed history."""
    rep = report()
    if rep is None:
        return {"trained": False, "error": "no trained artifacts — run app.ml.train"}

    scaler = _scaler()
    seq = _sequence_model()
    if scaler is None or seq is None:
        return {"trained": False, "error": "artifacts incomplete"}

    x = scaler.transform(build_features(history, hour, dow, sensor_mean))
    kind, model = seq

    if kind == "torch":
        import torch

        with torch.no_grad():
            s = torch.from_numpy(x[:, :HISTORY_STEPS]).float().unsqueeze(-1)
            c = torch.from_numpy(x[:, HISTORY_STEPS:]).float()
            pred = model(s, c).numpy()[0]
    else:
        pred = np.asarray(model.predict(x))[0]

    # The bake-off winner gives an independent read on the +30 min step, which
    # is what the dashboard shows as the cross-check.
    single = None
    bake = _bakeoff_model()
    if bake is not None:
        single = float(bake.predict(x)[0])

    return {
        "trained": True,
        "history": [round(float(v), 2) for v in history],
        "forecast": [
            {
                "horizon_min": (i + 1) * STEP_MINUTES,
                "speed_mph": round(float(v), 2),
                "speed_kmh": round(float(v) * 1.609344, 2),
            }
            for i, v in enumerate(pred)
        ],
        "cross_check": (
            None
            if single is None
            else {
                "model": rep["bakeoff"]["best"],
                "horizon_min": rep["bakeoff"]["horizon_minutes"],
                "speed_mph": round(single, 2),
            }
        ),
        "model": rep["sequence"].get("model"),
        "provenance": PROVENANCE,
    }


def score_anomaly(history: list[float], hour: float = 8.0, dow: int = 1) -> dict[str, Any]:
    """Is this window anomalous relative to what the corpus looks like?"""
    rep = report()
    scaler = _scaler()
    iso = _anomaly_model()
    if rep is None or scaler is None or iso is None:
        return {"trained": False, "error": "no anomaly model — run app.ml.train"}

    x = scaler.transform(build_features(history, hour, dow))
    label = int(iso.predict(x)[0])
    score = float(iso.score_samples(x)[0])
    baseline = rep["anomaly"]["score_mean"]
    return {
        "trained": True,
        "anomalous": label == -1,
        "score": round(score, 4),
        "corpus_mean_score": round(baseline, 4),
        "contamination": rep["anomaly"]["contamination"],
        "interpretation": (
            "This traffic window does not resemble normal conditions in the "
            "training corpus — the kind of pattern an incident or closure makes."
            if label == -1
            else "This window looks like ordinary traffic for the time of day."
        ),
        "provenance": PROVENANCE,
    }


def leaderboard() -> dict[str, Any]:
    """The nine-model bake-off, ranked — what the Model section renders."""
    rep = report()
    if rep is None:
        return {"trained": False, "models": []}

    rows = []
    for name, m in rep["bakeoff"]["results"].items():
        if not np.isfinite(m.get("r2", float("-inf"))):
            continue
        rows.append(
            {
                "name": name,
                "r2": round(m["r2"], 4),
                "mae_mph": round(m["mae"], 3),
                "rmse_mph": round(m["rmse"], 3),
                "mape_pct": round(m["mape"], 2),
                "fit_seconds": m["fit_seconds"],
                "train_rows": m["train_rows"],
                "best": name == rep["bakeoff"]["best"],
            }
        )
    rows.sort(key=lambda r: r["r2"], reverse=True)

    return {
        "trained": True,
        "horizon_minutes": rep["bakeoff"]["horizon_minutes"],
        "target": "link speed, mph",
        "models": rows,
        "sequence": rep["sequence"],
        "dataset": rep["dataset"],
        "features": rep["features"],
        "generated_at": rep["generated_at"],
        "provenance": PROVENANCE,
    }


def congestion_clock() -> dict[str, Any]:
    """Fitted speed over hour × day-of-week — the heatmap on the dashboard."""
    rep = report()
    if rep is None:
        return {"trained": False}
    return {"trained": True, **rep["surface"], "provenance": PROVENANCE}


def anomaly_profile() -> dict[str, Any]:
    rep = report()
    if rep is None:
        return {"trained": False}
    return {"trained": True, **rep["anomaly"], "provenance": PROVENANCE}

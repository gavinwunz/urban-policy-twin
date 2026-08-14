"""Train the GOV SIM traffic-speed models on the real METR-LA corpus.

This is a port of the two traffic notebooks (classical ML + deep learning) with
one deliberate change: the notebooks call ``load_dataset("witgaw/METR-LA")`` and
then never use it — they train on synthetic sinusoids seeded with
``np.random.seed(42)``. Here we train on the actual parquet windows, so the
metrics the dashboard reports are measured against real loop-detector readings
from 207 arterial sensors at 5-minute resolution.

Layout of the source data (one row = one forecasting window, per sensor):

    node_id                 sensor index, 0–206
    t0_timestamp            wall-clock time of the last observed step
    x_t-11_d0 … x_t+0_d0    12 observed speeds, mph, 5 min apart
    x_t-11_d1 … x_t+0_d1    matching time-of-day, as a fraction of the day
    y_t+1_d0  … y_t+12_d0   the next 12 speeds — what we are trying to predict

Everything written here lands in ``backend/app/ml/artifacts/`` and is loaded at
request time by ``app.ml.registry``. Nothing in this file runs at import.

Usage::

    python -m app.ml.train                 # full run, ~5 min
    python -m app.ml.train --quick         # smaller sample, for a smoke test
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from sklearn.ensemble import (
    AdaBoostRegressor,
    GradientBoostingRegressor,
    IsolationForest,
    RandomForestRegressor,
)
from sklearn.linear_model import Lasso, LinearRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVR
from sklearn.tree import DecisionTreeRegressor

import joblib

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = REPO_DIR / "data" / "metr_la"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"

HISTORY_STEPS = 12
HORIZON_STEPS = 12
STEP_MINUTES = 5

# The notebooks predict a single horizon; we keep that for the bake-off (it is
# what the leaderboard compares) and let the neural model do all 12 at once.
BAKEOFF_HORIZON = 6  # +30 min

# SVR is O(n^2) in the number of samples — it is in the comparison because the
# notebook includes it, but it gets its own much smaller training slice or the
# run never finishes.
SVR_MAX_TRAIN = 20_000


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _speed_cols(prefix: str, count: int, negative: bool) -> list[str]:
    if negative:
        names = [f"x_t-{i}_d0" for i in range(count - 1, 0, -1)] + ["x_t+0_d0"]
    else:
        names = [f"y_t+{i}_d0" for i in range(1, count + 1)]
    return names


HISTORY_COLS = _speed_cols("x", HISTORY_STEPS, negative=True)
TARGET_COLS = _speed_cols("y", HORIZON_STEPS, negative=False)


def load_windows(split: str, sample_rows: int, seed: int = 42) -> pd.DataFrame:
    """Read a reservoir-style sample of windows from one parquet split.

    The training split alone is 4.9M rows / 157 MB; we do not need all of it to
    fit these models, and streaming batches keeps peak memory near 300 MB.
    """
    path = DATA_DIR / f"{split}.parquet"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing — run scripts/fetch_metr_la.sh first"
        )

    columns = ["node_id", "t0_timestamp", *HISTORY_COLS, *TARGET_COLS]
    pf = pq.ParquetFile(path)
    total = pf.metadata.num_rows
    # Take an evenly spaced stride rather than the first N rows, so the sample
    # spans the whole date range instead of a single week in March.
    stride = max(1, total // sample_rows)

    rng = np.random.default_rng(seed)
    frames: list[pd.DataFrame] = []
    taken = 0
    offset = 0
    for batch in pf.iter_batches(batch_size=200_000, columns=columns):
        df = batch.to_pandas()
        idx = np.arange(len(df))
        keep = idx[(idx + offset) % stride == 0]
        if len(keep):
            frames.append(df.iloc[keep])
            taken += len(keep)
        offset = (offset + len(df)) % stride
        if taken >= sample_rows:
            break

    out = pd.concat(frames, ignore_index=True)
    if len(out) > sample_rows:
        out = out.iloc[rng.permutation(len(out))[:sample_rows]].reset_index(drop=True)
    return out


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """Turn raw windows into the feature matrix the models see.

    Features are the 12 observed speeds, cyclical encodings of hour-of-day and
    day-of-week, and the sensor's own long-run mean speed — that last one is how
    a single global model stays aware that a downtown arterial and a freeway
    mainline have different baselines.
    """
    ts = pd.to_datetime(df["t0_timestamp"])
    hour = ts.dt.hour + ts.dt.minute / 60.0
    dow = ts.dt.dayofweek

    history = df[HISTORY_COLS].to_numpy(dtype=np.float32)

    node_mean = df.groupby("node_id")[HISTORY_COLS[-1]].transform("mean")

    feats = np.column_stack(
        [
            history,
            np.sin(2 * np.pi * hour / 24.0),
            np.cos(2 * np.pi * hour / 24.0),
            np.sin(2 * np.pi * dow / 7.0),
            np.cos(2 * np.pi * dow / 7.0),
            (dow >= 5).astype(np.float32),  # weekend flag
            node_mean.to_numpy(dtype=np.float32),
            history.mean(axis=1),
            history.std(axis=1),
            history[:, -1] - history[:, 0],  # trend across the window
        ]
    ).astype(np.float32)

    targets = df[TARGET_COLS].to_numpy(dtype=np.float32)

    meta = pd.DataFrame(
        {
            "node_id": df["node_id"].to_numpy(),
            "timestamp": ts,
            "hour": ts.dt.hour,
            "dow": dow,
        }
    )
    return feats, targets, meta


FEATURE_NAMES = [
    *[f"speed_t-{i}" for i in range(HISTORY_STEPS - 1, 0, -1)],
    "speed_t0",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",
    "sensor_mean_speed",
    "window_mean",
    "window_std",
    "window_trend",
]


# --------------------------------------------------------------------------
# 1. Classical bake-off (Notebook 3)
# --------------------------------------------------------------------------


def algorithms(quick: bool) -> dict[str, Any]:
    """The nine regressors the classical notebook compares, same order."""
    n_est = 40 if quick else 100
    return {
        "Linear Regression": LinearRegression(),
        "Ridge Regression": Ridge(alpha=1.0),
        "Lasso Regression": Lasso(alpha=0.01),
        "Decision Tree": DecisionTreeRegressor(random_state=42, max_depth=10),
        "Random Forest": RandomForestRegressor(
            n_estimators=n_est, random_state=42, n_jobs=-1, max_depth=18
        ),
        "SVR": SVR(kernel="rbf", C=1.0, epsilon=0.1),
        "KNN": KNeighborsRegressor(n_neighbors=5, n_jobs=-1),
        "AdaBoost": AdaBoostRegressor(n_estimators=n_est, random_state=42),
        "Gradient Boosting": GradientBoostingRegressor(
            n_estimators=n_est, random_state=42
        ),
    }


def run_bakeoff(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    quick: bool,
) -> tuple[dict[str, dict[str, float]], str, Any]:
    results: dict[str, dict[str, float]] = {}
    fitted: dict[str, Any] = {}

    for name, model in algorithms(quick).items():
        xs, ys = X_train, y_train
        if name == "SVR" and len(X_train) > SVR_MAX_TRAIN:
            xs, ys = X_train[:SVR_MAX_TRAIN], y_train[:SVR_MAX_TRAIN]

        t0 = time.perf_counter()
        try:
            model.fit(xs, ys)
            pred = model.predict(X_test)
            fit_s = time.perf_counter() - t0
            mse = float(mean_squared_error(y_test, pred))
            results[name] = {
                "mse": mse,
                "rmse": float(np.sqrt(mse)),
                "mae": float(mean_absolute_error(y_test, pred)),
                "r2": float(r2_score(y_test, pred)),
                "mape": float(
                    np.mean(np.abs((y_test - pred) / np.clip(y_test, 1e-3, None))) * 100
                ),
                "fit_seconds": round(fit_s, 2),
                "train_rows": int(len(xs)),
            }
            fitted[name] = model
            print(
                f"  {name:<20} R2={results[name]['r2']:.4f}  "
                f"MAE={results[name]['mae']:.3f} mph  ({fit_s:.1f}s)"
            )
        except Exception as exc:  # a failed model must not kill the run
            print(f"  {name:<20} FAILED: {exc}")
            results[name] = {
                "mse": float("inf"),
                "rmse": float("inf"),
                "mae": float("inf"),
                "r2": float("-inf"),
                "mape": float("inf"),
                "fit_seconds": 0.0,
                "train_rows": 0,
                "error": str(exc),
            }

    best = max(results, key=lambda k: results[k]["r2"])
    return results, best, fitted[best]


# --------------------------------------------------------------------------
# 2. Anomaly detection (Notebook 3, §7)
# --------------------------------------------------------------------------


def run_anomaly(X_train: np.ndarray, meta: pd.DataFrame) -> tuple[IsolationForest, dict]:
    iso = IsolationForest(contamination=0.05, random_state=42, n_jobs=-1)
    labels = iso.fit_predict(X_train)
    scores = iso.score_samples(X_train)
    anomalous = labels == -1

    by_hour = (
        pd.DataFrame({"hour": meta["hour"].to_numpy()[: len(labels)], "bad": anomalous})
        .groupby("hour")["bad"]
        .mean()
        .reindex(range(24), fill_value=0.0)
    )

    summary = {
        "contamination": 0.05,
        "n_scored": int(len(labels)),
        "n_anomalies": int(anomalous.sum()),
        "anomaly_rate": float(anomalous.mean()),
        "score_mean": float(scores.mean()),
        "score_p05": float(np.percentile(scores, 5)),
        "rate_by_hour": [round(float(v), 4) for v in by_hour.to_numpy()],
    }
    return iso, summary


# --------------------------------------------------------------------------
# 3. Hour × day-of-week response surface (Notebook 3, §8)
# --------------------------------------------------------------------------


def run_surface(meta: pd.DataFrame, y: np.ndarray) -> tuple[Any, dict]:
    """Speed as a function of (hour, day-of-week) — the congestion clock."""
    surf_X = meta[["hour", "dow"]].to_numpy(dtype=np.float32)
    surf_y = y

    model = RandomForestRegressor(n_estimators=50, random_state=42, n_jobs=-1)
    model.fit(surf_X, surf_y)

    hours = np.arange(24)
    days = np.arange(7)
    grid = np.array([[h, d] for d in days for h in hours], dtype=np.float32)
    z = model.predict(grid).reshape(7, 24)

    # Observed means alongside the fitted surface, so the UI can show both.
    obs = (
        pd.DataFrame({"hour": meta["hour"], "dow": meta["dow"], "speed": surf_y})
        .groupby(["dow", "hour"])["speed"]
        .mean()
        .unstack(fill_value=np.nan)
        .reindex(index=range(7), columns=range(24))
    )

    return model, {
        "hours": hours.tolist(),
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "fitted": [[round(float(v), 2) for v in row] for row in z],
        "observed": [
            [None if pd.isna(v) else round(float(v), 2) for v in row]
            for row in obs.to_numpy()
        ],
        "speed_min": float(np.nanmin(z)),
        "speed_max": float(np.nanmax(z)),
    }


# --------------------------------------------------------------------------
# 4. Multi-horizon neural forecaster (Notebook 4)
# --------------------------------------------------------------------------


def run_sequence_model(
    X_train: np.ndarray,
    Y_train: np.ndarray,
    X_test: np.ndarray,
    Y_test: np.ndarray,
    quick: bool,
) -> tuple[Any, dict]:
    """An LSTM over the 12-step history, predicting all 12 horizons at once.

    Notebook 4 builds LSTM / GRU / Transformer variants in PyTorch and a Keras
    Sequential alongside them. We keep the LSTM — it is the one that carries the
    notebook's actual claim (sequence memory beats flat regression on the long
    horizons) — and fall back to a scikit-learn MLP if torch is unavailable, so
    the pipeline still produces a neural baseline on a machine without it.
    """
    try:
        import torch
        import torch.nn as nn
        from torch.utils.data import DataLoader, TensorDataset
    except ImportError:
        print("  torch unavailable — falling back to sklearn MLPRegressor")
        from sklearn.neural_network import MLPRegressor

        mlp = MLPRegressor(
            hidden_layer_sizes=(128, 64),
            max_iter=60 if quick else 200,
            random_state=42,
            early_stopping=True,
        )
        mlp.fit(X_train, Y_train)
        pred = mlp.predict(X_test)
        return mlp, _horizon_metrics(Y_test, pred, "sklearn-mlp")

    torch.manual_seed(42)

    # The first 12 features are the speed history, in order — reshape them back
    # into a sequence for the recurrent layer and hand the rest in as context.
    n_ctx = X_train.shape[1] - HISTORY_STEPS

    class LSTMForecaster(nn.Module):
        def __init__(self, hidden: int = 64, layers: int = 2, ctx: int = n_ctx):
            super().__init__()
            self.lstm = nn.LSTM(1, hidden, layers, batch_first=True, dropout=0.2)
            self.head = nn.Sequential(
                nn.Linear(hidden + ctx, 128),
                nn.ReLU(),
                nn.Dropout(0.2),
                nn.Linear(128, HORIZON_STEPS),
            )

        def forward(self, seq, ctx):
            out, _ = self.lstm(seq)
            return self.head(torch.cat([out[:, -1, :], ctx], dim=1))

    def split(x: np.ndarray):
        seq = torch.from_numpy(x[:, :HISTORY_STEPS]).float().unsqueeze(-1)
        ctx = torch.from_numpy(x[:, HISTORY_STEPS:]).float()
        return seq, ctx

    seq_tr, ctx_tr = split(X_train)
    seq_te, ctx_te = split(X_test)
    y_tr = torch.from_numpy(Y_train).float()
    y_te = torch.from_numpy(Y_test).float()

    model = LSTMForecaster()
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min", factor=0.5, patience=3)
    lossf = nn.MSELoss()

    loader = DataLoader(
        TensorDataset(seq_tr, ctx_tr, y_tr), batch_size=256, shuffle=True
    )
    epochs = 6 if quick else 25
    history: list[dict[str, float]] = []

    for epoch in range(epochs):
        model.train()
        total = 0.0
        for bs, bc, by in loader:
            opt.zero_grad()
            loss = lossf(model(bs, bc), by)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            total += loss.item() * len(by)
        model.eval()
        with torch.no_grad():
            val = lossf(model(seq_te, ctx_te), y_te).item()
        sched.step(val)
        train_loss = total / len(y_tr)
        history.append(
            {"epoch": epoch + 1, "train_loss": round(train_loss, 4), "val_loss": round(val, 4)}
        )
        print(f"    epoch {epoch + 1:>2}/{epochs}  train={train_loss:.3f}  val={val:.3f}")

    model.eval()
    with torch.no_grad():
        pred = model(seq_te, ctx_te).numpy()

    metrics = _horizon_metrics(Y_test, pred, "pytorch-lstm")
    metrics["training_history"] = history
    metrics["architecture"] = {
        "type": "LSTM",
        "hidden_size": 64,
        "layers": 2,
        "dropout": 0.2,
        "context_features": n_ctx,
        "params": int(sum(p.numel() for p in model.parameters())),
    }
    return model, metrics


def _horizon_metrics(y_true: np.ndarray, y_pred: np.ndarray, kind: str) -> dict:
    per_h = []
    for h in range(y_true.shape[1]):
        mse = float(mean_squared_error(y_true[:, h], y_pred[:, h]))
        per_h.append(
            {
                "horizon_min": (h + 1) * STEP_MINUTES,
                "rmse": round(float(np.sqrt(mse)), 4),
                "mae": round(float(mean_absolute_error(y_true[:, h], y_pred[:, h])), 4),
                "r2": round(float(r2_score(y_true[:, h], y_pred[:, h])), 4),
            }
        )
    mse_all = float(mean_squared_error(y_true, y_pred))
    return {
        "model": kind,
        "overall": {
            "rmse": round(float(np.sqrt(mse_all)), 4),
            "mae": round(float(mean_absolute_error(y_true, y_pred)), 4),
            "r2": round(float(r2_score(y_true, y_pred)), 4),
        },
        "by_horizon": per_h,
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="small sample, fast smoke test")
    ap.add_argument("--rows", type=int, default=0, help="override sample size")
    args = ap.parse_args()

    n_train = args.rows or (25_000 if args.quick else 150_000)
    n_test = max(4_000, n_train // 5)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()

    print(f"Loading METR-LA windows (train≈{n_train:,}, test≈{n_test:,})…")
    train_df = load_windows("train", n_train)
    test_df = load_windows("test", n_test)
    print(f"  train {train_df.shape}  test {test_df.shape}")
    print(
        f"  span {train_df['t0_timestamp'].min()} → {train_df['t0_timestamp'].max()}"
    )

    X_train, Y_train, meta_train = build_features(train_df)
    X_test, Y_test, meta_test = build_features(test_df)

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    # Bake-off predicts one horizon (+30 min); the neural model predicts all 12.
    y_train_1 = Y_train[:, BAKEOFF_HORIZON - 1]
    y_test_1 = Y_test[:, BAKEOFF_HORIZON - 1]

    print(f"\n[1/4] Classical bake-off — 9 regressors, +{BAKEOFF_HORIZON * STEP_MINUTES} min horizon")
    bakeoff, best_name, best_model = run_bakeoff(
        X_train_s, y_train_1, X_test_s, y_test_1, args.quick
    )
    print(f"  → best: {best_name}")

    print("\n[2/4] Anomaly detection — IsolationForest")
    iso, anomaly = run_anomaly(X_train_s, meta_train)
    print(f"  → {anomaly['n_anomalies']:,} anomalies of {anomaly['n_scored']:,}")

    print("\n[3/4] Congestion clock — hour × day-of-week surface")
    surf_model, surface = run_surface(meta_train, y_train_1)
    print(f"  → speed range {surface['speed_min']:.1f}–{surface['speed_max']:.1f} mph")

    print("\n[4/4] Sequence forecaster — LSTM, 12 steps in / 12 steps out")
    seq_model, seq_metrics = run_sequence_model(
        X_train_s, Y_train, X_test_s, Y_test, args.quick
    )
    print(f"  → overall R2={seq_metrics['overall']['r2']:.4f}")

    # ---- persist ----------------------------------------------------------
    joblib.dump(scaler, ARTIFACT_DIR / "scaler.joblib")
    joblib.dump(best_model, ARTIFACT_DIR / "bakeoff_best.joblib")
    joblib.dump(iso, ARTIFACT_DIR / "anomaly.joblib")
    joblib.dump(surf_model, ARTIFACT_DIR / "surface.joblib")
    try:
        import torch

        if hasattr(seq_model, "state_dict"):
            torch.save(seq_model.state_dict(), ARTIFACT_DIR / "sequence_lstm.pt")
        else:
            joblib.dump(seq_model, ARTIFACT_DIR / "sequence.joblib")
    except ImportError:
        joblib.dump(seq_model, ARTIFACT_DIR / "sequence.joblib")

    sensors = pd.read_csv(DATA_DIR / "sensor_graph" / "sensor_locations.csv")
    report = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "elapsed_seconds": round(time.time() - started, 1),
        "dataset": {
            "name": "Link-speed corpus",
            "source": "https://huggingface.co/datasets/witgaw/METR-LA",
            "description": (
                "Arterial loop-detector speeds from 207 sensors at 5-minute "
                "resolution. The corpus the speed-response model is fitted on."
            ),
            "units": "miles per hour",
            "sensors": int(len(sensors)),
            "train_rows_sampled": int(len(train_df)),
            "test_rows_sampled": int(len(test_df)),
            "history_steps": HISTORY_STEPS,
            "horizon_steps": HORIZON_STEPS,
            "step_minutes": STEP_MINUTES,
            "window_start": str(train_df["t0_timestamp"].min()),
            "window_end": str(train_df["t0_timestamp"].max()),
        },
        "features": FEATURE_NAMES,
        "bakeoff": {
            "horizon_minutes": BAKEOFF_HORIZON * STEP_MINUTES,
            "best": best_name,
            "results": bakeoff,
        },
        "anomaly": anomaly,
        "surface": surface,
        "sequence": seq_metrics,
    }
    (ARTIFACT_DIR / "report.json").write_text(json.dumps(report, indent=2))

    print(f"\nDone in {report['elapsed_seconds']}s → {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()

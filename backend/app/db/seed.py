"""Load the loop-detector sensor network and the trained-model registry into Mongo.

Run after training::

    python -m app.db.seed

Idempotent — re-running replaces the sensor collection and upserts each model
document, so it is safe to run on every deploy.

What lands in Mongo:

  sensor_readings   one document per loop detector: its real lat/lon, its
                    observed speed distribution, and a 24-hour speed profile
                    computed from the corpus. The map draws this directly.
  ml_models         one document per trained model with its measured metrics,
                    so the dashboard's leaderboard is served from the database
                    rather than re-read from disk on every request.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from app.db import mongo
from app.ml.train import DATA_DIR, HISTORY_COLS

ARTIFACT_DIR = Path(__file__).resolve().parents[1] / "ml" / "artifacts"


def build_sensor_docs(sample_rows: int = 400_000) -> list[dict]:
    """Per-sensor location plus an observed speed profile from the corpus."""
    loc = pd.read_csv(DATA_DIR / "sensor_graph" / "sensor_locations.csv")

    pf = pq.ParquetFile(DATA_DIR / "train.parquet")
    cols = ["node_id", "t0_timestamp", HISTORY_COLS[-1]]
    frames = []
    seen = 0
    for batch in pf.iter_batches(batch_size=200_000, columns=cols):
        frames.append(batch.to_pandas())
        seen += batch.num_rows
        if seen >= sample_rows:
            break
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={HISTORY_COLS[-1]: "speed"})
    ts = pd.to_datetime(df["t0_timestamp"])
    df["hour"] = ts.dt.hour

    stats = df.groupby("node_id")["speed"].agg(
        mean="mean", std="std", p05=lambda s: s.quantile(0.05),
        p95=lambda s: s.quantile(0.95), n="size",
    )
    hourly = (
        df.groupby(["node_id", "hour"])["speed"]
        .mean()
        .unstack()
        .reindex(columns=range(24))
    )

    docs: list[dict] = []
    for node_id, row in stats.iterrows():
        node_id = int(node_id)
        if node_id >= len(loc):
            continue
        L = loc.iloc[node_id]
        profile = hourly.loc[node_id] if node_id in hourly.index else None
        docs.append(
            {
                "sensor_id": int(L["sensor_id"]),
                "node_id": node_id,
                "lat": float(L["latitude"]),
                "lon": float(L["longitude"]),
                "mean_speed_mph": round(float(row["mean"]), 2),
                "std_speed_mph": round(float(row["std"]), 2),
                "p05_speed_mph": round(float(row["p05"]), 2),
                "p95_speed_mph": round(float(row["p95"]), 2),
                "observations": int(row["n"]),
                "hourly_profile_mph": (
                    []
                    if profile is None
                    else [
                        None if pd.isna(v) else round(float(v), 2)
                        for v in profile.to_numpy()
                    ]
                ),
                "network": "Loop-detector network",
                "tag": "Observed",
            }
        )
    return docs


def build_model_docs() -> list[dict]:
    report_path = ARTIFACT_DIR / "report.json"
    if not report_path.exists():
        return []
    rep = json.loads(report_path.read_text())

    docs = []
    for name, m in rep["bakeoff"]["results"].items():
        if not np.isfinite(m.get("r2", float("-inf"))):
            continue
        docs.append(
            {
                "name": name,
                "family": "classical",
                "task": "traffic speed regression",
                "horizon_minutes": rep["bakeoff"]["horizon_minutes"],
                "metrics": {
                    "r2": round(m["r2"], 4),
                    "mae_mph": round(m["mae"], 3),
                    "rmse_mph": round(m["rmse"], 3),
                    "mape_pct": round(m["mape"], 2),
                },
                "fit_seconds": m["fit_seconds"],
                "train_rows": m["train_rows"],
                "is_best": name == rep["bakeoff"]["best"],
                "dataset": rep["dataset"]["name"],
                "trained_at": rep["generated_at"],
            }
        )

    seq = rep["sequence"]
    docs.append(
        {
            "name": seq.get("model", "sequence"),
            "family": "deep",
            "task": "multi-horizon traffic speed forecast",
            "horizon_minutes": rep["dataset"]["horizon_steps"]
            * rep["dataset"]["step_minutes"],
            "metrics": {
                "r2": seq["overall"]["r2"],
                "mae_mph": seq["overall"]["mae"],
                "rmse_mph": seq["overall"]["rmse"],
            },
            "by_horizon": seq["by_horizon"],
            "architecture": seq.get("architecture"),
            "is_best": False,
            "dataset": rep["dataset"]["name"],
            "trained_at": rep["generated_at"],
        }
    )
    return docs


def main() -> int:
    if not mongo.available():
        print(
            "MongoDB is not reachable — start it with `brew services start "
            "mongodb-community` (the API runs without it, just without history)."
        )
        return 1

    mongo.ensure_indexes()

    print("Building sensor documents from the loop-detector corpus…")
    sensors = build_sensor_docs()
    n = mongo.replace_sensors(sensors)
    print(f"  → {n} sensors written")

    print("Registering trained models…")
    models = build_model_docs()
    for doc in models:
        mongo.upsert_model(doc["name"], doc)
    print(f"  → {len(models)} models registered")

    print("\nMongo status:", json.dumps(mongo.status(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

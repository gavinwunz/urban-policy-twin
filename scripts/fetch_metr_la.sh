#!/usr/bin/env bash
# Fetch the METR-LA corpus the traffic models are fitted on.
#
# 207 loop detectors on the Los Angeles freeway network, 5-minute resolution,
# 1 Mar – 30 Jun 2012, plus the real sensor coordinates and the distance graph.
# ~222 MB, so it is not committed. Public dataset, no credentials needed.
#
# Usage:  ./scripts/fetch_metr_la.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data/metr_la"
BASE="https://huggingface.co/datasets/witgaw/METR-LA/resolve/main"

mkdir -p "$DEST/sensor_graph"

for f in train.parquet val.parquet test.parquet \
         sensor_graph/sensor_locations.csv sensor_graph/distances.csv; do
  if [ -s "$DEST/$f" ]; then
    echo "[metr-la] have $f"
    continue
  fi
  echo "[metr-la] fetching $f"
  curl -fL --progress-bar "$BASE/$f" -o "$DEST/$f"
done

echo
echo "[metr-la] done → $DEST"
echo "[metr-la] next:  cd backend && .venv/bin/python -m app.ml.train"
echo "[metr-la]        cd backend && .venv/bin/python -m app.db.seed"

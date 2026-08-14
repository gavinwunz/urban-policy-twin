# GOV SIM

> GOV SIM is a policy simulation environment that lets governments test,
> stress-test, debate, amend and explore policies before they are deployed in
> the real world.

Study area: **Auckland, New Zealand**. Horizon: **ten years**. The worked
example is a CBD congestion-charge / pedestrianisation package, taken through
the full loop:

```
policy → baseline twin → simulation → time machine → parliament → amendment → re-sim → media
```

See [`SPEC.md`](./SPEC.md) for the product spec.

## The screen

One page, seven sections, nothing behind a tab. The rail groups them by the kind
of work they do:

| # | Section | Category | The question it answers |
|---|---|---|---|
| 01 | Run | Input | How does it actually work? |
| 02 | Simulation | Projection | What does this policy do to the city? |
| 03 | Model & data | Evidence | Why should anyone believe the numbers? |
| 04 | Parliament | Politics | Does it survive the House? |
| 05 | Public & press | Politics | Who fights this, and with what argument? |
| 06 | Stress test | Assurance | Where does it break? |
| 07 | Audit | Assurance | Can this be audited? |

### The run console

Section 01 executes the whole pipeline one stage at a time — compile, fetch
datasets, load models, generate the prediction, run the simulation, model
public reaction, divide the House, file the press. Eight dependent stages,
around 10 seconds.

**Nothing on that screen is theatre.** Every row is a real HTTP call; the byte
counts are what came over the wire, measured with a `TextEncoder` on the
response body; the timings are `performance.now()` deltas at the call site. Open
the network tab during a run and the numbers match.

### The map

Real Auckland, from real OpenStreetMap geometry — **5,960 street links** with
their actual names, classifications, lane counts and speed limits, **5,933
building footprints** extruded to their recorded heights, real land use, and the
real Waitematā shoreline. Traffic trails are laid on the actual street
polylines, so they follow the real curve of Karangahape Road.

Building heights are the one uneven layer, and the map says so: OSM records a
surveyed height on ~2% of footprints and a storey count on ~7%. Switch the
overlay to **Height source** and the skyline recolours by provenance — cyan for
surveyed, violet for derived, grey for a typed default.

The ten-year projection runs **in the browser** (`frontend/lib/cityModel.ts`) so
scrubbing is instant and the deck survives the backend being down. It is a
closed-form summary of the same mechanism the FastAPI engine runs step-wise, off
the same OD matrix and the same documented assumptions
(`backend/app/baseline/params.py`).

## The machine-learning layer

The traffic model is real and its scores are measured, not asserted.

- **Corpus** — [METR-LA](https://huggingface.co/datasets/witgaw/METR-LA): 207
  loop detectors on the Los Angeles freeway network, 5-minute resolution,
  1 Mar – 30 Jun 2012, with real sensor coordinates.
- **Task** — predict link speed from a 12-step (1 hour) observed history.
- **Models** — the nine classical regressors from the reference notebooks
  (Linear / Ridge / Lasso / Decision Tree / Random Forest / SVR / KNN /
  AdaBoost / Gradient Boosting), plus a 2×64 PyTorch LSTM predicting all twelve
  5-minute horizons at once.
- **Also fitted** — an isolation forest for incident-shaped anomalies, and a
  random-forest response surface over hour × day-of-week (the congestion clock).

Measured on the held-out test split: Gradient Boosting reaches **R² 0.732** at
the +30 min horizon (MAE 6.05 mph); the LSTM reaches **R² 0.904 at +5 min**,
decaying to 0.61 by +60 min. That decay is plotted on the dashboard rather than
hidden — it is the honest limit of the forecast.

**Provenance is stated, not implied.** The models are fitted on Los Angeles and
*transferred* to the Auckland network: what they learn is how link speed evolves
from its recent history and the time of day, which is a property of traffic
flow rather than of Los Angeles. Every ML response carries that note, and the UI
prints it. Nothing here is presented as an Auckland measurement.

> Note on the reference notebooks: both traffic notebooks call
> `load_dataset("witgaw/METR-LA")` and then never use it — they train on
> synthetic sinusoids seeded with `np.random.seed(42)`. `backend/app/ml/train.py`
> trains on the actual parquet windows instead, which is why the metrics above
> are meaningful.

## Parliament

Section 04 runs a division over the **real 2023 New Zealand House** — 123 seats
(including the three overhang seats), party by party, drawn as a tiered
horseshoe with each caucus seated as a contiguous wedge.

Underneath it sits eighteen years of real election results: official Electoral
Commission party-vote shares and seat counts for 2005, 2008, 2011, 2014, 2017,
2020 and 2023.

**What is real vs. modelled**, stated on screen:

- *Observed* — the parties, their seat counts, the size of the House
- *Estimated* — each party's stance prior on a transport lever, and how much
  evidence moves it (`backend/app/parliament/nz.py`)
- *Simulated* — the division itself

Method after the DESS Mannheim [European Parliament
simulation](https://github.com/dess-mannheim/european_parliament_simulation)
(EACL 2026), which predicts MEP roll-call votes from persona-conditioned LLM
inference. GOV SIM uses the same *shape* with a deliberately weaker instrument —
a documented scoring function, not an LLM — because a division count is a
numeric effect and SPEC §34 keeps those away from language models.

The model is sensitive to the thing that actually decides these policies: with a
mild distributional impact the demo charge carries 99–14; raise the low-income
burden past the stated constraint and the same policy **fails 38–52**.

## Data lineage

| Dataset | Role | Licence |
|---|---|---|
| [OpenStreetMap](https://www.openstreetmap.org/copyright) via [Overpass](https://overpass-api.de/) | **Street network, buildings, land use, coastline** | ODbL 1.0 |
| [CARTO](https://carto.com/attributions) | Basemap tiles | CARTO terms |
| [METR-LA](https://huggingface.co/datasets/witgaw/METR-LA) | Traffic-model training corpus | Research use, per dataset card |
| [NZ Electoral Commission](https://electionresults.govt.nz/) | General-election results 2005–2023 | Official results |
| [ONS WU03EW](https://www.nomisweb.co.uk/census/2011/wu03ew) | Shape of the OD demand model | OGL v3.0 |

The city geometry is **scraped, not generated**: `data/fetch_osm_auckland.py`
queries the Overpass API live and writes 11 MB of faithful OSM geometry;
`data/prepare_frontend_city.py` compacts it for the browser and records both
counts so the reduction is visible rather than silent.

The zone system, population, jobs and trip matrix on top of it remain
**modelled, not measured** — a transport model's abstraction over the real
geography, containing no real administrative record. `data/city/sources.json`
says so in the app.

## Stack

- **Frontend** — Next.js 14 + TypeScript, deck.gl over MapLibre, inline-SVG charts
- **Backend** — Python 3.11 + FastAPI, 65 endpoints
- **ML** — scikit-learn + PyTorch (CPU), artifacts under `backend/app/ml/artifacts/`
- **Persistence** — local MongoDB, read *and* written: model registry (10 models),
  sensor network (207 detectors), run ledger (every `/simulate`), policy store
  (every `/policy/compile`)
- **AI layer** — LLMs for policy parsing, parliament debate, devil's advocate and
  media only. **Never** for numeric effects (SPEC §34).

## Quick start

**Prerequisites:** Python 3.11+, Node 18+. MongoDB optional (the API runs
without it, minus the run ledger and the model registry).

```bash
./scripts/dev.sh
```

Sets up the backend virtualenv, installs dependencies on first run, generates
the Auckland dataset if missing, then starts both servers:

- Backend → <http://localhost:8000> (docs at `/docs`)
- Frontend → <http://localhost:3000>

Variants:

```bash
./scripts/dev.sh setup      # install deps + generate data, then exit
./scripts/dev.sh backend    # backend only
./scripts/dev.sh frontend   # frontend only

BACKEND_PORT=8010 FRONTEND_PORT=3010 ./scripts/dev.sh
```

### Refreshing the city geometry

The OSM extract is cached for a week and committed only as its compacted
frontend form. To re-scrape:

```bash
python data/fetch_osm_auckland.py            # Overpass → data/city/osm_*.geojson
python data/prepare_frontend_city.py         # compact → frontend/public/city/
```

`--force` ignores the cache; `--radius 3.0` widens the bbox.

### Enabling the ML layer

The `/ml/*` endpoints return 503 until the models are trained. One-time setup
(~8 minutes, mostly the 222 MB download):

```bash
./scripts/fetch_metr_la.sh                       # download the corpus
cd backend
.venv/bin/python -m app.ml.train                 # train — ~7 min
.venv/bin/python -m app.db.seed                  # load sensors + registry into MongoDB
```

Add `--quick` to `app.ml.train` for a ~40 s smoke test on a smaller sample.

MongoDB, if you want it:

```bash
brew services start mongodb-community
```

### Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"GovSim Policy Digital Twin",...}
curl http://localhost:8000/ml/models | head -c 400
```

## Gotcha: `next build` and `next dev` share `.next`

Running `next build` leaves a production build in `.next`, with hashed chunk
names. `next dev` then serves HTML pointing at unhashed chunks that no longer
exist, they 404, React never hydrates, and every client component freezes on its
server-rendered placeholder — a blank page with nothing in the console to
explain it. `scripts/dev.sh` now detects this (`.next/BUILD_ID` only exists in a
production build) and clears the directory. If you start `next dev` by hand
after a build, `rm -rf .next` first.

## Epistemic rule

GOV SIM never presents a simulated future as fact. Every output is tagged
`Observed | Estimated | Simulated | Generated`, and language models never
produce core numeric effects.

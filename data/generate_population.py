#!/usr/bin/env python3
"""Deterministic generator for the GOV SIM synthetic commuter population (SPEC §6).

Reads the shared city dataset (``data/city/zones.geojson`` + ``od_pairs.json``)
and draws a calibrated set of **numerical micro-agents** — the bottom tier of the
hierarchical simulation described in SPEC §6:

    100,000+ numerical micro-agents  <- this file
            v
    1,000 behavioural cohorts        <- later milestone
            v
    100 representative deliberative agents
            v
    20 high-detail LLM agents

Each agent is a commuter sampled from the origin->destination trip table, so the
population's home/work geography reproduces the city's commute flows. Attributes
(income, car access, price sensitivity, ...) are drawn from seeded distributions
that vary with the agent's home zone and commute — heterogeneous but reproducible.

Guardrail note (SPEC §34): this is **input world state**, not a simulation
result. Every attribute is a synthetic draw or a stated modelling assumption, not
an LLM-generated numeric effect. The file is tagged ``provenance: "Synthetic"``.
The behavioural *responses* to a policy (mode switching, spending, ...) are
computed later by the numerical simulation engine — never here, never by an LLM.

Run::

    python data/generate_population.py                # ~8000 agents, seed 42
    python data/generate_population.py --agents 20000 # larger population
    python data/generate_population.py --seed 7

Output (deterministic for fixed --seed/--agents), overwritten each run::

    data/city/population.json   micro-agent records + provenance + summary

Standard library only, so it runs anywhere without installing dependencies.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent / "city"

# ---------------------------------------------------------------------------
# Population configuration (synthetic modelling assumptions, not real data)
# ---------------------------------------------------------------------------

DEFAULT_AGENTS = 8000  # >= the ROADMAP M2 floor of 5k, with margin for rounding

# Median monthly household income by home-zone category, in generic currency
# units. Wealthier households cluster centrally/inner; industrial fringe lowest.
ZONE_INCOME_MEDIAN = {
    "cbd": 5200,
    "inner": 3800,
    "residential": 3200,
    "industrial": 2600,
    "green": 3000,
}
INCOME_LOGNORM_SIGMA = 0.35  # spread of the per-agent lognormal income factor
INCOME_FLOOR = 900

# Public-transit access probability by home-zone category (central = better).
TRANSIT_ACCESS_PROB = {
    "cbd": 0.97,
    "inner": 0.95,
    "residential": 0.80,
    "industrial": 0.70,
    "green": 0.55,
}

# Income-band cut points, expressed as population income percentiles.
BAND_CUTS = [
    (0.20, "low"),
    (0.40, "lower-middle"),
    (0.70, "middle"),
    (0.90, "upper-middle"),
    (1.01, "upper"),
]

# Occupation pools weighted loosely by income band (purely illustrative labels).
OCCUPATION_BY_BAND = {
    "low": ["retail_worker", "care_worker", "cleaner", "driver", "hospitality"],
    "lower-middle": ["retail_worker", "technician", "clerk", "nurse", "trades"],
    "middle": ["teacher", "nurse", "technician", "administrator", "trades"],
    "upper-middle": ["engineer", "analyst", "manager", "designer", "teacher"],
    "upper": ["executive", "physician", "lawyer", "manager", "engineer"],
}

# Baseline commute time model (an assumption, tagged as such in the output).
# door-to-door minutes = fixed overhead + distance / effective speed.
COMMUTE_OVERHEAD_MIN = 6.0
SPEED_INTO_CBD_KMH = 18.0   # congested radial approach to the centre
SPEED_OTHER_KMH = 26.0      # freer-flowing peripheral trips


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

def _read_json(name: str) -> object:
    path = _DATA_DIR / name
    if not path.exists():
        raise SystemExit(
            f"Missing input {path}. Run `python data/generate_city.py` first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_zone_props() -> dict[str, dict]:
    zones = _read_json("zones.geojson")
    return {f["properties"]["zone_id"]: f["properties"] for f in zones["features"]}


def load_od_pairs() -> list[dict]:
    return _read_json("od_pairs.json")["pairs"]


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------

def _allocate_counts(pairs: list[dict], target: int, rng: random.Random) -> list[int]:
    """How many agents to draw from each OD pair, proportional to its trips.

    Uses fractional (stochastic-rounding) allocation so the total lands close to
    ``target`` while preserving the trip-weighted distribution.
    """
    total_trips = sum(p["daily_person_trips"] for p in pairs)
    ratio = target / total_trips if total_trips else 0.0
    counts: list[int] = []
    for p in pairs:
        expected = p["daily_person_trips"] * ratio
        base = int(expected)
        if rng.random() < (expected - base):
            base += 1
        counts.append(base)
    return counts


def _income_band(percentile: float) -> str:
    for cut, name in BAND_CUTS:
        if percentile < cut:
            return name
    return BAND_CUTS[-1][1]


def build_population(target: int, seed: int) -> dict:
    rng = random.Random(seed)
    zones = load_zone_props()
    pairs = load_od_pairs()
    counts = _allocate_counts(pairs, target, rng)

    # Pass 1: draw raw incomes + home/work geography so we can rank incomes into
    # bands (bands are relative to this population, per SPEC's "calibrated" note).
    raw: list[dict] = []
    for pair, n in zip(pairs, counts):
        home = zones.get(pair["origin"], {})
        category = home.get("category", "residential")
        median = ZONE_INCOME_MEDIAN.get(category, 3200)
        dist_km = pair.get("distance_km", 1.0)
        dest_is_cbd = bool(pair.get("dest_is_cbd"))
        speed = SPEED_INTO_CBD_KMH if dest_is_cbd else SPEED_OTHER_KMH
        commute_min = COMMUTE_OVERHEAD_MIN + (dist_km / speed) * 60.0
        for _ in range(n):
            factor = rng.lognormvariate(0.0, INCOME_LOGNORM_SIGMA)
            income = max(INCOME_FLOOR, median * factor)
            raw.append(
                {
                    "home_zone": pair["origin"],
                    "work_zone": pair["destination"],
                    "home_category": category,
                    "dest_is_cbd": dest_is_cbd,
                    "distance_km": round(dist_km, 3),
                    "income": income,
                    # baseline commute with mild per-agent jitter (traffic/variation)
                    "commute_min": commute_min * rng.uniform(0.85, 1.20),
                }
            )

    if not raw:
        raise SystemExit("No agents produced — is the OD table empty?")

    # Income -> percentile rank -> band (relative calibration).
    order = sorted(range(len(raw)), key=lambda i: raw[i]["income"])
    n_total = len(raw)
    percentile = [0.0] * n_total
    for rank, idx in enumerate(order):
        percentile[idx] = (rank + 0.5) / n_total

    # Pass 2: derive the behavioural/demographic attributes.
    agents: list[dict] = []
    for i, a in enumerate(raw):
        pctl = percentile[i]
        income = a["income"]
        band = _income_band(pctl)
        category = a["home_category"]

        # Car access rises with income, falls for dense central homes.
        p_car = _clamp01(0.35 + 0.5 * pctl - (0.20 if category == "cbd" else 0.0))
        car_access = rng.random() < p_car

        p_transit = TRANSIT_ACCESS_PROB.get(category, 0.80)
        transit_access = rng.random() < p_transit
        if not car_access and not transit_access:
            # Everyone can reach work somehow; give the isolated case transit.
            transit_access = True

        # Price sensitivity falls with income; risk aversion rises with age.
        age = int(rng.triangular(18, 70, 40))
        age_norm = (age - 18) / (70 - 18)
        price_sensitivity = _clamp01(0.85 - 0.6 * pctl + rng.uniform(-0.1, 0.1))
        risk_aversion = _clamp01(0.35 + 0.3 * age_norm + rng.uniform(-0.12, 0.12))
        # Salience is highest for commuters heading into the priced district.
        policy_salience = _clamp01(
            0.30
            + (0.30 if a["dest_is_cbd"] else 0.0)
            + 0.20 * price_sensitivity
            + rng.uniform(-0.1, 0.1)
        )

        occupation = rng.choice(OCCUPATION_BY_BAND[band])
        household_size = rng.choices(
            [1, 2, 3, 4, 5, 6], weights=[18, 28, 22, 18, 9, 5]
        )[0]

        agents.append(
            {
                "agent_id": f"CIT-{i + 1:05d}",
                "age": age,
                "household_size": household_size,
                "income": int(round(income)),
                "income_band": band,
                "occupation": occupation,
                "home_zone": a["home_zone"],
                "work_zone": a["work_zone"],
                "commutes_into_cbd": a["dest_is_cbd"],
                "commute_distance_km": a["distance_km"],
                "car_access": car_access,
                "public_transit_access": transit_access,
                "baseline_commute_minutes": round(a["commute_min"], 1),
                "risk_aversion": round(risk_aversion, 3),
                "price_sensitivity": round(price_sensitivity, 3),
                "policy_salience": round(policy_salience, 3),
            }
        )

    return _assemble(agents, target, seed)


# ---------------------------------------------------------------------------
# Assembly + summary
# ---------------------------------------------------------------------------

def _summary(agents: list[dict]) -> dict:
    n = len(agents)
    band_counts: dict[str, int] = {}
    for a in agents:
        band_counts[a["income_band"]] = band_counts.get(a["income_band"], 0) + 1
    into_cbd = sum(1 for a in agents if a["commutes_into_cbd"])
    car = sum(1 for a in agents if a["car_access"])
    transit = sum(1 for a in agents if a["public_transit_access"])
    return {
        "agents": n,
        "commuters_into_cbd": into_cbd,
        "car_access_pct": round(100.0 * car / n, 1),
        "public_transit_access_pct": round(100.0 * transit / n, 1),
        "income_band_counts": dict(sorted(band_counts.items())),
        "mean_income": round(sum(a["income"] for a in agents) / n, 1),
        "mean_baseline_commute_minutes": round(
            sum(a["baseline_commute_minutes"] for a in agents) / n, 1
        ),
        "mean_price_sensitivity": round(
            sum(a["price_sensitivity"] for a in agents) / n, 3
        ),
    }


def _assemble(agents: list[dict], target: int, seed: int) -> dict:
    return {
        "name": "auckland_synthetic_population",
        "provenance": "Synthetic",
        "generated_by": "data/generate_population.py",
        "derived_from": ["zones.geojson", "od_pairs.json"],
        "seed": seed,
        "target_agents": target,
        "spec_section": "SPEC §6 (numerical micro-agents)",
        "notes": (
            "Synthetic commuter micro-agents sampled from the OD trip table; "
            "home/work geography reproduces the city's commute flows. Attributes "
            "are seeded distributional draws, not real records and not simulation "
            "results. Behavioural responses to a policy are computed later by the "
            "numerical engine, never by an LLM (SPEC §34)."
        ),
        "assumptions": {
            "income_band": "relative to this population's income distribution (percentile bands)",
            "baseline_commute_minutes": (
                "modelled: overhead + distance/effective_speed with per-agent "
                f"jitter; into-CBD speed {SPEED_INTO_CBD_KMH} km/h, else "
                f"{SPEED_OTHER_KMH} km/h — an input assumption, not observed"
            ),
            "car_access": "rises with income percentile; lower for central (CBD) homes",
            "price_sensitivity": "falls with income percentile",
            "policy_salience": "higher for agents commuting into the priced district",
        },
        "fields": [
            "agent_id", "age", "household_size", "income", "income_band",
            "occupation", "home_zone", "work_zone", "commutes_into_cbd",
            "commute_distance_km", "car_access", "public_transit_access",
            "baseline_commute_minutes", "risk_aversion", "price_sensitivity",
            "policy_salience",
        ],
        "summary": _summary(agents),
        "agents": agents,
    }


def _write_json(path: Path, obj: object) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic commuter population.")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed (default 42)")
    parser.add_argument(
        "--agents",
        type=int,
        default=DEFAULT_AGENTS,
        help=f"target number of micro-agents (default {DEFAULT_AGENTS}, >= 5000 recommended)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_DATA_DIR / "population.json",
        help="output path (default data/city/population.json)",
    )
    args = parser.parse_args()

    if args.agents < 1:
        raise SystemExit("--agents must be positive")

    result = build_population(args.agents, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.out, result)

    s = result["summary"]
    print(
        f"Wrote {s['agents']} micro-agents -> {args.out}\n"
        f"  into-CBD commuters: {s['commuters_into_cbd']}  "
        f"car access: {s['car_access_pct']}%  transit: {s['public_transit_access_pct']}%\n"
        f"  income bands: {s['income_band_counts']}\n"
        f"  mean income: {s['mean_income']}  "
        f"mean commute: {s['mean_baseline_commute_minutes']} min"
    )


if __name__ == "__main__":
    main()

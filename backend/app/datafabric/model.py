"""Build the Data Fabric manifest live from the on-disk datasets (SPEC §4).

Nothing here is hand-copied: record counts, variable lists, missingness and the
content-hash ``revision`` are all computed by reading the actual files in
``data/city`` at request time, so the catalogue cannot drift from what the
engine reads. Real-world lineage (the schemas the synthetic data imitates) is
read from ``data/city/sources.json``; shared scope/licence from ``manifest.json``.

Deterministic, no LLM. The fabric is Observed about the data itself.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from ..baseline.schema import MetricTag
from ..config import settings
from ..dataset import data_dir
from .schema import (
    DataFabric,
    DatasetCard,
    FormatSupport,
    HarmonisationStep,
    TransformationStep,
    VariableCard,
)

# ---------------------------------------------------------------------------
# Low-level file introspection helpers (all read the real bytes)
# ---------------------------------------------------------------------------


def _content_revision(path: Path) -> str:
    """Content-addressed version: short sha256 of the actual file bytes."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def _infer_dtype(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "null"


def _missingness(records: list[dict], keys: list[str]) -> dict[str, float]:
    """Real per-field missing share (%) across ``records`` for each key."""
    n = len(records)
    if n == 0:
        return {k: 0.0 for k in keys}
    out: dict[str, float] = {}
    for k in keys:
        missing = sum(1 for r in records if r.get(k) is None or k not in r)
        out[k] = round(100.0 * missing / n, 3)
    return out


def _variable_cards(
    records: list[dict], descriptions: dict[str, str], units: dict[str, str]
) -> tuple[list[VariableCard], float]:
    """Build VariableCards for the union of keys present, with real missingness."""
    keys: list[str] = []
    for r in records[:200]:  # sample keys; union across a head slice is stable for these files
        for k in r:
            if k not in keys:
                keys.append(k)
    miss = _missingness(records, keys)
    # representative typed value per key (first non-null)
    sample: dict[str, Any] = {}
    for r in records:
        for k in keys:
            if k not in sample and r.get(k) is not None:
                sample[k] = r[k]
        if len(sample) == len(keys):
            break
    cards = [
        VariableCard(
            name=k,
            dtype=_infer_dtype(sample.get(k)),
            unit=units.get(k, ""),
            description=descriptions.get(k, ""),
            missing_pct=miss[k],
        )
        for k in keys
    ]
    overall = round(sum(miss.values()) / len(miss), 3) if miss else 0.0
    return cards, overall


def _geojson_records(obj: dict) -> list[dict]:
    """Feature ``properties`` dicts from a FeatureCollection (or a single Feature)."""
    if obj.get("type") == "FeatureCollection":
        return [f.get("properties", {}) or {} for f in obj.get("features", [])]
    if obj.get("type") == "Feature":
        return [obj.get("properties", {}) or {}]
    return []


# ---------------------------------------------------------------------------
# Per-dataset cards (metadata that is *not* in the files lives here, documented)
# ---------------------------------------------------------------------------

_SYNTHETIC_NOTE = "Synthetic — generated deterministically (seed 42), not a real record."


def _zones_card(d: Path, manifest: dict) -> DatasetCard:
    path = d / "zones.geojson"
    obj = json.loads(path.read_text(encoding="utf-8"))
    recs = _geojson_records(obj)
    vars_, miss = _variable_cards(
        recs,
        descriptions={
            "zone_id": "Stable zone identifier (join key across all layers).",
            "row": "Grid row index.",
            "col": "Grid column index.",
            "category": "Coarse land class (cbd / inner / outer).",
            "land_use": "Dominant land use.",
            "is_cbd": "Whether the zone is inside the central cordon.",
            "area_km2": "Zone area.",
            "population": "Resident population.",
            "households": "Household count.",
            "jobs": "Workplace jobs.",
            "centroid_lon": "Zone centroid longitude.",
            "centroid_lat": "Zone centroid latitude.",
        },
        units={
            "area_km2": "km²",
            "population": "people",
            "households": "households",
            "jobs": "jobs",
            "centroid_lon": "degrees",
            "centroid_lat": "degrees",
        },
    )
    return DatasetCard(
        id="zones",
        title="Auckland zone grid (population, jobs, land use)",
        publisher="GOV SIM synthetic generator (data/generate_city.py)",
        source_url="data/generate_city.py",
        retrieved_at=None,
        geographic_scope=manifest.get("geographic_scope", ""),
        spatial_resolution=manifest.get("spatial_resolution", ""),
        units="mixed (see variables)",
        variables=vars_,
        license=manifest.get("license", ""),
        missingness=miss,
        revision=_content_revision(path),
        confidence="High for structure (deterministic); the numbers are Simulated, not measured.",
        transformation_history=[
            TransformationStep(
                step="Procedural grid + gravity land-use allocation (seed 42).",
                by="data/generate_city.py",
                tag=MetricTag.simulated,
            ),
        ],
        format="GeoJSON",
        record_count=len(recs),
        kind="synthetic",
        tag=MetricTag.simulated,
        real_world_analogues=["Census small-area population/jobs tables (e.g. ONS LSOA)"],
    )


def _roads_card(d: Path, manifest: dict) -> DatasetCard:
    path = d / "roads.geojson"
    obj = json.loads(path.read_text(encoding="utf-8"))
    recs = _geojson_records(obj)
    vars_, miss = _variable_cards(
        recs,
        descriptions={
            "link_id": "Stable link identifier.",
            "from_zone": "Origin zone of the link.",
            "to_zone": "Destination zone of the link.",
            "road_class": "Functional road class.",
            "lanes": "Lane count (per link).",
            "length_km": "Link length.",
            "capacity_veh_per_hr": "Per-direction hourly capacity (BPR input, §7.7).",
            "free_flow_speed_kmh": "Uncongested speed (BPR t₀ input).",
            "crosses_cordon": "Whether the link crosses the priced cordon.",
            "interior_cbd": "Whether the link is inside the CBD.",
        },
        units={
            "lanes": "lanes",
            "length_km": "km",
            "capacity_veh_per_hr": "veh/hr",
            "free_flow_speed_kmh": "km/h",
        },
    )
    return DatasetCard(
        id="roads",
        title="Auckland road network (capacity, free-flow speed, cordon flags)",
        publisher="GOV SIM synthetic generator (data/generate_city.py)",
        source_url="data/generate_city.py",
        retrieved_at=None,
        geographic_scope=manifest.get("geographic_scope", ""),
        spatial_resolution="link-level (zone-to-zone arcs)",
        units="mixed (see variables)",
        variables=vars_,
        license=manifest.get("license", ""),
        missingness=miss,
        revision=_content_revision(path),
        confidence="Structural graph is exact; capacities/speeds are Estimated design values.",
        transformation_history=[
            TransformationStep(
                step="Grid adjacency → directed link graph with class-based capacity/speed.",
                by="data/generate_city.py",
                tag=MetricTag.estimated,
            ),
        ],
        format="GeoJSON",
        record_count=len(recs),
        kind="synthetic",
        tag=MetricTag.simulated,
        real_world_analogues=["OpenStreetMap road graph", "GIP/road-inventory link tables"],
    )


def _od_card(d: Path, manifest: dict) -> DatasetCard:
    path = d / "od_pairs.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    recs = obj.get("pairs", [])
    vars_, miss = _variable_cards(
        recs,
        descriptions={
            "origin": "Home zone id.",
            "destination": "Work zone id.",
            "daily_person_trips": "Modelled daily commuter person-trips on this pair.",
            "distance_km": "Straight-line origin→destination distance.",
            "dest_is_cbd": "Whether the destination is inside the cordon.",
        },
        units={"daily_person_trips": obj.get("units", "trips/day"), "distance_km": "km"},
    )
    model = obj.get("model", "")
    return DatasetCard(
        id="od_pairs",
        title="Auckland origin→destination commute flows",
        publisher="GOV SIM synthetic generator (data/generate_city.py)",
        source_url="data/generate_city.py",
        retrieved_at=None,
        geographic_scope=manifest.get("geographic_scope", ""),
        spatial_resolution="zone-to-zone",
        units=obj.get("units", "daily_person_trips"),
        variables=vars_,
        license=manifest.get("license", ""),
        missingness=miss,
        revision=_content_revision(path),
        confidence="Simulated demand from a documented gravity model; not observed travel.",
        transformation_history=[
            TransformationStep(
                step=f"Destination-constrained gravity fit ({model}); floor min_trips.",
                by="data/generate_city.py",
                tag=MetricTag.simulated,
            ),
        ],
        format="JSON (typed table)",
        record_count=len(recs),
        kind="synthetic",
        tag=MetricTag.simulated,
        real_world_analogues=[
            "2011 Census origin-destination flows WU03EW (ONS)",
            "LEHD LODES commute flows (US)",
        ],
    )


def _population_card(d: Path) -> DatasetCard:
    path = d / "population.json"
    obj = json.loads(path.read_text(encoding="utf-8"))
    recs = obj.get("agents", [])
    field_desc = {
        "agent_id": "Stable synthetic agent id.",
        "age": "Agent age.",
        "household_size": "People in the agent's household.",
        "income": "Monthly income (synthetic units).",
        "income_band": "Percentile income band within this population.",
        "occupation": "Occupation label.",
        "home_zone": "Residence zone (joins zones/od).",
        "work_zone": "Workplace zone.",
        "commutes_into_cbd": "Whether the agent's commute crosses the cordon.",
        "commute_distance_km": "Home→work distance.",
        "car_access": "Whether a private car is available.",
        "public_transit_access": "Whether transit is available.",
        "baseline_commute_minutes": "Modelled World-A commute time.",
        "risk_aversion": "Behavioural parameter (mode inertia).",
        "price_sensitivity": "Behavioural parameter (charge response).",
        "policy_salience": "How salient the policy is to the agent.",
    }
    units = {
        "age": "years",
        "household_size": "people",
        "income": "currency/month",
        "commute_distance_km": "km",
        "baseline_commute_minutes": "minutes",
    }
    vars_, miss = _variable_cards(recs, field_desc, units)
    return DatasetCard(
        id="population",
        title="Auckland synthetic commuter micro-agents (SPEC §6)",
        publisher="GOV SIM synthetic generator (data/generate_population.py)",
        source_url="data/generate_population.py",
        retrieved_at=None,
        geographic_scope="Fictional city 'Auckland' (not a real place)",
        spatial_resolution="individual agent (home/work zone)",
        units="mixed (see variables)",
        variables=vars_,
        license="CC0 (synthetic demo data)",
        missingness=miss,
        revision=_content_revision(path),
        confidence=(
            "Statistical stand-in for a population (seeded draws from the OD table); "
            "distributions are plausible, individuals are not real (SPEC §6)."
        ),
        transformation_history=[
            TransformationStep(
                step="Seeded distributional draws from zones + OD table; behavioural params by rule.",
                by="data/generate_population.py",
                tag=MetricTag.simulated,
            ),
        ],
        format="JSON (records)",
        record_count=len(recs),
        kind="synthetic",
        tag=MetricTag.simulated,
        real_world_analogues=[
            "Census microdata / SPENSER-style synthetic populations",
            "Travel survey diaries (e.g. National Travel Survey)",
        ],
    )


def _buildings_card(d: Path, manifest: dict) -> DatasetCard:
    path = d / "buildings.geojson"
    obj = json.loads(path.read_text(encoding="utf-8"))
    recs = _geojson_records(obj)
    vars_, miss = _variable_cards(
        recs,
        descriptions={
            "z": "Zone id the building sits in.",
            "k": "Building kind (tower / midrise / lowrise / park).",
            "h": "Height today, t=0 (metres).",
            "dh": "Height change over the 10-year pipeline (metres).",
            "td": "Pipeline delivery time (years).",
            "t0": "Start time of the change (years).",
            "g": "Greenable/green flag.",
            "cbd": "Inside the cordon (1/0).",
            "d": "Distance to CBD centre (km).",
        },
        units={"h": "m", "dh": "m", "td": "years", "t0": "years", "d": "km"},
    )
    return DatasetCard(
        id="buildings",
        title="Auckland building footprints + 10-year height pipeline",
        publisher="GOV SIM synthetic generator (data/generate_buildings.py)",
        source_url="data/generate_buildings.py",
        retrieved_at=None,
        geographic_scope=manifest.get("geographic_scope", ""),
        spatial_resolution="individual footprint (LOD1)",
        units="mixed (see variables)",
        variables=vars_,
        license=manifest.get("license", ""),
        missingness=miss,
        revision=_content_revision(path),
        confidence="3D scene geometry; heights/pipeline are Simulated design assumptions.",
        transformation_history=[
            TransformationStep(
                step="Per-zone footprint + height allocation with transit-linked growth pipeline.",
                by="data/generate_buildings.py",
                tag=MetricTag.simulated,
            ),
        ],
        format="GeoJSON",
        record_count=len(recs),
        kind="synthetic",
        tag=MetricTag.simulated,
        real_world_analogues=["3DCityDB / CityGML LOD1 building models"],
    )


def _baseline_params_card() -> DatasetCard:
    """The assumption-set powering the mode-choice core (SPEC §4/§26)."""
    from ..baseline.params import DEFAULT_PARAMS

    keys = [k for k in vars(DEFAULT_PARAMS)] if hasattr(DEFAULT_PARAMS, "__dict__") else []
    vars_ = [
        VariableCard(
            name=k,
            dtype=_infer_dtype(getattr(DEFAULT_PARAMS, k)),
            unit="",
            description="Documented mode-choice model constant (auditable, human-correctable).",
            missing_pct=0.0,
        )
        for k in keys
    ]
    return DatasetCard(
        id="baseline_params",
        title="Baseline mode-choice modelling assumptions",
        publisher="GOV SIM engine (backend/app/baseline/params.py)",
        source_url="backend/app/baseline/params.py",
        retrieved_at=None,
        geographic_scope="model-wide (not geographic)",
        spatial_resolution="n/a",
        units="mixed (see variables)",
        variables=vars_,
        license="project code",
        missingness=0.0,
        revision="live:DEFAULT_PARAMS",
        confidence="Estimated transparent constants; each is auditable and correctable (§26).",
        transformation_history=[
            TransformationStep(
                step="Hand-set, documented constants read live at request time.",
                by="backend/app/baseline/params.py",
                tag=MetricTag.estimated,
            ),
        ],
        format="Python dataclass (introspected)",
        record_count=len(vars_),
        kind="assumption-set",
        tag=MetricTag.estimated,
        real_world_analogues=["Published transport-appraisal parameter books (e.g. WebTAG)"],
    )


# ---------------------------------------------------------------------------
# Format support & harmonisation pipeline (honest about what actually runs)
# ---------------------------------------------------------------------------


def _format_support() -> list[FormatSupport]:
    native = "Read directly by the engine in this build."
    ready = "Schema/loader contract fits; no live feed wired for the synthetic demo."
    declared = "Part of the §4 ingestion contract; not exercised in the demo."
    return [
        FormatSupport(format="JSON", status="native", note=native),
        FormatSupport(format="GeoJSON / geospatial files", status="native", note=native),
        FormatSupport(format="CSV", status="adapter-ready", note=ready),
        FormatSupport(format="XLSX", status="adapter-ready", note=ready),
        FormatSupport(format="GTFS transit feeds", status="declared", note=declared),
        FormatSupport(format="Government / open-data APIs", status="declared", note=declared),
        FormatSupport(format="Historical census tables", status="declared", note=declared),
        FormatSupport(format="Economic time series", status="declared", note=declared),
        FormatSupport(format="Public budget data", status="declared", note=declared),
        FormatSupport(format="Parliamentary records / Hansard", status="declared", note=declared),
        FormatSupport(format="Election results", status="declared", note=declared),
        FormatSupport(format="Public consultation data", status="declared", note=declared),
        FormatSupport(format="Historical policy evaluations", status="declared", note=declared),
        FormatSupport(format="Survey data", status="declared", note=declared),
        FormatSupport(format="Environmental measurements", status="declared", note=declared),
        FormatSupport(format="Anonymised administrative datasets", status="declared", note=declared),
    ]


def _harmonisation() -> list[HarmonisationStep]:
    return [
        HarmonisationStep(
            step="geographic joins",
            implemented=True,
            where="All layers key on `zone_id` (zones ↔ roads from/to ↔ od origin/destination ↔ "
            "population home/work); the spatial layer builds the directed graph from these joins.",
        ),
        HarmonisationStep(
            step="schema mapping",
            implemented=True,
            where="backend/app/dataset.py normalises raw GeoJSON properties / JSON records into "
            "typed accessors (zone_index, population_agents, …) consumed everywhere.",
        ),
        HarmonisationStep(
            step="unit normalisation",
            implemented=True,
            where="The mode-choice core converts money↔minutes via `money_to_minutes`; speeds "
            "(km/h), capacities (veh/hr) and CO₂ (kg/km) carry explicit units end-to-end.",
        ),
        HarmonisationStep(
            step="population weighting",
            implemented=True,
            where="The spatial/microsim layers expand the ~8k sampled agents to city scale by a "
            "representation factor read live from the OD totals (≈18×), so sample stats match scale.",
        ),
        HarmonisationStep(
            step="provenance tracking",
            implemented=True,
            where="This fabric + the §32 reproducibility manifest pin each dataset by a sha256 of "
            "its bytes; every downstream metric carries a MetricTag back to source.",
        ),
        HarmonisationStep(
            step="deduplication",
            implemented=True,
            where="OD flows are unique per (origin, destination); zone/link ids are unique keys.",
            note="Trivially satisfied by construction on synthetic data.",
        ),
        HarmonisationStep(
            step="missing-data treatment",
            implemented=True,
            where="The gravity model floors sparse pairs at `min_trips`; generated fields are "
            "complete by construction (this fabric measures 0% missingness live).",
            note="No imputation of *real* gaps is needed because no real feed is ingested.",
        ),
        HarmonisationStep(
            step="time alignment",
            implemented=False,
            where="N/A — a single base-year snapshot is ingested. The §7.2 time-series layer "
            "*synthesises* a monthly history from this snapshot rather than aligning real series.",
        ),
        HarmonisationStep(
            step="inflation adjustment",
            implemented=False,
            where="N/A — single base-year nominal money; no multi-year price series is ingested.",
        ),
        HarmonisationStep(
            step="outlier detection",
            implemented=False,
            where="N/A — data is deterministically generated within bounded rules, so there are no "
            "measurement outliers to screen. A real feed would gain this stage.",
        ),
    ]


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build_data_fabric() -> DataFabric:
    """Assemble the §4 Data Fabric manifest by reading the real files on disk."""
    d = data_dir()
    manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))

    datasets: list[DatasetCard] = [
        _zones_card(d, manifest),
        _roads_card(d, manifest),
        _od_card(d, manifest),
        _population_card(d),
        _baseline_params_card(),
    ]
    # buildings.geojson is optional (large, generated separately) — include if present.
    if (d / "buildings.geojson").exists():
        datasets.insert(4, _buildings_card(d, manifest))

    fmt = _format_support()
    harm = _harmonisation()
    counts = {
        "datasets": len(datasets),
        "synthetic": sum(1 for x in datasets if x.kind == "synthetic"),
        "assumption_sets": sum(1 for x in datasets if x.kind == "assumption-set"),
        "records_total": sum(x.record_count for x in datasets if x.kind == "synthetic"),
        "formats_native": sum(1 for f in fmt if f.status == "native"),
        "harmonisation_implemented": sum(1 for h in harm if h.implemented),
        "harmonisation_total": len(harm),
    }
    return DataFabric(
        app_version=settings.version,
        datasets=datasets,
        format_support=fmt,
        harmonisation=harm,
        counts=counts,
    )

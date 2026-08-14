"""Pydantic schemas for the spatial traffic-assignment report (SPEC §7.7)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from ..baseline.schema import MetricTag


class NetworkState(BaseModel):
    """Aggregate network performance for one world (peak hour)."""

    world: str = Field(description="'A' baseline or 'B' policy.")
    total_vehicle_hours: float = Field(description="Σ arc flow × congested time (veh-hr/peak-hr).")
    mean_vc: float = Field(description="Flow-weighted mean volume/capacity ratio.")
    max_vc: float = Field(description="Worst arc volume/capacity ratio.")
    congested_arcs: int = Field(description="Arcs with v/c ≥ 0.9.")
    overcapacity_arcs: int = Field(description="Arcs with v/c ≥ 1.0 (bottlenecks).")
    mean_speed_kmh: float = Field(description="Length-weighted mean congested speed.")
    cordon_inflow_veh_per_hr: float = Field(description="Peak vehicles entering the CBD cordon.")
    total_vehicle_km: float = Field(description="Σ arc flow × length (veh-km/peak-hr).")


class ArcLoad(BaseModel):
    """Per-arc load in both worlds (for notable/cordon/bottleneck arcs)."""

    arc_id: str
    from_zone: str
    to_zone: str
    road_class: str
    crosses_cordon: bool
    capacity_veh_per_hr: float
    flow_a: float
    flow_b: float
    vc_a: float
    vc_b: float
    speed_a_kmh: float
    speed_b_kmh: float
    delta_flow: float = Field(description="World B − World A peak vehicles.")


class ZoneChange(BaseModel):
    """A per-zone value in both worlds (accessibility or pollution)."""

    zone_id: str
    is_cbd: bool
    value_a: float
    value_b: float
    delta: float
    delta_pct: float


class AccessibilityReport(BaseModel):
    """Gravity job-accessibility by congested car network (SPEC §7.7)."""

    metric: str = Field(
        default="jobs_reachable_gravity",
        description="A_i = Σ_j jobs_j · exp(−decay · congested_time_ij).",
    )
    tag: MetricTag = MetricTag.simulated
    mean_a: float
    mean_b: float
    mean_delta_pct: float = Field(description="Population-weighted mean change (%).")
    top_gainers: list[ZoneChange] = Field(default_factory=list)
    top_losers: list[ZoneChange] = Field(default_factory=list)


class PollutionReport(BaseModel):
    """Road-CO₂ dispersion proxy by zone (SPEC §7.7)."""

    metric: str = Field(default="road_co2_kg_per_peak_hr")
    tag: MetricTag = MetricTag.simulated
    cbd_a: float = Field(description="Total dispersed CO₂ over CBD zones, World A.")
    cbd_b: float = Field(description="Total dispersed CO₂ over CBD zones, World B.")
    cbd_delta_pct: float
    network_total_a: float
    network_total_b: float
    biggest_drops: list[ZoneChange] = Field(default_factory=list)
    biggest_rises: list[ZoneChange] = Field(
        default_factory=list, description="Zones where traffic (and CO₂) is displaced upward."
    )
    displacement_note: str = ""


class SpatialReport(BaseModel):
    """Full spatial traffic-assignment report (SPEC §7.7)."""

    policy_id: str
    provenance: MetricTag = Field(
        MetricTag.simulated,
        description="Link flows/accessibility/pollution are produced by a "
        "deterministic assignment model → Simulated. No LLM (SPEC §34).",
    )
    note: str = Field(
        default=(
            "Peak-hour static traffic assignment (MSA user-equilibrium, BPR "
            "volume-delay) over the Auckland road network. Car demand comes from "
            "the same deterministic agent-based mode-choice model as /simulate — "
            "only the agents who still choose to drive are loaded onto the "
            "network. No LLM produces any number (SPEC §34)."
        )
    )
    peak_hour_car_trips_a: int = Field(description="Peak-hour car person-trips, World A.")
    peak_hour_car_trips_b: int = Field(description="Peak-hour car person-trips, World B.")
    world_a: NetworkState
    world_b: NetworkState
    cordon_inflow_delta_pct: float
    vehicle_hours_delta_pct: float
    notable_arcs: list[ArcLoad] = Field(default_factory=list)
    bottlenecks_a: list[ArcLoad] = Field(default_factory=list)
    bottlenecks_b: list[ArcLoad] = Field(default_factory=list)
    accessibility: AccessibilityReport
    pollution: PollutionReport
    params: dict = Field(default_factory=dict, description="Spatial assumptions used (auditable).")
    not_modelled: list[str] = Field(default_factory=list)

"""Spatial traffic-assignment model (SPEC §7.7).

Ties the deterministic agent-based mode-choice model to an explicit geography.
The pipeline is:

1. **Demand** — run the same mode-choice model as ``/simulate`` over every
   synthetic commuter (World A with :func:`choose_mode`, World B with
   :func:`choose_mode_policy`). Each commuter who *still chooses to drive*
   contributes their home→work trip to a peak-hour origin→destination vehicle
   table (persons → vehicles via occupancy and a peak-hour concentration).
2. **Assignment** — load that demand onto the Auckland road network and solve an
   approximate static user equilibrium (MSA + BPR), so drivers re-route around
   congestion. This is the spatial effect the aggregate ABM cannot see.
3. **Read-out** — congested link flows / speeds, cordon inflow, network vehicle-
   hours, gravity **job accessibility** by congested car time, and a per-zone
   **road-CO₂ dispersion proxy** — each as World A vs World B vs Δ.

Every number is Simulated and produced deterministically — no LLM (SPEC §34).
The spatial assumptions (peak-hour share, occupancy, BPR α/β, accessibility
decay, dispersion smoothing) are documented Estimated inputs in
:mod:`app.spatial.params`.
"""

from __future__ import annotations

from .. import dataset
from ..baseline.model import CAR, choose_mode
from ..baseline.params import DEFAULT_PARAMS, BaselineParams
from ..policy.dsl import PolicyDSL
from ..simulation.levers import (
    DEFAULT_SIM_PARAMS,
    PolicyLevers,
    SimParams,
    derive_levers,
)
from ..simulation.model import choose_mode_policy
from .assignment import AssignmentResult, assign
from .network import Network
from .params import DEFAULT_SPATIAL_PARAMS, SpatialParams
from .schema import (
    AccessibilityReport,
    ArcLoad,
    NetworkState,
    PollutionReport,
    SpatialReport,
    ZoneChange,
)


def _round(x: float, d: int = 2) -> float:
    return round(float(x), d)


def _pct_change(a: float, b: float) -> float:
    if a == 0:
        return 0.0
    return _round(100.0 * (b - a) / abs(a), 1)


def _representation_factor() -> float:
    """How many real commuters each sampled agent stands for.

    The synthetic population (~8k agents) is a *sample* of the full commute-flow
    table (``od_pairs.json`` ≈ 145k one-way home→work trips), whereas the road
    ``capacity_veh_per_hr`` values are real-city scale. To make peak-hour link
    volumes comparable with capacities, each sampled car trip is expanded by this
    factor. Derived live from the dataset so it cannot drift; a documented,
    auditable scaling assumption (Estimated).
    """
    od = dataset.load_od_pairs()
    total = sum(float(p.get("daily_person_trips", 0.0)) for p in od.get("pairs", []))
    n = len(dataset.population_agents())
    return total / n if n else 1.0


def _car_demand(
    agents: list[dict],
    policy_levers: PolicyLevers | None,
    cbd_zone_ids: set[str],
    params: BaselineParams,
    spatial: SpatialParams,
    rep_factor: float,
) -> tuple[dict[tuple[str, str], float], int]:
    """Peak-hour vehicle OD table + peak-hour car person-trip count for one world.

    ``policy_levers`` is ``None`` for World A (baseline mode choice); when supplied
    it selects the policy mode-choice model (World B). Sample car trips are
    expanded to city scale by ``rep_factor`` (see :func:`_representation_factor`).
    """
    persons: dict[tuple[str, str], float] = {}
    car_agents = 0
    for a in agents:
        if policy_levers is None:
            mode = choose_mode(a, params)
        else:
            mode = choose_mode_policy(a, policy_levers, cbd_zone_ids, params)
        if mode != CAR:
            continue
        car_agents += 1
        key = (a["home_zone"], a["work_zone"])
        persons[key] = persons.get(key, 0.0) + 1.0

    # sample persons → city-scale peak-hour vehicles: expand to city scale,
    # concentrate into the busiest hour, then divide by average occupancy.
    veh_factor = rep_factor * spatial.peak_hour_share / max(0.1, spatial.car_occupancy)
    demand = {k: v * veh_factor for k, v in persons.items()}
    peak_person_trips = int(round(car_agents * rep_factor * spatial.peak_hour_share))
    return demand, peak_person_trips


def _network_state(world: str, net: Network, res: AssignmentResult, cbd: set[str]) -> NetworkState:
    total_veh_hours = sum(res.flow[i] * res.time_min[i] / 60.0 for i in range(len(net.arcs)))
    total_veh_km = sum(res.flow[i] * net.arcs[i].length_km for i in range(len(net.arcs)))
    flow_sum = sum(res.flow) or 1.0
    mean_vc = sum(res.vc[i] * res.flow[i] for i in range(len(net.arcs))) / flow_sum
    len_sum = sum(net.arcs[i].length_km * res.flow[i] for i in range(len(net.arcs))) or 1.0
    mean_speed = sum(res.speed_kmh[i] * net.arcs[i].length_km * res.flow[i] for i in range(len(net.arcs))) / len_sum
    cordon_inflow = sum(
        res.flow[i]
        for i, arc in enumerate(net.arcs)
        if arc.crosses_cordon and arc.v in cbd
    )
    return NetworkState(
        world=world,
        total_vehicle_hours=_round(total_veh_hours, 1),
        mean_vc=_round(mean_vc, 3),
        max_vc=_round(max(res.vc) if res.vc else 0.0, 3),
        congested_arcs=sum(1 for v in res.vc if v >= 0.9),
        overcapacity_arcs=sum(1 for v in res.vc if v >= 1.0),
        mean_speed_kmh=_round(mean_speed, 1),
        cordon_inflow_veh_per_hr=_round(cordon_inflow, 1),
        total_vehicle_km=_round(total_veh_km, 1),
    )


def _accessibility(
    net: Network, res: AssignmentResult, spatial: SpatialParams
) -> dict[str, float]:
    """Gravity job accessibility per zone from congested car skims."""
    zi = dataset.zone_index()
    jobs = {z: float(p.get("jobs", 0.0)) for z, p in zi.items()}
    decay = spatial.access_decay_per_min
    access: dict[str, float] = {}
    for origin in net.nodes:
        skim = res.skims.get(origin, {origin: 0.0})
        total = 0.0
        for dest, j in jobs.items():
            t = skim.get(dest)
            if t is None:
                continue
            total += j * pow(2.718281828459045, -decay * t)
        access[origin] = total
    return access


def _pollution(net: Network, res: AssignmentResult, spatial: SpatialParams) -> dict[str, float]:
    """Per-zone road-CO₂ dispersion proxy from arc vehicle-km."""
    zi = dataset.zone_index()
    local = {z: 0.0 for z in zi}
    for i, arc in enumerate(net.arcs):
        co2 = res.flow[i] * arc.length_km * spatial.co2_kg_per_veh_km
        # Attribute an arc's emissions half to each endpoint zone.
        if arc.u in local:
            local[arc.u] += co2 / 2.0
        if arc.v in local:
            local[arc.v] += co2 / 2.0
    # Grid-neighbour dispersion smoothing.
    neigh: dict[str, set[str]] = {z: set() for z in zi}
    for arc in net.arcs:
        if arc.u in neigh and arc.v in zi:
            neigh[arc.u].add(arc.v)
    share = spatial.pollution_neighbour_share
    diffused: dict[str, float] = {}
    for z in zi:
        ns = neigh.get(z, set())
        nmean = sum(local[n] for n in ns) / len(ns) if ns else 0.0
        diffused[z] = (1.0 - share) * local[z] + share * nmean
    return diffused


def _zone_changes(a: dict[str, float], b: dict[str, float], cbd: set[str]) -> list[ZoneChange]:
    out: list[ZoneChange] = []
    for z in sorted(a):
        va, vb = a[z], b.get(z, 0.0)
        out.append(
            ZoneChange(
                zone_id=z,
                is_cbd=z in cbd,
                value_a=_round(va, 2),
                value_b=_round(vb, 2),
                delta=_round(vb - va, 2),
                delta_pct=_pct_change(va, vb),
            )
        )
    return out


def _arc_loads(net: Network, ra: AssignmentResult, rb: AssignmentResult, idxs: list[int]) -> list[ArcLoad]:
    loads = []
    for i in idxs:
        arc = net.arcs[i]
        loads.append(
            ArcLoad(
                arc_id=arc.arc_id,
                from_zone=arc.u,
                to_zone=arc.v,
                road_class=arc.road_class,
                crosses_cordon=arc.crosses_cordon,
                capacity_veh_per_hr=_round(arc.capacity_veh_per_hr, 1),
                flow_a=_round(ra.flow[i], 1),
                flow_b=_round(rb.flow[i], 1),
                vc_a=_round(ra.vc[i], 3),
                vc_b=_round(rb.vc[i], 3),
                speed_a_kmh=_round(ra.speed_kmh[i], 1),
                speed_b_kmh=_round(rb.speed_kmh[i], 1),
                delta_flow=_round(rb.flow[i] - ra.flow[i], 1),
            )
        )
    return loads


def build_spatial_report(
    policy: PolicyDSL,
    params: BaselineParams = DEFAULT_PARAMS,
    sim: SimParams = DEFAULT_SIM_PARAMS,
    spatial: SpatialParams = DEFAULT_SPATIAL_PARAMS,
) -> SpatialReport:
    """Run the spatial traffic-assignment layer for ``policy`` (SPEC §7.7)."""
    agents = dataset.population_agents()
    cbd = dataset.cbd_zone_ids()
    net = Network.from_dataset()

    # --- Demand for both worlds from the same mode-choice model ------------
    rep = _representation_factor()
    demand_a, car_trips_a = _car_demand(agents, None, cbd, params, spatial, rep)
    levers = derive_levers(policy, params=params, sim=sim)
    demand_b, car_trips_b = _car_demand(agents, levers, cbd, params, spatial, rep)

    # --- Equilibrium assignment -------------------------------------------
    res_a = assign(net, demand_a, spatial)
    res_b = assign(net, demand_b, spatial)

    state_a = _network_state("A", net, res_a, cbd)
    state_b = _network_state("B", net, res_b, cbd)

    # --- Accessibility -----------------------------------------------------
    acc_a = _accessibility(net, res_a, spatial)
    acc_b = _accessibility(net, res_b, spatial)
    zi = dataset.zone_index()
    pop = {z: float(p.get("population", 0.0)) for z, p in zi.items()}
    pop_tot = sum(pop.values()) or 1.0
    mean_a = sum(acc_a[z] * pop[z] for z in acc_a) / pop_tot
    mean_b = sum(acc_b[z] * pop[z] for z in acc_b) / pop_tot
    acc_changes = _zone_changes(acc_a, acc_b, cbd)
    acc_sorted = sorted(acc_changes, key=lambda c: c.delta)
    accessibility = AccessibilityReport(
        mean_a=_round(mean_a, 1),
        mean_b=_round(mean_b, 1),
        mean_delta_pct=_pct_change(mean_a, mean_b),
        top_gainers=list(reversed(acc_sorted[-5:])),
        top_losers=acc_sorted[:5],
    )

    # --- Pollution proxy ---------------------------------------------------
    pol_a = _pollution(net, res_a, spatial)
    pol_b = _pollution(net, res_b, spatial)
    pol_changes = _zone_changes(pol_a, pol_b, cbd)
    pol_sorted = sorted(pol_changes, key=lambda c: c.delta)
    cbd_a = sum(pol_a[z] for z in cbd)
    cbd_b = sum(pol_b[z] for z in cbd)
    rises = [c for c in reversed(pol_sorted) if c.delta > 0][:5]
    displacement = (
        "Some traffic re-routes onto non-central roads; zones with rising CO₂ show "
        "where deterred cordon traffic is displaced."
        if rises
        else "No material upward displacement of road CO₂ detected outside the cordon."
    )
    pollution = PollutionReport(
        cbd_a=_round(cbd_a, 1),
        cbd_b=_round(cbd_b, 1),
        cbd_delta_pct=_pct_change(cbd_a, cbd_b),
        network_total_a=_round(sum(pol_a.values()), 1),
        network_total_b=_round(sum(pol_b.values()), 1),
        biggest_drops=pol_sorted[:5],
        biggest_rises=rises,
        displacement_note=displacement,
    )

    # --- Notable arcs + bottlenecks ---------------------------------------
    cordon_idxs = [i for i, arc in enumerate(net.arcs) if arc.crosses_cordon]
    # Top arcs by absolute flow change (biggest reroute effects), excluding dups.
    by_delta = sorted(
        range(len(net.arcs)), key=lambda i: abs(res_b.flow[i] - res_a.flow[i]), reverse=True
    )
    notable_idxs = list(dict.fromkeys(cordon_idxs + by_delta[:8]))
    notable = _arc_loads(net, res_a, res_b, notable_idxs)
    bottleneck_a = _arc_loads(net, res_a, res_b, [i for i in range(len(net.arcs)) if res_a.vc[i] >= 1.0][:10])
    bottleneck_b = _arc_loads(net, res_a, res_b, [i for i in range(len(net.arcs)) if res_b.vc[i] >= 1.0][:10])

    return SpatialReport(
        policy_id=policy.id,
        peak_hour_car_trips_a=car_trips_a,
        peak_hour_car_trips_b=car_trips_b,
        world_a=state_a,
        world_b=state_b,
        cordon_inflow_delta_pct=_pct_change(
            state_a.cordon_inflow_veh_per_hr, state_b.cordon_inflow_veh_per_hr
        ),
        vehicle_hours_delta_pct=_pct_change(
            state_a.total_vehicle_hours, state_b.total_vehicle_hours
        ),
        notable_arcs=notable,
        bottlenecks_a=bottleneck_a,
        bottlenecks_b=bottleneck_b,
        accessibility=accessibility,
        pollution=pollution,
        params={**spatial.as_dict(), "representation_factor": _round(rep, 2)},
        not_modelled=[
            "Only the AM inbound commute peak is assigned; time-of-day dynamics, "
            "off-peak and non-commute (freight, shopping, leisure) trips are not.",
            "Peak-hour share, car occupancy, BPR α/β and accessibility decay are "
            "Estimated inputs, not calibrated to observed counts.",
            "Static (within-day) equilibrium: departure-time choice and day-to-day "
            "learning are not modelled.",
            "Pedestrianisation is applied on the demand side (CBD-bound car trips "
            "drop); physical road closures / through-traffic rerouting across a "
            "closed core are not imposed on the graph.",
            "The CO₂ field is a crude neighbour-smoothed dispersion proxy, not a "
            "physical pollutant plume / air-quality model.",
            "Transit is not spatially assigned — only the road network is.",
        ],
    )

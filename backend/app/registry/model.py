"""Assemble the model registry by introspecting the live model parameters (SPEC §33).

The published assumption values are read straight from the dataclasses the
simulator actually uses (``DEFAULT_PARAMS``, ``DEFAULT_SIM_PARAMS``,
``DEFAULT_ADAPTATION``, ``OpinionParams``), so the manifest can never disagree
with the code. Everything here is deterministic and LLM-free (SPEC §34).
"""

from __future__ import annotations

from ..baseline.params import DEFAULT_PARAMS
from ..baseline.schema import MetricTag
from ..config import settings
from ..dynamics.params import DEFAULT_SD_PARAMS
from ..economy.params import DEFAULT_ECON_PARAMS
from ..opinion.params import OpinionParams
from ..simulation.levers import DEFAULT_SIM_PARAMS
from ..simulation.timeline import DEFAULT_ADAPTATION
from ..spatial.params import DEFAULT_SPATIAL_PARAMS
from ..timeseries.params import DEFAULT_TS_PARAMS
from .schema import (
    AssumptionRecord,
    DataSourceCard,
    GuardrailCheck,
    ModelCard,
    ModelRegistry,
)


def _rec(name: str, label: str, value, unit: str, source: str, tag: MetricTag) -> AssumptionRecord:
    return AssumptionRecord(
        name=name, label=label, value=value, unit=unit, source=source, tag=tag
    )


def _baseline_assumptions() -> list[AssumptionRecord]:
    p = DEFAULT_PARAMS
    est = MetricTag.estimated
    return [
        _rec("walk_max_km", "Max walkable one-way distance", p.walk_max_km, "km",
             "Trips longer than this are not walked", est),
        _rec("walk_speed_kmh", "Walking speed", p.walk_speed_kmh, "km/h", "Typical adult walk pace", est),
        _rec("car_speed_cbd_kmh", "Congested central car speed", p.car_speed_cbd_kmh, "km/h",
             "Central-area congested speed", est),
        _rec("car_speed_kmh", "Non-central car speed", p.car_speed_kmh, "km/h", "Arterial road speed", est),
        _rec("transit_speed_kmh", "Effective transit speed", p.transit_speed_kmh, "km/h",
             "Includes stops/dwell", est),
        _rec("car_overhead_min", "Car access/egress overhead", p.car_overhead_min, "min/trip",
             "Parking search + walk from parking", est),
        _rec("transit_overhead_min", "Transit access/egress overhead", p.transit_overhead_min, "min/trip",
             "Walk to stop + wait", est),
        _rec("car_cost_per_km", "Car marginal cost", p.car_cost_per_km, "currency/km",
             "Fuel + wear", est),
        _rec("transit_fare", "Flat transit fare", p.transit_fare, "currency/trip", "Baseline fare", est),
        _rec("money_to_minutes", "Value-of-time conversion", p.money_to_minutes, "min/currency",
             "Money disutility → minutes-equivalent, scaled by agent price sensitivity", est),
        _rec("trips_per_commuter_per_day", "Daily trips per commuter", p.trips_per_commuter_per_day,
             "trips", "Outbound + return", est),
        _rec("workdays_per_year", "Workdays per year", p.workdays_per_year, "days",
             "Annualisation factor", est),
        _rec("car_co2_kg_per_km", "Tailpipe CO₂ factor", p.car_co2_kg_per_km, "kg/veh-km",
             "Average petrol car; totals become Simulated once multiplied by modelled veh-km", est),
    ]


def _timeseries_assumptions() -> list[AssumptionRecord]:
    t = DEFAULT_TS_PARAMS
    est = MetricTag.estimated
    return [
        _rec("history_months", "Synthetic history length", t.history_months, "months",
             "Monthly pre-implementation history manufactured to fit (Simulated, anchored to ABM baseline)", est),
        _rec("season_period", "Seasonal period", t.season_period, "months", "Annual seasonality", est),
        _rec("trend_per_year", "Synthetic-history trend", t.trend_per_year, "relative/yr",
             "Mild demand drift of the synthetic history for volume metrics", est),
        _rec("seasonal_amplitude", "Synthetic seasonal amplitude", t.seasonal_amplitude, "relative",
             "Annual seasonal swing of the synthetic history (volumes)", est),
        _rec("ar1_phi", "Synthetic AR(1) persistence", t.ar1_phi, "coefficient",
             "Persistence of the synthetic-history noise", est),
        _rec("noise_rel_sigma", "Synthetic noise std", t.noise_rel_sigma, "relative",
             "Month-to-month wobble of the synthetic history (volumes)", est),
        _rec("share_damping", "Share-metric damping", t.share_damping, "relative",
             "Trend/seasonality/noise damping applied to %-share metrics", est),
        _rec("holdout_months", "Backtest holdout", t.holdout_months, "months",
             "Held-out tail for the out-of-sample MAPE backtest", est),
        _rec("min_rel_sigma", "Interval floor", t.min_rel_sigma, "relative",
             "Floor on residual std so a near-perfect fit still yields an honest band", est),
        _rec("seed", "History RNG seed", t.seed, "int", "Fixed seed → byte-reproducible history (SPEC §34)", est),
    ]


def _sim_assumptions() -> list[AssumptionRecord]:
    s = DEFAULT_SIM_PARAMS
    est = MetricTag.estimated
    return [
        _rec("charge_trips_per_day", "Charge amortisation trips", s.charge_trips_per_day, "trips",
             "Daily cordon charge spread across daily trips for per-one-way comparability", est),
        _rec("reinvest_max_fare_cut", "Max fare cut at full reinvestment", s.reinvest_max_fare_cut,
             "relative", "Transit fare reduction cap when 100% revenue → transit", est),
        _rec("reinvest_max_speed_gain", "Max speed uplift at full reinvestment", s.reinvest_max_speed_gain,
             "relative", "Transit effective-speed uplift cap when 100% revenue → transit", est),
        _rec("active_travel_max_speed_gain", "Max active-travel gain at full active-travel spend",
             s.active_travel_max_speed_gain, "relative",
             "Active-travel effective-speed and viable-range uplift cap when 100% revenue → walking/cycling (not derived from the £ amount)", est),
        _rec("lez_noncompliant_share", "LEZ non-compliant fleet share", s.lez_noncompliant_share,
             "share", "Fraction of the CBD-bound car fleet that pays the low-emission-zone charge", est),
        _rec("lez_clean_factor_ratio", "LEZ clean-vehicle CO₂ ratio", s.lez_clean_factor_ratio,
             "× baseline factor", "CO₂/km of a compliant replacement vehicle vs the baseline fleet factor", est),
        _rec("parking_levy_passthrough_share", "Parking-levy employer pass-through", s.parking_levy_passthrough_share,
             "share", "Fraction of a workplace parking levy passed from employer to commuter as a behavioural signal", est),
        _rec("transit_investment_intensity", "Transit-investment service intensity", s.transit_investment_intensity,
             "intensity", "Service uplift of a standalone transit investment as a fraction of the max fare-cut/speed-gain (not derived from the £ amount)", est),
        _rec("commute_inbound_peak_start", "Inbound commute peak start", s.commute_inbound_peak_start,
             "HH:MM", "Start of the AM inbound-commute peak used to score a charge's operating-hours coverage (peak-only vs all-day)", est),
        _rec("commute_inbound_peak_end", "Inbound commute peak end", s.commute_inbound_peak_end,
             "HH:MM", "End of the AM inbound-commute peak used to score a charge's operating-hours coverage (peak-only vs all-day)", est),
    ]


def _adaptation_assumptions() -> list[AssumptionRecord]:
    a = DEFAULT_ADAPTATION
    est = MetricTag.estimated
    return [
        _rec("behaviour_tau_months", "Behavioural substitution time-constant", a.behaviour_tau_months,
             "months", "How fast commuters re-choose mode after the charge/ban lands", est),
        _rec("transit_lag_months", "Transit capacity delivery lag", a.transit_lag_months, "months",
             "Delay before revenue-funded transit capacity appears", est),
        _rec("transit_tau_months", "Transit capacity ramp time-constant", a.transit_tau_months, "months",
             "Ramp of the revenue-funded transit uplift after the lag", est),
        _rec("uncertainty_base", "World-B band half-width at T0", a.uncertainty_base, "relative",
             "Starting uncertainty band for policy trajectories", est),
        _rec("uncertainty_slope_per_year", "Band widening per year", a.uncertainty_slope_per_year,
             "relative/yr", "Horizon-widening of the confidence band (SPEC §9)", est),
        _rec("uncertainty_cap", "Band half-width cap", a.uncertainty_cap, "relative",
             "Keeps a 10-year band interpretable", est),
    ]


def _opinion_assumptions() -> list[AssumptionRecord]:
    o = OpinionParams()
    est = MetricTag.estimated
    return [
        _rec("w_material", "Weight: own material impact", o.w_material, "weight",
             "How much a cohort's own travel-cost change drives its opinion", est),
        _rec("w_fairness", "Weight: perceived fairness", o.w_fairness, "weight",
             "Regressivity / exemptions / reinvestment perception weight", est),
        _rec("w_prior", "Weight: ideological prior", o.w_prior, "weight",
             "Income-band prior toward/against pricing interventions", est),
        _rec("opinion_sigma", "Opinion dispersion σ", o.opinion_sigma, "opinion units",
             "Spread mapping latent support → 6-bucket Likert distribution", est),
    ]


def _economy_assumptions() -> list[AssumptionRecord]:
    e = DEFAULT_ECON_PARAMS
    est = MetricTag.estimated
    return [
        _rec("local_consumption_mpc", "Local MPC out of withdrawn charge",
             e.local_consumption_mpc, "share",
             "Fraction of charged household spend that was local (leaves demand pre-recycling)", est),
        _rec("fiscal_multiplier", "Local fiscal multiplier on recycled revenue",
             e.fiscal_multiplier, "×", "Local expenditure multiplier on re-spent public revenue", est),
        _rec("revenue_local_share", "Local share of recycled revenue", e.revenue_local_share,
             "share", "Fraction of recycled revenue re-spent inside the local economy", est),
        _rec("pedestrianisation_retail_uplift", "Pedestrianisation retail-amenity uplift",
             e.pedestrianisation_retail_uplift, "relative",
             "CBD retail turnover uplift from pedestrianisation (literature, not agent-derived)", est),
        _rec("cbd_retail_spend_per_commuter_year", "CBD retail spend per commuter/yr",
             e.cbd_retail_spend_per_commuter_year, "currency/yr",
             "Scales commuter volume to central discretionary spend", est),
        _rec("cbd_trip_avoidance_fraction", "Deterred-trip avoidance fraction",
             e.cbd_trip_avoidance_fraction, "share",
             "Share of deterred CBD car trips foregone entirely vs mode-switched", est),
        _rec("freight_entry_share", "Freight share of cordon entries", e.freight_entry_share,
             "share", "Documented ratio — freight is not in the synthetic population", est),
        _rec("freight_cost_pass_through", "Freight cost pass-through", e.freight_cost_pass_through,
             "share", "Share of the freight charge passed to CBD business/customers", est),
    ]


def _dynamics_assumptions() -> list[AssumptionRecord]:
    d = DEFAULT_SD_PARAMS
    est = MetricTag.estimated
    return [
        _rec("behaviour_tau_months", "Demand-response time constant", d.behaviour_tau_months,
             "months", "Speed the transit-demand stock relaxes toward the charge's pull", est),
        _rec("capacity_programme_years", "Capacity programme scope",
             d.capacity_programme_years, "years",
             "Years of nominal-charge reinvestment the capacity plan is sized to cost", est),
        _rec("max_capacity_uplift", "Max funded capacity uplift", d.max_capacity_uplift,
             "fraction", "Peak-capacity uplift a fully-funded programme delivers", est),
        _rec("capacity_build_tau_months", "Capacity build time constant",
             d.capacity_build_tau_months, "months",
             "Delivery lag of capacity toward its funded target", est),
        _rec("support_tau_months", "Opinion stickiness", d.support_tau_months, "months",
             "Speed the support stock relaxes toward its target", est),
        _rec("crowding_penalty", "Crowding support penalty", d.crowding_penalty, "support/×",
             "Support lost per unit of sustained over-capacity crowding", est),
        _rec("political_threshold", "Political-response trigger", d.political_threshold,
             "net support", "Support level below which an amendment builds", est),
        _rec("patience_months", "Amendment patience", d.patience_months, "months",
             "Consecutive months below threshold before a charge cut is forced", est),
        _rec("charge_cut_factor", "Amendment charge cut", d.charge_cut_factor, "×",
             "Fraction the charge is cut to when an amendment fires", est),
    ]


def _spatial_assumptions() -> list[AssumptionRecord]:
    s = DEFAULT_SPATIAL_PARAMS
    est = MetricTag.estimated
    return [
        _rec("peak_hour_share", "Peak-hour share of commute trips", s.peak_hour_share,
             "share", "Fraction of a car commuter's inbound trip in the busiest hour", est),
        _rec("car_occupancy", "Car occupancy", s.car_occupancy, "persons/veh",
             "Persons per vehicle — converts person trips to vehicle trips", est),
        _rec("bpr_alpha", "BPR α", s.bpr_alpha, "coefficient",
             "US Bureau of Public Roads volume-delay coefficient", est),
        _rec("bpr_beta", "BPR β", s.bpr_beta, "exponent",
             "US Bureau of Public Roads volume-delay exponent", est),
        _rec("assignment_iterations", "MSA iterations", s.assignment_iterations, "iterations",
             "Method-of-Successive-Averages steps toward static user equilibrium", est),
        _rec("access_decay_per_min", "Accessibility impedance decay", s.access_decay_per_min,
             "1/min", "Gravity job-accessibility decay per minute of congested car time", est),
        _rec("pollution_neighbour_share", "Pollution dispersion smoothing",
             s.pollution_neighbour_share, "share",
             "Share of a zone's road CO₂ spread to grid neighbours (proxy, not a plume model)", est),
    ]


def _models() -> list[ModelCard]:
    sim = MetricTag.simulated
    est = MetricTag.estimated
    return [
        ModelCard(
            id="agent_based_mode_choice",
            name="Agent-based mode-choice model (World A baseline)",
            spec_sections=["§5", "§6", "§7.5"],
            layer="Agent-Based Layer (SPEC §7.5)",
            method=(
                "Each synthetic commuter minimises a generalized cost (in-vehicle "
                "time + access/egress overhead + money→minutes, scaled by the "
                "agent's price sensitivity) across feasible modes; choices are "
                "aggregated into mode share, traffic, transit and emissions."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["synthetic population", "baseline params", "geography (zones/CBD)"],
            outputs=["mode_share", "traffic.*", "transit.*", "emissions.*"],
            output_tag=sim,
            code="app.baseline.model",
            assumptions=_baseline_assumptions(),
        ),
        ModelCard(
            id="policy_world_b",
            name="Policy simulation (World B)",
            spec_sections=["§7.5", "§7.7"],
            layer="Agent-Based + Spatial Layer (SPEC §7.5/§7.7)",
            method=(
                "The compiled Policy DSL is mapped to numeric levers (cordon "
                "charge, car ban, transit reinvestment) by explicit rules, then "
                "the same mode-choice model is re-run to produce World B; effects "
                "are isolated as Δ(B−A)."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["compiled Policy DSL", "baseline params", "sim params"],
            outputs=["World B metrics", "Δ(B−A) per metric"],
            output_tag=sim,
            code="app.simulation.model / app.simulation.levers",
            assumptions=_sim_assumptions(),
        ),
        ModelCard(
            id="time_machine",
            name="Time Machine (staged adaptation timeline)",
            spec_sections=["§9", "§24"],
            layer="System Dynamics Layer (SPEC §7.6)",
            method=(
                "Interpolates between structural anchors via a fast behavioural "
                "substitution ramp and a lagged, revenue-funded transit capacity "
                "ramp, with a confidence band that widens monotonically with "
                "horizon (SPEC §9)."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["World A / World B anchors", "adaptation params"],
            outputs=["per-checkpoint trajectories", "widening confidence bands"],
            output_tag=sim,
            code="app.simulation.timeline",
            assumptions=_adaptation_assumptions(),
        ),
        ModelCard(
            id="uncertainty_monte_carlo",
            name="Uncertainty engine (Monte-Carlo elasticity sweep)",
            spec_sections=["§24"],
            layer="Ensemble / Uncertainty (SPEC §8/§24)",
            method=(
                "Triangular Monte-Carlo sampling over documented uncertain "
                "assumptions, re-running the deterministic model per sample → "
                "median + 50/80/95% intervals per checkpoint and a one-at-a-time "
                "sensitivity ranking of the most influential assumptions."
            ),
            determinism="stochastic (seeded)",
            produces_numbers=True,
            llm_role="none",
            inputs=["policy", "uncertain assumption ranges", "seed", "sample count"],
            outputs=["median + 50/80/95% intervals", "assumption sensitivity ranking"],
            output_tag=sim,
            code="app.uncertainty.engine",
            assumptions=[],
        ),
        ModelCard(
            id="cohort_opinion",
            name="Cohort opinion model (public reaction)",
            spec_sections=["§13"],
            layer="Public Reaction (SPEC §13)",
            method=(
                "Per cohort (income band × geography × mode): own material impact "
                "(generalized-cost Δ) + perceived fairness + ideological prior → a "
                "latent support score mapped to a 6-bucket Likert distribution."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["Δ generalized cost per cohort", "policy fairness structure"],
            outputs=["support distribution per cohort + overall"],
            output_tag=sim,
            code="app.opinion.model",
            assumptions=_opinion_assumptions(),
        ),
        ModelCard(
            id="opinion_diffusion",
            name="Opinion diffusion (Friedkin–Johnsen social network)",
            spec_sections=["§14"],
            layer="Social Network / Opinion Diffusion (SPEC §14)",
            method=(
                "A typed, row-stochastic influence graph over citizen cohorts and "
                "institutional actors runs a deterministic Friedkin–Johnsen "
                "diffusion; each actor drifts toward its neighbours' weighted "
                "opinion while staying partly anchored to its own conviction."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["cohort opinions (seed)", "actor priors", "influence matrix", "shocks"],
            outputs=["opinion trajectories", "salience/polarisation", "coalitions"],
            output_tag=sim,
            code="app.diffusion.model",
            assumptions=[],
        ),
        ModelCard(
            id="economic_spillover",
            name="Economic spillover layer (input-output / elasticities)",
            spec_sections=["§7.4"],
            layer="Economic Spillover Layer (SPEC §7.4)",
            method=(
                "Translates the deterministic mode-choice sim's Simulated physical "
                "outputs (cordon revenue, Δ CBD car commuters, Σ Δ commuter travel-"
                "minutes, freight-entry proxy) into local-economy channels via "
                "transparent input-output relationships and elasticities: charge "
                "transfer, revenue recycling (fiscal multiplier), CBD footfall, "
                "business logistics and commuter travel cost → a net partial-"
                "equilibrium estimate with a band. Physical drivers Simulated, the "
                "monetary translation Estimated."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["World A / World B mode-choice outputs", "economic coefficients"],
            outputs=["economic channels", "sector exposure", "net annual estimate + band"],
            output_tag=est,
            code="app.economy.model",
            assumptions=_economy_assumptions(),
        ),
        ModelCard(
            id="system_dynamics",
            name="System dynamics / recursive feedback loop",
            spec_sections=["§7.6", "§19"],
            layer="System Dynamics Layer (SPEC §7.6)",
            method=(
                "Integrates four coupled stocks (charge, transit demand, transit "
                "capacity, public support) month-by-month, closing the SPEC §19 "
                "loop: charge → mode shift → revenue → funded capacity, and "
                "sustained negative support → an endogenous amendment that cuts the "
                "charge → weaker effect → less revenue → renewed crowding. The "
                "magnitudes each stock chases are read from the deterministic ABM "
                "at the in-force charge (Simulated); the temporal coefficients "
                "coupling them are documented Estimated inputs."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["compiled Policy DSL", "ABM anchors per charge", "dynamics coefficients"],
            outputs=[
                "coupled stock trajectories",
                "structured feedback events",
                "closed- vs open-loop contrast",
            ],
            output_tag=sim,
            code="app.dynamics.model",
            assumptions=_dynamics_assumptions(),
        ),
        ModelCard(
            id="spatial_assignment",
            name="Spatial traffic-assignment layer",
            spec_sections=["§7.7"],
            layer="Spatial Layer (SPEC §7.7)",
            method=(
                "Loads the car demand from the deterministic mode-choice model onto "
                "the Auckland road network and solves an approximate static user "
                "equilibrium (Method of Successive Averages over all-or-nothing "
                "assignments, BPR volume-delay). Reads out congested link flows, "
                "cordon inflow, network vehicle-hours, gravity job accessibility by "
                "congested car time and a per-zone road-CO₂ dispersion proxy — each "
                "as World A vs World B. Sample demand is expanded to city scale by a "
                "representation factor read live from the OD table."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["road network", "OD car demand from mode-choice model", "spatial params"],
            outputs=[
                "congested link flows / speeds",
                "cordon inflow + network vehicle-hours",
                "job accessibility",
                "road-CO₂ dispersion proxy",
            ],
            output_tag=sim,
            code="app.spatial.model / app.spatial.assignment",
            assumptions=_spatial_assumptions(),
        ),
        ModelCard(
            id="microsimulation",
            name="Distributional microsimulation (who gains / who loses)",
            spec_sections=["§7.3"],
            layer="Microsimulation Layer (SPEC §7.3)",
            method=(
                "Computes each synthetic commuter's change in minimum generalized "
                "cost between World A and World B under the same deterministic mode-"
                "choice model as /simulate, plus the out-of-pocket charge they pay, "
                "and rolls the person-level welfare change up by income decile, "
                "household type, home neighbourhood and occupation → winners/losers, "
                "mean impact, and a charge-burden regressivity gradient. The welfare "
                "change is Simulated; the money-equivalent uses a documented "
                "Estimated population value-of-time."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["synthetic population (income/household/zone/occupation)", "policy levers"],
            outputs=[
                "winners / losers / unaffected",
                "impact by decile / household / geography / occupation",
                "charge-burden regressivity ratio",
            ],
            output_tag=sim,
            code="app.microsim.model",
            assumptions=[],
        ),
        ModelCard(
            id="citizen_view",
            name="Citizen View (single-household drill-down)",
            spec_sections=["§17", "§31"],
            layer="Microsimulation Layer (SPEC §7.3) — per-agent projection",
            method=(
                "Projects one synthetic household's commute time, monthly transport "
                "cost and policy support across the Time Machine. World-A and "
                "World-B states use the same deterministic mode-choice model as "
                "/simulate; support uses the same per-agent function as /public. The "
                "household is interpolated between three structural anchors (World A, "
                "behaviour-only World B, fully-adapted World B) on the same "
                "behaviour/transit-ramp curves as the aggregate timeline, so its "
                "worse-before-better arc and far-horizon values match the "
                "dashboard. Bands widen monotonically with the horizon (SPEC §9)."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["synthetic household record", "policy levers", "staged-adaptation curve"],
            outputs=[
                "per-household commute / transport-cost trajectory",
                "per-household policy support (SPEC §31 Agent State)",
                "deterministic 'why?' narrative",
            ],
            output_tag=sim,
            code="app.citizen.service",
            assumptions=[],
        ),
        ModelCard(
            id="business_view",
            name="Business View (single-firm drill-down)",
            spec_sections=["§17"],
            layer="Economic Spillover Layer (SPEC §7.4) — per-firm projection",
            method=(
                "Projects one synthetic firm's footfall, labour accessibility, "
                "deliveries, added cost and revenue proxy across the Time Machine. "
                "Labour accessibility is the commute generalized cost of the firm's "
                "own workers, computed with the same deterministic mode-choice model "
                "as /simulate; footfall / deliveries / cost / revenue reuse the same "
                "economic coefficients as /economy (spend-per-visit, freight "
                "pass-through, car-avoidance fraction, pedestrianisation uplift). "
                "Firms are the commercial buildings; jobs are allocated from zone "
                "totals by floor-space share. Metrics are interpolated between three "
                "structural anchors (World A, behaviour-only World B, fully-adapted "
                "World B) on the same adaptation curves as the aggregate timeline; "
                "bands widen monotonically with the horizon (SPEC §9)."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=[
                "synthetic building/firm record",
                "policy levers",
                "per-work-zone commuter aggregates",
                "economic-translation coefficients",
                "staged-adaptation curve",
            ],
            outputs=[
                "per-firm footfall / labour-accessibility / deliveries trajectory",
                "per-firm added cost + revenue proxy (Estimated)",
                "deterministic adaptation decisions + 'why?' narrative",
            ],
            output_tag=est,
            code="app.business.service",
            assumptions=[],
        ),
        ModelCard(
            id="policy_optimiser",
            name="Policy optimiser (grid search → Pareto set)",
            spec_sections=["§22"],
            layer="Policy Search (SPEC §22)",
            method=(
                "Grid-searches candidate interventions, simulates each with the "
                "deterministic World-B + cohort-opinion models, and builds a "
                "multi-objective Pareto frontier under the supplied constraints."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["objective", "constraints", "candidate grid"],
            outputs=["scored candidates", "Pareto frontier", "labelled picks"],
            output_tag=sim,
            code="app.optimiser.search",
            assumptions=[],
        ),
        ModelCard(
            id="parliament",
            name="Model Parliament (evidence-grounded debate)",
            spec_sections=["§11", "§12"],
            layer="Multi-Agent Institutional Layer (SPEC §18)",
            method=(
                "Persona agents deterministically select supporting evidence "
                "(metrics + event-ledger entries) and a stance; an LLM (when "
                "configured) only polishes the prose, with a deterministic "
                "template fallback. No agent invents a number."
            ),
            determinism="deterministic (prose optional LLM)",
            produces_numbers=False,
            llm_role="prose only — never numbers (SPEC §34)",
            inputs=["/simulate metrics", "event ledger"],
            outputs=["grounded arguments", "tally", "failure-mode register"],
            output_tag=est,
            code="app.parliament",
            assumptions=[],
        ),
        ModelCard(
            id="media",
            name="Simulated press room (archetype headlines)",
            spec_sections=["§15"],
            layer="Simulated Media (SPEC §15)",
            method=(
                "Archetype editorial lenses build headlines strictly from the "
                "event ledger + Δ metrics + opinion state; every artifact is "
                "labelled SIMULATED with a fictional outlet — no real bylines."
            ),
            determinism="deterministic (prose optional LLM)",
            produces_numbers=False,
            llm_role="prose only — labelled SIMULATED (SPEC §15/§34)",
            inputs=["event ledger", "Δ metrics", "opinion state"],
            outputs=["archetype headlines (Generated, labelled SIMULATED)"],
            output_tag=MetricTag.generated,
            code="app.media.generator",
            assumptions=[],
        ),
        ModelCard(
            id="historical_analogue",
            name="Historical analogue / causal layer",
            spec_sections=["§7.1", "§8"],
            layer="Historical Analogue / Causal Layer (SPEC §7.1)",
            method=(
                "Difference-in-differences read (treated cordon change − background "
                "control trend) over a fixed database of real congestion-pricing / "
                "access-restriction schemes (London, Stockholm, Singapore, Milan, "
                "Gothenburg, Oslo, Ghent, Madrid), transferred to the input policy by "
                "an auditable similarity score (intervention family, charge strength, "
                "revenue recycling, city context) and pooled by identification-weighted "
                "transferability into an estimate + widening confidence interval."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["policy DSL", "historical case database (illustrative, Observed)"],
            outputs=["estimated_effect_pct + CI (Estimated)", "per-case DiD effects (Observed)"],
            output_tag=MetricTag.estimated,
            code="app.analogues.model",
            assumptions=[],
        ),
        ModelCard(
            id="time_series",
            name="Structural time-series layer (World-A forecast)",
            spec_sections=["§7.2", "§8"],
            layer="Time-Series Layer (SPEC §7.2)",
            method=(
                "Fits a structural time-series model (OLS local-linear-trend + "
                "12-month seasonal dummies, AR(1) on the residuals) to a seeded "
                "synthetic monthly history anchored to the ABM baseline snapshot, "
                "and forecasts World A across the Time-Machine checkpoints. "
                "Prediction-interval variance is derived from the fit — regression "
                "mean-estimation variance (grows with the extrapolation distance) "
                "plus accumulated AR(1) innovation variance — so the band widens "
                "with horizon. The deterministic ABM Δ(B−A) then alters the "
                "baseline trajectory to give World B."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=[
                "compiled Policy DSL",
                "ABM baseline snapshot (anchor)",
                "ABM Δ(B−A) trajectory",
                "documented history/model assumptions",
            ],
            outputs=[
                "synthetic history (Simulated)",
                "World-A forecast + intervals (Estimated)",
                "World-B forecast (policy-shifted, Simulated)",
                "fit diagnostics + holdout backtest",
            ],
            output_tag=est,
            code="app.timeseries.model",
            assumptions=_timeseries_assumptions(),
        ),
        ModelCard(
            id="sensitivity_tornado",
            name="Global sensitivity tornado (one-at-a-time)",
            spec_sections=["§24", "§26"],
            layer="Ensemble / Uncertainty (SPEC §8/§24) — explainability (§26)",
            method=(
                "One-at-a-time sensitivity: each documented assumption (the same set "
                "the §24 Monte-Carlo engine sweeps) is pinned to its plausible low, "
                "then high, edge while the others stay at default, and the resulting "
                "swing in EVERY headline metric's policy effect Δ(B−A) is measured by "
                "re-running the deterministic pipeline. Per metric → a tornado; per "
                "assumption → a scale-free leverage score (mean share of each metric's "
                "total sensitivity). Deterministic, no sampling, no LLM."
            ),
            determinism="deterministic",
            produces_numbers=True,
            llm_role="none",
            inputs=["policy", "documented assumption ranges", "horizon"],
            outputs=[
                "per-metric tornado (assumption swings)",
                "global driver ranking",
                "honest not-modelled scope (interactions, likelihood)",
            ],
            output_tag=est,
            code="app.sensitivity.service",
            assumptions=[],
        ),
    ]


def _data_sources() -> list[DataSourceCard]:
    return [
        DataSourceCard(
            id="synthetic_population",
            name="Synthetic commuter population",
            kind="synthetic",
            description=(
                "Deterministically generated agents with home/work zones, income "
                "band and price sensitivity; a statistical stand-in, not real "
                "individuals (SPEC §6)."
            ),
            tag=MetricTag.simulated,
            used_by=["agent_based_mode_choice", "policy_world_b", "cohort_opinion"],
        ),
        DataSourceCard(
            id="baseline_params",
            name="Baseline modelling assumptions",
            kind="assumption-set",
            description=(
                "Transparent input constants (speeds, costs, overheads, CO₂ "
                "factor) parameterising the mode-choice model; each is auditable "
                "and human-correctable (SPEC §4/§26)."
            ),
            tag=MetricTag.estimated,
            used_by=["agent_based_mode_choice", "policy_world_b", "time_machine"],
        ),
        DataSourceCard(
            id="policy_dsl",
            name="Compiled Policy DSL",
            kind="assumption-set",
            description=(
                "Structured policy produced by the compiler; an LLM may structure "
                "the language but the numeric intervention fields are explicit and "
                "auditable (SPEC §3/§34)."
            ),
            tag=MetricTag.estimated,
            used_by=["policy_world_b", "policy_optimiser"],
        ),
    ]


def _guardrails() -> list[GuardrailCheck]:
    return [
        GuardrailCheck(
            id="no_llm_numbers",
            rule="LLMs never generate core numeric simulation effects.",
            enforced_by=(
                "All numeric models (baseline, world_b, timeline, uncertainty, "
                "opinion, diffusion, economic spillover, system dynamics, spatial "
                "assignment, microsimulation, optimiser) are pure deterministic/"
                "seeded code; LLM use "
                "is confined to prose (parliament, media) and language structuring "
                "(policy compiler)."
            ),
            holds=True,
        ),
        GuardrailCheck(
            id="provenance_tags",
            rule="Every metric is tagged Observed/Estimated/Simulated/Generated.",
            enforced_by=(
                "Metric/MetricSeries schemas carry a required MetricTag; model "
                "cards above declare each layer's output_tag."
            ),
            holds=True,
        ),
        GuardrailCheck(
            id="media_labelled",
            rule="Generated media is labelled SIMULATED.",
            enforced_by=(
                "The media generator stamps a SIMULATED banner and fictional "
                "outlet on every artifact; output_tag=Generated."
            ),
            holds=True,
        ),
        GuardrailCheck(
            id="widening_uncertainty",
            rule="Long-run uncertainty widens with horizon.",
            enforced_by=(
                "Timeline bands widen monotonically per year (uncertainty_slope_"
                "per_year) and the Monte-Carlo intervals fan out per checkpoint."
            ),
            holds=True,
        ),
        GuardrailCheck(
            id="reproducible",
            rule="Runs are reproducible / auditable.",
            enforced_by=(
                "Deterministic models return identical output for identical input; "
                "stochastic sweeps are seeded; every assumption is published here "
                "by live introspection."
            ),
            holds=True,
        ),
    ]


def build_registry() -> ModelRegistry:
    """Build the full transparency manifest (SPEC §33). Deterministic, no LLM."""
    models = _models()
    data_sources = _data_sources()
    guardrails = _guardrails()

    # Flat, de-duplicated assumption index across every model.
    seen: set[str] = set()
    index: list[AssumptionRecord] = []
    for m in models:
        for a in m.assumptions:
            if a.name in seen:
                continue
            seen.add(a.name)
            index.append(a)

    counts = {
        "models": len(models),
        "numeric_models": sum(1 for m in models if m.produces_numbers),
        "deterministic_models": sum(1 for m in models if m.determinism.startswith("deterministic")),
        "models_touching_numbers_with_llm": sum(1 for m in models if m.llm_touches_numbers),
        "documented_assumptions": len(index),
        "data_sources": len(data_sources),
        "guardrails_holding": sum(1 for g in guardrails if g.holds),
        "guardrails_total": len(guardrails),
    }

    return ModelRegistry(
        app_version=settings.version,
        models=models,
        data_sources=data_sources,
        guardrails=guardrails,
        assumption_index=index,
        counts=counts,
    )

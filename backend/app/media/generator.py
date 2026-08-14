"""Deterministic simulated-media generator (ROADMAP M6, SPEC §15).

Reads ONLY the event ledger, the Δ(B−A) outcome metrics and the cohort opinion
state, and emits archetype headlines at two horizons (Month 5, Year 2). Each
archetype applies a fixed editorial lens to the *same* structured facts, so the
coverage is plausible and varied without any real outlet, byline, or invented
quantity. Every artifact carries the SIMULATED banner (SPEC §15).

Guardrail (SPEC §34): headlines are built from the model's numbers via templates
— Generated prose over Simulated figures. No LLM and no fabricated event.
"""

from __future__ import annotations

from ..baseline.model import compute_baseline
from ..baseline.timeseries import build_timeseries
from ..opinion import PublicOpinion, compute_public_opinion
from ..policy.dsl import PolicyDSL
from ..simulation.compare import build_delta
from ..simulation.events import build_event_ledger
from ..simulation.schema import DeltaTimeSeries, EventLedger, LedgerEvent
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .schema import Headline, MediaArchetype, MediaResponse, MediaScenario

# Horizons SPEC §15 / UI §10 call out for simulated coverage.
_SCENARIO_HORIZONS: tuple[tuple[str, float], ...] = (
    ("Month 5", 5.0),
    ("Year 2", 24.0),
)

_OUTLET_LABELS = {
    MediaArchetype.public_broadcaster: "The National Broadcaster (SIMULATED)",
    MediaArchetype.business_press: "Business Daily (SIMULATED)",
    MediaArchetype.local_news: "The Auckland Courier (SIMULATED)",
    MediaArchetype.tabloid: "The Daily Pulse (SIMULATED)",
    MediaArchetype.environmental: "Clean City Review (SIMULATED)",
    MediaArchetype.industry: "Transport & Logistics Weekly (SIMULATED)",
}


class _HorizonState:
    """The structured facts available to the press at one horizon."""

    def __init__(
        self,
        month: float,
        delta: DeltaTimeSeries,
        ledger: EventLedger,
        opinion: PublicOpinion,
    ) -> None:
        self.month = month
        self.opinion = opinion
        # Nearest checkpoint index at or before this horizon.
        self.cp_idx = max(
            (i for i, cp in enumerate(delta.checkpoints) if cp.t_months <= month),
            default=0,
        )
        self.metric: dict[str, dict] = {}
        for s in delta.series:
            if s.points:
                p = s.points[self.cp_idx]
                self.metric[s.key] = {
                    "world_a": p.world_a,
                    "world_b": p.world_b,
                    "delta": p.delta,
                    "delta_pct": p.delta_pct,
                    "unit": s.unit,
                    "label": s.label,
                }
        # Events that have fired by this horizon.
        self.events: dict[str, LedgerEvent] = {
            e.type: e for e in ledger.events if e.scenario_month <= month
        }

    def m(self, key: str) -> dict | None:
        return self.metric.get(key)

    def ev(self, etype: str) -> LedgerEvent | None:
        return self.events.get(etype)


def _headline(
    archetype: MediaArchetype,
    headline: str,
    standfirst: str,
    angle: str,
    sentiment: str,
    refs: list[str],
) -> Headline:
    return Headline(
        archetype=archetype,
        outlet_label=_OUTLET_LABELS[archetype],
        headline=headline,
        standfirst=standfirst,
        angle=angle,
        sentiment=sentiment,
        cited_refs=refs,
    )


def _public_broadcaster(st: _HorizonState) -> Headline:
    cordon = st.ev("cordon_load")
    net = st.opinion.overall.net_support
    mood = "broad backing" if net > 0.1 else "a divided public" if net > -0.1 else "public resistance"
    cordon_m = st.m("traffic.vehicle_trips_into_cbd")
    if cordon and cordon_m and cordon_m["delta_pct"] is not None:
        head = f"City-centre traffic down {abs(cordon_m['delta_pct']):.0f}% as charge beds in"
        stand = f"Officials point to falling cordon traffic; polling shows {mood}."
        refs = [cordon.id, "opinion.net_support"]
    else:
        car = st.m("mode_share.car_pct")
        head = "Transport reforms show early effect, review finds"
        stand = f"Independent modelling reports a measured shift amid {mood}."
        refs = (["mode_share.car_pct"] if car else []) + ["opinion.net_support"]
    return _headline(
        MediaArchetype.public_broadcaster, head, stand,
        "Balanced public-interest reporting", "mixed", refs,
    )


def _business_press(st: _HorizonState) -> Headline:
    cordon = st.ev("cordon_load")
    cap = st.ev("transit_capacity")
    if cordon:
        head = "CBD traffic falls, but logistics operators warn of rising delivery costs"
        stand = (
            f"Cordon vehicle trips down to {st.m('traffic.vehicle_trips_into_cbd')['world_b']:.0f}/day; "
            "freight and last-mile operators flag detour and timing costs."
        )
        refs = [cordon.id, "traffic.vehicle_trips_into_cbd"]
    else:
        head = "Businesses weigh access costs against a quieter city centre"
        stand = "Firms call for clarity on exemptions and delivery windows."
        refs = ["traffic.vehicle_trips_into_cbd"]
    if cap:
        stand += " Employers watch transit reliability closely."
        refs.append(cap.id)
    return _headline(
        MediaArchetype.business_press, head, stand,
        "Commercial cost / access lens", "critical", refs,
    )


def _local_news(st: _HorizonState) -> Headline:
    cap = st.ev("transit_capacity")
    if cap:
        head = "Bus crowding emerges as central complaint months into transport reforms"
        stand = (
            f"Peak demand runs about {cap.affected_agents:,} trips over comfortable "
            "capacity; riders report squeeze at rush hour."
        )
        refs = [cap.id]
    else:
        boardings = st.m("transit.daily_transit_trips")
        head = "More neighbours are taking the bus — and noticing the difference"
        stand = (
            f"Daily boardings up to {boardings['world_b']:.0f} as commuters adjust."
            if boardings else "Commuters describe changing their daily routine."
        )
        refs = ["transit.daily_transit_trips"] if boardings else []
    return _headline(
        MediaArchetype.local_news, head, stand,
        "Lived-experience / community lens", "mixed", refs,
    )


def _tabloid(st: _HorizonState) -> Headline:
    opposed = st.opinion.overall.oppose + st.opinion.overall.strong_oppose
    head = "DRIVERS HAMMERED: new city charge hits pockets every single day"
    stand = (
        f"With {opposed:.0%} of the public opposed, critics call it a tax on getting to work."
    )
    refs = ["opinion.oppose", "opinion.strong_oppose"]
    return _headline(
        MediaArchetype.tabloid, head, stand,
        "Populist / emotive lens", "critical", refs,
    )


def _environmental(st: _HorizonState) -> Headline:
    emis = st.ev("emissions")
    m = st.m("emissions.daily_co2_tonnes")
    if emis:
        head = f"Commuter CO₂ falls {abs(m['delta_pct']):.0f}% under the new scheme"
        stand = (
            f"Daily commute emissions drop from {m['world_a']:.2f} to {m['world_b']:.2f} "
            "tonnes — a rare, measurable air-quality win."
        )
        refs = [emis.id, "emissions.daily_co2_tonnes"]
    else:
        head = "Modest emissions gains, but campaigners want the charge to go further"
        stand = "Air-quality groups welcome the direction while pressing for more."
        refs = ["emissions.daily_co2_tonnes"] if m else []
    return _headline(
        MediaArchetype.environmental, head, stand,
        "Climate / air-quality lens", "positive", refs,
    )


def _industry(st: _HorizonState) -> Headline:
    reinv = st.ev("transit_reinvestment")
    cap = st.ev("transit_capacity")
    if reinv:
        head = "Charge revenue funds bus capacity as ridership climbs"
        stand = "Operators report the reinvestment ramp landing; scheduling under review."
        refs = [reinv.id]
    elif cap:
        head = "Operators race to add capacity as demand outstrips the timetable"
        stand = "Network planners warn capacity must catch up with the modal shift."
        refs = [cap.id]
    else:
        head = "Transport sector eyes the reforms for network investment signals"
        stand = "Industry awaits detail on how revenue will be recycled."
        refs = ["transit.daily_transit_trips"]
    return _headline(
        MediaArchetype.industry, head, stand,
        "Operator / investment lens", "mixed", refs,
    )


_ARCHETYPE_BUILDERS = (
    _public_broadcaster,
    _business_press,
    _local_news,
    _tabloid,
    _environmental,
    _industry,
)


def build_media(
    policy: PolicyDSL,
    delta: DeltaTimeSeries,
    ledger: EventLedger,
    opinion: PublicOpinion,
) -> MediaResponse:
    """Build simulated media coverage from the run's ledger + metrics + opinion."""
    scenarios: list[MediaScenario] = []
    for label, month in _SCENARIO_HORIZONS:
        st = _HorizonState(month, delta, ledger, opinion)
        headlines = [build(st) for build in _ARCHETYPE_BUILDERS]
        scenarios.append(
            MediaScenario(label=label, scenario_month=month, headlines=headlines)
        )
    return MediaResponse(policy_id=policy.id, method="template", scenarios=scenarios)


def run_media(policy: PolicyDSL, shocks: Shocks | None = None) -> MediaResponse:
    """Run the simulation + opinion pipeline, then generate simulated coverage."""
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)
    b_ts = build_world_b_timeline(policy, baseline=base, params=params, trend=trend)
    delta = build_delta(base_ts, b_ts)
    ledger = build_event_ledger(policy, base, delta)
    opinion = compute_public_opinion(policy, params=params)
    return build_media(policy, delta, ledger, opinion)

"""Deterministic press-conference builder (SPEC §16).

Reads ONLY the Δ(B−A) metrics, the event ledger and the cohort opinion state,
then stages an opening statement plus five archetype journalist exchanges. Each
question and answer is grounded in a specific figure copied from the model, so
the scene is plausible and adversarial without any real outlet or invented
number. An optional LLM polishes prose; the template path (no key) is the default.
"""

from __future__ import annotations

from ..baseline.model import compute_baseline
from ..baseline.schema import Checkpoint
from ..baseline.timeseries import build_timeseries
from ..opinion import PublicOpinion, compute_public_opinion
from ..policy.dsl import PolicyDSL
from ..simulation.compare import build_delta
from ..simulation.events import build_event_ledger
from ..simulation.schema import DeltaTimeSeries, EventLedger, LedgerEvent
from ..simulation.shocks import Shocks, apply_shocks
from ..simulation.timeline import build_world_b_timeline
from .llm import PressLLMUnavailable, polish_prose
from .schema import (
    PressAnswer,
    PressConference,
    PressExchange,
    PressQuestion,
    ReporterArchetype,
)

_OUTLETS = {
    ReporterArchetype.public_broadcaster: ("The National Broadcaster (SIMULATED)", "Political editor"),
    ReporterArchetype.business_press: ("Business Daily (SIMULATED)", "Business correspondent"),
    ReporterArchetype.tabloid: ("The Daily Pulse (SIMULATED)", "News reporter"),
    ReporterArchetype.environmental: ("Clean City Review (SIMULATED)", "Environment correspondent"),
    ReporterArchetype.opposition_local: ("The Auckland Courier (SIMULATED)", "Local affairs reporter"),
}


class _HorizonState:
    """Structured facts available at one horizon (Δ metrics + ledger + opinion)."""

    def __init__(
        self,
        month: float,
        delta: DeltaTimeSeries,
        ledger: EventLedger,
        opinion: PublicOpinion,
        exemptions: list[str] | None = None,
    ) -> None:
        self.month = month
        self.opinion = opinion
        self.exemptions = list(exemptions or [])
        self.cp_idx = max(
            (i for i, cp in enumerate(delta.checkpoints) if cp.t_months <= month), default=0
        )
        self.checkpoint = delta.checkpoints[self.cp_idx]
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
        self.events: dict[str, LedgerEvent] = {
            e.type: e for e in ledger.events if e.scenario_month <= month
        }

    def m(self, key: str) -> dict | None:
        return self.metric.get(key)

    def ev(self, etype: str) -> LedgerEvent | None:
        return self.events.get(etype)


def _pct(v: float | None) -> str:
    return f"{abs(v):.0f}%" if v is not None else "a measurable amount"


# --------------------------------------------------------------------------- #
# Opening statement
# --------------------------------------------------------------------------- #
def _opening(st: _HorizonState) -> tuple[str, list[str]]:
    refs: list[str] = []
    parts = ["Thank you all for coming."]
    cordon = st.m("traffic.vehicle_trips_into_cbd")
    if cordon and cordon["delta_pct"] is not None and cordon["delta"] < 0:
        parts.append(
            f"Since the scheme began, vehicle trips into the city centre are down "
            f"{_pct(cordon['delta_pct'])}, from about {cordon['world_a']:.0f} to "
            f"{cordon['world_b']:.0f} a day."
        )
        refs.append("traffic.vehicle_trips_into_cbd")
    emis = st.m("emissions.daily_co2_tonnes")
    if emis and emis["delta"] < 0:
        parts.append(
            f"Daily commuter CO₂ has fallen {_pct(emis['delta_pct'])}, to "
            f"{emis['world_b']:.2f} tonnes."
        )
        refs.append("emissions.daily_co2_tonnes")
    reinv = st.ev("transit_reinvestment")
    if reinv:
        parts.append("Every unit of revenue is being reinvested into public transport.")
        refs.append(reinv.id)
    parts.append("We know there is more to do, and I'll take your questions.")
    return " ".join(parts), refs


# --------------------------------------------------------------------------- #
# Question / answer builders (one per archetype)
# --------------------------------------------------------------------------- #
def _public_broadcaster(st: _HorizonState) -> PressExchange:
    car = st.m("mode_share.car_pct")
    q_refs = ["mode_share.car_pct"] if car else []
    net = st.opinion.overall.net_support
    if car:
        question = (
            f"The car share of commutes has moved from {car['world_a']:.0f}% to "
            f"{car['world_b']:.0f}%. Is that the scale of change you promised, or is "
            "this scheme underdelivering?"
        )
    else:
        question = "Can you show any hard evidence this scheme is actually working yet?"
    q = PressQuestion(
        archetype=ReporterArchetype.public_broadcaster,
        outlet_label=_OUTLETS[ReporterArchetype.public_broadcaster][0],
        reporter=_OUTLETS[ReporterArchetype.public_broadcaster][1],
        question=question,
        angle="Is it working? Public-interest scrutiny.",
        hostility="neutral",
        cited_refs=q_refs,
    )
    cordon = st.m("traffic.vehicle_trips_into_cbd")
    a_refs = list(q_refs)
    ans = ["The evidence is early but consistent."]
    if cordon and cordon["delta"] < 0:
        ans.append(
            f"Central traffic is down {_pct(cordon['delta_pct'])} — that is real, measured change."
        )
        a_refs.append("traffic.vehicle_trips_into_cbd")
    ans.append(
        "We always said behaviour shifts first and transit capacity follows the revenue; "
        "that is exactly the sequence we are seeing."
    )
    a = PressAnswer(stance="defends", answer=" ".join(ans), cited_refs=a_refs)
    return PressExchange(question=q, answer=a)


def _business_press(st: _HorizonState) -> PressExchange:
    cordon = st.m("traffic.vehicle_trips_into_cbd")
    q_refs = ["traffic.vehicle_trips_into_cbd"] if cordon else []
    question = (
        "Deliveries and trades still need to reach the centre. What is your answer to "
        "operators telling us the charge is just another cost passed on to customers?"
    )
    q = PressQuestion(
        archetype=ReporterArchetype.business_press,
        outlet_label=_OUTLETS[ReporterArchetype.business_press][0],
        reporter=_OUTLETS[ReporterArchetype.business_press][1],
        question=question,
        angle="Commercial access / cost pass-through.",
        hostility="hostile",
        cited_refs=q_refs,
    )
    cap = st.ev("transit_capacity")
    a_refs = list(q_refs)
    ans = [
        "A less congested centre is itself a productivity gain — faster, more reliable "
        "journeys for the vehicles that genuinely need to be there."
    ]
    if cordon and cordon["delta"] < 0:
        ans.append(f"Trips into the cordon are down to about {cordon['world_b']:.0f} a day.")
    ans.append(
        "We are keeping exemptions and delivery windows under review and will act on the data."
    )
    stance = "acknowledges" if cap else "defends"
    a = PressAnswer(stance=stance, answer=" ".join(ans), cited_refs=a_refs)
    return PressExchange(question=q, answer=a)


def _tabloid(st: _HorizonState) -> PressExchange:
    opposed = st.opinion.overall.oppose + st.opinion.overall.strong_oppose
    q_refs = ["opinion.oppose", "opinion.strong_oppose"]
    question = (
        f"{opposed:.0%} of the public are against this. Ordinary drivers are being "
        "hammered every single day just to get to work — isn't this simply a tax on "
        "working people?"
    )
    q = PressQuestion(
        archetype=ReporterArchetype.tabloid,
        outlet_label=_OUTLETS[ReporterArchetype.tabloid][0],
        reporter=_OUTLETS[ReporterArchetype.tabloid][1],
        question=question,
        angle="Populist 'war on drivers'.",
        hostility="hostile",
        cited_refs=q_refs,
    )
    a_refs = list(q_refs)
    ans = ["I understand the frustration, and no one likes a new charge."]
    reinv = st.ev("transit_reinvestment")
    if reinv:
        ans.append(
            "But the money does not disappear — it funds cheaper, faster public transport "
            "that most commuters use."
        )
        a_refs.append(reinv.id)
    ans.append(
        "The alternative — doing nothing about congestion and air quality — has a cost too, "
        "and it falls on the same working people."
    )
    a = PressAnswer(stance="rebuts", answer=" ".join(ans), cited_refs=a_refs)
    return PressExchange(question=q, answer=a)


def _environmental(st: _HorizonState) -> PressExchange:
    emis = st.m("emissions.daily_co2_tonnes")
    q_refs = ["emissions.daily_co2_tonnes"] if emis else []
    if emis and emis["delta"] < 0:
        question = (
            f"A {_pct(emis['delta_pct'])} cut in commuter CO₂ is welcome, but it is nowhere "
            "near what the climate targets demand. Will you widen the cordon or raise the "
            "charge to go further?"
        )
    else:
        question = "Where are the emissions savings you promised, and when will we see them?"
    q = PressQuestion(
        archetype=ReporterArchetype.environmental,
        outlet_label=_OUTLETS[ReporterArchetype.environmental][0],
        reporter=_OUTLETS[ReporterArchetype.environmental][1],
        question=question,
        angle="Not ambitious enough on climate.",
        hostility="neutral",
        cited_refs=q_refs,
    )
    a_refs = list(q_refs)
    ans = []
    if emis and emis["delta"] < 0:
        ans.append(
            f"Cutting daily commute emissions to {emis['world_b']:.2f} tonnes is a genuine, "
            "measurable air-quality win."
        )
    ans.append(
        "We designed this to be expandable. We will let the data on this phase guide any "
        "decision to widen the zone or adjust the charge — we will not commit to numbers we "
        "cannot yet stand behind."
    )
    a = PressAnswer(stance="commits", answer=" ".join(ans), cited_refs=a_refs)
    return PressExchange(question=q, answer=a)


def _opposition_local(st: _HorizonState) -> PressExchange:
    # Equity angle: worst-hit cohort = highest mean_material_impact (+ = worse off).
    worst = None
    for c in st.opinion.cohorts:
        if worst is None or c.mean_material_impact > worst.mean_material_impact:
            worst = c
    q_refs = ["opinion.cohorts"]
    if worst is not None:
        label = f"{worst.income_band}-income {worst.travel_mode}"
        question = (
            f"For {label} commuters this lands as a real hit to the household budget. "
            "How is charging the people with the least fair?"
        )
    else:
        question = "How can you call this fair to lower-income households?"
    q = PressQuestion(
        archetype=ReporterArchetype.opposition_local,
        outlet_label=_OUTLETS[ReporterArchetype.opposition_local][0],
        reporter=_OUTLETS[ReporterArchetype.opposition_local][1],
        question=question,
        angle="Distributional fairness / who pays.",
        hostility="hostile",
        cited_refs=q_refs,
    )
    a_refs = list(q_refs)
    ans = ["Fairness is central to this, and we do not pretend the burden is identical for everyone."]
    # Reflect whether the policy actually exempts low income / reinvests.
    if any("low" in e.lower() and "income" in e.lower() for e in st.exemptions):
        ans.append("That is exactly why lower-income commuters are exempt from the charge.")
    reinv = st.ev("transit_reinvestment")
    if reinv:
        ans.append(
            "And because revenue funds cheaper, better public transport, the households that "
            "rely on it most see the direct benefit."
        )
        a_refs.append(reinv.id)
    ans.append("We will keep publishing the distributional numbers so this can be judged openly.")
    a = PressAnswer(stance="defends", answer=" ".join(ans), cited_refs=a_refs)
    return PressExchange(question=q, answer=a)


_BUILDERS = (
    _public_broadcaster,
    _business_press,
    _tabloid,
    _environmental,
    _opposition_local,
)


def _mood(opinion: PublicOpinion) -> str:
    net = opinion.overall.net_support
    if net > 0.1:
        return "The room senses broad public backing."
    if net > -0.1:
        return "The public is visibly divided."
    return "There is clear public resistance to manage."


def build_press_conference(
    policy: PolicyDSL,
    delta: DeltaTimeSeries,
    ledger: EventLedger,
    opinion: PublicOpinion,
    horizon_months: float = 5.0,
    use_llm: bool = True,
) -> PressConference:
    """Build the press conference from the run's Δ metrics + ledger + opinion."""
    st = _HorizonState(
        horizon_months, delta, ledger, opinion, exemptions=policy.exemptions
    )
    opening, opening_refs = _opening(st)
    exchanges = [b(st) for b in _BUILDERS]

    method = "template"
    if use_llm:
        try:
            opening = polish_prose("opening statement by a government spokesperson", opening)
            for ex in exchanges:
                ex.answer.answer = polish_prose(
                    f"spokesperson reply ({ex.answer.stance})", ex.answer.answer
                )
            method = "llm"
        except PressLLMUnavailable:
            method = "template"

    cp = st.checkpoint
    return PressConference(
        policy_id=policy.id,
        method=method,
        horizon=Checkpoint(label=cp.label, t_months=cp.t_months, t_years=cp.t_years),
        opening_statement=opening,
        opening_refs=opening_refs,
        exchanges=exchanges,
        public_mood=_mood(opinion),
    )


def run_press_conference(
    policy: PolicyDSL,
    shocks: Shocks | None = None,
    horizon_months: float = 5.0,
    use_llm: bool = True,
) -> PressConference:
    """Run the sim + opinion pipeline, then stage the press conference."""
    params, trend = apply_shocks(shocks)
    base = compute_baseline(params)
    base_ts = build_timeseries(base, trend)
    b_ts = build_world_b_timeline(policy, baseline=base, params=params, trend=trend)
    delta = build_delta(base_ts, b_ts)
    ledger = build_event_ledger(policy, base, delta)
    opinion = compute_public_opinion(policy, params=params)
    return build_press_conference(
        policy, delta, ledger, opinion, horizon_months=horizon_months, use_llm=use_llm
    )

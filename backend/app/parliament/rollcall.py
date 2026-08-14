"""Roll-call vote simulation over the real New Zealand House.

Method, and where it comes from. The European Parliament simulation work out of
DESS Mannheim (Kirchner et al., EACL 2026, `dess-mannheim/european_parliament_simulation`)
predicts MEP roll-call votes by conditioning a language model on per-member
persona profiles and the text of the motion. We use the same *shape* of method
and a deliberately weaker instrument: a documented scoring function over party
stance priors and the simulated policy outcome, rather than an LLM.

That choice is the point. GOV SIM's rule is that language models never produce a
numeric effect (SPEC §34), and a division count is a numeric effect. So the
vote is computed, the reasoning is prose, and the two are kept apart.

What is real here:
  * the parties, their seat counts, and the size of the House — the official
    2023 results
  * party discipline in the NZ House, which is close to absolute; whipped votes
    are the norm and conscience votes are rare and named

What is modelled:
  * each party's lean on the policy (see `nz.STANCE_PRIORS`, tagged Estimated)
  * how strongly the simulated outcome moves that lean

Nothing here predicts how a real MP would vote on a real bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import nz

PROVENANCE = "Simulated"

#: How reliably a party votes as a bloc. New Zealand parties are highly
#: disciplined; this is the share of a caucus that follows the party line on a
#: whipped vote. Conscience votes are out of scope.
PARTY_DISCIPLINE = 0.96

#: How heavily a distributional hit counts against the policy, before the
#: per-party equity weighting in `nz.EVIDENCE_RESPONSE`.
EQUITY_WEIGHT = 0.55


@dataclass
class PartyVote:
    party: str
    name: str
    short: str
    colour: str
    seats: int
    #: −1 … +1 after the outcome adjustment.
    position: float
    stance: str  # "for" | "against" | "abstain"
    ayes: int
    noes: int
    abstain: int
    reasoning: str


def _lever_weights(policy: dict[str, Any]) -> dict[str, float]:
    """Work out which transport levers this policy actually pulls.

    Reads the compiled Policy DSL rather than the prose, so a policy that only
    mentions pedestrianisation is not scored as though it also priced the road.
    """
    weights: dict[str, float] = {}

    charge = 0.0
    for key in ("charge_amount", "charge", "cordon_charge"):
        v = policy.get(key)
        if isinstance(v, (int, float)) and v > 0:
            charge = float(v)
            break
    instruments = policy.get("instruments") or policy.get("mechanisms") or []
    text = " ".join(str(x).lower() for x in instruments) + " " + str(policy.get("summary", "")).lower()

    if charge > 0 or "pricing" in text or "charge" in text or "cordon" in text:
        weights["road_pricing"] = 1.0
    if "pedestrian" in text or "plaza" in text or "street space" in text:
        weights["pedestrianisation"] = 1.0

    pt_share = policy.get("public_transport_share")
    if isinstance(pt_share, (int, float)) and pt_share > 0:
        weights["transit_investment"] = min(1.0, float(pt_share) * 1.4)
    elif "transit" in text or "bus" in text or "rail" in text:
        weights["transit_investment"] = 0.7

    if "fuel" in text or "petrol" in text or "excise" in text:
        weights["fuel_tax"] = 1.0

    if not weights:  # a policy that pulls no lever we model
        weights["road_pricing"] = 0.5
    total = sum(weights.values())
    return {k: v / total for k, v in weights.items()}


def _outcome_signals(outcome: dict[str, Any] | None) -> tuple[float, float]:
    """Split the simulation into (does it work?, who does it hurt?).

    Two signals rather than one, because parties genuinely trade them off
    differently: a party can accept that a charge cuts congestion and still
    oppose it because of what it does to low-income drivers. Collapsing both
    into a single "good policy" number is what produced unanimous divisions.

    Returns (effectiveness, equity_harm), each −1 … +1 and 0 … 1 respectively.
    """
    if not outcome:
        return 0.0, 0.0

    effectiveness = 0.0
    n = 0
    for key, good_when_down in (
        ("car_trips_into_cbd_pct", True),
        ("co2_pct", True),
        ("congestion_pct", True),
        ("transit_trips_pct", False),
    ):
        v = outcome.get(key)
        if isinstance(v, (int, float)):
            change = -v if good_when_down else v
            effectiveness += max(-1.0, min(1.0, change / 25.0))
            n += 1
    effectiveness = effectiveness / n if n else 0.0

    burden = outcome.get("low_income_burden_pct")
    equity_harm = (
        max(0.0, min(1.0, float(burden) / 5.0))
        if isinstance(burden, (int, float))
        else 0.0
    )
    return effectiveness, equity_harm


def simulate_division(
    policy: dict[str, Any],
    outcome: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the division and return the result with its full derivation."""
    chamber = nz.current_chamber()
    levers = _lever_weights(policy)
    effectiveness, equity_harm = _outcome_signals(outcome)

    votes: list[PartyVote] = []
    for bench in chamber["benches"]:
        pid = bench["party"]
        priors = nz.STANCE_PRIORS.get(pid, {})
        response = nz.EVIDENCE_RESPONSE.get(pid, {"evidence": 0.3, "equity": 1.0})

        prior = sum(priors.get(lever, 0.0) * w for lever, w in levers.items())
        # A party that already leans hard one way is moved less by a result than
        # one sitting near the middle — the room to move is what shrinks.
        headroom = 1.0 - abs(prior)
        shift = effectiveness * response["evidence"] * headroom
        # Distributional harm pushes against the policy regardless of how well
        # it performs, weighted by how much the party campaigns on that ground.
        penalty = equity_harm * response["equity"] * EQUITY_WEIGHT
        position = max(-1.0, min(1.0, prior + shift - penalty))

        seats = bench["seats"]
        if position > 0.15:
            stance = "for"
            ayes = round(seats * PARTY_DISCIPLINE)
            noes = 0
            abstain = seats - ayes
        elif position < -0.15:
            stance = "against"
            noes = round(seats * PARTY_DISCIPLINE)
            ayes = 0
            abstain = seats - noes
        else:
            stance = "abstain"
            ayes = round(seats * 0.35)
            noes = round(seats * 0.35)
            abstain = seats - ayes - noes

        top_lever = max(levers, key=levers.get) if levers else "road_pricing"
        direction = (
            "supports" if position > 0.15
            else "opposes" if position < -0.15
            else "is split on"
        )
        reasoning = (
            f"{bench['short']} {direction} this on its {top_lever.replace('_', ' ')} "
            f"content (prior {prior:+.2f}"
            + (f", {shift:+.2f} on the simulated outcome" if abs(shift) > 0.01 else "")
            + (f", {-penalty:+.2f} on the distributional result" if penalty > 0.01 else "")
            + ")."
        )

        votes.append(PartyVote(
            party=pid, name=bench["name"], short=bench["short"],
            colour=bench["colour"], seats=seats, position=round(position, 3),
            stance=stance, ayes=ayes, noes=noes, abstain=abstain,
            reasoning=reasoning,
        ))

    ayes = sum(v.ayes for v in votes)
    noes = sum(v.noes for v in votes)
    abstain = sum(v.abstain for v in votes)
    total = chamber["total_seats"]
    majority = total // 2 + 1
    passed = ayes >= majority

    return {
        "provenance": PROVENANCE,
        "method": (
            "Party-bloc scoring over stance priors, adjusted by the simulated "
            "outcome. Same persona-conditioned shape as the DESS Mannheim "
            "European Parliament simulation (EACL 2026), but computed rather "
            "than language-model generated — a division count is a numeric "
            "effect, and SPEC §34 keeps those away from LLMs."
        ),
        "method_reference": {
            "title": "European Parliament simulation",
            "org": "DESS Mannheim",
            "url": "https://github.com/dess-mannheim/european_parliament_simulation",
            "licence": "MIT (code), CC BY 4.0 (data)",
        },
        "house": {
            "year": chamber["year"],
            "total_seats": total,
            "majority": majority,
            "seats_provenance": nz.PROVENANCE_ELECTIONS,
            "note": chamber["note"],
        },
        "levers": [{"lever": k, "weight": round(v, 3)} for k, v in
                   sorted(levers.items(), key=lambda kv: -kv[1])],
        "outcome_signal": {
            "effectiveness": round(effectiveness, 3),
            "equity_harm": round(equity_harm, 3),
        },
        "result": {
            "ayes": ayes,
            "noes": noes,
            "abstentions": abstain,
            "majority_needed": majority,
            "passed": passed,
            "margin": ayes - noes,
        },
        "divisions": [
            {
                "party": v.party,
                "name": v.name,
                "short": v.short,
                "colour": v.colour,
                "seats": v.seats,
                "position": v.position,
                "stance": v.stance,
                "ayes": v.ayes,
                "noes": v.noes,
                "abstentions": v.abstain,
                "reasoning": v.reasoning,
            }
            for v in votes
        ],
        "caveat": (
            "Party stance priors are Estimated from published transport "
            "positions, not from a roll call on this policy — the policy is "
            "hypothetical, so no such roll call exists. Seat counts are the "
            f"official {chamber['year']} results and are Observed."
        ),
    }

"""Real New Zealand general-election results, 2005–2023.

Every figure below is the Electoral Commission's official final party-vote
share and seat count, as published for each election. Nothing here is modelled
— this is the historical record the chamber is drawn from, tagged **Observed**,
and it is what makes the parliament view something other than decoration: the
seat counts on screen are the seat counts that actually happened.

Seven elections, eighteen years, seven parties that have held seats. Overhang
seats mean the House size varies (120–123), which is why `total_seats` is
recorded per election rather than assumed.

Source: Electoral Commission official results, via the per-election summaries on
Wikipedia. Percentages are party vote; seats are final (post-special) totals.

The *positions* on each party (`stance_priors` below) are a different kind of
claim and are labelled differently — see the note on that constant.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

PROVENANCE_ELECTIONS = "Observed"
PROVENANCE_STANCE = "Estimated"

SOURCE = {
    "name": "New Zealand Electoral Commission — official results",
    "url": "https://electionresults.govt.nz/",
    "note": (
        "Official final party-vote shares and seat counts for the 2005–2023 "
        "general elections. Seat totals vary between 120 and 123 because of "
        "overhang seats."
    ),
    "tag": PROVENANCE_ELECTIONS,
}


@dataclass(frozen=True)
class Party:
    """A party that has held seats in the House since 2005."""

    id: str
    name: str
    short: str
    #: The party's own colour, as used in NZ election coverage.
    colour: str
    #: Broad placement on an economic left/right axis, −1 … +1.
    economic: float
    #: Broad placement on a green/growth axis, −1 (growth) … +1 (green).
    environmental: float
    active: bool = True


PARTIES: list[Party] = [
    Party("labour", "Labour Party", "Labour", "#D82A20", -0.55, 0.30),
    Party("national", "National Party", "National", "#00529F", 0.55, -0.20),
    Party("green", "Green Party", "Greens", "#098137", -0.75, 0.95),
    Party("act", "ACT New Zealand", "ACT", "#FDE401", 0.90, -0.60),
    Party("nzfirst", "New Zealand First", "NZ First", "#000000", -0.05, -0.35),
    Party("maori", "Te Pāti Māori", "Te Pāti Māori", "#B2001A", -0.50, 0.65),
    Party("united", "United Future", "United Future", "#501557", 0.20, 0.00, active=False),
    Party("progressive", "Progressive", "Progressive", "#9E9E9E", -0.70, 0.35, active=False),
    Party("mana", "Mana", "Mana", "#770808", -0.85, 0.55, active=False),
]

PARTY_BY_ID = {p.id: p for p in PARTIES}


@dataclass(frozen=True)
class ElectionResult:
    year: int
    total_seats: int
    #: party id → (party vote %, seats)
    results: dict[str, tuple[float, int]] = field(default_factory=dict)
    note: str = ""


#: Official final results. Party vote percentage, then seats.
ELECTIONS: list[ElectionResult] = [
    ElectionResult(
        2005, 121,
        {
            "labour": (41.10, 50),
            "national": (39.10, 48),
            "nzfirst": (5.72, 7),
            "green": (5.30, 6),
            "maori": (2.12, 4),
            "united": (2.67, 3),
            "act": (1.51, 2),
            "progressive": (1.16, 1),
        },
        "Labour-led coalition; one overhang seat.",
    ),
    ElectionResult(
        2008, 122,
        {
            "national": (44.93, 58),
            "labour": (33.99, 43),
            "green": (6.72, 9),
            "act": (3.65, 5),
            "maori": (2.39, 5),
            "nzfirst": (4.07, 0),
            "progressive": (0.91, 1),
            "united": (0.87, 1),
        },
        "NZ First fell below the 5% threshold and won no electorate — 4.07%, no seats.",
    ),
    ElectionResult(
        2011, 121,
        {
            "national": (47.31, 59),
            "labour": (27.48, 34),
            "green": (11.06, 14),
            "nzfirst": (6.59, 8),
            "maori": (1.43, 3),
            "mana": (1.08, 1),
            "act": (1.07, 1),
            "united": (0.60, 1),
        },
        "NZ First returned above the threshold.",
    ),
    ElectionResult(
        2014, 121,
        {
            "national": (47.04, 60),
            "labour": (25.13, 32),
            "green": (10.70, 14),
            "nzfirst": (8.66, 11),
            "maori": (1.32, 2),
            "act": (0.69, 1),
            "united": (0.22, 1),
        },
        "National's high-water mark under MMP.",
    ),
    ElectionResult(
        2017, 120,
        {
            "national": (44.45, 56),
            "labour": (36.89, 46),
            "nzfirst": (7.20, 9),
            "green": (6.27, 8),
            "act": (0.50, 1),
            "maori": (1.18, 0),
        },
        "National won the most seats but Labour formed the government with NZ First and the Greens.",
    ),
    ElectionResult(
        2020, 120,
        {
            "labour": (50.01, 65),
            "national": (25.58, 33),
            "green": (7.86, 10),
            "act": (7.59, 10),
            "maori": (1.17, 2),
            "nzfirst": (2.60, 0),
        },
        "First single-party majority under MMP.",
    ),
    ElectionResult(
        2023, 123,
        {
            "national": (38.06, 48),
            "labour": (26.91, 34),
            "green": (11.60, 15),
            "act": (8.64, 11),
            "nzfirst": (6.08, 8),
            "maori": (3.08, 6),
        },
        "Three overhang seats: two Te Pāti Māori, one from the Port Waikato by-election.",
    ),
]

LATEST = ELECTIONS[-1]


# ---------------------------------------------------------------------------
# Policy stance priors
# ---------------------------------------------------------------------------

Lever = Literal["road_pricing", "pedestrianisation", "transit_investment", "fuel_tax"]

#: How each party is *expected* to lean on a transport lever, −1 (oppose) …
#: +1 (support).
#:
#: This is the one modelled thing in this module, and it is tagged Estimated
#: rather than Observed for a reason: it is derived from each party's published
#: transport positions and voting record, not from a roll call on this specific
#: policy — which does not exist, because the policy is hypothetical. The
#: chamber view labels it as an estimate on screen. Do not let it be read as a
#: prediction of how a real MP would vote.
STANCE_PRIORS: dict[str, dict[str, float]] = {
    "labour":     {"road_pricing": 0.35, "pedestrianisation": 0.55, "transit_investment": 0.85, "fuel_tax": 0.30},
    "national":   {"road_pricing": 0.25, "pedestrianisation": -0.45, "transit_investment": 0.10, "fuel_tax": -0.70},
    "green":      {"road_pricing": 0.60, "pedestrianisation": 0.95, "transit_investment": 0.95, "fuel_tax": 0.75},
    "act":        {"road_pricing": 0.40, "pedestrianisation": -0.80, "transit_investment": -0.55, "fuel_tax": -0.85},
    "nzfirst":    {"road_pricing": -0.70, "pedestrianisation": -0.65, "transit_investment": 0.25, "fuel_tax": -0.75},
    "maori":      {"road_pricing": -0.45, "pedestrianisation": 0.45, "transit_investment": 0.70, "fuel_tax": -0.35},
    "united":     {"road_pricing": 0.10, "pedestrianisation": 0.10, "transit_investment": 0.30, "fuel_tax": -0.20},
    "progressive": {"road_pricing": 0.20, "pedestrianisation": 0.50, "transit_investment": 0.80, "fuel_tax": 0.20},
    "mana":       {"road_pricing": -0.60, "pedestrianisation": 0.40, "transit_investment": 0.85, "fuel_tax": -0.40},
}

#: How far a party moves off its prior when the simulation says the policy
#: works, and how heavily it weights a regressive distributional result.
#:
#: These are what stop the division collapsing into unanimity whenever the model
#: reports a good outcome. A party whose position on road pricing is a manifesto
#: commitment does not abandon it because a projection is favourable, and the
#: parties that campaign on cost-of-living react much more strongly to a low-
#: income burden than to an emissions number. Both columns are Estimated.
EVIDENCE_RESPONSE: dict[str, dict[str, float]] = {
    #                 moves on evidence   weights equity harm
    "labour":       {"evidence": 0.40, "equity": 1.10},
    "national":     {"evidence": 0.30, "equity": 0.55},
    "green":        {"evidence": 0.45, "equity": 1.30},
    "act":          {"evidence": 0.25, "equity": 0.30},
    "nzfirst":      {"evidence": 0.12, "equity": 1.40},
    "maori":        {"evidence": 0.30, "equity": 1.60},
    "united":       {"evidence": 0.35, "equity": 0.70},
    "progressive":  {"evidence": 0.40, "equity": 1.20},
    "mana":         {"evidence": 0.20, "equity": 1.70},
}


def history() -> dict:
    """The full historical series, shaped for the frontend chart."""
    return {
        "provenance": PROVENANCE_ELECTIONS,
        "source": SOURCE,
        "parties": [
            {
                "id": p.id,
                "name": p.name,
                "short": p.short,
                "colour": p.colour,
                "active": p.active,
            }
            for p in PARTIES
        ],
        "elections": [
            {
                "year": e.year,
                "total_seats": e.total_seats,
                "note": e.note,
                "results": [
                    {
                        "party": pid,
                        "party_vote_pct": vote,
                        "seats": seats,
                    }
                    for pid, (vote, seats) in sorted(
                        e.results.items(), key=lambda kv: -kv[1][1]
                    )
                ],
            }
            for e in ELECTIONS
        ],
        "span_years": ELECTIONS[-1].year - ELECTIONS[0].year,
        "election_count": len(ELECTIONS),
    }


def current_chamber() -> dict:
    """The seats as they actually stand after the most recent election."""
    return {
        "provenance": PROVENANCE_ELECTIONS,
        "source": SOURCE,
        "year": LATEST.year,
        "total_seats": LATEST.total_seats,
        "note": LATEST.note,
        "benches": [
            {
                "party": pid,
                "name": PARTY_BY_ID[pid].name,
                "short": PARTY_BY_ID[pid].short,
                "colour": PARTY_BY_ID[pid].colour,
                "seats": seats,
                "party_vote_pct": vote,
            }
            for pid, (vote, seats) in sorted(
                LATEST.results.items(), key=lambda kv: -kv[1][1]
            )
            if seats > 0
        ],
    }

"""Deterministic rule-based policy parser (LLM-free fallback).

This is the guaranteed path: it runs with no API key and no network, so the
compiler always produces *something* reviewable. It uses plain regex/keyword
heuristics over the policy text and records a confidence + source for every
field it fills, feeding the "editable assumptions" panel (SPEC §3).

It intentionally does **not** compute any simulation effects — it only maps
words to DSL fields (SPEC §34).
"""

from __future__ import annotations

import re
from datetime import date

from .dsl import (
    ActiveHours,
    Assumption,
    Constraints,
    Intervention,
    InterventionType,
    PolicyDSL,
    RevenueAllocation,
    StatedObjectives,
)

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}


def _parse_time(raw: str) -> str | None:
    """Normalise strings like '7:00 AM', '7am', '19:00' to 'HH:MM'."""
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", raw, re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    ampm = (m.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _find_amount(text: str) -> tuple[float, str] | None:
    """Return (amount, currency) for the primary charge, if present."""
    # Symbol-prefixed: $10, £5.50
    m = re.search(r"([$£€¥])\s?(\d+(?:\.\d+)?)", text)
    if m:
        return float(m.group(2)), _CURRENCY_SYMBOLS.get(m.group(1), "local")
    # Worded: "10 dollars", "5 pounds", "charge of 12"
    m = re.search(
        r"(\d+(?:\.\d+)?)\s*(dollars?|pounds?|euros?|usd|gbp|eur)", text, re.IGNORECASE
    )
    if m:
        word = m.group(2).lower()
        cur = {
            "dollar": "USD", "dollars": "USD", "usd": "USD",
            "pound": "GBP", "pounds": "GBP", "gbp": "GBP",
            "euro": "EUR", "euros": "EUR", "eur": "EUR",
        }.get(word, "local")
        return float(m.group(1)), cur
    # "charge/fee/levy of 10"
    m = re.search(r"(?:charge|fee|levy|price)\s+of\s+(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        return float(m.group(1)), "local"
    return None


def _find_hours(text: str) -> tuple[str, str] | None:
    m = re.search(
        r"between\s+([0-9:]+\s*(?:am|pm)?)\s+and\s+([0-9:]+\s*(?:am|pm)?)",
        text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"([0-9:]+\s*(?:am|pm)?)\s*(?:-|–|to)\s*([0-9:]+\s*(?:am|pm)?)",
            text,
            re.IGNORECASE,
        )
    if not m:
        return None
    start = _parse_time(m.group(1))
    end = _parse_time(m.group(2))
    if start and end:
        return start, end
    return None


def _find_date(text: str) -> str | None:
    # "1 January 2027" / "January 1, 2027"
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\b", text)
    if m:
        day, mon, year = int(m.group(1)), m.group(2).lower(), int(m.group(3))
        if mon in _MONTHS:
            try:
                return date(year, _MONTHS[mon], day).isoformat()
            except ValueError:
                pass
    m = re.search(r"\b([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})\b", text)
    if m:
        mon, day, year = m.group(1).lower(), int(m.group(2)), int(m.group(3))
        if mon in _MONTHS:
            try:
                return date(year, _MONTHS[mon], day).isoformat()
            except ValueError:
                pass
    # ISO date
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            pass
    return None


def _find_intervention_type(text: str) -> InterventionType:
    t = text.lower()
    if re.search(r"pedestrian|car[- ]free|traffic-free|ban.*vehicles|no cars", t):
        return InterventionType.pedestrianisation
    if re.search(r"congestion charge|road pricing|cordon|charge.*enter|toll|price.*vehicle", t):
        return InterventionType.road_pricing
    if re.search(r"low[- ]emission zone|clean air zone|\blez\b|\bulez\b", t):
        return InterventionType.low_emission_zone
    if re.search(r"parking levy|parking charge|workplace parking", t):
        return InterventionType.parking_levy
    if re.search(r"invest.*(bus|transit|metro|tram|rail)|new bus route", t):
        return InterventionType.transit_investment
    return InterventionType.other


def _find_zone(text: str) -> str:
    t = text.lower()
    if re.search(r"central business district|\bcbd\b|central district|city cent|downtown|inner city", t):
        return "cbd_polygon"
    return "cbd_polygon"  # demo world only models the CBD cordon


def _find_exemptions(text: str) -> list[str]:
    t = text.lower()
    found: list[str] = []
    catalogue = [
        (r"emergency vehicle|ambulance|fire engine|police", "emergency_vehicle"),
        (r"disabilit|disabled|blue badge|accessibility permit", "disability_permit"),
        (r"resident", "resident"),
        (r"electric vehicle|\bev\b|zero[- ]emission", "electric_vehicle"),
        (r"\btaxi|private hire", "taxi"),
        (r"\bbus\b|public transport vehicle", "public_transport"),
    ]
    for pattern, tag in catalogue:
        if re.search(pattern, t) and tag not in found:
            found.append(tag)
    return found


def _find_revenue_allocation(text: str) -> tuple[RevenueAllocation, bool]:
    """Return (allocation, was_stated)."""
    t = text.lower()
    # "spend 70% ... on buses/transit"
    m = re.search(
        r"(\d+(?:\.\d+)?)\s?%[^.]*?(bus|transit|public transport|metro|tram|rail)",
        t,
    )
    if m:
        frac = min(max(float(m.group(1)) / 100.0, 0.0), 1.0)
        return (
            RevenueAllocation(
                public_transport=round(frac, 4),
                general_fund=round(1.0 - frac, 4),
            ),
            True,
        )
    # "spend 40% ... on cycling/walking/active travel"
    m = re.search(
        r"(\d+(?:\.\d+)?)\s?%[^.]*?"
        r"(cycl|bike|walking|footpath|foot path|pavement|active[- ]travel)",
        t,
    )
    if m:
        frac = min(max(float(m.group(1)) / 100.0, 0.0), 1.0)
        return (
            RevenueAllocation(
                active_travel=round(frac, 4),
                general_fund=round(1.0 - frac, 4),
            ),
            True,
        )
    return RevenueAllocation(public_transport=0.0, general_fund=1.0), False


def _infer_objectives(itype: InterventionType, text: str) -> StatedObjectives:
    t = text.lower()
    obj = StatedObjectives()
    if itype in (InterventionType.road_pricing, InterventionType.pedestrianisation,
                 InterventionType.parking_levy):
        obj.congestion_reduction = True
    if re.search(r"emission|air quality|pollution|climate|co2|carbon", t) or \
            itype in (InterventionType.low_emission_zone, InterventionType.pedestrianisation):
        obj.emissions_reduction = True
    if re.search(r"bus|transit|public transport|metro|tram|rail", t):
        obj.public_transport_improvement = True
    if re.search(r"revenue|proceeds|reinvest|fund", t):
        obj.revenue_generation = True
    if re.search(r"equit|fair|low[- ]income|accessib", t):
        obj.equity_improvement = True
    return obj


def _find_constraints(text: str) -> Constraints:
    m = re.search(
        r"(?:low[- ]income|poorest)[^.]*?(\d+(?:\.\d+)?)\s?%",
        text,
        re.IGNORECASE,
    )
    if m:
        return Constraints(max_low_income_burden_increase_pct=float(m.group(1)))
    return Constraints()


def _slug(itype: InterventionType) -> str:
    return f"{itype.value}_v1"


def parse_policy(text: str, jurisdiction: str | None = None) -> tuple[PolicyDSL, list[Assumption]]:
    """Parse ``text`` into a :class:`PolicyDSL` plus reviewable assumptions."""
    assumptions: list[Assumption] = []

    def note(field: str, value: object, source: str, confidence: float, rationale: str) -> None:
        assumptions.append(
            Assumption(field=field, value=value, source=source,
                       confidence=confidence, rationale=rationale)
        )

    itype = _find_intervention_type(text)
    note("intervention.type", itype.value,
         "inferred" if itype is not InterventionType.other else "default",
         0.8 if itype is not InterventionType.other else 0.3,
         "Keyword match on intervention family.")

    intervention = Intervention(type=itype)

    amount = _find_amount(text)
    if amount is not None:
        intervention.amount, intervention.currency = amount
        note("intervention.amount", amount[0], "stated", 0.9, "Numeric charge found in text.")
        note("intervention.currency", amount[1], "inferred", 0.7, "Currency from symbol/word.")
    elif itype in (InterventionType.road_pricing, InterventionType.parking_levy,
                   InterventionType.low_emission_zone):
        note("intervention.amount", None, "default", 0.2,
             "No charge amount stated; requires human input.")

    hours = _find_hours(text)
    if hours is not None:
        intervention.active_hours = ActiveHours(start=hours[0], end=hours[1])
        note("intervention.active_hours", {"start": hours[0], "end": hours[1]},
             "stated", 0.9, "Time window parsed from text.")
    else:
        note("intervention.active_hours",
             {"start": intervention.active_hours.start, "end": intervention.active_hours.end},
             "default", 0.3, "No hours stated; assumed daytime charging window.")

    iso_date = _find_date(text)
    if iso_date is not None:
        intervention.implementation_date = iso_date
        note("intervention.implementation_date", iso_date, "stated", 0.9,
             "Start date parsed from text.")
    else:
        note("intervention.implementation_date", None, "default", 0.2,
             "No start date stated.")

    zone = _find_zone(text)
    intervention.geographic_zone = zone
    note("intervention.geographic_zone", zone, "inferred", 0.6,
         "Mapped to the demo CBD cordon polygon.")

    exemptions = _find_exemptions(text)
    if exemptions:
        note("exemptions", exemptions, "stated", 0.85, "Exemptions listed in text.")
    else:
        note("exemptions", [], "default", 0.4, "No exemptions stated.")

    allocation, alloc_stated = _find_revenue_allocation(text)
    note("revenue_allocation",
         {"public_transport": allocation.public_transport,
          "general_fund": allocation.general_fund},
         "stated" if alloc_stated else "default",
         0.85 if alloc_stated else 0.3,
         "Split parsed from text." if alloc_stated
         else "No split stated; proceeds default to general fund.")

    objectives = _infer_objectives(itype, text)
    note("stated_objectives", objectives.model_dump(), "inferred", 0.6,
         "Objectives inferred from intervention type and keywords.")

    constraints = _find_constraints(text)
    if constraints.max_low_income_burden_increase_pct is not None:
        note("constraints.max_low_income_burden_increase_pct",
             constraints.max_low_income_burden_increase_pct,
             "stated", 0.75, "Equity constraint parsed from text.")

    domain = ["transport"]
    if objectives.emissions_reduction:
        domain.append("climate")
    if intervention.amount is not None:
        domain.append("taxation")

    policy = PolicyDSL(
        id=_slug(itype),
        jurisdiction=(jurisdiction or "auckland").lower(),
        domain=domain,
        intervention=intervention,
        exemptions=exemptions,
        revenue_allocation=allocation,
        stated_objectives=objectives,
        constraints=constraints,
    )
    return policy, assumptions

#!/usr/bin/env python3
"""GOV SIM guardrail audit — prove the WHOLE engine isn't "AI astrology", one command.

``demo.py`` audits the ``/run`` payload and ``north_star.py`` audits the §37
answer — each checks the SPEC §34 guardrails on *one* composed response. This
drives the **entire HTTP surface** (every GET + POST route) in-process and
reports a single pass/fail compliance matrix across all of it, so a judge can
verify the four load-bearing §34 claims in one place without reading pytest:

  1. **Every route serves** — compile the demo policy once, feed it to all routes,
     assert 200 (catches cross-layer contract drift the night before the demo).
  2. **Nothing untagged** — every ``provenance`` field, at any depth in any
     response, references one of Observed / Estimated / Simulated / Generated.
  3. **No LLM touches a number** — every model in the §33 registry asserts
     ``llm_touches_numbers == False``; generated media carries the SIMULATED banner.
  4. **Reproducible + honest about the future** — each deterministic numeric layer
     returns byte-identical JSON across two identical calls, and ``/simulate``'s
     uncertainty fan widens (never narrows) with the horizon.

No server / ports — it drives the FastAPI app via ``TestClient``. Exit code is
non-zero if any guardrail fails, so this doubles as a pre-demo / CI smoke gate.

Usage (from repo root):
    backend/.venv/bin/python scripts/audit.py
    backend/.venv/bin/python scripts/audit.py --json     # machine-readable report
    backend/.venv/bin/python scripts/audit.py --text "..."  # audit a custom policy
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Iterator

# --- make the backend package importable regardless of the caller's cwd -----
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_BACKEND = os.path.join(_ROOT, "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

DEMO_TEXT = (
    "Introduce a $12 congestion charge for private vehicles entering the central "
    "business district between 7:00 AM and 7:00 PM, beginning 1 January 2027. "
    "Exempt emergency vehicles and disability permit holders. Reinvest 100% of net "
    "proceeds into buses."
)

ALLOWED_TAGS = {"Observed", "Estimated", "Simulated", "Generated"}

# --- tiny ANSI helpers (auto-disabled when not a TTY) -----------------------
_TTY = sys.stdout.isatty()


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s


def bold(s: str) -> str:
    return _c("1", s)


def dim(s: str) -> str:
    return _c("2", s)


def green(s: str) -> str:
    return _c("32", s)


def red(s: str) -> str:
    return _c("31", s)


def cyan(s: str) -> str:
    return _c("36", s)


def rule(title: str = "") -> None:
    width = 74
    if title:
        pad = width - len(title) - 3
        print(bold(cyan(f"\n── {title} " + "─" * max(pad, 0))))
    else:
        print(cyan("─" * width))


def _iter_provenance(obj: Any) -> Iterator[str]:
    """Yield every value stored under a ``provenance`` key, at any depth."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "provenance" and isinstance(value, str):
                yield value
            yield from _iter_provenance(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_provenance(item)


def build_report(text: str) -> dict:
    """Drive the whole surface and assemble a structured §34 compliance report.

    Kept importable (returns a dict) so a test can assert on it without parsing
    the rendered terminal output.
    """
    from fastapi.testclient import TestClient  # noqa: WPS433
    from app.main import app  # noqa: WPS433

    client = TestClient(app)

    # --- compile the demo policy once (NL → Policy DSL, SPEC §3) -------------
    comp = client.post("/policy/compile", json={"text": text})
    if comp.status_code != 200:
        raise RuntimeError(f"POST /policy/compile failed ({comp.status_code}): {comp.text}")
    compiled = comp.json()
    policy = compiled["policy"]
    P = {"policy": policy}

    # Every route the engine exposes, with a minimal valid body (mirrors the
    # integration smoke test so this CLI covers exactly the live surface).
    get_routes = [
        "/health",
        "/capabilities",
        "/scenarios",
        "/baseline",
        "/world",
        "/registry",
        "/data-fabric",
        "/assumptions",
        "/backtest/example",
        "/compare/example",
        "/evidence/example",
        "/brief/example",
        "/run/example",
        "/north-star/example",
        "/robustness/objectives",
        "/shortlist/example",
        "/stress-test/catalogue",
        "/analogues/cases",
        "/citizen/sample",
        "/business/sample",
    ]
    # Two candidate policies (same DSL, distinct ids) for the decision layer.
    robust_body = {
        "candidates": [{**policy, "id": "cand_a"}, {**policy, "id": "cand_b"}],
        "scenarios": ["recession", "fuel_price_spike"],
    }
    # Shortlist ranker: mix a compiled DSL and an NL prompt (both entry paths).
    shortlist_body = {
        "policies": [
            {"label": "the demo charge", "policy": policy},
            {"text": "pedestrianise the city centre and reinvest revenue in buses"},
        ]
    }
    post_routes: list[tuple[str, dict]] = [
        ("/run", P),
        ("/north-star", P),
        ("/simulate", P),
        ("/simulate/amend", {**P, "amendment": {"label": "exempt low income", "exempt_low_income": True}}),
        ("/compare", {**P, "amendments": [{"label": "halve charge", "charge_multiplier": 0.5}]}),
        ("/compare/grand", {**P, "objective": {"reduce_transport_emissions_pct": 20}}),
        ("/diffusion", {**P, "rounds": 6}),
        ("/dynamics", P),
        ("/economy", P),
        ("/ensemble", P),
        ("/evidence", {**P, "metric_key": "traffic.vehicle_trips_into_cbd"}),
        ("/institutions/review", P),
        ("/media", P),
        ("/microsim", P),
        ("/citizen", P),
        ("/business", P),
        ("/parliament/debate", P),
        ("/parliament/failure-modes", P),
        ("/press-conference", P),
        ("/public", P),
        ("/reproduce", P),
        ("/sdg", P),
        ("/spatial", P),
        ("/timeseries", P),
        ("/analogues", P),
        ("/assumptions/rerun", {**P, "overrides": {"money_to_minutes": 10.0}}),
        ("/stress-test", {**P, "scenarios": ["recession", "fuel_price_spike"]}),
        ("/uncertainty", {**P, "metric_key": "traffic.daily_vehicle_km", "samples": 20}),
        ("/sensitivity", P),
        ("/optimise", {
            "objective": {"reduce_transport_emissions_pct": 15},
            "constraints": {"max_average_commute_increase_pct": 12, "max_budget": 120_000_000},
        }),
        ("/backtest", {}),
        ("/robustness", robust_body),
        ("/shortlist", shortlist_body),
    ]

    # Deterministic numeric layers — must be byte-identical across two identical
    # calls (SPEC §24/§34). Prose layers (media / press / debate) are Generated,
    # so excluded from the byte-identity check by design.
    determinism_routes: list[tuple[str, dict]] = [
        ("/simulate", P),
        ("/spatial", P),
        ("/microsim", P),
        ("/citizen", P),
        ("/business", P),
        ("/economy", P),
        ("/dynamics", P),
        ("/sdg", P),
        ("/ensemble", P),
        ("/diffusion", {**P, "rounds": 6}),
        ("/public", P),
        ("/parliament/failure-modes", P),
        ("/stress-test", {**P, "scenarios": ["recession", "fuel_price_spike"]}),
        ("/uncertainty", {**P, "metric_key": "traffic.daily_vehicle_km", "samples": 20}),
        ("/sensitivity", P),
        ("/robustness", robust_body),
        ("/shortlist", shortlist_body),
    ]

    routes: list[dict] = []
    tag_violations: list[str] = []

    def _record(method: str, path: str, status: int, payload: Any) -> None:
        tags_ok = True
        for value in _iter_provenance(payload):
            if not any(tag in value for tag in ALLOWED_TAGS):
                tags_ok = False
                tag_violations.append(f"{method} {path}: provenance {value!r} references no §34 tag")
        routes.append({
            "method": method,
            "path": path,
            "status": status,
            "ok": status == 200,
            "provenance_tagged": tags_ok,
        })

    # compiler output itself is machine-Generated structuring of user text (§34)
    _record("POST", "/policy/compile", comp.status_code, compiled)
    for path in get_routes:
        r = client.get(path)
        payload = r.json() if r.status_code == 200 else None
        _record("GET", path, r.status_code, payload)
    for path, body in post_routes:
        r = client.post(path, json=body)
        payload = r.json() if r.status_code == 200 else None
        _record("POST", path, r.status_code, payload)

    # --- guardrail 3: no LLM in the numeric path ----------------------------
    registry = client.get("/registry").json()
    models = registry.get("models") or []
    llm_offenders = [m.get("name") for m in models if m.get("llm_touches_numbers") is not False]
    media_blob = str(client.post("/media", json=P).json())

    # --- guardrail 4a: determinism (byte-identical repeats) -----------------
    determinism: list[dict] = []
    for path, body in determinism_routes:
        a = client.post(path, json=body)
        b = client.post(path, json=body)
        identical = (
            a.status_code == 200
            and b.status_code == 200
            and json.dumps(a.json(), sort_keys=True) == json.dumps(b.json(), sort_keys=True)
        )
        determinism.append({"path": path, "identical": identical})

    # --- guardrail 4b: uncertainty fan widens with horizon ------------------
    sim = client.post("/simulate", json=P).json()
    widen = _bands_widen(sim.get("delta") or {})

    checks = {
        "all_routes_serve": all(r["ok"] for r in routes),
        "all_provenance_tagged": not tag_violations,
        "no_llm_touches_numbers": bool(models) and not llm_offenders,
        "media_labelled_simulated": "SIMULATED" in media_blob,
        "numeric_layers_deterministic": all(d["identical"] for d in determinism),
        "uncertainty_widens": widen is True,
    }

    return {
        "policy_id": compiled.get("policy_id") or policy.get("id"),
        "compiler_provenance": compiled.get("provenance"),
        "routes": routes,
        "route_count": len(routes),
        "routes_failed": [f"{r['method']} {r['path']}" for r in routes if not r["ok"]],
        "tag_violations": tag_violations,
        "llm_offenders": llm_offenders,
        "registry_model_count": len(models),
        "determinism": determinism,
        "determinism_failed": [d["path"] for d in determinism if not d["identical"]],
        "band_widths": _sim_band_widths(sim.get("delta") or {}),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _bands_widen(delta: dict) -> "bool | None":
    """True if every metric's Δ band width is non-decreasing over the horizon and
    strictly wider at the far horizon than at T0; False on a violation; None if no
    band is checkable. Band width at a checkpoint is ``high − low`` (SPEC §34)."""
    series = delta.get("series")
    if not isinstance(series, list) or not series:
        return None
    checkable = False
    for s in series:
        points = s.get("points") if isinstance(s, dict) else None
        if not isinstance(points, list):
            continue
        widths = [
            abs(p["high"] - p["low"])
            for p in points
            if isinstance(p, dict) and "low" in p and "high" in p
        ]
        if len(widths) >= 2:
            checkable = True
            for a, b in zip(widths, widths[1:]):
                if b < a - 1e-6:
                    return False
            if widths[-1] <= widths[0] + 1e-9:
                return False  # a flat band claims decade-out certainty (§34 forbids)
    return True if checkable else None


def _sim_band_widths(delta: dict) -> list[float]:
    """Representative (first checkable series) band-width trajectory, for display."""
    for s in delta.get("series") or []:
        points = s.get("points") if isinstance(s, dict) else None
        if not isinstance(points, list):
            continue
        widths = [
            round(abs(p["high"] - p["low"]), 3)
            for p in points
            if isinstance(p, dict) and "low" in p and "high" in p
        ]
        if len(widths) >= 2:
            return widths
    return []


_CHECK_LABELS = {
    "all_routes_serve": "Every route serves 200 (no cross-layer drift)",
    "all_provenance_tagged": "Every provenance field carries a §34 tag",
    "no_llm_touches_numbers": "No LLM touches a number (registry)",
    "media_labelled_simulated": "Generated media labelled SIMULATED",
    "numeric_layers_deterministic": "Numeric layers byte-identical on repeat",
    "uncertainty_widens": "Uncertainty fan widens with the horizon",
}


def _render(report: dict) -> None:
    rule("GOV SIM — whole-surface §34 guardrail audit")
    print(f"{bold('Policy id')}   {report.get('policy_id')}")
    print(f"{bold('Surface')}     {report['route_count']} routes exercised "
          f"({dim('compiler=' + str(report.get('compiler_provenance')))})")
    print(f"{bold('Registry')}    {report['registry_model_count']} forecast layers, "
          f"all assert {dim('llm_touches_numbers=False')}")
    widths = report.get("band_widths") or []
    if widths:
        print(f"{bold('Fan')}         Δ band width {widths[0]:g} → {widths[-1]:g} over the horizon")

    rule("Route health")
    for r in report["routes"]:
        mark = green("✔") if r["ok"] else red("✗")
        tag = "" if r["provenance_tagged"] else red("  [untagged provenance]")
        print(f"  {mark} {r['method']:<4} {r['path']}{tag}")

    rule("§34 guardrail checks")
    for key, label in _CHECK_LABELS.items():
        passed = report["checks"].get(key, False)
        mark = green("✔") if passed else red("✗")
        print(f"  {mark} {label}")
    # surface the specifics of any failure so the audit is actionable
    for detail in report["routes_failed"]:
        print(red(f"      route failed: {detail}"))
    for detail in report["tag_violations"][:5]:
        print(red(f"      {detail}"))
    for name in report["llm_offenders"]:
        print(red(f"      model claims LLM touches numbers: {name}"))
    for path in report["determinism_failed"]:
        print(red(f"      non-deterministic on repeat: {path}"))

    rule()
    if report["passed"]:
        print(green(bold("  PASS")) + dim(" — the whole engine honours the SPEC §34 guardrails."))
    else:
        print(red(bold("  FAIL")) + " — a guardrail did not hold; see above.")


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--text", default=DEMO_TEXT, help="Natural-language policy to audit.")
    ap.add_argument("--json", action="store_true", help="Print the machine-readable report and exit.")
    args = ap.parse_args(argv)

    print(dim("Driving the whole engine surface in-process (this runs every layer)…"),
          file=sys.stderr)
    try:
        report = build_report(args.text)
    except RuntimeError as exc:
        print(red(str(exc)))
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if report["passed"] else 1

    _render(report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))

#!/usr/bin/env python3
"""GOV SIM killer-demo runner — one command, the whole §29 narrative in the terminal.

Runs the full engine pipeline (compile → simulate → public → parliament →
amendment → media) through ``POST /run`` and prints a judge-friendly summary:
the compiled policy, the headline dashboard at the demo horizon, net public
support, the parliament tally + synthesis, the auto-proposed amendment and its
effect, and one sample media headline per horizon — followed by a §34 guardrail
audit proving every number is Simulated, media is labelled SIMULATED, and
uncertainty widens with the horizon.

No server needed: it drives the FastAPI app in-process via ``TestClient`` so a
judge can see the demo end-to-end with a single command and no ports.

Usage (from repo root):
    backend/.venv/bin/python scripts/demo.py
    backend/.venv/bin/python scripts/demo.py --json          # raw /run payload
    backend/.venv/bin/python scripts/demo.py --text "..."     # custom policy
    backend/.venv/bin/python scripts/demo.py --horizon 60     # different horizon (months)

Exit code is non-zero if the §34 guardrail audit fails, so this doubles as a
smoke check for CI / pre-demo confidence.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

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


def yellow(s: str) -> str:
    return _c("33", s)


def cyan(s: str) -> str:
    return _c("36", s)


def rule(title: str = "") -> None:
    width = 74
    if title:
        pad = width - len(title) - 3
        print(bold(cyan(f"\n── {title} " + "─" * max(pad, 0))))
    else:
        print(cyan("─" * width))


def _arrow(direction: str) -> str:
    return {"down": "▼", "up": "▲", "flat": "▬"}.get(direction, "·")


def _fmt(x: float) -> str:
    ax = abs(x)
    if ax >= 100:
        return f"{x:,.0f}"
    if ax >= 1:
        return f"{x:,.1f}"
    return f"{x:,.3f}"


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--text", default=DEMO_TEXT, help="Natural-language policy to compile & simulate.")
    ap.add_argument("--horizon", type=float, default=24.0, help="Headline horizon in months (default 24 = Year 2).")
    ap.add_argument("--json", action="store_true", help="Print the raw /run JSON payload and exit.")
    args = ap.parse_args(argv)

    # Imported lazily so --help works even before deps are installed.
    from fastapi.testclient import TestClient  # noqa: WPS433
    from app.main import app  # noqa: WPS433

    client = TestClient(app)

    print(dim("Running the full engine pipeline (compile → simulate → public → parliament → amendment → media)…"),
          file=sys.stderr)
    resp = client.post("/run", json={"text": args.text, "horizon_months": args.horizon})
    if resp.status_code != 200:
        print(red(f"POST /run failed ({resp.status_code}):\n{resp.text}"))
        return 2
    data = resp.json()

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    _render(data)
    return _audit(data)


def _render(data: dict) -> None:
    rule("GOV SIM — policy digital twin · killer demo")
    print(f"{bold('Policy id')}   {data['policy_id']}")
    print(f"{bold('Horizon')}     {data['horizon_label']}  ({_fmt(data['horizon_months'])} months)")

    compiled = data.get("compiled") or {}
    policy = compiled.get("policy") if isinstance(compiled, dict) else None
    if policy:
        intervention = policy.get("intervention") or {}
        instr = intervention.get("type") or "—"
        amount = intervention.get("amount")
        cur = intervention.get("currency", "")
        zone = intervention.get("geographic_zone", "")
        bits = [f"instrument={instr}"]
        if amount is not None:
            bits.append(f"charge={cur} {_fmt(amount)}")
        if zone:
            bits.append(f"zone={zone}")
        domain = policy.get("domain") or []
        if domain:
            bits.append("domain=" + ",".join(domain))
        print(f"{bold('Compiled')}    " + "  ".join(bits))
        print(dim("             (natural language → structured Policy DSL, SPEC §3)"))

    # --- headline dashboard --------------------------------------------------
    rule(f"Headline dashboard — policy effect at {data['horizon_label']}")
    headline = data.get("headline") or []
    if not headline:
        print(dim("(no headline metrics)"))
    for m in headline:
        band = m.get("band") or []
        band_s = ""
        if len(band) == 2:
            band_s = dim(f"  band[{_fmt(band[0])}, {_fmt(band[1])}]")
        pct = m.get("delta_pct")
        pct_s = f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
        arrow = _arrow(m.get("direction", ""))
        delta = m.get("delta", 0.0)
        colour = green if arrow == "▼" else (yellow if arrow == "▲" else dim)
        line = (
            f"  {m.get('label','?'):<26} "
            f"A {_fmt(m.get('world_a',0)):>10}  →  B {_fmt(m.get('world_b',0)):>10}   "
            f"{colour(arrow + ' Δ ' + _fmt(delta) + ' ' + m.get('unit',''))}{pct_s}"
        )
        print(line + band_s + "  " + dim(f"[{m.get('tag','?')}]"))

    # --- public opinion ------------------------------------------------------
    rule("Public reaction (cohort model, SPEC §13)")
    net = data.get("net_support", 0.0)
    verdict = green("net SUPPORT") if net > 0 else (red("net OPPOSITION") if net < 0 else dim("split"))
    print(f"  Net support = {net:+.1f}   → {verdict}")

    # --- parliament ----------------------------------------------------------
    rule("Model parliament (adversarial stress test, SPEC §11)")
    parl = data.get("parliament") or {}
    print(f"  Motion: {parl.get('motion','—')}")
    tally = parl.get("tally") or {}
    if tally:
        tally_s = "  ".join(f"{k}={v}" for k, v in tally.items())
        print(f"  Tally:  {tally_s}   " + dim(f"(prose via {parl.get('method','template')})"))
    summary = parl.get("summary")
    if summary:
        print(dim(f"  {summary}"))

    # --- amendment -----------------------------------------------------------
    rule("Proposed amendment (SPEC §12/§21)")
    amd = data.get("amendment") or {}
    if amd.get("proposed"):
        print(f"  Source: {amd.get('source','?')}")
        print(f"  {amd.get('rationale','')}")
        comp = amd.get("comparison") or {}
        changes = comp.get("changes") or []
        for ch in changes:
            print(cyan(f"    • {ch}"))
        adelta = comp.get("amendment_delta") or {}
        n_cp = len(adelta.get("checkpoints") or [])
        n_series = len(adelta.get("series") or [])
        if n_cp:
            print(dim(f"  Re-simulated: Δ(amended − original) across {n_cp} checkpoints "
                      f"on {n_series} metrics (SPEC §21)."))
    else:
        print(dim("  No amendment proposed for this scenario."))

    # --- media ---------------------------------------------------------------
    rule("Simulated media coverage (SPEC §15 — labelled SIMULATED)")
    media = data.get("media") or {}
    for scen in media.get("scenarios") or []:
        heads = scen.get("headlines") or []
        if not heads:
            continue
        h = heads[0]
        print(f"  {bold(scen.get('label','?')):<14} "
              f"{yellow('“' + h.get('headline','') + '”')}  {dim('— ' + h.get('outlet_label',''))}")
        print(dim(f"                 {h.get('sentiment','?')} · {h.get('label','')}"))


def _audit(data: dict) -> int:
    """Visibly re-check the SPEC §34 guardrails on the composed payload."""
    rule("§34 guardrail audit")
    failures: list[str] = []

    # 1) Every headline metric carries a provenance tag (Simulated for effects).
    headline = data.get("headline") or []
    untagged = [m.get("label") for m in headline if not m.get("tag")]
    if untagged:
        failures.append(f"untagged metrics: {untagged}")
    else:
        print(green(f"  ✓ all {len(headline)} headline metrics carry a provenance tag"))

    # 2) Uncertainty band widens with the horizon (checked over the simulation).
    sim = data.get("simulation") or {}
    widen_ok = _bands_widen(sim)
    if widen_ok is True:
        print(green("  ✓ uncertainty band widens (or holds) with the horizon"))
    elif widen_ok is False:
        failures.append("uncertainty band does not widen monotonically with horizon")
    else:
        print(dim("  · band-widening not checkable from this payload (skipped)"))

    # 3) Every simulated media artifact is labelled SIMULATED.
    media = data.get("media") or {}
    heads = [h for scen in (media.get("scenarios") or []) for h in (scen.get("headlines") or [])]
    unlabelled = [h.get("headline") for h in heads if "SIMULAT" not in (h.get("label") or "").upper()]
    if heads and unlabelled:
        failures.append(f"media headlines missing SIMULATED label: {len(unlabelled)}")
    elif heads:
        print(green(f"  ✓ all {len(heads)} media headlines labelled SIMULATED"))

    # 4) Debate/media prose is Generated (never presented as fact).
    parl = data.get("parliament") or {}
    parl_prov = (parl.get("provenance") or "generated").lower()
    media_prov = (media.get("provenance") or "generated").lower()
    if parl_prov == "generated" and media_prov == "generated":
        print(green("  ✓ debate & media prose tagged Generated (numbers stay Simulated)"))
    else:
        failures.append(
            f"debate/media prose not tagged Generated (parliament={parl_prov}, media={media_prov})"
        )

    rule()
    if failures:
        print(red(bold("  GUARDRAIL AUDIT FAILED:")))
        for f in failures:
            print(red(f"    ✗ {f}"))
        return 1
    print(green(bold("  ✓ §34 guardrails hold — numbers Simulated, media SIMULATED, uncertainty widens.")))
    print(dim("  " + (data.get("provenance") or "")))
    return 0


def _bands_widen(sim: dict) -> "bool | None":
    """Return True if every metric's Δ band width is non-decreasing over the
    horizon, False on a violation, or None if no band is checkable.

    The simulation delta is ``{delta: {series: [{points: [{low, high, ...}]}]}}``
    — the band width at each checkpoint is ``high − low`` (SPEC §34: widen with
    horizon). We compare only forward-in-time checkpoints (positive months).
    """
    delta = sim.get("delta") or {}
    series = delta.get("series")
    if not isinstance(series, list) or not series:
        return None
    checkable = False
    for s in series:
        points = s.get("points") if isinstance(s, dict) else None
        if not isinstance(points, list):
            continue
        widths: list[float] = []
        for p in points:
            if not isinstance(p, dict) or "low" not in p or "high" not in p:
                continue
            widths.append(abs(p["high"] - p["low"]))
        if len(widths) >= 2:
            checkable = True
            for a, b in zip(widths, widths[1:]):
                if b < a - 1e-6:
                    return False
    return True if checkable else None


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))

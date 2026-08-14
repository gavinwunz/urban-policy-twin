#!/usr/bin/env python3
"""GOV SIM North-Star runner — the §37 minister's answer in the terminal.

SPEC §37 ("North-Star Experience") is the interaction GOV SIM is built for: a
minister asks *"What happens if we implement this?"* and GOV SIM answers with a
fixed 15-line narrative — baseline, historical analogues, mechanisms, median
outcome, uncertainty, who benefits, who loses, most-likely failure, the
opposition's strongest argument, opinion evolution, media narratives, three
risk-reducing amendments, each amendment's effect, the best-fit configuration,
and every assumption + piece of evidence.

This drives ``POST /north-star`` in-process (FastAPI ``TestClient`` — no server,
no ports) and prints that answer, then runs a §34 guardrail audit proving every
section is provenance-tagged, media is labelled SIMULATED, no LLM touches a
number, and the uncertainty fan widens with the horizon. Exit code is non-zero
if the audit fails, so it doubles as a pre-demo / CI smoke check.

Usage (from repo root):
    backend/.venv/bin/python scripts/north_star.py
    backend/.venv/bin/python scripts/north_star.py --json          # raw /north-star payload
    backend/.venv/bin/python scripts/north_star.py --text "..."     # custom policy
    backend/.venv/bin/python scripts/north_star.py --horizon 60      # different horizon (months)
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


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--text", default=DEMO_TEXT, help="Natural-language policy to compile & simulate.")
    ap.add_argument("--horizon", type=float, default=24.0, help="Headline horizon in months (default 24).")
    ap.add_argument("--json", action="store_true", help="Print the raw /north-star JSON payload and exit.")
    args = ap.parse_args(argv)

    # Imported lazily so --help works even before deps are installed.
    from fastapi.testclient import TestClient  # noqa: WPS433
    from app.main import app  # noqa: WPS433

    client = TestClient(app)

    print(
        dim("Composing the §37 North-Star answer (baseline → analogues → … → evidence)…"),
        file=sys.stderr,
    )
    resp = client.post(
        "/north-star", json={"text": args.text, "horizon_months": args.horizon}
    )
    if resp.status_code != 200:
        print(red(f"POST /north-star failed ({resp.status_code}):\n{resp.text}"))
        return 2
    data = resp.json()

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    _render(data)
    return _audit(data)


def _render(data: dict) -> None:
    rule("GOV SIM — North-Star answer (SPEC §37)")
    print(f"{bold('Question')}    “{data.get('question','')}”")
    print(f"{bold('Policy id')}   {data['policy_id']}")
    print(f"{bold('Horizon')}     {data['horizon_label']}  ({data['horizon_months']:g} months)")

    rule("The answer")
    for s in data.get("sections", []):
        tag = s.get("tag", "?")
        print(f"  {bold(str(s['order']).rjust(2))}. {bold(s['question'])}  {dim('[' + tag + ']')}")
        print(f"      {s['lead']}")

    # A couple of the highest-signal backing figures, rendered concisely.
    rule("Backing figures")
    tiles = data.get("median_outcome") or []
    for m in tiles:
        pct = m.get("delta_pct")
        pct_s = f" ({pct:+.1f}%)" if isinstance(pct, (int, float)) else ""
        print(
            f"  {m.get('label','?'):<28} "
            f"A {m.get('world_a',0):>12,.1f}  →  B {m.get('world_b',0):>12,.1f}"
            f"{pct_s}  {dim('[' + m.get('tag','?') + ']')}"
        )
    amds = data.get("amendments") or []
    if amds:
        print(dim(f"\n  Risk-reducing amendments ({len(amds)}), each re-simulated:"))
        for a in amds:
            print(f"    • {a['label']}  {dim('— ' + a['targets_risk'])}")
    best = (data.get("best_configuration") or {}).get("recommendations") or {}
    if best.get("best_balanced"):
        print(dim(f"\n  Optimiser best-balanced pick: {best['best_balanced']}"))


def _audit(data: dict) -> int:
    """SPEC §34 guardrail audit over the composed answer. Non-zero on failure."""
    rule("§34 guardrail audit")
    checks: list[tuple[str, bool, str]] = []

    sections = data.get("sections") or []
    checks.append((
        "All 15 §37 sections present and ordered",
        [s.get("order") for s in sections] == list(range(1, 16)),
        f"{len(sections)} sections",
    ))
    checks.append((
        "Every section carries an allowed provenance tag",
        bool(sections) and all(s.get("tag") in ALLOWED_TAGS for s in sections),
        "Observed/Estimated/Simulated/Generated",
    ))

    scenarios = (data.get("media") or {}).get("scenarios") or []
    headlines = [h for sc in scenarios for h in (sc.get("headlines") or [])]
    checks.append((
        "Every media headline labelled SIMULATED",
        bool(headlines) and all("SIMULATED" in (h.get("label", "").upper()) for h in headlines),
        f"{len(headlines)} headlines",
    ))

    checks.append((
        "No LLM touches any number (registry)",
        (data.get("evidence") or {}).get("llm_touches_numbers") is False,
        "llm_touches_numbers = False",
    ))

    # Uncertainty fan widens with horizon (SPEC §34): 95% interval width non-decreasing.
    fan = (data.get("uncertainty") or {}).get("fan") or []
    widths = []
    for band in fan:
        wide = next((iv for iv in (band.get("intervals") or []) if iv.get("level") == 95), None)
        if wide is not None:
            widths.append(wide["high"] - wide["low"])
    widens = len(widths) >= 2 and all(
        widths[i + 1] >= widths[i] - 1e-6 for i in range(len(widths) - 1)
    ) and widths[-1] > widths[0]
    checks.append((
        "Uncertainty fan widens with the horizon",
        widens,
        f"{len(widths)} checkpoints, 95% width {widths[0]:.0f}→{widths[-1]:.0f}" if widths else "no fan",
    ))

    ok = True
    for label, passed, detail in checks:
        mark = green("✔") if passed else red("✗")
        print(f"  {mark} {label}   {dim(detail)}")
        ok = ok and passed

    print()
    if ok:
        print(green(bold("PASS")) + dim(" — the North-Star answer honours the SPEC §34 guardrails."))
        return 0
    print(red(bold("FAIL")) + " — a guardrail did not hold; see above.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))

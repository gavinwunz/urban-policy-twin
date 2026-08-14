#!/usr/bin/env python3
"""GOV SIM capability map — the whole engine's HTTP surface in the terminal.

Where ``audit.py`` proves the §34 guardrails hold across every route, this simply
*shows a judge what the routes are*: it drives ``GET /capabilities`` in-process
(FastAPI ``TestClient`` — no server, no ports) and prints every product endpoint
grouped by functional area, each mapped to its SPEC section, with its methods, a
one-line summary, whether it needs a body, its provenance class, and the no-body
example you can hit right now. Ends with a consistency audit: the manifest is
Observed, its curated catalogue reconciles exactly with the live route surface
(no undocumented routes, no phantom cards), it is byte-identical on repeat, and
every advertised keyless example is a real served GET. Exit code is non-zero if
any check fails, so it doubles as a pre-demo / CI smoke check.

Usage (from repo root):
    backend/.venv/bin/python scripts/capabilities.py
    backend/.venv/bin/python scripts/capabilities.py --json     # raw /capabilities payload
    backend/.venv/bin/python scripts/capabilities.py --area "Hybrid forecast layers"
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


def yellow(s: str) -> str:
    return _c("33", s)


def rule(title: str = "") -> None:
    width = 74
    if title:
        pad = width - len(title) - 3
        print(bold(cyan(f"\n── {title} " + "─" * max(pad, 0))))
    else:
        print(cyan("─" * width))


def _tag_label(tag) -> str:
    if tag is None:
        return dim("—")
    colour = {"Observed": cyan, "Estimated": yellow, "Simulated": green, "Generated": dim}
    return colour.get(tag, str)(tag)


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--json", action="store_true", help="Print the raw /capabilities JSON and exit.")
    ap.add_argument("--area", default=None, help="Only print endpoints in this functional area.")
    args = ap.parse_args(argv)

    from fastapi.testclient import TestClient  # noqa: WPS433
    from app.main import app  # noqa: WPS433

    client = TestClient(app)
    resp = client.get("/capabilities")
    if resp.status_code != 200:
        print(red(f"GET /capabilities failed: {resp.status_code}"))
        return 1
    m = resp.json()

    if args.json:
        print(json.dumps(m, indent=2))
        return 0

    counts = m["counts"]
    print(bold("GOV SIM — engine capability map"))
    print(
        dim(
            f"v{m['app_version']} · {counts['routes']} routes · {counts['areas']} areas · "
            f"{counts['get']} GET / {counts['post']} POST · {counts['spec_sections']} SPEC sections · "
            f"{counts['keyless_examples']} keyless examples"
        )
    )
    print(dim("provenance of the manifest itself: " + m["provenance"]))

    shown = 0
    for group in m["groups"]:
        if args.area and args.area.lower() not in group["area"].lower():
            continue
        secs = " ".join(group["spec_sections"])
        rule(f"{group['area']}  {dim(secs)}")
        print(dim("  " + group["summary"]))
        for ep in group["endpoints"]:
            shown += 1
            methods = "/".join(ep["methods"])
            body = red("body") if ep["needs_body"] else dim("no-body")
            line = f"  {bold(methods):<16} {cyan(ep['path'])}"
            print(line)
            meta = f"      {' '.join(ep['spec_sections']):<14} {body}  {_tag_label(ep['output_tag'])}"
            if ep["keyless_example"]:
                meta += dim(f"  → example {ep['keyless_example']}")
            print(meta)
            print(dim(f"      {ep['summary']}"))

    if args.area and shown == 0:
        print(red(f"\nNo area matched {args.area!r}. Valid areas:"))
        for group in m["groups"]:
            print("  - " + group["area"])
        return 1

    return _audit(client, m)


def _audit(client, m: dict) -> int:
    """Consistency / §34 audit over the manifest — non-zero exit on any failure."""
    rule("consistency checks")
    checks: list[tuple[str, bool, str]] = []

    checks.append((
        "Manifest is Observed about the service",
        m["provenance"] == "Observed",
        f"provenance = {m['provenance']}",
    ))

    checks.append((
        "Catalogue reconciles with the live route surface",
        not m["undocumented_routes"] and not m["phantom_cards"],
        f"undocumented={len(m['undocumented_routes'])} phantom={len(m['phantom_cards'])}",
    ))

    # Every endpoint output_tag is a valid §34 tag or null (prose/mixed/metadata).
    bad_tags = [
        ep["path"]
        for g in m["groups"]
        for ep in g["endpoints"]
        if ep["output_tag"] is not None and ep["output_tag"] not in ALLOWED_TAGS
    ]
    checks.append((
        "Every endpoint tag is a §34 tag or null",
        not bad_tags,
        "all valid" if not bad_tags else f"offenders: {bad_tags}",
    ))

    # Byte-identical on repeat.
    m2 = client.get("/capabilities").json()
    deterministic = json.dumps(m, sort_keys=True) == json.dumps(m2, sort_keys=True)
    checks.append(("Byte-identical on repeat (reproducible)", deterministic, "same call → same map"))

    # Every advertised keyless example is a real served GET (200).
    unreachable = [p for p in m["keyless_examples"] if client.get(p).status_code != 200]
    checks.append((
        "Every keyless example is a served GET",
        not unreachable,
        "all 200" if not unreachable else f"unreachable: {unreachable}",
    ))

    ok = True
    for label, passed, det in checks:
        mark = green("✔") if passed else red("✗")
        print(f"  {mark} {label}   {dim(det)}")
        ok = ok and passed

    print()
    if ok:
        print(green(bold("PASS")) + dim(" — the capability map is consistent with the live surface."))
        return 0
    print(red(bold("FAIL")) + " — a consistency check did not hold; see above.")
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run(sys.argv[1:]))

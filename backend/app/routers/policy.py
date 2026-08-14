"""Policy compiler endpoint (SPEC §3, Step 2).

``POST /policy/compile`` turns natural-language policy text into the structured
Policy DSL, exposing every extracted assumption for human correction. The LLM is
used only for language structuring with a deterministic rule-based fallback;
neither path produces numeric simulation effects (SPEC §34).
"""

from __future__ import annotations

import hashlib
import json

from fastapi import APIRouter

from ..db import mongo
from ..policy import compile_policy
from ..policy.dsl import CompileRequest, CompileResponse

router = APIRouter(prefix="/policy", tags=["policy"])


@router.post("/compile", response_model=CompileResponse, summary="Compile NL policy → DSL")
def compile_endpoint(req: CompileRequest) -> CompileResponse:
    """Compile ``req.text`` into a Policy DSL plus reviewable assumptions.

    ``method`` reports whether the LLM or the rule-based fallback produced the
    DSL. ``assumptions`` lists every inferred/defaulted field so the frontend can
    render an editable panel (SPEC §3: never bury assumptions).
    """
    result = compile_policy(req.text, req.jurisdiction)

    # Persist the compiled policy so a later run can be traced back to the exact
    # text and DSL that produced it. Content-addressed, so recompiling the same
    # prose updates one document rather than accumulating duplicates. A Mongo
    # outage must not fail a compile, so this is best-effort by construction.
    dsl = result.policy.model_dump(mode="json")
    policy_hash = hashlib.sha256(
        json.dumps(dsl, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]
    mongo.save_policy(
        policy_hash,
        {
            "text": req.text,
            "jurisdiction": req.jurisdiction,
            "dsl": dsl,
            "method": result.method,
        },
    )
    return result

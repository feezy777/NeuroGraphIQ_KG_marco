"""Prompt for the circuit semantic novelty comparison.

One call, two pools, one verdict per target Circuit. The prompt carries the
TARGET run's circuits and the PRIOR pool they must be judged against, and asks
for a classification of each target circuit into the frozen vocabulary.

Design notes that are deliberate:

  * The vocabulary and the counting rule are rendered FROM the schema module, so
    the prompt cannot drift from the contract it is asking the model to obey.

  * No `confidence` is sent. Discovery confidence is the model's own belief about
    a hypothesis, and the assessor is forbidden from using it as novelty
    evidence; the surest way to obey that is not to show it the number at all.

  * The prior pool carries each earlier circuit's CONTEXT, not just its name,
    because "is this the same concept?" is not answerable from a name: the
    Round-4/5 audits found genuine reformulations and genuine distinctions that
    only the description separated.

  * Nothing here instructs the model to be decisive. The uncertainty rule points
    at BORDERLINE, and BORDERLINE counts as novelty — so a model that is unsure
    does not silently shrink the count.
"""
from __future__ import annotations

import json
from typing import Any

from app.schemas.circuit_novelty import NOVELTY_CLASSES

#: Frozen prompt identity, stored on every persisted assessment so a judgement
#: can always be traced to the exact instructions that produced it. Bump
#: PROMPT_VERSION whenever the instructions or the class definitions change —
#: a bumped version is a DIFFERENT assessment, i.e. a new row, never an edit.
PROMPT_KEY = "knowledge_production.circuit_novelty"
PROMPT_VERSION = "1.0.0"

SYSTEM_PROMPT = """\
You compare newly discovered neural CIRCUIT candidates against circuits that were
already discovered for the same brain region and the same discovery view.

Your job is NOT to decide what is true, and NOT to tidy a list. It is to answer,
for each NEW circuit, one question: has this concept already been found?

Classify each new circuit as exactly one of:

  NEW             A meaningfully distinct circuit concept. Nothing already found
                  describes this.
  ALIAS           The SAME circuit concept under another established name. Both
                  names refer to one thing, and a reader who knew both would say
                  they are the same.
  REFORMULATION   The same underlying circuit concept, expressed differently —
                  re-described, re-scoped, or renamed after a different author
                  or model — but not a distinct piece of knowledge.
  BORDERLINE      Possibly distinct, but you do not have a sufficient basis to
                  collapse it into anything already found.

WHEN IN DOUBT, CHOOSE BORDERLINE.

This matters more than precision. A circuit wrongly collapsed into an earlier
one is lost from discovery and can never be recovered by a later round. A
circuit carried forward as BORDERLINE costs one extra row for a later, evidence-
backed layer to judge. Those two errors are not equally bad, so do not resolve
uncertainty toward collapsing:

  * unsure whether it is NEW or an ALIAS            -> BORDERLINE
  * unsure whether it is NEW or a REFORMULATION     -> BORDERLINE
  * same words but a different scope or mechanism   -> BORDERLINE
  * confidently the same concept, different name    -> ALIAS
  * confidently the same concept, re-described      -> REFORMULATION

Judge on MEANING, not on wording. Two circuits with different names may be the
same concept, and two with similar names may be different mechanisms at
different scales. Use each circuit's description, rationale, topology and
participating regions — not its name alone.

You are not asked whether a circuit is correct, well-evidenced, well-named or
scientifically important. Only whether it is already present in the prior list.

Reply with JSON only, no prose around it:

{"verdicts": [
  {"candidate_id": "<the target circuit's candidate_id, copied exactly>",
   "novelty_class": "NEW" | "ALIAS" | "REFORMULATION" | "BORDERLINE",
   "matched_prior_candidate_id": "<candidate_id of the earlier circuit, or null>",
   "short_reason": "<one sentence>"}
]}

Rules for the reply:
  * Exactly one verdict for EVERY circuit in the TARGET list. Do not skip any,
    and do not invent any.
  * `matched_prior_candidate_id` is REQUIRED for ALIAS and REFORMULATION and
    must be a candidate_id taken from the PRIOR list. Never invent an id.
  * `matched_prior_candidate_id` is null for NEW, and optional for BORDERLINE
    (use it when there is one specific earlier circuit you were unsure about).
"""


def _circuit_payload(circuit: Any) -> dict[str, Any]:
    """One circuit as the model should see it: context, no confidence."""
    return {
        "candidate_id": circuit.candidate_id,
        "name": circuit.name,
        "description": circuit.description,
        "rationale": circuit.rationale,
        "topology_hint": circuit.topology_hint,
        "region_refs": list(circuit.region_refs),
        "connection_refs": list(circuit.connection_refs),
        "function_refs": list(circuit.function_refs),
    }


def build_novelty_prompt(*, target: Any, prior: Any, seed_entity_id: str,
                         discovery_view: str | None) -> dict[str, str]:
    """Return ``{"system_prompt": ..., "user_prompt": ...}`` for one call.

    Both pools are rendered in full. The prior pool is what makes the judgement
    possible at all: a model shown only names would be guessing.
    """
    body = {
        "seed_entity_id": seed_entity_id,
        "discovery_view": discovery_view,
        "task": (
            "Classify every circuit in TARGET_NEW_CIRCUITS against "
            "PRIOR_ALREADY_DISCOVERED_CIRCUITS."
        ),
        "classes": list(NOVELTY_CLASSES),
        "prior_already_discovered_circuits": [
            _circuit_payload(c) for c in prior
        ],
        "target_new_circuits": [_circuit_payload(c) for c in target],
    }
    return {
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": json.dumps(body, ensure_ascii=False, indent=1),
    }

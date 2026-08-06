"""Pure ONT_* validation rule builders (no DB / no network).

These builders produce the ontology-related checks defined in the Phase 1
spec: 3 hard rules (term anchored, predicate known, enum valid) + 1 soft
rule (region external alignment).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OntologyCheck:
    rule_code: str
    severity: str
    status: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def build_ontology_function_checks(
    *,
    function_term: str | None,
    term_status: str | None,
    relation_type: str | None,
    active_relation_types: set[str],
    category: str | None,
    active_categories: set[str],
    domain: str | None,
    active_domains: set[str],
    role: str | None,
    active_roles: set[str],
    effect_type: str | None,
    active_effect_types: set[str],
) -> list[OntologyCheck]:
    """Build ONT_* checks for a function-like record."""
    checks: list[OntologyCheck] = []
    term = (function_term or "").strip()
    if term and term_status != "active":
        checks.append(
            OntologyCheck(
                rule_code="ONT_TERM_UNGROUNDED",
                severity="blocker",
                status="blocked",
                message="function_term is not anchored to an active ontology term",
                details={"function_term": term, "term_status": term_status},
            )
        )
    if relation_type and relation_type not in active_relation_types:
        checks.append(
            OntologyCheck(
                rule_code="ONT_PREDICATE_UNKNOWN",
                severity="blocker",
                status="blocked",
                message=f"relation_type not in active ontology vocabulary: {relation_type}",
                details={"relation_type": relation_type},
            )
        )
    enum_fields = (
        ("category", category, active_categories),
        ("domain", domain, active_domains),
        ("role", role, active_roles),
        ("effect_type", effect_type, active_effect_types),
    )
    for field_name, value, allowed in enum_fields:
        if value and allowed and value not in allowed:
            checks.append(
                OntologyCheck(
                    rule_code="ONT_ENUM_INVALID",
                    severity="blocker",
                    status="blocked",
                    message=f"invalid {field_name} for ontology vocabulary: {value}",
                    details={"field": field_name, "value": value},
                )
            )
    return checks


def build_region_alignment_checks(
    *,
    uberon_iri: str | None,
    nifstd_iri: str | None,
) -> list[OntologyCheck]:
    """Soft warning when a brain region has no external standard identifier."""
    if not (uberon_iri or "").strip() and not (nifstd_iri or "").strip():
        return [
            OntologyCheck(
                rule_code="ONT_REGION_ALIGNMENT_MISSING",
                severity="warning",
                status="warning",
                message="region has no UBERON/NIFSTD external identifier",
                details={"uberon_iri": uberon_iri, "nifstd_iri": nifstd_iri},
            )
        ]
    return []

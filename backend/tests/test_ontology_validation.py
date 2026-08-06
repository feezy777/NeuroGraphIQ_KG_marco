"""Pure ONT_* validation rule tests (no DB, no network)."""

from __future__ import annotations

from app.services.ontology_validation_rules import (
    build_ontology_function_checks,
    build_region_alignment_checks,
    build_term_status_checks,
)

ACTIVE_RELATIONS = {"associated_with", "modulates", "unknown"}
ACTIVE_CATEGORIES = {"memory", "motor", "unknown"}


def test_term_ungrounded_blocker():
    checks = build_ontology_function_checks(
        function_term="novel phrase",
        term_status=None,
        relation_type="associated_with",
        active_relation_types=ACTIVE_RELATIONS,
        category="memory",
        active_categories=ACTIVE_CATEGORIES,
        domain=None,
        active_domains=set(),
        role=None,
        active_roles=set(),
        effect_type=None,
        active_effect_types=set(),
    )
    codes = [c.rule_code for c in checks]
    assert "ONT_TERM_UNGROUNDED" in codes
    assert checks[0].severity == "blocker"


def test_proposed_term_is_blocker():
    checks = build_ontology_function_checks(
        function_term="memory",
        term_status="proposed",
        relation_type="associated_with",
        active_relation_types=ACTIVE_RELATIONS,
        category="memory",
        active_categories=ACTIVE_CATEGORIES,
        domain=None,
        active_domains=set(),
        role=None,
        active_roles=set(),
        effect_type=None,
        active_effect_types=set(),
    )
    assert any(c.rule_code == "ONT_TERM_UNGROUNDED" for c in checks)


def test_predicate_unknown_blocker():
    checks = build_ontology_function_checks(
        function_term="memory",
        term_status="active",
        relation_type="bogus_relation",
        active_relation_types=ACTIVE_RELATIONS,
        category="memory",
        active_categories=ACTIVE_CATEGORIES,
        domain=None,
        active_domains=set(),
        role=None,
        active_roles=set(),
        effect_type=None,
        active_effect_types=set(),
    )
    assert any(c.rule_code == "ONT_PREDICATE_UNKNOWN" for c in checks)


def test_enum_invalid_blocker():
    checks = build_ontology_function_checks(
        function_term="memory",
        term_status="active",
        relation_type="associated_with",
        active_relation_types=ACTIVE_RELATIONS,
        category="bogus_category",
        active_categories=ACTIVE_CATEGORIES,
        domain="bogus_domain",
        active_domains={"memory"},
        role=None,
        active_roles=set(),
        effect_type=None,
        active_effect_types=set(),
    )
    codes = [c.rule_code for c in checks]
    assert codes.count("ONT_ENUM_INVALID") == 2


def test_all_passed_no_checks():
    checks = build_ontology_function_checks(
        function_term="memory",
        term_status="active",
        relation_type="associated_with",
        active_relation_types=ACTIVE_RELATIONS,
        category="memory",
        active_categories=ACTIVE_CATEGORIES,
        domain=None,
        active_domains=set(),
        role=None,
        active_roles=set(),
        effect_type=None,
        active_effect_types=set(),
    )
    assert checks == []


def test_region_alignment_warning():
    checks = build_region_alignment_checks(uberon_iri=None, nifstd_iri="")
    assert len(checks) == 1
    assert checks[0].rule_code == "ONT_REGION_ALIGNMENT_MISSING"
    assert checks[0].severity == "warning"


def test_region_alignment_present_no_warning():
    assert build_region_alignment_checks(uberon_iri="http://purl.obolibrary.org/obo/UBERON_0001946", nifstd_iri=None) == []


def test_term_status_ungrounded_blocker():
    checks = build_term_status_checks(function_term="memory", term_id=None, term_status=None)
    assert checks[0].rule_code == "ONT_TERM_UNGROUNDED"
    assert checks[0].severity == "blocker"


def test_term_status_proposed_warning():
    checks = build_term_status_checks(function_term="memory", term_id="t1", term_status="proposed")
    assert checks[0].rule_code == "ONT_TERM_NOT_ACTIVE"
    assert checks[0].severity == "warning"


def test_term_status_deprecated_blocker_with_replacement():
    checks = build_term_status_checks(
        function_term="memory", term_id="t1", term_status="merged",
        replaced_by_term_code="ng:func:memory_v2",
    )
    assert checks[0].rule_code == "ONT_TERM_DEPRECATED"
    assert checks[0].severity == "blocker"
    assert checks[0].details["replaced_by_term_code"] == "ng:func:memory_v2"


def test_term_status_active_no_checks():
    assert build_term_status_checks(function_term="memory", term_id="t1", term_status="active") == []

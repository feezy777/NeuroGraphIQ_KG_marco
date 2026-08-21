"""CN1.2-2A: frozen connection mapping rules (pure unit tests, no DB)."""

from __future__ import annotations

import uuid

import pytest

from app.services import connection_mapping_service as cms

SRC = uuid.uuid4()
TGT = uuid.uuid4()


# --------------------------------------------------------------------------- #
# map_connection_type
# --------------------------------------------------------------------------- #


def test_map_structural():
    assert cms.map_connection_type("structural_connection") == "structural"


def test_map_projection_to_structural():
    assert cms.map_connection_type("projection") == "structural"


def test_map_functional():
    assert cms.map_connection_type("functional_connectivity") == "functional"
    assert cms.map_connection_type("effective_connectivity") == "functional"


def test_map_remaining_types():
    assert cms.map_connection_type("coactivation") == "coactivation"
    assert cms.map_connection_type("association") == "association"
    assert cms.map_connection_type("uncertain_connection") == "uncertain"
    assert cms.map_connection_type("unknown") == "uncertain"
    # empty values degrade to unknown -> uncertain
    assert cms.map_connection_type(None) == "uncertain"
    assert cms.map_connection_type("") == "uncertain"


def test_map_unmapped_type_raises():
    with pytest.raises(cms.ConnectionMappingError, match="unmapped"):
        cms.map_connection_type("quantum")


# --------------------------------------------------------------------------- #
# map_directionality_policy
# --------------------------------------------------------------------------- #


def test_directionality_kept():
    assert cms.map_directionality_policy("directed") == "directed"
    assert cms.map_directionality_policy("source_to_target") == "directed"
    assert cms.map_directionality_policy("bidirectional") == "bidirectional"
    assert cms.map_directionality_policy("undirected") == "undirected"


def test_directionality_unknown_to_unspecified():
    assert cms.map_directionality_policy("unknown") == "unspecified"
    assert cms.map_directionality_policy(None) == "unspecified"
    assert cms.map_directionality_policy("") == "unspecified"


def test_directionality_unmapped_raises():
    with pytest.raises(cms.ConnectionMappingError, match="unmapped"):
        cms.map_directionality_policy("sideways")


# --------------------------------------------------------------------------- #
# normalize_macro_connection_key
# --------------------------------------------------------------------------- #


def test_key_ab_and_ba_not_merged():
    ab = cms.normalize_macro_connection_key(SRC, TGT, "structural")
    ba = cms.normalize_macro_connection_key(TGT, SRC, "structural")
    assert ab != ba  # directional identity, no auto reverse merge


def test_key_structural_and_functional_not_merged():
    a = cms.normalize_macro_connection_key(SRC, TGT, "structural")
    b = cms.normalize_macro_connection_key(SRC, TGT, "functional")
    assert a != b


def test_key_has_no_confidence_component():
    key = cms.normalize_macro_connection_key(SRC, TGT, "functional")
    assert key == (str(SRC), str(TGT), "functional")  # 3-tuple, confidence absent


def test_key_accepts_str_ids_and_rejects_raw_type():
    assert cms.normalize_macro_connection_key(str(SRC), str(TGT), "association") == (
        str(SRC),
        str(TGT),
        "association",
    )
    # clearly-raw mirror values are rejected — the batch must map first
    with pytest.raises(cms.ConnectionMappingError, match="canonical connection_type"):
        cms.normalize_macro_connection_key(SRC, TGT, "structural_connection")
    # NOTE: "projection" exists in BOTH value spaces (mirror raw -> structural,
    # canonical enum value -> projection), so membership validation cannot
    # detect it; the frozen rule is that callers ALWAYS map first via
    # map_connection_type (mirror "projection" -> "structural", see
    # test_map_projection_to_structural), then normalize keys the mapped value.


def test_key_projection_ambiguity_resolved_by_mapping_first():
    raw = "projection"
    mapped = cms.map_connection_type(raw)
    assert mapped == "structural"
    key = cms.normalize_macro_connection_key(SRC, TGT, mapped)
    assert key == (str(SRC), str(TGT), "structural")
    # an explicitly canonical projection concept keys as "projection"
    assert cms.normalize_macro_connection_key(SRC, TGT, "projection") == (
        str(SRC),
        str(TGT),
        "projection",
    )


# --------------------------------------------------------------------------- #
# build_connection_provenance
# --------------------------------------------------------------------------- #


def test_provenance_preserved():
    p = cms.build_connection_provenance(
        [SRC, TGT],
        ["structural_connection", "projection"],
        [0.8, 0.7],
    )
    assert p == {
        "original_connection_ids": [str(SRC), str(TGT)],
        "original_relation_types": ["structural_connection", "projection"],
        "original_confidence": [0.8, 0.7],
        "mapping_method": "macro96_canonical_connection_v1",
    }


def test_provenance_with_endpoint_grounding():
    grounding = {
        "grounding_source": "candidate_brain_regions.canonical_region_id",
        "source_canonical_region_id": str(SRC),
    }
    p = cms.build_connection_provenance(
        [SRC],
        ["structural_connection"],
        [0.5],
        endpoint_grounding=grounding,
    )
    assert p["endpoint_grounding"] == grounding
    assert set(p.keys()) == {
        "original_connection_ids",
        "original_relation_types",
        "original_confidence",
        "mapping_method",
        "endpoint_grounding",
    }


def test_provenance_custom_method_and_none_confidence():
    p = cms.build_connection_provenance(
        [SRC],
        ["unknown"],
        [None],
        mapping_method="custom_v2",
    )
    assert p["original_confidence"] == [None]
    assert p["mapping_method"] == "custom_v2"


def test_provenance_length_mismatch_rejected():
    with pytest.raises(cms.ConnectionMappingError, match="same length"):
        cms.build_connection_provenance([SRC], ["structural_connection", "projection"], [0.8])


def test_provenance_empty_rejected():
    with pytest.raises(cms.ConnectionMappingError, match="must not be empty"):
        cms.build_connection_provenance([], [], [])

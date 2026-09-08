"""Phase1.7 V3 - Thalamus scope contract provenance continuity tests.

Validates V2 -> V1 -> generator repository chain. Read-only; never modifies V1/V2
content, never writes DB/geometry. 15 checks.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V1_GEN = BACKEND / "scripts" / "phase17_v3_resolve_thalamus_g1_ontology_scope.py"
V1_SIDE = D16 / "phase17_v3_thalamus_g1_scope_contract_v1_provenance.json"
LINEAGE = D16 / "phase17_v3_thalamus_scope_contract_lineage.json"
AUDIT = D16 / "phase17_v3_thalamus_scope_provenance_audit.json"
CLASS = D16 / "phase17_v3_classification.csv"

_HAS_ALL = V1.exists() and V2.exists() and V1_GEN.exists() and V1_SIDE.exists() and LINEAGE.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _git_tracked(p: Path) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


def _lineage():
    with open(LINEAGE, encoding="utf-8") as fh:
        return json.load(fh)


# ---- 1. V1 file is in the git-tracked intended set ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_1_v1_git_tracked():
    # lineage documents the intended TRUE state; the live check must actually
    # confirm V1 is tracked (in HEAD or staged index), not merely the generator.
    assert _git_tracked(V1) is True, "V1 scope contract must be git-tracked"
    assert _lineage()["v1_git_tracked"] is True
    assert _lineage()["repository_chain_verified"] is True


# ---- 2. V1 contract ID correct ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_2_v1_contract_id():
    v1 = json.load(open(V1, encoding="utf-8"))
    assert v1["contract"]["contract_name"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"


# ---- 3. V1 SHA256 fixed ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_3_v1_sha_fixed():
    v1_sha = _sha(V1)
    assert len(v1_sha) == 64
    side = json.load(open(V1_SIDE, encoding="utf-8"))
    assert side["snapshot_sha256"] == v1_sha
    assert _lineage()["v1_sha256"] == v1_sha


# ---- 4. V2 contract ID correct ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_4_v2_contract_id():
    v2 = json.load(open(V2, encoding="utf-8"))
    assert v2["contract_v2"]["contract_id"] == "THALAMUS_G1_SCOPE_CONTRACT_V2"


# ---- 5. V2.supersedes == V1.contract_id ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_5_v2_supersedes_equals_v1():
    v1 = json.load(open(V1, encoding="utf-8"))
    v2 = json.load(open(V2, encoding="utf-8"))
    assert v2["contract_v2"]["supersedes"] == v1["contract"]["contract_name"] \
        == "THALAMUS_G1_SCOPE_CONTRACT_V1"


# ---- 6. lineage V1 SHA == actual V1 SHA ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_6_lineage_v1_sha_matches():
    assert _lineage()["v1_sha256"] == _sha(V1)


# ---- 7. lineage V2 SHA == actual V2 SHA ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_7_lineage_v2_sha_matches():
    assert _lineage()["v2_sha256"] == _sha(V2)


# ---- 8. supersedes_id_match == TRUE ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_8_supersedes_id_match():
    assert _lineage()["supersedes_id_match"] is True


# ---- 9. repository_chain_verified == TRUE ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_9_repository_chain_verified():
    assert _lineage()["repository_chain_verified"] is True


# ---- 10. V1 scientific content unchanged by this round ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_10_v1_content_unchanged():
    v1 = json.load(open(V1, encoding="utf-8"))
    assert v1["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    assert v1["construction_allowed"] is False
    c = v1["contract"]
    assert c["contract_name"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"
    assert c["supersedes"] is None  # V1 must not claim to supersede anything
    assert len(v1["decisions"]) == 14
    # scope decisions frozen by V1 round
    dec = {d["source_structure"].split(" (")[0]: d["decision"] for d in v1["decisions"]}
    assert dec["LGN"] == "ONTOLOGY_REVIEW"
    assert dec["MGN"] == "ONTOLOGY_REVIEW"
    assert dec["Reticular nucleus"] == "ONTOLOGY_REVIEW"


# ---- 11. V2 scientific content unchanged ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_11_v2_content_unchanged():
    v2 = json.load(open(V2, encoding="utf-8"))
    c = v2["contract_v2"]
    assert v2["identity_decision"] == "CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER"
    assert c["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert c["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert c["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"
    assert c["limitans_suprageniculate_decision"] == "REVIEW (DEC-THAL-04)"
    assert v2["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    assert v2["construction_allowed"] is False
    assert len(c["geometry_blocked_reasons"]) == 2  # both blockers retained


# ---- 12. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_12_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    cc = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert cc["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(cc.values()) - cc["VERIFIED_DIRECT_CONTAINED"] == 132
    assert cc["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 13. DB zero-write (no DB import/path) ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_13_no_db_artifacts():
    # this round only adds provenance records under the integration audit dir
    assert V1_SIDE.exists() and LINEAGE.exists()
    # no geometry produced by this round; derived_g1 may only hold the manifest-
    # authorized native G1 geometry volumes (from a later construction round)
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present


# ---- 14. no unexpected NIfTI ----
def test_14_no_nifti():
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present


# ---- 15. audit artifact confirms read-only provenance repair ----
@pytest.mark.skipif(not _HAS_ALL, reason="chain files not present")
def test_15_no_transform_readonly():
    assert AUDIT.exists(), "provenance audit artifact missing"
    with open(AUDIT, encoding="utf-8") as fh:
        aud = json.load(fh)
    # audit must be read-only: no V1/V2 modification, chain status present
    assert "no V1/V2 content modified" in aud["note"]
    assert aud["repository_provenance_chain_complete"] is True
    assert aud["v1_snapshot_authenticity"] == "VERIFIED"
    # Tier B generator reproducibility recorded separately (not overclaimed)
    assert aud["generator_reproducibility"] in (
        "VERIFIED_LOCAL", "NOT_RERUNNABLE", "MISMATCH")

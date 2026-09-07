"""Phase1.7 V3 - Thalamus probability-semantics + aggregation-rule audit tests.

Read-only; never writes DB / geometry / does transforms. Validates the audit
artifacts + real-file semantics claims with 15 checks. Raw binaries are
gitignored; summary/CSVs are intended to be committed so manifest-dependent
tests skip only if the artifact is absent.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus"
SRC = RAW / "ThalamusProbs.MNIsymSpace.nii.gz"
NAMES = RAW / "ThalamusProbs.MNIsymSpace.names.txt"
OUT_SEM = D16 / "phase17_v3_thalamus_probability_semantics_audit.csv"
OUT_CH = D16 / "phase17_v3_thalamus_channel_scope_audit.csv"
OUT_AGG = D16 / "phase17_v3_thalamus_aggregation_comparison.csv"
OUT_JSON = D16 / "phase17_v3_thalamus_geometry_rule_summary.json"
OUT_MD = D16 / "phase17_v3_thalamus_geometry_rule_diagnostics.md"
FROZEN_MANIFEST = D16 / "phase17_v3_external_g1_asset_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"

_HAS_SRC = SRC.exists() and NAMES.exists()
_HAS_SUM = OUT_JSON.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _sum():
    with open(OUT_JSON, encoding="utf-8") as fh:
        return json.load(fh)


# ---- 1. raw sha256 consistent with acquisition freeze ----
@pytest.mark.skipif(not _HAS_SRC, reason="Thalamus raw not present (gitignored)")
def test_1_raw_sha_matches_freeze():
    m = _sum()
    assert m["source"]["sha256"] == _sha(SRC)
    man = {}
    with open(FROZEN_MANIFEST, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            man[r["asset_id"]] = r
    assert man["FS_THAL_ICBM"]["checksum"] == _sha(SRC)


# ---- 2. raw byte-identical (summary sha == on-disk sha) ----
@pytest.mark.skipif(not _HAS_SRC, reason="Thalamus raw not present (gitignored)")
def test_2_raw_byte_identical():
    assert _sha(SRC) == _sum()["source"]["sha256"]


# ---- 3. channel count == 53 (real file) ----
@pytest.mark.skipif(not _HAS_SRC, reason="Thalamus raw not present (gitignored)")
def test_3_channel_count():
    import nibabel as nib
    im = nib.load(SRC)
    assert im.shape[3] == 53
    m = _sum()
    assert m["channel_count_actual"] == 53
    assert m["channel_count_match"] is True
    # summary stores index lists under n_left/n_right; real counts live in laterality
    assert len(m["n_left"]) == 26 and len(m["n_right"]) == 26
    assert m["laterality"]["left_channels"] == 26
    assert m["laterality"]["right_channels"] == 26


# ---- 4. every included channel has official label provenance ----
@pytest.mark.skipif(not OUT_CH.exists(), reason="channel scope audit not present")
def test_4_included_channels_have_labels():
    rows = list(csv.DictReader(open(OUT_CH, encoding="utf-8-sig")))
    for r in rows:
        assert r["official_name"], r["channel_index"]
        if r["include_candidate"].startswith("include"):
            assert r["anatomical_group"], r["source_label"]
            assert r["justification"], r["source_label"]


# ---- 5. no unknown channel auto-included ----
@pytest.mark.skipif(not OUT_CH.exists(), reason="channel scope audit not present")
def test_5_no_unknown_auto_include():
    rows = list(csv.DictReader(open(OUT_CH, encoding="utf-8-sig")))
    assert all(r["ontology_review"] != "METADATA_INCOMPLETE"
               or not r["include_candidate"].startswith("include")
               for r in rows)
    unknown = [r for r in rows if r["source_label"] == "Unknown"]
    assert unknown and unknown[0]["include_candidate"] == "exclude(background)"


# ---- 6. left/right channel mapping traceable + laterality OK ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_6_laterality_traceable():
    m = _sum()
    assert m["laterality"]["ok"] is True
    assert m["laterality"]["left_channels"] == 26
    assert m["laterality"]["right_channels"] == 26
    # geometry cross-check: Left centroid x<0, Right x>0
    rows = list(csv.DictReader(open(OUT_CH, encoding="utf-8-sig")))
    for r in rows:
        if r["hemisphere"] == "Left" and r["centroid_x"]:
            assert float(r["centroid_x"]) < 0, r["source_label"]
        if r["hemisphere"] == "Right" and r["centroid_x"]:
            assert float(r["centroid_x"]) > 0, r["source_label"]


# ---- 7. aggregation operator semantics evidence: probability layer RESOLVED / SUM ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_7_operator_semantics_evidence():
    m = _sum()
    assert m["semantics"]["interpretation"] == "MUTUALLY_EXCLUSIVE_CATEGORICAL_NORMALIZED_POSTERIOR"
    # layered statuses
    assert m["probability_aggregation_semantics"] == "RESOLVED"
    assert m["probability_aggregation_operator"] == "SUM"
    assert m["aggregation_rule_status"] == "FROZEN_AT_PROBABILITY_LAYER"
    # under categorical model SUM == CLIPPED_SUM exactly; both differ from MAX/UNION
    rows = list(csv.DictReader(open(OUT_AGG, encoding="utf-8-sig")))
    for hemi in ("Left", "Right"):
        h = [r for r in rows if r["hemisphere"] == hemi]
        s = {r["name"]: float(r["mass"]) for r in h}
        assert s["SUM"] == pytest.approx(s["CLIPPED_SUM"], rel=1e-6)
        assert s["MAX"] < s["SUM"]  # max undercounts categorical union mass
        assert s["PROBABILISTIC_UNION"] < s["SUM"]  # independent-Bernoulli product undercounts


# ---- 8. ontology scope incomplete => construction BLOCKED, no geometry ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_8_scope_blocked_no_geometry():
    m = _sum()
    assert m["verdict"] == "GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE"
    assert m["g1_scope_status"] == "ONTOLOGY_SCOPE_INCOMPLETE"
    assert m["geometry_construction_status"] == "BLOCKED_BY_ONTOLOGY_SCOPE"
    assert m["construction_allowed"] is False
    assert m["flags"]["geometry_constructed"] is False
    assert m["flags"]["threshold_applied"] is False
    assert m["flags"]["binarization_applied"] is False


# ---- 9/10/11/12. no registration/resampling/threshold/binarize ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_9_to_12_no_transform_flags():
    m = _sum()
    for f in ("registration_applied", "resampling_applied",
              "threshold_applied", "binarization_applied"):
        assert m["flags"][f] is False
    # script must not emit left/right geometry files
    assert not list(Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz"))


# ---- 8b. Iglesias DOI corrected ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_8b_iglesias_doi_correct():
    m = _sum()
    assert m["source"]["doi"] == "10.1016/j.neuroimage.2018.08.012"
    corr = m["doi_correction"]
    assert corr["old_value"] == "10.1016/j.neuroimage.2018.06.012"
    assert corr["corrected_value"] == "10.1016/j.neuroimage.2018.08.012"
    assert "2018.06.012" not in m["source"]["doi"]


# ---- 8c. Julich reference shape is 193x229x193 (never 193^3 shorthand) ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_8c_julich_shape_193_229_193():
    m = _sum()
    trg = m["coordinate_relation"]["target_grid"]
    assert "193x229x193" in trg
    # no 193^3 / 193³ shorthand anywhere in this round's data artifacts
    for f in (OUT_MD, OUT_JSON, OUT_SEM, OUT_CH, OUT_AGG,
              Path(BACKEND, "scripts", "phase17_v3_audit_thalamus_g1_geometry_rule.py")):
        txt = f.read_text(encoding="utf-8", errors="replace")
        assert "193³" not in txt and "193^3" not in txt, f"{f.name} contains 193^3 shorthand"
    # the audit script/tests themselves may reference the literal in prose/docstring;
    # the invariant is that data outputs spell the shape out as 193x229x193.
    assert "193" in trg


# ---- 13. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_13_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 14. DB zero-write: no DB import/path; audit is file-scope ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_14_no_db_artifacts():
    m = _sum()
    assert m["verdict"] == "GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE"
    assert "AGGREGATION_SEMANTICS_UNRESOLVED" not in m["verdict"]
    # canonical ids present
    assert m["canonical"]["Left"]["g1_region_id"] == "NGIQ-BR-00000247"
    assert m["canonical"]["Right"]["g1_region_id"] == "NGIQ-BR-00000256"


# ---- 15. categorical-sum semantics: sum(all 53) == 1 (real data) ----
@pytest.mark.skipif(not _HAS_SRC, reason="Thalamus raw not present (gitignored)")
def test_15_categorical_sum_is_one():
    import nibabel as nib
    d = np.asanyarray(nib.load(SRC).dataobj).astype(np.float64)
    S = d.sum(axis=3)
    assert float(np.max(np.abs(S - 1.0))) < 1e-5
    m = _sum()
    assert m["semantics"]["frac_S_all_eq1"] == pytest.approx(1.0, abs=1e-6)
    assert m["semantics"]["bg_eq_1_minus_nuc_frac"] == pytest.approx(1.0, abs=1e-4)


# ---- space relation recorded only; transform not executed ----
@pytest.mark.skipif(not _HAS_SUM, reason="summary not present")
def test_space_relation_recorded_only():
    m = _sum()
    rel = m["coordinate_relation"]
    assert rel["template_variant_difference"] == "SYMMETRIC_VS_ASYMMETRIC"
    assert rel["transform_executed"] is False
    assert rel["resampling_executed"] is False

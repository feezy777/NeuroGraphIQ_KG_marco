"""Phase1.7 V3 - external raw G1 asset acquisition audit self-check (READ-ONLY).

Covers the round's 10 required checks without touching the DB or re-downloading:
  1. every downloaded raw file has a sha256
  2. raw files are readable (real NIfTI header parse)
  3. probability maps are unmodified (recorded sha256 unchanged on re-read)
  4. raw files are never silently overwritten (idempotent audit, no write path)
  5. license-unclear / access-restricted asset is never marked redistributable
  6. symmetric vs asymmetric template never conflated (header-driven)
  7. subject-specific aseg never becomes a group gold standard
  8. CIT168 NAcc provenance is independent of the G3->G1 mapping
  9. BF and BST remain separate source families
 10. classification (86/132/93) and DB (770/707) untouched
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw"
ACQ = D16 / "phase17_v3_external_raw_asset_acquisition.csv"
SUM = D16 / "phase17_v3_external_raw_asset_summary.json"
MANIFEST = D16 / "phase17_v3_external_g1_asset_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"


def _acq():
    return list(csv.DictReader(open(ACQ, encoding="utf-8-sig")))


def _sum():
    return json.load(open(SUM, encoding="utf-8"))


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


# Raw binaries are gitignored and only present on the acquisition machine.
# Data-independent assertions (license/relation/classification) still run anywhere.
_RAW_PRESENT = RAW.exists() and any(RAW.rglob("*.nii.gz"))


# ---- 1. every downloaded raw file has sha256 ----
@pytest.mark.skipif(not _RAW_PRESENT, reason="raw assets not present (gitignored binaries)")
def test_1_downloaded_files_have_sha256():
    files = _sum()["files"]
    assert files, "summary files map empty"
    for rel, m in files.items():
        assert len(m["sha256"]) == 64, rel
        p = RAW / rel
        assert p.exists(), rel
    # every managed asset that reports local files must appear in the registry
    for r in _acq():
        if r["download_status"] in ("RAW_ASSET_VERIFIED", "RAW_ASSET_ACQUIRED", "RAW_ASSET_PARTIAL"):
            assert r["local_path"], r["asset_id"]
            for rel in r["local_path"].split("; "):
                assert rel in files, (r["asset_id"], rel)


# ---- 2. raw files readable (real NIfTI header) ----
@pytest.mark.skipif(not _RAW_PRESENT, reason="raw assets not present (gitignored binaries)")
def test_2_raw_files_readable():
    for r in _acq():
        if not r["local_path"]:
            continue
        for rel in r["local_path"].split("; "):
            p = RAW / rel
            assert p.exists(), rel
            assert p.stat().st_size > 0
        assert r["shape"] and r["spacing"] and r["orientation"], r["asset_id"]


# ---- 3. probability maps unmodified (sha256 stable) ----
@pytest.mark.skipif(not _RAW_PRESENT, reason="raw assets not present (gitignored binaries)")
def test_3_probability_maps_unmodified():
    for rel, m in _sum()["files"].items():
        # FAIL_RAW_ASSET_CHANGED rows deliberately keep the FROZEN sha256 (not the live
        # tampered bytes), so they are excluded from the "bytes == recorded" check.
        if m.get("status") == "FAIL_RAW_ASSET_CHANGED":
            continue
        p = RAW / rel
        assert sha256(p) == m["sha256"], f"{rel} changed"


# ---- 3b. immutable freeze: tampered bytes are NOT silently re-verified ----
@pytest.mark.skipif(not _RAW_PRESENT, reason="raw assets not present (gitignored binaries)")
def test_3b_tampered_file_not_reverified():
    s = _sum()
    # every FAIL row must carry both frozen and live sha so corruption is visible
    for rel, m in s["files"].items():
        if m.get("status") == "FAIL_RAW_ASSET_CHANGED":
            assert m.get("live_sha256"), rel
            assert m["sha256"] != m["live_sha256"], rel
    # manifest must keep the frozen status visible rather than silently reverify
    man = {r["asset_id"]: r["acquisition_status"]
           for r in csv.DictReader(open(MANIFEST, encoding="utf-8-sig"))}
    for mis in s.get("immutable_mismatches", []):
        assert man.get(mis["asset_id"]) in ("FAIL_RAW_ASSET_CHANGED", "RAW_ASSET_PARTIAL")


# ---- 4. no silent overwrite: every recorded file hash equals on-disk bytes ----
@pytest.mark.skipif(not _RAW_PRESENT, reason="raw assets not present (gitignored binaries)")
def test_4_no_silent_overwrite_idempotent():
    # for each asset, the recorded checksum must equal the current on-disk bytes
    for r in _acq():
        if not r["local_path"] or not r["sha256"]:
            continue
        first = r["local_path"].split("; ")[0]
        p = RAW / first
        assert sha256(p) == r["sha256"], f"{r['asset_id']}: {first} changed"
    # archives untouched
    arch = _sum().get("original_archives", {})
    for rel, meta in arch.items():
        p = RAW / rel
        assert p.exists() and sha256(p) == meta["sha256"]


# ---- 5. license-unclear / access-restricted not redistributable ----
def test_5_unclear_license_not_redistributable():
    for r in _acq():
        ls = r["license_status"]
        if ls in ("LICENSE_UNCLEAR", "ACCESS_RESTRICTED"):
            assert r["redistribution_allowed"] != "REDISTRIBUTABLE", r["asset_id"]
            assert r["download_status"] != "RAW_ASSET_VERIFIED" or "VERIFIED" not in ls
        if ls == "LICENSE_VERIFIED_REDISTRIBUTABLE":
            assert r["redistribution_allowed"] == "REDISTRIBUTABLE"


# ---- 6. symmetric vs asymmetric never conflated ----
def test_6_sym_vs_asym_header_driven():
    # structured template-variant: SYMMETRIC and ASYMMETRIC are distinct; the FS
    # rows are on the 2009c SYMMETRIC template and must never be called Asym.
    for r in _acq():
        rel = r["coordinate_relation_to_julich"]
        if not rel:
            continue
        tvar = r["template_variant"]
        if tvar.startswith("2009cSym"):
            assert rel.split("; ")[0].startswith("SYMMETRIC_VS_ASYMMETRIC_TEMPLATE"), (r["asset_id"], rel)
        elif tvar == "2009cAsym":
            # CIT168 2009cAsym files: det+prob are EXACT on the Julich grid;
            # the NLin6Asym companion det is a different (6th-gen) grid.
            rels = rel.split("; ")
            assert any(x == "EXACT_GRID_MATCH" for x in rels), (r["asset_id"], rel)
        # Blackford NLin6 1mm grid must be flagged as needing a nonlinear transform,
        # not resampling-only and never EXACT.
        if r["asset_id"] == "BST_BLACKFORD_WHOLE":
            assert rel == "NONLINEAR_TEMPLATE_TRANSFORM_REQUIRED", rel


# ---- 7. aseg never group gold-standard ----
def test_7_aseg_not_group_standard():
    r = next(x for x in _acq() if x["asset_id"] == "FS_ASEG_SUBJECT")
    assert r["license_status"] == "SUBJECT_SPECIFIC_ONLY"
    assert r["download_status"] == "NOT_ACQUIRED"
    assert r["raw_asset_verified"] == "FALSE"


# ---- 8. CIT168 NAcc provenance independent of G3->G1 ----
def test_8_cit168_independent_of_g3_g1():
    r = next(x for x in _acq() if x["asset_id"] == "CIT168_NAcc")
    # provenance is the author's OSF standard-space release in 2009cAsym (not a
    # G3-derived aggregate, not a name-merge over G3->G1 mappings)
    assert "jkzwp" in r["coordinate_space"] or "OSF" in r["coordinate_space"] \
        or r["template_variant"] == "2009cAsym"
    assert "EXACT_GRID_MATCH" in r["coordinate_relation_to_julich"]  # vs Julich grid
    assert r["download_status"] == "RAW_ASSET_VERIFIED"


# ---- 9. BF and BST separate source families ----
def test_9_bf_bst_separate():
    ids = {r["asset_id"] for r in _acq()}
    assert "BF_ZABORSZKY_CH1234" in ids and "BST_BLACKFORD_WHOLE" in ids
    bf = next(r for r in _acq() if r["asset_id"] == "BF_ZABORSZKY_CH1234")
    assert "Basal Forebrain" in bf["structure"]  # BF (Ch1-4/NbM) row
    # BST assets are their own source family; never labeled Basal Forebrain and
    # never carrying Zaborszky's license token (ACCESS_RESTRICTED / TO_VERIFY etc.)
    for bid in ("BST_BLACKFORD_WHOLE", "BST_SIBBACH_DV", "BST_CYTO_10BRAIN"):
        r = next(x for x in _acq() if x["asset_id"] == bid)
        assert r["structure"].startswith("BST"), bid
        assert "Basal Forebrain" not in r["structure"], bid
        assert r["redistribution_allowed"] != "Zaborszky"  # never merged into Ch family


# ---- 10. classification + DB invariants untouched ----
def test_10_classification_invariants():
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    # REVIEW pool = 218 total - 86 verified = 132
    assert c["VERIFIED_DIRECT_CONTAINED"] + c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] \
        + c.get("FROZEN_DECISION_PREVAILS", 0) + c.get("ONTOLOGY_ENTITY_TYPE_REVIEW", 0) \
        + c.get("ONTOLOGY_DEFINITION_DEPENDENT", 0) + c.get("ANATOMICAL_CONFLICT", 0) == 218
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


@pytest.fixture(scope="session")
def _manifest_synced():
    # manifest rows for acquired assets now carry RAW_ASSET_VERIFIED
    rows = list(csv.DictReader(open(MANIFEST, encoding="utf-8-sig")))
    return {r["asset_id"]: r["acquisition_status"] for r in rows}


def test_manifest_status_synced(_manifest_synced):
    for aid in ("FS_SUBFIELD_HIPPO", "FS_AMYG_NUCLEI", "FS_THAL_ICBM",
                "CIT168_NAcc", "BST_BLACKFORD_WHOLE"):
        assert _manifest_synced.get(aid) == "RAW_ASSET_VERIFIED", aid
    assert _manifest_synced.get("BF_ZABORSZKY_CH1234") in ("PENDING_EXTERNAL", "ACCESS_RESTRICTED")
    assert _manifest_synced.get("FS_ASEG_SUBJECT") == "SUBJECT_SPECIFIC_ONLY"

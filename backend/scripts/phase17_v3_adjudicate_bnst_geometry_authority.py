"""Phase1.7 V3 - BNST geometry authority selection / precedence audit.

ONTOLOGY/GEOMETRY-AUTHORITY AUDIT ONLY. Does NOT start BNST geometry construction,
does NOT run any NLin6->2009c transform, does NOT create NIfTI, does NOT modify DB,
does NOT reclassify any Phase1.7 mapping, does NOT modify Basal Forebrain relations,
does NOT allocate canonical NGIQ-BR IDs.

Question: for the proposed canonical Left/Right whole-BNST entities (commit e04ed86,
BNST_CANONICAL_ENTITY_ADMISSION_V1 = ADMIT_AS_CANONICAL_BRAINREGION), which human
dataset should be the PRIMARY anatomical geometry authority, and which should be
retained as corroborating / reference geometry evidence?

Three distinct roles (never collapsed):
  A. ENTITY AUTHORITY            - what establishes BNST/BST as a valid canonical
                                    BrainRegion (canonical admission; human identity).
  B. ANATOMICAL GEOMETRY AUTHORITY - what defines the canonical anatomical spatial
                                    representation of the whole-BNST complex.
  C. CORROBORATING / CLINICAL GEOMETRY ASSET - independent MRI-scale support retained
                                    for corroboration (not primary).

Repo evidence inspected (live):
  - stored Julich-Brain v3.1 whole BST probability maps (L/R)
      BST_BASAL_FOREBRAIN_BED_NUCLEUS_{LEFT,RIGHT}.nii.gz
      dataset_doi 10.25493/KNSN-XB4 ; reference_space MNI 152 ICBM 2009c Nonlinear
      Asymmetric ; human cytoarchitectonic family ; whole-BST (no subdivision split).
  - Brandstetter et al. 2026 BST cytoarchitectonic subdivision atlas (BSTC/D/M/P,
      10 postmortem brains; BigBrain + MNI/Colin27) DOI 10.1162/IMAG.a.1260 -
      NOT_ACQUIRED (metadata only, ACCESS_RESTRICTED in acquisition CSV).
      Equivalence of the stored v3.1 whole BST map to an aggregation of the 2026
      subdivision set is NOT assumed (provenance DOIs differ; recorded separately).
  - Theiss/Blackford 2017 whole-BNST in-vivo MRI group mask (n=10), MNI152NLin6 FSL
      1 mm grid, probabilistic, CC0, ACQUIRED_VERIFIED (sha d7bfa26c...).
  - Sibbach et al. 2024 dBNST/vBNST (n=25, 7T) - NOT_ACQUIRED metadata.

Decision (evidence-driven):
  A. ENTITY AUTHORITY: human canonical admission already ADMIT (Julich/Brandstetter
     human cytoarchitectonic BST definition + Theiss/Blackford human in-vivo MRI).
  B. PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Brandstetter/Juellich human
     cytoarchitectonic BST family, whose current repo representation is the Julich-
     Brain v3.1 whole-BST L/R probability map on MNI152NLin2009cAsym (dataset_doi
     10.25493/KNSN-XB4). Highest anatomical-definition authority (postmortem
     cytoarchitecture), whole-BST scope compatible, source-native left/right, already
     in the target 2009cAsym frame, probabilistic and in-repo. The 2026 subdivision
     set (10.1162/IMAG.a.1260) is retained as the reference-definitional / future
     higher-resolution geometry source until acquired (NOT selected as the primary
     asset this round because it is not repo-available).
  C. CORROBORATING_CLINICAL_MRI_GEOMETRY = Theiss/Blackford 2017 (in-vivo MRI whole-
     BNST, n=10, MNI152NLin6 probabilistic). Retained as independent MRI-scale
     clinical corroboration; NOT primary (coarser, bilateral single map, needs
     NLin6->2009c route and world-X laterality derivation).
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
JUL_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
JUL_PROV = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "provenance" / "asset_provenance.json"
ACQ_CSV = D16 / "phase17_v3_external_raw_asset_acquisition.csv"
ADMISSION = D16 / "phase17_v3_bnst_canonical_admission_v1.json"
PROPOSAL = D16 / "phase17_v3_bnst_canonical_region_proposal_v1.json"
SCRIPT_VERSION = "phase17_v3_adjudicate_bnst_geometry_authority.py v1"

OUT_AUDIT = D16 / "phase17_v3_bnst_geometry_authority_audit.json"
OUT_DEC = D16 / "phase17_v3_bnst_geometry_authority_decision.json"
OUT_MD = D16 / "phase17_v3_bnst_geometry_authority_diagnostics.md"

JUL_LEFT = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_LEFT.nii.gz"
JUL_RIGHT = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_RIGHT.nii.gz"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def julich_bst_provenance() -> dict:
    prov = json.load(open(JUL_PROV, encoding="utf-8"))
    out = {}
    for a in prov.get("assets", []):
        fn = a.get("file_name", "")
        if "BST_BASAL_FOREBRAIN_BED_NUCLEUS" in fn:
            side = "left" if "_LEFT" in fn else "right"
            out[side] = dict(file_name=fn, sha256=a.get("sha256", ""),
                             official_region_id=a.get("official_region_id", ""),
                             atlas=a.get("atlas", ""), version=a.get("version", ""),
                             dataset_doi=a.get("dataset_doi", ""),
                             reference_space=a.get("reference_space", ""),
                             representation_type=a.get("representation_type", ""),
                             provider=a.get("provider", ""))
    return out


def acquisition_rows() -> dict:
    rows = {}
    for r in csv.DictReader(open(ACQ_CSV, encoding="utf-8-sig")):
        if r["asset_id"].startswith("BST_"):
            rows[r["asset_id"]] = dict(asset_id=r["asset_id"],
                                       status=r.get("download_status", ""),
                                       license=r.get("license_status", ""),
                                       local_path=r.get("local_path", ""),
                                       coordinate_space=r.get("coordinate_space", ""),
                                       sha256=r.get("sha256", "")[:16] or "NONE")
    return rows


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not (JUL_LEFT.exists() and JUL_RIGHT.exists()):
        raise SystemExit("stored Julich v3.1 whole-BST maps not found")
    jul = julich_bst_provenance()
    if len(jul) != 2:
        raise SystemExit("expected left+right Julich BST provenance")
    acq = acquisition_rows()
    admission = json.load(open(ADMISSION, encoding="utf-8"))
    proposal = json.load(open(PROPOSAL, encoding="utf-8"))
    if admission["verdict"] != "ADMIT_AS_CANONICAL_BRAINREGION":
        raise SystemExit("admission verdict drifted")

    source_cards = dict(
        julich_v31_whole_bst=dict(
            family="Brandstetter/Juellich human cytoarchitectonic BST (whole-BST representation)",
            stored=True, modality="postmortem histology / cytoarchitecture",
            whole_scope=True, laterality="source-native left/right",
            reference_space="MNI152NLin2009cAsym (stored maps)",
            probability_map=True, subdivisions="none (whole); subdivision split not present",
            resolution="~1 mm (cyto-derived)",
            provenance_doi="10.25493/KNSN-XB4 (Julich-Brain v3.1 dataset)",
            in_repo_sha=dict(left=sha256(JUL_LEFT), right=sha256(JUL_RIGHT)),
            acquisition_status="STORED_VERIFIED_IN_REPO",
            stored_sha_verified=dict(
                left=(sha256(JUL_LEFT) == jul.get("left", {}).get("sha256")),
                right=(sha256(JUL_RIGHT) == jul.get("right", {}).get("sha256"))),
            note="current in-repo representation of the primary anatomical family"),
        brandstetter_2026=dict(
            family="Brandstetter et al. 2026 (Imaging Neuroscience) cytoarchitectonic BST",
            stored=False, modality="postmortem histology / cytoarchitecture",
            whole_scope=False, laterality="left/right information (metadata)",
            reference_space="Colin27 / ICBM-152 + BigBrain",
            probability_map=True, subdivisions="BSTC / BSTD / BSTM / BSTP",
            doi="10.1162/IMAG.a.1260",
            acquisition_status=acq.get("BST_CYTO_10BRAIN", {}).get("status", "NOT_ACQUIRED"),
            note=("reference-definitional source for canonical cyto subdivision concept; "
                  "NOT repo-available; NOT assumed equivalent to the stored v3.1 whole map")),
        theiss_blackford_2017=dict(
            family="Theiss/Blackford 2017 whole-BNST in-vivo MRI",
            stored=True, modality="human in-vivo MRI (manual delineation, ~10 healthy subjects)",
            whole_scope=True, laterality="bilateral single map (world-X split would be a DERIVATION)",
            reference_space="MNI152NLin6Asym (FSL 182x218x182 @1 mm)",
            probability_map=True, subdivisions="none (whole)",
            doi="10.1016/j.neuroimage.2016.11.047",
            acquisition_status=acq.get("BST_BLACKFORD_WHOLE", {}).get("status", ""),
            in_repo_sha=acq.get("BST_BLACKFORD_WHOLE", {}).get("sha256", ""),
            note="independent MRI-scale clinical corroboration; NOT the primary geometry"),
        sibbach_2024=dict(
            family="Sibbach et al. 2024 dBNST/vBNST (7T)",
            stored=False, modality="human in-vivo 7T MRI",
            whole_scope=False, laterality="dorsal/ventral subdivisions",
            reference_space="MNI (7T normalized; variant metadata only)",
            probability_map=True, subdivisions="dBNST / vBNST",
            acquisition_status=acq.get("BST_SIBBACH_DV", {}).get("status", "NOT_ACQUIRED"),
            note="subdivision evidence only; not a whole-BNST authority"))

    audit = dict(
        audit_id="BNST_GEOMETRY_AUTHORITY_AUDIT",
        question="which human dataset is PRIMARY anatomical geometry authority for whole-BNST?",
        source_cards=source_cards,
        equivalence_caveat=("the stored Julich-Brain v3.1 whole-BST map (dataset DOI "
                            "10.25493/KNSN-XB4) and the Brandstetter 2026 BSTC/D/M/P set "
                            "(DOI 10.1162/IMAG.a.1260) are BOTH in the Julich cytoarchitectonic BST "
                            "family, but their exact relationship is NOT assumed from the label; "
                            "provenance DOIs differ and the 2026 subdivision set is not acquired."),
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_AUDIT, "w", encoding="utf-8") as fh:
        json.dump(audit, fh, ensure_ascii=False, indent=2)

    dims = [
        ("anatomical-definition authority", "Brandstetter/Juellich cytoarchitectonic BST (primary)",
         "Theiss/Blackford MRI whole-BNST"),
        ("whole-BNST scope compatibility", "whole-BST map (stored v3.1)", "whole-BNST (manual)"),
        ("left/right compatibility", "source-native L/R (stored v3.1)", "bilateral single map (world-X split needed)"),
        ("human-only validity", "human (postmortem)", "human (in-vivo MRI)"),
        ("imaging/histology modality", "postmortem histology / cytoarchitecture", "in-vivo MRI"),
        ("stereotaxic reference space", "MNI152NLin2009cAsym (stored v3.1)", "MNI152NLin6Asym"),
        ("probability-map availability", "available in-repo (v3.1 whole L/R)", "available in-repo (prob 0-1)"),
        ("subdivision contamination risk", "none (whole map; subdivision set separate)", "none (whole)"),
        ("resolution", "cyto-derived ~1 mm", "MRI 1 mm"),
        ("reproducibility / provenance", "dataset DOI 10.25493/KNSN-XB4 (stored); 2026 DOI 10.1162/IMAG.a.1260 (ref)",
         "DOI 10.1016/j.neuroimage.2016.11.047; CC0"),
        ("WHOLE_BNST_COMPLEX compatibility", "yes (whole-BST)", "yes (whole-BNST)"),
        ("future canonical geometry construction suitability", "primary (cyto, whole, L/R, target grid)",
         "corroborating (MRI, bilateral, needs route + split)"),
        ("clinical-MRI corroborating evidence", "reference-definitional only", "primary corroborating MRI asset"),
    ]

    decision = dict(
        decision_id="BNST_GEOMETRY_AUTHORITY_DECISION_V1",
        entity_authority=dict(
            role="A. ENTITY AUTHORITY",
            value=("human canonical admission already ADMIT_AS_CANONICAL_BRAINREGION "
                   "(BNST_CANONICAL_ENTITY_ADMISSION_V1): human neuroanatomical/cytoarchitectonic "
                   "identity (Julich/Brandstetter) corroborated by Theiss/Blackford in-vivo MRI.")),
        primary_anatomical_geometry_authority=dict(
            role="B. ANATOMICAL GEOMETRY AUTHORITY",
            value=("PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Brandstetter/Juellich human "
                   "cytoarchitectonic BST family; current repo representation = Julich-Brain v3.1 "
                   "whole-BST L/R probability maps on MNI152NLin2009cAsym (dataset_doi "
                   "10.25493/KNSN-XB4). Rationale: postmortem cytoarchitectonic anatomical "
                   "definition; whole-BST scope compatible with WHOLE_BNST_COMPLEX; source-native "
                   "left/right; already in the target 2009cAsym frame; probabilistic; in-repo "
                   "provenance. The Brandstetter 2026 BSTC/D/M/P set (10.1162/IMAG.a.1260) is the "
                   "reference-definitional / future subdivision-resolved source, NOT selected as "
                   "the primary asset this round because it is not repo-available.")),
        corroborating_clinical_mri_geometry=dict(
            role="C. CORROBORATING / CLINICAL GEOMETRY ASSET",
            value=("CORROBORATING_CLINICAL_MRI_GEOMETRY = Theiss/Blackford 2017 (in-vivo MRI "
                   "whole-BNST, ~10 healthy subjects, MNI152NLin6Asym probabilistic mask, CC0). "
                   "Retained as independent MRI-scale clinical corroboration only; not primary "
                   "(coarser MRI delineation, bilateral single map, requires NLin6->2009c route "
                   "and a world-X laterality derivation).")),
        adjudication_dimensions=[dict(dimension=d[0], primary_geometry=d[1],
                                      corroborating_clinical=d[2]) for d in dims],
        notes=[
            "geometry asset exists != authority selected; authority is decided on evidence, "
            "availability recorded separately",
            "no multi-atlas fusion (union/intersection/majority vote) is used to build a geometry",
            "no geometry construction started; no NIfTI generated; no transform run",
            "Basal Forebrain relations untouched; no DB write; no Phase1.7 reclassification; "
            "no NGIQ-BR allocation",
            "admission verdict (ADMIT_AS_CANONICAL_BRAINREGION) unchanged from commit e04ed86",
        ],
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_DEC, "w", encoding="utf-8") as fh:
        json.dump(decision, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - BNST geometry authority selection / precedence audit", "",
        "Role A (ENTITY AUTHORITY): canonical admission already ADMIT_AS_CANONICAL_BRAINREGION "
        "(human identity, BNST_CANONICAL_ENTITY_ADMISSION_V1).", "",
        "Role B (ANATOMICAL GEOMETRY AUTHORITY): PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = "
        "Brandstetter/Juellich human cytoarchitectonic BST family; current repo representation = "
        "Julich-Brain v3.1 whole-BST L/R probability maps on MNI152NLin2009cAsym "
        "(dataset_doi 10.25493/KNSN-XB4).", "",
        "Role C (CORROBORATING / CLINICAL GEOMETRY ASSET): CORROBORATING_CLINICAL_MRI_GEOMETRY = "
        "Theiss/Blackford 2017 (in-vivo MRI whole-BNST, n~10, MNI152NLin6Asym).", "",
        "Provenance caveat: stored Julich-Brain v3.1 whole-BST (10.25493/KNSN-XB4) and Brandstetter "
        "2026 BSTC/D/M/P (10.1162/IMAG.a.1260) are both in the Julich cytoarchitectonic BST family, "
        "but equivalence is NOT assumed; the 2026 subdivision set is NOT_ACQUIRED (metadata only).",
        "Sibbach 2024 dBNST/vBNST: subdivision evidence only (NOT_ACQUIRED).", "",
        "Guards: geometry construction NOT_STARTED; no NIfTI; no transform; no DB write; no "
        "Phase1.7 reclassification; no Basal Forebrain relation; no NGIQ-BR allocation; admission "
        "verdict unchanged; prior frozen Thalamus/Amygdala/Hippocampus outputs untouched.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Brandstetter/Juellich cyto BST "
          "(Julich-Brain v3.1 whole-BST L/R in-repo)")
    print("CORROBORATING_CLINICAL_MRI_GEOMETRY = Theiss/Blackford 2017")
    print("geometry construction NOT_STARTED | wrote 3 artifacts")


if __name__ == "__main__":
    main()

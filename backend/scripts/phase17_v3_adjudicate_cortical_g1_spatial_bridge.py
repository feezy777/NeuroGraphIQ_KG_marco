"""Phase1.7 V3 - Cortical G1 surface-to-volume spatial bridge authority + method audit.

METHOD/SPATIAL-BRIDGE FREEZE AUDIT ONLY (not 83-relation validation). Determines
whether a reproducible, mapping-independent FreeSurfer/Desikan-Killiany fsaverage
SURFACE -> MNI152NLin2009cAsym Julich VOLUME bridge can be frozen from real in-repo
assets and an authoritative source-template->2009cAsym transform.

No geometry is generated, no pilot volume is produced (toolchain/assets missing), no
relation validation, no reclassification, no DB, no promotion.

VERDICT (evidence-based): CORTICAL_SURFACE_TO_VOLUME_BRIDGE_BLOCKED.
Core missing pieces (verified live):
  - no fsaverage Desikan-Killiany aparc.annot (only Brainnetome BN_Atlas label.gii on
    fsaverage surfaces; per-subject aseg.mgz for subject 001, not fsaverage);
  - no fsaverage reference VOLUME (orig/brain/aseg.mgz in fsaverage space) -> the
    fsaverage source volume template identity is UNRESOLVED (gate D aspect);
  - no talairach / MNI305 / fsaverage -> MNI152NLin2009cAsym transform in the repo
    (TemplateFlow only holds NLin6Asym->2009cAsym);
  - no FreeSurfer surface->volume toolchain (mri_surf2vol / mri_label2vol) available
    for execution in this environment.
The historical BN<->DK fsaverage route proves only SURFACE-TO-SURFACE compatibility
on fsaverage; it is NOT a surface->volume bridge and is not reused as one.

Cortical universe is computed live from the frozen G3->G1 manifest intersected with
the frozen DK34 surface-label->G1 crosswalk (data/integration/g3_surface_dk_audits).
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
FS_DIR = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "surface_raw" / "extracted" / "BN_Atlas_freesurfer" / "fsaverage"
SCRIPT_VERSION = "phase17_v3_adjudicate_cortical_g1_spatial_bridge.py v1"

OUT_TARGETS = D16 / "phase17_v3_cortical_g1_target_inventory.csv"
OUT_DK = D16 / "phase17_v3_cortical_dk_authority_crosswalk.csv"
OUT_ASSET = D16 / "phase17_v3_cortical_surface_asset_manifest.json"
OUT_COORD = D16 / "phase17_v3_cortical_coordinate_system_audit.json"
OUT_ROUTES = D16 / "phase17_v3_cortical_spatial_route_candidates.csv"
OUT_RIBBON = D16 / "phase17_v3_cortical_ribbon_construction_audit.json"
OUT_PILOT = D16 / "phase17_v3_cortical_bridge_pilot_qc.csv"
OUT_MD = D16 / "phase17_v3_cortical_spatial_bridge_diagnostics.md"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def dk_aligned_g1():
    """frozen DK34 surface-label -> G1 mapping (ALIGNED rows only)."""
    rows = list(csv.DictReader(open(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv",
                                    encoding="utf-8-sig")))
    aligned = []
    for r in rows:
        if r.get("alignment_status") == "ALIGNED" and r.get("g1_entity_id"):
            aligned.append(dict(hemisphere=r["hemisphere"], dk_label_id=r["dk_label_id"],
                                dk_label_name=r["dk_label_name"],
                                g1_entity_id=r["g1_entity_id"], g1_name_en=r["g1_name_en"]))
    return aligned


def cortical_relations(aligned_ids: set[str]) -> list[dict]:
    out = []
    for r in csv.DictReader(open(G3MAN, encoding="utf-8-sig")):
        if r.get("primary_target_g1_entity_id") in aligned_ids:
            out.append(dict(g3_entity_id=r["g3_entity_id"],
                            official_code=r.get("official_code", ""),
                            hemisphere=r.get("hemisphere", ""),
                            target=r["primary_target_g1_entity_id"],
                            target_name=r.get("primary_target_g1_name", "")))
    return out


def fsaverage_surface_files():
    out = []
    for f in sorted(FS_DIR.rglob("*.surf.gii")):
        out.append(dict(path=str(f.relative_to(BACKEND)).replace("\\", "/"),
                        sha256=sha256(f), size=f.stat().st_size))
    return out


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    aligned = dk_aligned_g1()
    if len(aligned) < 30:
        raise SystemExit("dk aligned crosswalk unexpectedly small")
    aligned_ids = {a["g1_entity_id"] for a in aligned}
    rels = cortical_relations(aligned_ids)
    targets = {}
    for a in aligned:
        t = targets.setdefault(a["g1_entity_id"],
                               dict(canonical_region_id=a["g1_entity_id"], name=a["g1_name_en"],
                                     left=False, right=False))
        t[a["hemisphere"]] = True
    # dynamic universe
    with open(OUT_TARGETS, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["canonical_region_id", "g1_name_en", "hemisphere", "dk_label_name", "dk_label_id",
                "has_cortical_g3_relation"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for a in sorted(aligned, key=lambda x: x["g1_entity_id"]):
            has = any(r["target"] == a["g1_entity_id"] for r in rels)
            w.writerow(dict(canonical_region_id=a["g1_entity_id"], g1_name_en=a["g1_name_en"],
                            hemisphere=a["hemisphere"], dk_label_name=a["dk_label_name"],
                            dk_label_id=a["dk_label_id"],
                            has_cortical_g3_relation="TRUE" if has else "FALSE"))
    with open(OUT_DK, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["hemisphere", "dk_label_id", "dk_label_name", "g1_entity_id", "g1_name_en",
                "alignment_status"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in sorted(csv.DictReader(open(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv",
                                            encoding="utf-8-sig")),
                        key=lambda x: (x["hemisphere"], int(x["dk_label_id"]))):
            w.writerow({k: r.get(k, "") for k in cols})

    # surface assets present (fsaverage white/pial/etc surfaces; NO DK annot / volume / transforms)
    surf = fsaverage_surface_files()
    asset = dict(
        fsaverage_surfaces=dict(present=True, n_files=len(surf),
                                identity="fsaverage surface meshes (BN_Atlas/FreeSurfer extraction; "
                                         "white/pial/midthickness/inflated)", files=surf[:6],
                                note="surface meshes only; vertex coordinate space = fsaverage surface "
                                     "(tk)RAS; NO fsaverage volume reference anchored here"),
        dk_aparc_annot=dict(present=False,
                            note="no fsaverage Desikan-Killiany lh.aparc.annot / rh.aparc.annot found"),
        fsaverage_reference_volume=dict(present=False,
                                        note="no fsaverage orig/brain/aseg.mgz volume reference found; "
                                             "only subject-001 aseg.mgz (not fsaverage)"),
        talairach_or_mni305_transform=dict(present=False,
                                           note="no talairach.xfm / MNI305 / fsaverage->template transform in repo"),
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_ASSET, "w", encoding="utf-8") as fh:
        json.dump(asset, fh, ensure_ascii=False, indent=2)

    coord = dict(
        coordinate_systems=[
            dict(id="fsaverage_surface_xyz", meaning="fsaverage surface vertex coordinates",
                 present="SURFACES_PRESENT",
                 note="surface (tk)RAS mm on fsaverage; NOT MNI152NLin2009cAsym world XYZ"),
            dict(id="fsaverage_subject_volume", meaning="fsaverage MRI/orig voxel&world",
                 present="VOLUME_ABSENT",
                 note="no fsaverage volume reference -> voxel/world anchoring unresolved"),
            dict(id="tkRAS_world", meaning="FreeSurfer tkRAS (surface-space world)",
                 present="SURFACES_PRESENT",
                 note="distinct from scanner/world RAS of MNI templates"),
            dict(id="MNI305_Talairach", meaning="FreeSurfer talairach/MNI305",
                 present="TRANSFORMS_ABSENT",
                 note="no talairach.xfm / MNI305 transforms present; must not be conflated with MNI152"),
            dict(id="MNI152NLin2009cAsym", meaning="target Julich reference volume space",
                 present="TARGET_ONLY",
                 note="target grid/affine exist (Julich reference) but no bridge from fsaverage here")],
        hard_rule="no direct surface XYZ -> MNI2009cAsym XYZ; MNI305 and MNI152 must not be conflated",
        source_template_identity="UNRESOLVED_NO_FSAVERAGE_VOLUME",
        created_at=ts)
    with open(OUT_COORD, "w", encoding="utf-8") as fh:
        json.dump(coord, fh, ensure_ascii=False, indent=2)

    routes = [
        dict(route_id="A", name="FreeSurfer mri_surf2vol / mri_label2vol (official)", surface_source="DK fsaverage",
             volume_reference="needs fsaverage subject volume (absent)", coordinate_conversion="tkRAS->voxel",
             registration_transform="talairach (absent)", target_space="MNI305/Talairach (not 2009cAsym)",
             software="FreeSurfer", version="not available in env", interpolation="nearest/label",
             scientific_authority="official FS", reproducibility="high",
             availability="BLOCKED (fsaverage volume, DK annot, talairach, FS toolchain all absent)",
             known_limitations="requires fsaverage volume + annotation + talairach"),
        dict(route_id="B", name="freesurfer DK annot -> template-space (via validated template transform)",
             surface_source="DK fsaverage", volume_reference="absent",
             coordinate_conversion="surface->? volume", registration_transform="absent (no source-template "
             "->2009cAsym transform for fsaverage/MNI305)", target_space="MNI152NLin2009cAsym",
             software="n/a", version="-", interpolation="n/a",
             scientific_authority="not established", reproducibility="n/a",
             availability="BLOCKED (no source-template transform)"),
        dict(route_id="C", name="historical BN<->DK fsaverage surface route", surface_source="Brainnetome fsaverage + DK fsaverage",
             volume_reference="none (surface-to-surface only)", coordinate_conversion="fsaverage surface overlap",
             registration_transform="none needed (same fsaverage)", target_space="fsaverage surface (NOT volume)",
             software="surface overlap scripts", version="frozen phase17 route", interpolation="n/a",
             scientific_authority="surface-to-surface only",
             availability="AVAILABLE but NOT a surface->volume bridge; NOT reused as a volume bridge",
             known_limitations="proves SURFACE_TO_SURFACE only; must not masquerade as volume bridge"),
        dict(route_id="D", name="TemplateFlow NLin6Asym->2009cAsym transform", surface_source="not applicable",
             volume_reference="MNI152NLin6Asym", coordinate_conversion="n/a",
             registration_transform="MNI152NLin2009cAsym_from-MNI152NLin6Asym (h5 present)",
             target_space="MNI152NLin2009cAsym", software="SimpleITK 2.5.6", version="2.5.6",
             interpolation="Linear", scientific_authority="TemplateFlow",
             availability="present but source is NLin6Asym volume, NOT fsaverage/MNI305 surface",
             known_limitations="cannot bridge fsaverage surface; different source space"),
    ]
    with open(OUT_ROUTES, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(routes[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in routes:
            w.writerow(r)

    ribbon = dict(
        preferred_method="official FreeSurfer Desikan-Killiany ribbon: DK lh/rh.aparc.annot on white+pial "
                         "surfaces -> parcel cortical gray-matter ribbon volume (not a surface shell)",
        white_surface_authority="fsaverage.L/R.white.164k.surf.gii (present)",
        pial_surface_authority="fsaverage.L/R.pial.164k.surf.gii (present)",
        dk_annotation_authority="lh/rh.aparc.annot (ABSENT on fsaverage)",
        surface_to_volume_tool="FreeSurfer mri_surf2vol / mri_label2vol (not available in env)",
        note=("method is scientifically preferred but EXECUTION BLOCKED: no fsaverage DK annotation, no "
              "fsaverage volume reference, no FreeSurfer toolchain here"),
        surface_shell_not_volume=True,
        execution_status="NOT_RUN",
        created_at=ts)
    with open(OUT_RIBBON, "w", encoding="utf-8") as fh:
        json.dump(ribbon, fh, ensure_ascii=False, indent=2)

    # pilot QC: NOT RUN (assets/toolchain missing) - header-only informative row
    with open(OUT_PILOT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["pilot_status", "reason", "pilot_families"])
        w.writeheader()
        w.writerow(dict(pilot_status="NOT_RUN",
                        reason="fsaverage DK annotation / fsaverage volume / FreeSurfer toolchain absent; "
                               "pilot deferred to a round where the bridge is executable",
                        pilot_families="deferred (to be chosen by GEOMETRIC_COVERAGE_DIVERSITY, "
                                       "mapping-independent)"))

    n_left = sum(1 for a in aligned if a["hemisphere"] == "left")
    n_right = sum(1 for a in aligned if a["hemisphere"] == "right")
    rel_l = sum(1 for r in rels if r["hemisphere"] == "left")
    rel_r = sum(1 for r in rels if r["hemisphere"] == "right")
    verdict = "CORTICAL_SURFACE_TO_VOLUME_BRIDGE_BLOCKED"

    md = [
        "# Phase1.7 V3 - Cortical G1 surface-to-volume spatial bridge authority + method audit", "",
        "Cortical universe (computed live from frozen G3->G1 manifest x DK34 surface->G1 crosswalk):",
        f"  cortical G3->G1 relations = {len(rels)} (left {rel_l} / right {rel_r})",
        f"  aligned DK-label->G1 rows = {len(aligned)} (left {n_left} / right {n_right}) "
        f"-> distinct G1 targets = {len(targets)}",
        "  target inventory + DK crosswalk written to the CSVs.",
        "",
        "VERDICT: " + verdict,
        "  Reason: no fsaverage Desikan-Killiany aparc.annot, no fsaverage reference volume "
        "(source template identity unresolved), no talairach/MNI305->2009cAsym transform, and no "
        "FreeSurfer surface->volume toolchain available in this environment.",
        "  The historical BN<->DK fsaverage route is surface-to-surface only and is NOT reused as a "
        "volume bridge.",
        "  No pilot geometry was produced (assets/toolchain missing); pilot deferred.",
        "  No CORTICAL_G1_SPATIAL_BRIDGE_V1 is generated (bridge is not frozen).",
        "",
        "Coordinate hard rules recorded: no direct surface XYZ -> MNI2009cAsym; MNI305/MNI152 are "
        "never conflated; tkRAS/world-RAS kept separate.",
        "Guards: no bulk geometry, no relation validation, no reclassification, no DB, no "
        "promotion; Basal Forebrain blocker and prior frozen families (Thalamus/Amygdala/"
        "Hippocampus/BNST) unchanged.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("cortical relations:", len(rels), "(L", rel_l, "/ R", rel_r, ")")
    print("aligned DK rows:", len(aligned), "| distinct G1 targets:", len(targets))
    print("verdict:", verdict)
    print("wrote 8 artifacts (no bridge_v1; no pilot)")


if __name__ == "__main__":
    main()

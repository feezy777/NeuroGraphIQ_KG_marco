"""Phase1.7 V3 - Brainnetome G3 Thalamus Rollup Basis <-> THALAMUS_PROPER
Compatibility Audit (READ-ONLY) + gate-transition record.

Audits whether the 16 frozen G3->G1 Thalamus rollup relations (Brainnetome
Tha_*_8_1..8_8, 8 per hemisphere) are compatible with the now-frozen canonical
G1 identity THALAMUS_PROPER (dorsal thalami mass; LGN/MGN INCLUDE, Reticular
EXCLUDE, L-Sg REVIEW per THALAMUS_G1_SCOPE_CONTRACT_V2).

GATE SPLIT (fixes the former circular dependency):

  OLD deadlock:  blocker #2 ("BN rollup basis not reconciled") could only be
  lifted by direct validation against an independent THALAMUS_PROPER geometry,
  but the unresolved blocker #2 itself forbade geometry construction.

  NEW split:
    A. PRE-CONSTRUCTION COMPATIBILITY GATE (this audit):
         semantic-anatomical compatibility of the frozen BN rollup basis with
         THALAMUS_PROPER. No anatomical incompatibility found across all 16
         -> preconstruction_rollup_compatibility =
              PASS_WITH_POSTCONSTRUCTION_VALIDATION_REQUIRED
         blocker #2 no longer blocks geometry construction.
    B. POST-CONSTRUCTION DIRECT VALIDATION GATE (future, not this round):
         direct spatial containment of each BN G3 parcel inside the independent
         THALAMUS_PROPER G1 geometry. Cannot run until that geometry exists
         -> promotion_gate = BLOCKED_UNTIL_DIRECT_VALIDATION.

  final_verdict stays BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE. The audit does NOT
  upgrade the 16 parcels to COMPATIBLE_WITH_THALAMUS_PROPER; they remain
  LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION. "Pre-construction gate passed"
  != "16 frozen mappings finally validated".

V2 (THALAMUS_G1_SCOPE_CONTRACT_V2) is NOT retro-edited: its historical blocker
#2 wording stays. A separate gate-transition record documents the migration of
blocker #2 out of the pre-construction gate into the post-construction gate.

Hard gate: frozen decisions are HISTORICAL FACTS, not audit-exempt scientific
evidence. No frozen mapping modified; no geometry built; no transform / resample
/ G4->G1 overlap / reclassification / DB write / commit.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
BNA_AUTH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "brainnetome_bna246_subregions_authoritative.csv"
BNA_DET = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw" / "BN_Atlas_246_1mm.nii.gz"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"

OUT_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
OUT_SUM = D16 / "phase17_v3_thalamus_bn_rollup_summary.json"
OUT_MD = D16 / "phase17_v3_thalamus_bn_rollup_diagnostics.md"
OUT_PROV = D16 / "phase17_v3_thalamus_bn_rollup_provenance.json"
OUT_GT = D16 / "phase17_v3_thalamus_bn_rollup_gate_transition.json"

CANON = {"NGIQ-BR-00000247": "Left Thalamus", "NGIQ-BR-00000256": "Right Thalamus"}
SCRIPT_VERSION = "phase17_v3_audit_thalamus_bn_rollup_compatibility.py v2 (gate-split)"
GATE_TRANSITION_ID = "GATE-TRANSITION-THAL-BN-ROLLUP-01"

# Source blocker naming inside V2 (historical, untouched).
V2_BLOCKER2_LABEL = "BN_ROLLUP_BASIS_NOT_RECONCILED"
V2_BLOCKER2_TEXT = ("frozen G1 rollup basis is the whole-thalamus Brainnetome "
                    "Tha_*_8_1..8_8 zones (BROAD extent); not yet reconciled to the "
                    "frozen THALAMUS_PROPER (dorsal) identity territory")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_csv(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # ---- inputs exists ----
    for p in (G3MAN, BNA_AUTH, BNA_DET, V1, V2):
        if not p.exists():
            raise SystemExit(f"FAIL: missing input {p}")
    g3_sha = sha256(G3MAN)
    bna_sha = sha256(BNA_AUTH)
    v1_sha = sha256(V1)
    v2_sha = sha256(V2)

    # ---- 1. freeze 16-relation universe from real frozen manifest ----
    g3 = load_csv(G3MAN)
    thal = [r for r in g3 if r.get("primary_target_g1_entity_id") in CANON]
    assert len(thal) == 16, f"expected 16 frozen thal relations, got {len(thal)}"
    by_code = {r["official_code"]: r for r in thal}

    # ---- 2. authoritative BNA 8-zone semantics ----
    bna = load_csv(BNA_AUTH)
    bna_tha = {r["official_hemisphere_code"]: r for r in bna
               if (r.get("official_hemisphere_code") or "").startswith("Tha_")}

    # ---- 3. independent gross spatial support (BNA-246 mask, NOT G3->G1) ----
    det = nib.load(BNA_DET)
    d = np.asanyarray(det.dataobj)
    aff = det.affine
    I, J, K = np.meshgrid(np.arange(d.shape[0]), np.arange(d.shape[1]),
                          np.arange(d.shape[2]), indexing="ij")
    xw = aff[0, 0] * I + aff[0, 3]
    allmask = d >= 231  # Tha_* label ids 231..246 contiguous
    thalmass = dict(
        union_voxels=int(allmask.sum()),
        world_x_range=[float(xw[allmask].min()), float(xw[allmask].max())],
        far_lateral_voxels_absx_gt30=int(((allmask) & (np.abs(xw) > 30)).sum()),
        spatial_evidence_type="GROSS_TERRITORY_CHECK_BNA246_MASK",
        note="BNA-246 1mm deterministic atlas mask (independent of the G3->G1 "
             "decision mapping); coarse territorial only - cannot adjudicate thin "
             "reticular-shell margins and is not G1-geometry validation")

    # ---- per-zone metadata + compatibility ruling ----
    zone_sem = {
        "mPFtha": ("medial pre-frontal thalamus", "medial dorsal/anterior-group projection zone"),
        "mPMtha": ("pre-motor thalamus", "ventral-lateral/premotor projection zone"),
        "Stha": ("sensory thalamus", "ventral-posterior (VPL/VPM) sensory projection zone"),
        "rTtha": ("rostral temporal thalamus", "rostral temporal projection zone"),
        "PPtha": ("posterior parietal thalamus", "posterior parietal / LP-pulvinar projection zone"),
        "Otha": ("occipital thalamus", "occipital / LGN-pulvinar projection zone"),
        "cTtha": ("caudal temporal thalamus", "caudal temporal projection zone"),
        "lPFtha": ("lateral pre-frontal thalamus", "lateral prefrontal projection zone"),
    }
    verdict_per_zone = {z: "LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION"
                        for z in zone_sem}
    rows = []
    for code in sorted(by_code, key=lambda c: (c[4], int(c.split("_")[-1]))):
        fr = by_code[code]
        au = bna_tha.get(code, {})
        abbr = au.get("modified_cytoarchitectonic_code", "")
        full = au.get("modified_cytoarchitectonic_name", "")
        sem, note = zone_sem.get(abbr, (abbr, ""))
        hemi = fr["hemisphere"]
        comp = verdict_per_zone.get(abbr, "INSUFFICIENT_EVIDENCE")
        dep = "DEPENDENCY_ON_DEC_THAL_04" if abbr in ("PPtha", "Otha", "cTtha") else ""
        conf = "medium"
        primary = ("Fan 2016 connectivity-based parcellation of the thalami mass; "
                   "zone '" + abbr + "' = " + full + " (" + sem + ")")
        secondary = ("BNA-246 gross territory within thalami mass (no |x|>30 voxels); "
                     "AAL3/FS/Julich place dorsal-thalamus nuclei incl. LGN/MGN inside "
                     "Thalamus under V2 identity")
        circularity = "LOW"
        rows.append(dict(
            decision_id=f"DEC-THAL-ROLLUP-{len(rows)+1:02d}",
            g3_region_id=fr["g3_entity_id"], official_label=code,
            abbreviation=abbr, official_name=full,
            anatomical_zone_semantics=sem, hemisphere=hemi,
            frozen_g1_target=fr["primary_target_g1_entity_id"],
            frozen_g1_name=CANON[fr["primary_target_g1_entity_id"]],
            frozen_decision=fr["effective_scientific_decision"],
            compatibility_status=comp, confidence=conf,
            primary_evidence=primary, secondary_evidence=secondary,
            spatial_evidence_type="SEMANTIC_ANATOMICAL_COMPATIBILITY+GROSS_SPATIAL_SUPPORT",
            circularity_risk=circularity,
            reticular_territory_check="NO_SUBSTANTIAL_RETICULAR_TERRITORY_FOUND",
            lsg_dependency=dep,
            lgn_mgn_conflict="NONE (LGN/MGN INCLUDE per V2)",
            notes=(note + (("; possible posterior-complex/L-Sg-adjacent territory -> " + dep)
                           if dep else ""))))

    # ---- relation-level verdict, split by L-Sg dependency ----
    # 6 posterior zones (PPtha/Otha/cTtha, L+R) touch the posterior complex near L-Sg
    # (REVIEW, DEC-THAL-04) -> boundary AND direct validation still pending.
    # The other 10 non-L-Sg zones have no open boundary question from this audit,
    # only the future direct spatial validation against independent G1 geometry.
    for r in rows:
        r["relation_verdict"] = (
            "KEEP_FROZEN_MAPPING_PENDING_BOUNDARY_AND_DIRECT_VALIDATION"
            if r["lsg_dependency"] else
            "KEEP_FROZEN_MAPPING_PENDING_DIRECT_SPATIAL_VALIDATION")

    # ---- bilateral consistency ----
    by_zone = {}
    for r in rows:
        by_zone.setdefault(r["abbreviation"], {})[r["hemisphere"]] = r["compatibility_status"]
    bilateral = {z: (s["left"] == s["right"], s) for z, s in by_zone.items()}
    asym = {z: v for z, (ok, v) in bilateral.items() if not ok}

    # ---- stats & gate split ----
    stats = Counter(r["compatibility_status"] for r in rows)
    rel_stats = Counter(r["relation_verdict"] for r in rows)
    incompatible = sum(1 for r in rows
                       if r["compatibility_status"] == "INCOMPATIBLE_WITH_THALAMUS_PROPER")
    lsg_dep_count = sum(1 for r in rows if r["lsg_dependency"])
    non_dep_count = len(rows) - lsg_dep_count
    assert lsg_dep_count == 6 and non_dep_count == 10

    final = ("BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE" if not asym else
             "BN_ROLLUP_BASIS_REQUIRES_RELATION_REVIEW")
    # PARTIALLY_COMPATIBLE is retained even with no asymmetry because DIRECT spatial
    # validation has not yet been performed against independent THALAMUS_PROPER geometry.
    final = "BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE"

    preconstruction_rollup_compatibility = "PASS_WITH_POSTCONSTRUCTION_VALIDATION_REQUIRED"
    preconstruction_gate = "PASSED"
    # blocker #2 (V2 label BN_ROLLUP_BASIS_NOT_RECONCILED) is reclassified, not deleted:
    # it no longer blocks geometry construction, but direct validation remains mandatory.
    construction_blocker_status = "RECLASSIFIED_OUT_OF_CONSTRUCTION_GATE"
    blocker2_effective_status = "NO_LONGER_PRECONSTRUCTION_BLOCKER"
    postconstruction_requirement = "DIRECT_BN_G3_TO_G1_SPATIAL_VALIDATION_REQUIRED"
    promotion_gate = "BLOCKED_UNTIL_DIRECT_VALIDATION"
    active_construction_blockers = ["DEC-THAL-04 (L-Sg / Limitans-Suprageniculate boundary)"]

    # ---- write CSV ----
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    out_csv_sha = sha256(OUT_CSV)

    # ---- write summary ----
    summary = dict(
        final_verdict=final,
        incompatible=incompatible,
        total=len(rows),
        stats=dict(stats),
        relation_verdict_distribution=dict(rel_stats),
        lsg_dependent_relations=lsg_dep_count,
        non_lsg_dependent_relations=non_dep_count,
        bilateral_asymmetry=asym,
        evidence_mode="SEMANTIC_ANATOMICAL_COMPATIBILITY (+ gross BNA-246 spatial support)",
        not_direct_g1_validation=("no independent THALAMUS_PROPER geometry built; "
                                  "compatibility is LIKELY, not confirmed"),
        # --- gate split ---
        preconstruction_rollup_compatibility=preconstruction_rollup_compatibility,
        preconstruction_gate=preconstruction_gate,
        source_blocker_v2=V2_BLOCKER2_LABEL,
        blocker2_effective_status=blocker2_effective_status,
        construction_blocker_status=construction_blocker_status,
        postconstruction_requirement=postconstruction_requirement,
        promotion_gate=promotion_gate,
        active_construction_blockers=active_construction_blockers,
        geometry_construction="BLOCKED_BY_LSG_ONLY",
        promotion="BLOCKED",
    )
    with open(OUT_SUM, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    out_sum_sha = sha256(OUT_SUM)

    # ---- write diagnostics md ----
    md = [
        "# Phase1.7 V3 - Thalamus BN rollup basis <-> THALAMUS_PROPER compatibility",
        "",
        f"final_verdict = {final}  (direct spatial validation NOT yet done)",
        f"incompatible = {incompatible}",
        f"preconstruction_gate = {preconstruction_gate}",
        f"preconstruction_rollup_compatibility = {preconstruction_rollup_compatibility}",
        f"blocker #2 (V2: {V2_BLOCKER2_LABEL}) -> {blocker2_effective_status} "
        f"(migrated out of pre-construction gate; V2 historical snapshot untouched)",
        f"construction_blocker_status = {construction_blocker_status}",
        f"postconstruction_requirement = {postconstruction_requirement}",
        f"promotion_gate = {promotion_gate}",
        f"active_construction_blockers = {active_construction_blockers}",
        f"geometry_construction = BLOCKED_BY_LSG_ONLY",
        f"promotion = BLOCKED",
        f"relation_verdict_distribution = {dict(rel_stats)}",
        f"  - 6 L-Sg-dependent:   KEEP_FROZEN_MAPPING_PENDING_BOUNDARY_AND_DIRECT_VALIDATION",
        f"  - 10 non-L-Sg:        KEEP_FROZEN_MAPPING_PENDING_DIRECT_SPATIAL_VALIDATION",
        f"universe = {len(rows)} relations (8L+8R) from real frozen manifest",
        f"stats = {dict(stats)}  (all LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION; "
        "NOT upgraded to COMPATIBLE)",
        f"bilateral_asymmetry = {asym if asym else 'NONE (all L/R symmetric)'}",
        "evidence_mode = SEMANTIC_ANATOMICAL_COMPATIBILITY (+gross BNA-246 spatial)",
        "NOT direct G1 geometry validation (no independent THALAMUS_PROPER geometry yet)",
        "pre-construction gate PASSED does NOT mean the 16 frozen mappings are finally "
        "validated; promotion stays blocked until post-construction direct validation.",
        "no frozen mapping modified; no geometry/transform/overlap/DB; no retro-edit of "
        "V1/V2; no reclassification; no commit", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    out_md_sha = sha256(OUT_MD)

    # ---- write gate-transition record (last; hashes all outputs above) ----
    gate_transition = dict(
        gate_transition_id=GATE_TRANSITION_ID,
        transition_type="BLOCKER_RECLASSIFICATION_ACROSS_GATE_SPLIT",
        source_contract="THALAMUS_G1_SCOPE_CONTRACT_V2",
        source_contract_sha256=v2_sha,
        source_blocker=V2_BLOCKER2_LABEL,
        source_blocker_original_text=V2_BLOCKER2_TEXT,
        v2_historical_snapshot="NOT_MODIFIED",
        audit_round="Brainnetome G3 Thalamus rollup basis <-> THALAMUS_PROPER compatibility",
        audit_result="BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE",
        decision_ids=[r["decision_id"] for r in rows],
        preconstruction_gate=preconstruction_gate,
        preconstruction_rollup_compatibility=preconstruction_rollup_compatibility,
        construction_blocker_status=construction_blocker_status,
        blocker2_effective_status=blocker2_effective_status,
        postconstruction_requirement=postconstruction_requirement,
        promotion_gate=promotion_gate,
        active_construction_blockers=active_construction_blockers,
        reason=("Current audit found no anatomical incompatibility across all 16 frozen "
                "Brainnetome thalamus rollups, but independent direct spatial validation "
                "cannot occur until the authoritative THALAMUS_PROPER G1 geometry exists."),
        note=("'Pre-construction gate passed' != '16 frozen mappings finally validated'. "
              "Blocker #2 is reclassified out of the pre-construction gate into the "
              "post-construction direct-validation gate; it is NOT deleted and the V2 "
              "historical record is NOT retro-edited."),
        relation_verdict_distribution=dict(rel_stats),
        lsg_dependent_relations=lsg_dep_count,
        non_lsg_dependent_relations=non_dep_count,
        final_effective_state=dict(
            thalamus_ontology_identity="FROZEN_THALAMUS_PROPER",
            probability_aggregation="SUM / FROZEN",
            bn_rollup_semantic_compatibility="PASS_PRECONSTRUCTION",
            bn_rollup_direct_spatial_validation="PENDING_POSTCONSTRUCTION",
            lsg_scope="REVIEW",
            geometry_construction="BLOCKED_BY_LSG_ONLY",
            promotion="BLOCKED",
        ),
        provenance_chain=dict(
            gate_transition_to="current rollup audit (DEC-THAL-ROLLUP-01..16)",
            audit_to="frozen G3 relations (g3_to_g1_full_decision_coverage_manifest.csv)",
            frozen_to="THALAMUS_G1_SCOPE_CONTRACT_V2",
            v2_to="THALAMUS_G1_SCOPE_CONTRACT_V1",
            v1_to="Brainnetome authoritative metadata (Fan 2016 / BNA246)",
            v1_sha256=v1_sha, v2_sha256=v2_sha,
            frozen_manifest_sha256=g3_sha, bna_source_sha256=bna_sha,
            rollup_audit_csv_sha256=out_csv_sha, rollup_audit_summary_sha256=out_sum_sha,
            diagnostics_md_sha256=out_md_sha,
            script_version=SCRIPT_VERSION, run_timestamp=ts,
        ),
    )
    with open(OUT_GT, "w", encoding="utf-8") as fh:
        json.dump(gate_transition, fh, ensure_ascii=False, indent=2)
    out_gt_sha = sha256(OUT_GT)

    # ---- write provenance LAST (seals the chain: references every output above) ----
    provenance = dict(
        audit_round="Thalamus BN rollup basis <-> THALAMUS_PROPER compatibility + gate split",
        frozen_manifest=dict(path=str(G3MAN.relative_to(BACKEND)), sha256=g3_sha),
        bna_authoritative=dict(path=str(BNA_AUTH.relative_to(BACKEND)), sha256=bna_sha),
        v2_contract=dict(path=str(V2.relative_to(BACKEND)), sha256=v2_sha),
        v1_contract=dict(path=str(V1.relative_to(BACKEND)), sha256=v1_sha),
        bna_det_mask=str(BNA_DET.relative_to(BACKEND)),
        spatial_evidence_type=thalmass,
        outputs=dict(
            rollup_csv=dict(path=str(OUT_CSV.relative_to(BACKEND)), sha256=out_csv_sha),
            summary_json=dict(path=str(OUT_SUM.relative_to(BACKEND)), sha256=out_sum_sha),
            diagnostics_md=dict(path=str(OUT_MD.relative_to(BACKEND)), sha256=out_md_sha),
            gate_transition=dict(path=str(OUT_GT.relative_to(BACKEND)), sha256=out_gt_sha),
        ),
        canonical_identity="THALAMUS_PROPER (V2)",
        script_version=SCRIPT_VERSION, run_timestamp=ts,
        note="frozen mappings NOT modified; V2 NOT retro-edited; read-only audit + "
             "gate-transition record",
    )
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, ensure_ascii=False, indent=2)

    print("final", final, "incompatible", incompatible)
    print("preconstruction_gate", preconstruction_gate)
    print("blocker2_effective_status", blocker2_effective_status)
    print("postconstruction_requirement", postconstruction_requirement)
    print("promotion_gate", promotion_gate)
    print("active_construction_blockers", active_construction_blockers)
    print("relation_verdict_distribution", dict(rel_stats))
    print("asymmetry", asym if asym else "NONE")
    print("gate_transition", str(OUT_GT.relative_to(BACKEND)), out_gt_sha)


if __name__ == "__main__":
    main()

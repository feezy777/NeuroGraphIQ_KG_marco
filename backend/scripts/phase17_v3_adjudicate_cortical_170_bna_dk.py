"""Phase1.7 V3 - final ontology adjudication of the 170 cortical Brainnetome <-> DK relations.

SCOPE: the 170 frozen BNA(G3_MESO_FINE) <-> DK-derived G1 cortical candidate relations.
No new candidate relations are created; nothing outside this universe is adjudicated.

Evidence used (all already produced and frozen; nothing regenerated):
  - BNA authoritative subregion table (Fan 2016 Table 1): macro gyrus + cytoarchitectonic area
  - 170 relation universe (proposed G1 per fine parcel)
  - V2 direct-spatial evidence (containment, rank, competitor) - SUPPORTING ONLY
  - GM-weighted evidence (rank, margin)                       - SUPPORTING ONLY

Methodology constraints inherited from the frozen support-domain audit (b970f48):
  SPATIAL_ROUTE_COMPATIBILITY = CONFIRMED, SUPPORT_DOMAIN_EQUIVALENCE = FALSE.
  Therefore absolute containment, COM displacement, raw outside-union fraction and
  support-domain volume difference are NOT decision criteria. Only relative ranking and
  margin may be used, and only as supporting evidence. Relation type is decided from the
  DOCUMENTED ATLAS DEFINITIONS, never from volume.

Relation type: every BNA parcel is a documented subdivision of a macro gyrus, while the G1
target is the DK macro region (whole gyrus or a gyral part). The relation is therefore
`narrower` in the frozen BR3 vocabulary (exact/broader/narrower/uncertain). `exact` is
refuted definitionally: there is no 1:1 correspondence (2..14 BNA parcels per DK region)
and the two sides are defined by different criteria (cytoarchitectonic area vs FreeSurfer
gyral territory). The corresponding canonical hierarchy predicate is `part_of`.

Outputs are NEW artifacts only. No existing evidence file is modified. No DB access.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
BNA_SUB = (BACKEND / "data" / "atlases" / "brainnetome" / "bna246" /
           "brainnetome_bna246_subregions_authoritative.csv")

UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
EV2 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence_v2.csv"
GMW = D16 / "phase17_v3_cortical_170_gm_weighted_evidence.csv"
G1MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
SDSTATUS = D16 / "phase17_v3_cortical_support_domain_status.json"

OUT_CROSS = D16 / "phase17_v3_cortical_bna_dk_macro_gyrus_crosswalk_v1.csv"
OUT_ADJ = D16 / "phase17_v3_cortical_170_final_adjudication.csv"
OUT_QUEUE = D16 / "phase17_v3_cortical_170_adjudication_review_queue.csv"
OUT_SUM = D16 / "phase17_v3_cortical_170_adjudication_summary.json"
OUT_MD = D16 / "phase17_v3_cortical_170_adjudication_diagnostics.md"

SCRIPT_VERSION = "phase17_v3_adjudicate_cortical_170_bna_dk.py v1"

# ---------------------------------------------------------------------------
# Curated BNA macro gyrus -> DK (FreeSurfer aparc) label crosswalk.
# Each entry is (allowed dk_labels, documented basis). Built from the two official
# atlas definitions, then verified against the frozen universe (see verify_crosswalk).
# ---------------------------------------------------------------------------
GYRUS_TO_DK = {
    "Superior frontal gyrus": ({"superiorfrontal"},
                               "same structure; DK 'superiorfrontal' is the whole SFG (Fan2016 Table1 macro gyrus SFG)"),
    "Middle frontal gyrus": ({"rostralmiddlefrontal", "caudalmiddlefrontal"},
                             "DK splits the MFG into rostral and caudal parts; BNA MFG subregions distribute across both"),
    "Inferior frontal gyrus": ({"parsopercularis", "parstriangularis", "parsorbitalis"},
                               "DK represents the IFG by its pars; BNA IFG subregions map to the pars labels present in the selected-62 set"),
    "Precentral gyrus": ({"precentral"}, "same structure; direct name equivalence"),
    "Postcentral gyrus": ({"postcentral"}, "same structure; direct name equivalence"),
    "Cingulate gyrus": ({"caudalanteriorcingulate", "rostralanteriorcingulate",
                         "posteriorcingulate", "isthmuscingulate"},
                        "DK splits the cingulate gyrus into anterior-caudal / anterior-rostral / posterior / isthmus parts"),
    "Orbital gyrus": ({"lateralorbitofrontal", "medialorbitofrontal"},
                      "BNA orbital-gyrus subregions lie in the DK lateral / medial orbitofrontal cortex"),
    "Insular gyrus": ({"insula"}, "same structure; DK 'insula' is the insular cortex"),
    "Superior temporal gyrus": ({"superiortemporal"}, "same structure; direct name equivalence"),
    "Middle temporal gyrus": ({"middletemporal"}, "same structure; direct name equivalence"),
    "Inferior temporal gyrus": ({"inferiortemporal"}, "same structure; direct name equivalence"),
    "Fusiform gyrus": ({"fusiform"}, "same structure; direct name equivalence"),
    "Parahippocampal gyrus": ({"parahippocampal", "entorhinal"},
                              "the DK entorhinal cortex is the anterior part of the parahippocampal gyrus; BNA PHG subregions cover both"),
    "Superior parietal lobule": ({"superiorparietal"}, "same structure; direct name equivalence"),
    "Inferior parietal lobule": ({"inferiorparietal", "supramarginal"},
                                 "DK splits the IPL into inferior parietal and supramarginal parts"),
    "Precuneus": ({"precuneus"}, "same structure; direct name equivalence"),
    "Paracentral lobule": ({"paracentral"}, "same structure; direct name equivalence"),
    "Lateral occipital cortex": ({"lateraloccipital"}, "same structure; direct name equivalence"),
    "MedioVentral occipital cortex": ({"lingual"},
                                      "the DK lingual gyrus lies within the medioventral occipital cortex"),
    "Posterior superior temporal sulcus": (set(),
                                           "no selected-62 DK target exists; not present in the frozen 170 universe"),
}

# Final adjudication states (task section 3), with the nearest existing project status.
STATUS_DIRECT = "VERIFIED_DIRECT_MAPPING"
STATUS_HIER = "VERIFIED_HIERARCHICAL_MAPPING"
STATUS_REVIEW = "PLAUSIBLE_MAPPING_NEEDS_HUMAN_REVIEW"
STATUS_REJ_SEM = "REJECTED_SEMANTIC_MISMATCH"
STATUS_REJ_LAT = "REJECTED_LATERALITY_MISMATCH"
STATUS_UNRES = "UNRESOLVED_INSUFFICIENT_EVIDENCE"
STATUS_CODE = {STATUS_DIRECT: "A", STATUS_HIER: "B", STATUS_REVIEW: "C",
               STATUS_REJ_SEM: "D", STATUS_REJ_LAT: "E", STATUS_UNRES: "F"}
REUSED_PROJECT_STATUS = {
    STATUS_DIRECT: "VERIFIED_DIRECT_CONTAINED",
    STATUS_HIER: "VERIFIED_HIERARCHICAL_MAPPING (no prior equivalent; new state required)",
    STATUS_REVIEW: "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW",
    STATUS_REJ_SEM: "ANATOMICAL_CONFLICT",
    STATUS_REJ_LAT: "REJECTED_LATERALITY_MISMATCH (no prior equivalent; new state required)",
    STATUS_UNRES: "ONTOLOGY_DEFINITION_DEPENDENT",
}

RELATION_TYPE = "narrower"
HIERARCHY_PREDICATE = "part_of"

# Pre-declared review gate (task section 7 default policy).
WEAK_MARGIN = 0.10          # gm_margin below this = weak spatial discrimination
MIDLINE_CROSS = 0.96        # correct_side_fraction below this = notable midline crossing


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def rows(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def write_csv(p: Path, cols: list[str], data: list[dict]) -> None:
    with open(p, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in data:
            w.writerow(r)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")

    univ = rows(UNIV)
    ev2 = {r["fine_region_id"]: r for r in rows(EV2)}
    gmw = {r["fine_region_id"]: r for r in rows(GMW)}
    g1 = {r["canonical_region_id"]: r for r in rows(G1MAN)}
    bna = {int(r["parcel_id"]): r for r in rows(BNA_SUB)}
    sd = json.loads(SDSTATUS.read_text(encoding="utf-8"))

    assert len(univ) == 170, f"universe size changed: {len(univ)}"
    assert sd["verdict"] == "CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED"
    assert sd["cross_route_spatial_compatibility"] == "SPATIALLY_COMPATIBLE"

    # ---- verify the curated crosswalk against every pairing actually proposed ----
    pairings = set()
    for r in univ:
        s = bna[int(r["parcel_id"])]
        pairings.add((s["macro_gyrus_name"], g1[r["proposed_g1_id"]]["dk_label"]))
    uncovered = [(mg, dk) for mg, dk in pairings
                 if mg not in GYRUS_TO_DK or dk not in GYRUS_TO_DK[mg][0]]
    assert not uncovered, f"crosswalk does not cover observed pairings: {sorted(uncovered)}"

    trace, queue = [], []
    for r in univ:
        pid = r["fine_region_id"]
        s = bna[int(r["parcel_id"])]
        t = g1[r["proposed_g1_id"]]
        e, g = ev2[pid], gmw[pid]
        macro, dk_label = s["macro_gyrus_name"], t["dk_label"]
        hemi_ok = (r["hemisphere"] == t["hemisphere"])
        correct = float(e["correct_side_fraction"])
        contra = float(e["contralateral_fraction"])
        raw_rank = int(g["raw_proposed_rank"])
        gm_rank = int(g["gm_weighted_rank"])
        margin = float(g["gm_margin"])
        competitor = g["gm_best_non_proposed_id"]
        comp_name = g1[competitor]["name"] if competitor in g1 else ""

        # ---- evidence evaluation (semantic first, spatial supporting only) ----
        sem_ok = macro in GYRUS_TO_DK and dk_label in GYRUS_TO_DK[macro][0]
        split = len(GYRUS_TO_DK[macro][0]) > 1 if macro in GYRUS_TO_DK else False
        reasons, review_reasons = [], []

        if not hemi_ok:
            status, rel = STATUS_REJ_LAT, ""
            reasons.append("LAT_HEMISPHERE_LABEL_CONFLICT")
        elif not sem_ok:
            status, rel = STATUS_REJ_SEM, ""
            reasons.append("SEM_MACRO_GYRUS_DK_LABEL_INCOMPATIBLE")
        else:
            # semantic + hierarchy evidence established -> documented subdivision relation
            rel = RELATION_TYPE
            reasons.append("SEM_MACRO_GYRUS_SPLIT_BY_DK" if split
                           else "SEM_EXACT_MACRO_GYRUS_MATCH")
            reasons.append("HIER_FINE_SUBDIVISION_OF_MACRO_GYRUS")
            reasons.append("LAT_SIDE_CONSISTENT")
            reasons.append("SPATIAL_RANK1_RAW_AND_GM"
                           if (raw_rank == 1 and gm_rank == 1) else "SPATIAL_RANK_NOT_1")
            if margin < WEAK_MARGIN:
                review_reasons.append("SPATIAL_WEAK_DISCRIMINATION")
            if correct < MIDLINE_CROSS:
                review_reasons.append("LAT_MIDLINE_PARTIAL_CROSSING")
            if raw_rank != 1 or gm_rank != 1:
                review_reasons.append("SPATIAL_SEMANTIC_DISAGREEMENT")
            status = STATUS_REVIEW if review_reasons else STATUS_HIER

        trace.append({
            "relation_id": r["relation_id"],
            "source_canonical_id": pid,
            "source_name": s["official_hemisphere_code"],
            "source_macro_gyrus": macro,
            "source_cytoarchitectonic_id": s["modified_cytoarchitectonic_code"],
            "source_cytoarchitectonic_name": s["modified_cytoarchitectonic_name"],
            "target_canonical_id": r["proposed_g1_id"],
            "target_name": t["name"],
            "target_dk_label": dk_label,
            "hemisphere": r["hemisphere"],
            "relation_type": rel,
            "hierarchy_predicate": HIERARCHY_PREDICATE if rel else "",
            "final_adjudication_status": status,
            "status_code": STATUS_CODE[status],
            "reused_project_status": REUSED_PROJECT_STATUS[status],
            "semantic_evidence_code": "SEM_MACRO_GYRUS_TO_DK_CROSSWALK",
            "semantic_evidence_detail": GYRUS_TO_DK[macro][1] if macro in GYRUS_TO_DK else "",
            "hierarchy_evidence": (f"{s['official_hemisphere_code']} is the "
                                   f"{s['modified_cytoarchitectonic_name']} subdivision of the "
                                   f"{macro}; target is the DK region '{t['name']}'"),
            "laterality_status": ("SIDE_CONSISTENT" if hemi_ok else "HEMISPHERE_CONFLICT")
                                 + ("" if correct >= MIDLINE_CROSS else " + MIDLINE_CROSSING"),
            "correct_side_fraction": correct,
            "contralateral_fraction": contra,
            "spatial_raw_rank": raw_rank,
            "spatial_gm_weighted_rank": gm_rank,
            "spatial_gm_margin": margin,
            "spatial_competitor_target": comp_name,
            "provenance_source": "phase17_v3_cortical_170_relation_universe + V2 direct-spatial + GM-weighted",
            "decision_reason_codes": "|".join(reasons),
            "review_required": bool(review_reasons),
            "review_reason_codes": "|".join(review_reasons),
            "frozen_methodology_basis": "b970f48 CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED / SPATIALLY_COMPATIBLE",
        })
        if review_reasons:
            queue.append({
                "relation_id": r["relation_id"],
                "source_canonical_id": pid,
                "source_name": s["official_hemisphere_code"],
                "source_macro_gyrus": macro,
                "target_canonical_id": r["proposed_g1_id"],
                "target_name": t["name"],
                "hemisphere": r["hemisphere"],
                "review_reason_codes": "|".join(review_reasons),
                "review_reason_detail": "; ".join(
                    (f"margin {margin:.4f} < {WEAK_MARGIN} (competitor: {comp_name})"
                     if x == "SPATIAL_WEAK_DISCRIMINATION" else
                     f"correct_side_fraction {correct:.4f} < {MIDLINE_CROSS}"
                     if x == "LAT_MIDLINE_PARTIAL_CROSSING" else
                     "spatial rank is not 1 while semantic evidence asserts the pairing")
                    for x in review_reasons),
                "correct_side_fraction": correct,
                "spatial_gm_margin": margin,
                "proposed_status": STATUS_CODE[status],
            })

    # ---- crosswalk artifact ----
    cw_rows = []
    for mg, (dks, basis) in GYRUS_TO_DK.items():
        used = sorted({dk for m, dk in pairings if m == mg})
        cw_rows.append({
            "bna_macro_gyrus": mg,
            "allowed_dk_labels": "|".join(sorted(dks)),
            "dk_labels_used_in_universe": "|".join(used),
            "used_count": sum(1 for r in univ if bna[int(r["parcel_id"])]["macro_gyrus_name"] == mg),
            "all_used_labels_allowed": all(d in dks for d in used),
            "documented_basis": basis,
        })
    write_csv(OUT_CROSS, ["bna_macro_gyrus", "allowed_dk_labels", "dk_labels_used_in_universe",
                          "used_count", "all_used_labels_allowed", "documented_basis"], cw_rows)

    write_csv(OUT_ADJ, list(trace[0].keys()), trace)
    write_csv(OUT_QUEUE, list(queue[0].keys()), queue) if queue else write_csv(
        OUT_QUEUE, ["relation_id", "source_canonical_id", "source_name", "source_macro_gyrus",
                    "target_canonical_id", "target_name", "hemisphere", "review_reason_codes",
                    "review_reason_detail", "correct_side_fraction", "spatial_gm_margin",
                    "proposed_status"], [])

    from collections import Counter
    sc = Counter(t["status_code"] for t in trace)
    rc = Counter(t["relation_type"] for t in trace)
    dec = Counter(c for t in trace for c in t["decision_reason_codes"].split("|") if c)
    excluded = [p for p in range(1, 211)
                if p not in {int(r["parcel_id"]) for r in univ}]

    summary = dict(
        summary_id="CORTICAL_170_FINAL_ADJUDICATION_V1",
        universe=len(univ),
        scope="Brainnetome G3_MESO_FINE cortical parcels -> DK-derived G1 cortical regions",
        frozen_methodology_basis=dict(
            commit="b970f48",
            verdict=sd["verdict"],
            spatial_compatibility=sd["cross_route_spatial_compatibility"],
            not_used_as_criteria=["absolute containment", "COM displacement",
                                  "raw outside-union fraction",
                                  "support-domain volume difference"],
            used_as_supporting_only=["relative spatial ranking", "GM-weighted ranking and margin"],
        ),
        status_counts={s: int(n) for s, n in sc.items()},
        status_detail={s: int(n) for s, n in sc.items()},
        relation_type_counts=dict(rc),
        decision_reason_counts=dict(dec),
        rejected_semantic=int(sc.get("D", 0)),
        rejected_laterality=int(sc.get("E", 0)),
        unresolved=int(sc.get("F", 0)),
        review_queue=len(queue),
        review_gate=dict(weak_margin_lt=WEAK_MARGIN, midline_crossing_lt=MIDLINE_CROSS),
        relation_type_rationale=(
            "Every BNA parcel is a documented cytoarchitectonic subdivision of a macro gyrus "
            "while the G1 target is the DK macro region (whole gyrus or gyral part); the "
            "relation is therefore `narrower`. `exact` is refuted definitionally (2..14 BNA "
            "parcels per DK region; different defining criteria), not geometrically. Volume "
            "ratios were explicitly NOT used: they are dominated by the frozen support-domain "
            "thickness offset (median group ratio 2.28 approximates the measured 2.63)."),
        excluded_parcels=dict(count=len(excluded),
                              reason="no proposed G1 target inside the frozen 170 universe "
                                     "(bankssts / frontalpole / temporalpole and other "
                                     "unassigned DK targets); no new candidates created",
                              parcel_ids=excluded),
        new_relation_types_created=[],
        reused_project_statuses=REUSED_PROJECT_STATUS,
        evidence_inputs={n: dict(path=str(p).replace("\\", "/"), sha256=sha256(p))
                         for n, p in (("universe", UNIV), ("direct_spatial_v2", EV2),
                                      ("gm_weighted", GMW), ("g1_manifest", G1MAN),
                                      ("bna_authoritative", BNA_SUB))},
        no_mapping_mutation=True, no_geometry_change=True, no_transform_change=True,
        no_new_spatial_evidence=True, no_db_write=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    OUT_SUM.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [
        "# Phase1.7 V3 - final adjudication of the 170 cortical Brainnetome <-> DK relations", "",
        f"universe: {len(univ)} relations | scope: BNA G3_MESO_FINE cortical -> DK-derived G1 cortical",
        f"frozen methodology basis: b970f48 {sd['verdict']} / "
        f"{sd['cross_route_spatial_compatibility']}",
        "criteria NOT used: absolute containment, COM displacement, raw outside-union fraction, "
        "support-domain volume difference.",
        "criteria used as supporting only: relative spatial ranking and GM-weighted margin.", "",
        "## Final states",
    ]
    for status, code in sorted(STATUS_CODE.items(), key=lambda x: x[1]):
        md.append(f"- {code}. {status}: {int(sc.get(code, 0))}")
    md += [
        f"- review queue: {len(queue)} (weak margin < {WEAK_MARGIN} or midline crossing < {MIDLINE_CROSS})",
        f"- excluded BNA cortical parcels (no frozen G1 target, out of scope): {len(excluded)}", "",
        "## Relation type",
        f"all {len(univ)} relations are `narrower` (BR3 vocabulary), hierarchy predicate `part_of`; "
        "0 `exact`. Rationale: documented subdivision relation, not volume-based.", "",
        "## Decision reason codes",
    ]
    md += [f"- {k}: {v}" for k, v in sorted(dec.items(), key=lambda x: -x[1])]
    md += ["", "No existing evidence file was modified. No DB access. No new candidate relations.", ""]
    OUT_MD.write_text("\n".join(md) + "\n", encoding="utf-8")

    print("universe:", len(univ))
    print("status counts:", dict(sc))
    print("relation types:", dict(rc))
    print("review queue:", len(queue), [q["source_name"] for q in queue])
    print("excluded parcels:", len(excluded))


if __name__ == "__main__":
    main()

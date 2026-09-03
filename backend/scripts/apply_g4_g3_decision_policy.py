"""Phase 2I-A — G4→G3 Scientific Decision Policy Application V1.

Applies a FIXED, conservative, auditable decision policy to the 440 canonical
G4 leaves (376 direct spatial evidence + 64 shared-evidence-only), producing
preliminary scientific decisions for owner review. This is policy-derived
decision PREP — NOT expert approval, NOT mapping candidate staging, NOT DB
writes, NOT approval/promotion.

Decision vocabulary (source-level, scientific only):
  APPROVE_CONTAINED_IN / APPROVE_DOMINANT_OVERLAP / PARTIAL_OVERLAP /
  NO_G3_MAPPING / CONFLICT_REVIEW / SHARED_SPATIAL_EVIDENCE_ONLY

Evidence priority (frozen):
  PRIMARY  = Julich probability x Brainnetome probability
  AUXILIARY= hard-label (BN_Atlas deterministic) coverage of G4 probability mass
Hard-label coverage may explain containment but never overrides probability
evidence by itself; disagreement => CONFLICT_REVIEW.

Policy order (fixed, see policy_order in summary):
  shared exclusion -> noncanonical exclusion -> NO_G3_MAPPING
  -> disagreement conflict -> contained -> dominant -> partial -> fallback conflict

Operational note (recorded in the policy artifact): 0.80 / 0.50 etc. are
project-conservative operational decision thresholds, NOT a claim of any
universal neuroscience '80% rule'.

Usage:
    python scripts/apply_g4_g3_decision_policy.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
POLICY_VERSION = "G4_G3_SCIENTIFIC_POLICY_V1"

COV = np.load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))
HARD = COV["coverage"]          # 414 x 246 coverage
UNC = COV["uncovered"]
G2G = np.load(str(INT / "g4_g3_probability_overlap_matrix.npz"))
M = G2G["M"]                     # 414 x 246 joint

OUT_LEDGER = INT / "g4_g3_scientific_decision_policy_v1.csv"
OUT_REL = INT / "g4_g3_preliminary_relation_decisions.csv"
OUT_CONFLICT = INT / "g4_g3_conflict_review_queue.csv"
OUT_SHARED = INT / "g4_g3_shared_canonical_decision_exclusions.csv"
OUT_NONCANON = INT / "g4_g3_noncanonical_spatial_components.csv"
OUT_SUMMARY = INT / "g4_g3_scientific_decision_policy_summary.json"


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x):
    return None if x in ("", None) else float(x)


def _atomic(path, fn):
    tmp = path.with_name(path.name + ".tmp")
    fn(tmp)
    if path.exists():
        path.unlink()
    tmp.rename(path)


def _write_csv(path, rows, cols):
    def _fn(tmp):
        with open(tmp, "w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow(r)
    _atomic(path, _fn)


def main() -> int:
    profiles = _rows(INT / "g4_g3_overlap_interpretation_profiles.csv")
    canonical = _rows(INT / "g4_julich_spatial_to_canonical_alignment.csv")
    canon = {r["spatial_region_id"]: r for r in canonical}
    g3cols = _rows(INT / "g4_g3_probability_overlap_columns.csv")
    g3id_by_idx = {int(r["column_index"]) - 1: r["canonical_g3_id"] for r in g3cols}

    prof_by_row = {int(r["row_index"]): r for r in profiles}

    # ---- assemble the three evidence sets over canonical leaves ----
    direct = {}   # canonical leaf -> (component row)
    shared_leaves = {}   # canonical leaf -> component row
    noncanonical = []    # one-to-one components whose leaf is not canonical
    for r in profiles:
        leaves = [x for x in r["canonical_g4_ids"].split(";") if x]
        if r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL":
            leaf = leaves[0]
            if leaf in canon:
                direct[leaf] = r
            else:
                noncanonical.append(r)
        else:
            for leaf in leaves:
                if leaf in canon:
                    shared_leaves[leaf] = r
    assert len(direct) == 376, len(direct)
    assert len(noncanonical) == 14, len(noncanonical)
    assert len(shared_leaves) == 64, len(shared_leaves)
    assert len(direct) + len(shared_leaves) == 440

    # ---- decision helpers (all values from the component-level evidence) ----
    def no_mapping(r):
        """(decision, reason) for conservative NO_G3_MAPPING, else None."""
        pp1 = _f(r["pp_top1_joint_mass"])
        hard_total = _f(r["hard_total_bna_coverage"]) or 0.0
        pp_g4w1 = _f(r["pp_top1_g4_weighted"])
        pp1_null = r["pp_top1_g3_id"] in ("", None)
        if pp1_null and hard_total == 0.0:
            return ("NO_G3_MAPPING", "ZERO_BNA_SPATIAL_ASSOCIATION")
        if (hard_total < 0.10) and (pp_g4w1 is not None and pp_g4w1 < 0.05):
            return ("NO_G3_MAPPING", "BNA_COVERAGE_GAP")
        return None

    def pp_ratio_ok(r, thr):
        r2 = _f(r["pp_top2_g4_weighted"])
        r1 = _f(r["pp_top1_g4_weighted"]) or 0.0
        if r2 is None or r2 == 0.0:
            return True  # single positive pp target
        return (r1 / r2) >= thr

    def has_major_flag(r):
        fl = r["qa_flags"] or ""
        return ("NO_SPATIAL_ASSOCIATION" in fl) or ("BNA_COVERAGE_GAP_CANDIDATE" in fl)

    def decide(r, j):
        hard_total = _f(r["hard_total_bna_coverage"]) or 0.0
        hard1 = _f(r["hard_top1_coverage"])
        hard2 = _f(r["hard_top2_coverage"])
        unc = _f(r["bna_uncovered_fraction"]) or 1.0
        eff = _f(r["effective_target_count"])
        agree = r["top1_agreement"]
        hard_margin = _f(r["hard_top1_top2_margin"])

        nm = no_mapping(r)
        if nm is not None:
            return {"decision": nm[0], "reason_code": nm[1]}
        if agree == "FALSE":
            return {"decision": "CONFLICT_REVIEW", "reason_code": "PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT"}
        if agree != "TRUE":
            return {"decision": "CONFLICT_REVIEW", "reason_code": "PP_TOP1_OR_HARD_TOP1_UNDEFINED"}
        # contained
        if ((hard1 is not None and hard1 >= 0.80) and unc <= 0.15
                and (hard2 is None or hard2 <= 0.10)
                and (eff is None or eff <= 2.0)
                and pp_ratio_ok(r, 1.50)
                and not has_major_flag(r)):
            return {"decision": "APPROVE_CONTAINED_IN", "reason_code": "CONTAINED_CRITERIA_V1"}
        # dominant
        if (hard_total >= 0.70 and hard1 is not None and hard1 >= 0.50
                and (hard_margin is None or hard_margin >= 0.20)
                and pp_ratio_ok(r, 1.25)
                and not has_major_flag(r)):
            return {"decision": "APPROVE_DOMINANT_OVERLAP", "reason_code": "DOMINANT_CRITERIA_V1"}
        # partial (multi-target)
        if hard_total >= 0.60:
            cov = HARD[j]
            mrow = M[j]
            tgt = np.flatnonzero((cov >= 0.15) & (mrow > 0))
            if len(tgt) >= 2:
                top2 = np.sort(cov[tgt])[::-1][:2]
                if top2.sum() >= 0.60:
                    # consistency: every hard partial target must rank in pp Top3
                    pos = np.flatnonzero(mrow > 0)
                    rank = {int(i): k + 1 for k, i in enumerate(pos[np.argsort(-mrow[pos])])}
                    for i in tgt:
                        if rank.get(int(i), 99) > 3:
                            return {"decision": "CONFLICT_REVIEW",
                                    "reason_code": "PARTIAL_TARGET_EVIDENCE_INCONSISTENT"}
                    return {"decision": "PARTIAL_OVERLAP", "reason_code": "PARTIAL_CRITERIA_V1",
                            "partial_targets": [int(i) for i in tgt]}
        # fallback conflict reason
        if hard_total < 0.10 and (_f(r["pp_top1_g4_weighted"]) or 0) >= 0.05:
            reason = "LOW_BNA_COVERAGE"
        elif (eff or 0) > 3.0:
            reason = "HIGH_FRAGMENTATION"
        elif hard_total >= 0.50:
            reason = "LOW_DOMINANCE"
        else:
            reason = "DIFFUSE_ASSOCIATION"
        return {"decision": "CONFLICT_REVIEW", "reason_code": reason}

    # ---- direct decisions ----
    direct_dec = {}
    for leaf, r in direct.items():
        j = int(r["row_index"]) - 1
        direct_dec[leaf] = {"row": r, "j": j, **decide(r, j)}

    # ---- ledger (440 canonical leaves) ----
    ledger = []
    for leaf, c in canon.items():
        ent = c["g4_entity_id"]
        if leaf in direct_dec:
            r = direct_dec[leaf]["row"]
            d = direct_dec[leaf]
            status = "DIRECT_CANONICAL_SPATIAL_EVIDENCE"
        elif leaf in shared_leaves:
            r = shared_leaves[leaf]
            d = {"decision": "SHARED_SPATIAL_EVIDENCE_ONLY",
                 "reason_code": "NO_INDEPENDENT_LEAF_SPATIAL_EVIDENCE"}
            status = "SHARED_SPATIAL_EVIDENCE"
        else:  # should never happen (440 all covered)
            raise RuntimeError(f"uncovered canonical leaf {leaf}")
        rollup = d["decision"] == "APPROVE_CONTAINED_IN"
        ledger.append({
            "canonical_g4_id": ent,
            "canonical_g4_name": c["g4_name"],
            "hemisphere": c["hemisphere"],
            "spatial_component_id": r["julich_component_id"],
            "spatial_asset_file": r["julich_asset_file"],
            "spatial_evidence_status": status,
            "pp_top1_g3": r["pp_top1_g3_id"],
            "pp_top1_name": r["pp_top1_name"],
            "pp_top1_g4_weighted": r["pp_top1_g4_weighted"],
            "pp_top1_joint_mass": r["pp_top1_joint_mass"],
            "hard_top1_g3": r["hard_top1_g3_id"],
            "hard_top1_coverage": r["hard_top1_coverage"],
            "hard_top2_coverage": r["hard_top2_coverage"],
            "hard_top1_top2_margin": r["hard_top1_top2_margin"],
            "hard_total_bna_coverage": r["hard_total_bna_coverage"],
            "bna_uncovered_fraction": r["bna_uncovered_fraction"],
            "effective_target_count": r["effective_target_count"],
            "top1_agreement": r["top1_agreement"],
            "scientific_decision": d["decision"],
            "decision_reason_code": d["reason_code"],
            "future_rollup_eligible": str(rollup),
            "future_primary_rollup": str(rollup),
            "decision_policy_version": POLICY_VERSION,
            "review_status": "PENDING_OWNER_REVIEW",
        })
    ledger.sort(key=lambda r: r["canonical_g4_id"])
    assert len(ledger) == 440
    _write_csv(OUT_LEDGER, ledger, list(ledger[0].keys()))

    # ---- relation-level preliminary rows (only contained/dominant/partial) ----
    rel_rows = []
    for leaf, d in direct_dec.items():
        ent = canon[leaf]["g4_entity_id"]
        gname = canon[leaf]["g4_name"]
        r = d["row"]
        dec = d["decision"]
        hemi = canon[leaf]["hemisphere"]
        if dec == "APPROVE_CONTAINED_IN":
            targets = [(_f(r["hard_top1_coverage"]), r["hard_top1_g3_id"])]
            rel = "APPROVE_CONTAINED_IN"
        elif dec == "APPROVE_DOMINANT_OVERLAP":
            targets = [(_f(r["hard_top1_coverage"]), r["hard_top1_g3_id"])]
            rel = "APPROVE_DOMINANT_OVERLAP"
        elif dec == "PARTIAL_OVERLAP":
            cov = HARD[d["j"]]
            mrow = M[d["j"]]
            tgt = d["partial_targets"]
            targets = [(float(cov[i]), g3id_by_idx[i]) for i in tgt]
            rel = "PARTIAL_OVERLAP"
        else:
            continue
        for cov_t, g3id in targets:
            rel_rows.append({
                "canonical_g4_id": ent, "canonical_g4_name": gname, "hemisphere": hemi,
                "spatial_component_id": r["julich_component_id"],
                "relation": rel,
                "target_g3_id": g3id,
                "target_coverage": round(cov_t, 6) if cov_t is not None else None,
                "source_pp_top1_g4_weighted": r["pp_top1_g4_weighted"],
                "source_hard_total_bna_coverage": r["hard_total_bna_coverage"],
                "source_bna_uncovered_fraction": r["bna_uncovered_fraction"],
                "decision_reason_code": d["reason_code"],
                "future_rollup_eligible": str(rel == "APPROVE_CONTAINED_IN"),
                "future_primary_rollup": str(rel == "APPROVE_CONTAINED_IN"),
                "decision_policy_version": POLICY_VERSION,
                "preliminary_relation_status": "PENDING_OWNER_REVIEW",
            })
    rel_cols = ["canonical_g4_id", "canonical_g4_name", "hemisphere", "spatial_component_id",
                "relation", "target_g3_id", "target_coverage", "source_pp_top1_g4_weighted",
                "source_hard_total_bna_coverage", "source_bna_uncovered_fraction",
                "decision_reason_code", "future_rollup_eligible", "future_primary_rollup",
                "decision_policy_version", "preliminary_relation_status"]
    _write_csv(OUT_REL, rel_rows, rel_cols)

    # ---- conflict queue (sorted for review) ----
    conflict = [r for r in ledger if r["scientific_decision"] == "CONFLICT_REVIEW"]
    def _prio(x):
        hc = _f(x["hard_total_bna_coverage"]) or 0.0
        if x["decision_reason_code"] == "PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT":
            return (0, -hc)
        if x["decision_reason_code"] == "PARTIAL_TARGET_EVIDENCE_INCONSISTENT":
            return (1, -hc)
        if hc >= 0.5:
            return (2, -hc)
        return (3, -hc)
    conflict.sort(key=_prio)
    _write_csv(OUT_CONFLICT, conflict, list(ledger[0].keys()))

    # ---- shared canonical exclusions (64) ----
    shared_rows = [r for r in ledger if r["scientific_decision"] == "SHARED_SPATIAL_EVIDENCE_ONLY"]
    assert len(shared_rows) == 64
    for r in shared_rows:
        r["mapping_candidate_allowed"] = "FALSE"
    sh_cols = list(ledger[0].keys()) + ["mapping_candidate_allowed"]
    _write_csv(OUT_SHARED, shared_rows, sh_cols)

    # ---- noncanonical spatial audit (14) ----
    noncan_rows = []
    for r in sorted(noncanonical, key=lambda x: x["row_index"]):
        leaf = [x for x in r["canonical_g4_ids"].split(";") if x][0]
        noncan_rows.append({
            "row_index": r["row_index"],
            "spatial_component_id": r["julich_component_id"],
            "julich_asset_file": r["julich_asset_file"],
            "julich_leaf_id": leaf,
            "julich_region_name": r["julich_region_name"],
            "julich_hemisphere": r["julich_hemisphere"],
            "reason_not_in_canonical": "leaf id absent from g4_julich_spatial_to_canonical_alignment (440-canonical registry)",
            "pp_top1_g3_id": r["pp_top1_g3_id"],
            "pp_top1_name": r["pp_top1_name"],
            "pp_top1_g4_weighted": r["pp_top1_g4_weighted"],
            "hard_total_bna_coverage": r["hard_total_bna_coverage"],
            "bna_uncovered_fraction": r["bna_uncovered_fraction"],
            "production_mapping_allowed": "FALSE",
            "decision_policy_version": POLICY_VERSION,
        })
    assert len(noncan_rows) == 14
    _write_csv(OUT_NONCANON, noncan_rows, list(noncan_rows[0].keys()))

    # ---- sensitivity analysis (descriptive only) ----
    # candidate pool: direct rows that passed shared/no-mapping/disagreement (i.e. reach decision stages)
    eligible = {leaf: d for leaf, d in direct_dec.items()
                if d["decision"] in ("APPROVE_CONTAINED_IN", "APPROVE_DOMINANT_OVERLAP",
                                     "PARTIAL_OVERLAP", "CONFLICT_REVIEW")}
    def contained_cut(cut):
        n = 0
        for leaf, d in eligible.items():
            r = d["row"]
            hard1 = _f(r["hard_top1_coverage"])
            if (hard1 is not None and hard1 >= cut
                    and (_f(r["bna_uncovered_fraction"]) or 1.0) <= 0.15
                    and (_f(r["hard_top2_coverage"]) or 0.0) <= 0.10
                    and (_f(r["effective_target_count"]) or 99) <= 2.0
                    and pp_ratio_ok(r, 1.50)
                    and not has_major_flag(r) and r["top1_agreement"] == "TRUE"):
                n += 1
        return n
    def dominant_cut(cut):
        n = 0
        for leaf, d in eligible.items():
            if d["decision"] == "APPROVE_CONTAINED_IN":  # dominant stage runs after contained
                continue
            r = d["row"]
            hard1 = _f(r["hard_top1_coverage"])
            hard_total = _f(r["hard_total_bna_coverage"]) or 0.0
            if (r["top1_agreement"] == "TRUE" and hard_total >= 0.70
                    and hard1 is not None and hard1 >= cut
                    and (_f(r["hard_top1_top2_margin"]) or 0.0) >= 0.20
                    and pp_ratio_ok(r, 1.25)
                    and not has_major_flag(r)):
                n += 1
        return n
    sensitivity = {
        "contained_cut_counts": {f"{c:.2f}": contained_cut(c) for c in (0.75, 0.80, 0.85)},
        "dominant_top1_cut_counts": {f"{c:.2f}": dominant_cut(c) for c in (0.45, 0.50, 0.55)},
        "note": "SENSITIVITY_ANALYSIS only; does not change V1 policy result (V1 uses 0.80 contained / 0.50 dominant).",
    }

    # ---- summary ----
    from collections import Counter
    dec_counts = Counter(r["scientific_decision"] for r in ledger)
    rel_reason = Counter(r["decision_reason_code"] for r in ledger if r["scientific_decision"] == "CONFLICT_REVIEW")
    rollup_count = sum(1 for r in ledger if r["future_rollup_eligible"] == "True")
    summary = {
        "phase": "G4_G3_SCIENTIFIC_DECISION_POLICY_APPLICATION_V1",
        "canonical_g4_count": 440,
        "direct_decisionable_count": 376,
        "shared_canonical_count": 64,
        "noncanonical_spatial_component_count": 14,
        "decision_counts": {k: v for k, v in dec_counts.items()},
        "preliminary_relation_row_count": len(rel_rows),
        "contained_rollup_source_count": rollup_count,
        "conflict_reason_distribution": dict(rel_reason),
        "policy_order": ["1 SHARED_EVIDENCE_EXCLUSION", "2 NONCANONICAL_COMPONENT_EXCLUSION",
                         "3 NO_G3_MAPPING_ZERO_OR_COVERAGE_GAP", "4 DISAGREEMENT_CONFLICT",
                         "5 APPROVE_CONTAINED_IN", "6 APPROVE_DOMINANT_OVERLAP",
                         "7 PARTIAL_OVERLAP", "8 FALLBACK_CONFLICT"],
        "policy_thresholds_v1": {
            "contained_hard_top1_coverage_min": 0.80,
            "contained_uncovered_max": 0.15,
            "contained_hard_top2_max": 0.10,
            "contained_effective_targets_max": 2.0,
            "contained_pp_ratio_min": 1.50,
            "dominant_hard_total_min": 0.70,
            "dominant_hard_top1_min": 0.50,
            "dominant_margin_min": 0.20,
            "dominant_pp_ratio_min": 1.25,
            "partial_hard_total_min": 0.60,
            "partial_target_cov_min": 0.15,
            "partial_top2_cumulative_min": 0.60,
            "no_mapping_gap_hard_total_max": 0.10,
            "no_mapping_gap_pp_g4w_max": 0.05,
            "note": "project-conservative OPERATIONAL thresholds; NOT a universal neuroscience rule",
        },
        "policy_semantics": {
            "APPROVE_CONTAINED_IN": "majority of G4 mass inside ONE G3 + pp/hard agreement; future rollup TRUE (hierarchical parent)",
            "APPROVE_DOMINANT_OVERLAP": "clear dominant G3 but NOT strict containment; future rollup FALSE (dominant != parent)",
            "PARTIAL_OVERLAP": ">=2 co-dominant G3 targets (all targets with hard cov>=0.15 kept); future rollup FALSE",
            "NO_G3_MAPPING": "conservative: no reliable G3 association (zero BNA spatial association or coverage gap)",
            "CONFLICT_REVIEW": "evidence disagreement / near-boundary / ambiguous; NOT auto-decided",
            "SHARED_SPATIAL_EVIDENCE_ONLY": "no independent leaf spatial evidence; governance exclusion, NOT an ontology relation",
        },
        "sensitivity_analysis": sensitivity,
        "review_status": "PENDING_OWNER_REVIEW",
        "owner_review_required": True,
        "database_write": False,
        "mapping_candidate_staging": False,
        "approval_promotion": False,
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    _atomic(OUT_SUMMARY, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    # ---- integrity prints ----
    print("decisions:", dict(dec_counts))
    print("relation rows:", len(rel_rows), "| rollup sources:", rollup_count)
    print("conflict:", len(conflict), dict(rel_reason))
    print("sensitivity:", sensitivity)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 2I-C — Final Owner Scientific Decision Freeze.

Freezes the owner-confirmed scientific decisions into ONE final 440 canonical
G4 source-level ledger plus relation / exclusion / summary artifacts.

No overlap recompute, no 2G/2H/2I-A/2I-B modification, no DB, no staging, no
commit. OWNER_SCIENTIFIC_REVIEWED != production approved.

Final composition (conserved sources):
  APPROVE_CONTAINED_IN = 20        (2I-A contained minus VTM-00000370 -> conflict,
                                     minus Ph3-00000591 -> dominant)
  APPROVE_DOMINANT_OVERLAP = 110   (2I-A 109 + Ph3)
  PARTIAL_OVERLAP = 101 + 20 concordant + accepted-from-21 (final multi-target gate)
  NO_G3_MAPPING = 18 (frozen)
  SHARED_SPATIAL_EVIDENCE_ONLY = 64 (frozen)
  CONFLICT_REVIEW = remainder
  Total = 440.

Semantic compatibility gate on the 20 contained: only EXACT_FAMILY /
NESTED_COMPATIBLE_FAMILY allowed for rollup=TRUE; gate must yield 0 failures.
Operational note: 0.60 / 0.75 in the multi-target gate are PROJECT_OPERATIONAL
thresholds, not universal neuroscience thresholds (recorded in policy metadata).

Usage:
    python scripts/freeze_g4_g3_final_decisions.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
POLICY = "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"

LEDGER_A = INT / "g4_g3_scientific_decision_policy_v1.csv"
PROF = INT / "g4_g3_overlap_interpretation_profiles.csv"
COLS = list(csv.DictReader(open(INT / "g4_g3_probability_overlap_columns.csv", encoding="utf-8-sig")))
HARD = np.load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))["coverage"]
M = np.load(str(INT / "g4_g3_probability_overlap_matrix.npz"))["M"]

OUT_LEDGER = INT / "g4_g3_final_scientific_decisions.csv"
OUT_REL = INT / "g4_g3_final_relation_decisions.csv"
OUT_EXCL = INT / "g4_g3_final_scientific_exclusions.csv"
OUT_SUM = INT / "g4_g3_final_scientific_decision_summary.json"

VTM = "NGIQ-BR-00000370"   # -> CONFLICT (semantic family mismatch)
PH3 = "NGIQ-BR-00000591"   # -> DOMINANT (not containment)
FG5 = "NGIQ-BR-00000599"   # contained, owner semantic+spatial concordance

# semantic family status for the FINAL 20 contained pairs
# (assigned from official Julich + BNA names; only allowed classes used)
SEMANTIC = {
    "NGIQ-BR-00000335": "EXACT_FAMILY", "NGIQ-BR-00000337": "EXACT_FAMILY",
    "NGIQ-BR-00000338": "EXACT_FAMILY", "NGIQ-BR-00000413": "NESTED_COMPATIBLE_FAMILY",
    "NGIQ-BR-00000465": "NESTED_COMPATIBLE_FAMILY", "NGIQ-BR-00000467": "NESTED_COMPATIBLE_FAMILY",
    "NGIQ-BR-00000468": "NESTED_COMPATIBLE_FAMILY", "NGIQ-BR-00000494": "NESTED_COMPATIBLE_FAMILY",
    "NGIQ-BR-00000512": "NESTED_COMPATIBLE_FAMILY", "NGIQ-BR-00000515": "NESTED_COMPATIBLE_FAMILY",
    "NGIQ-BR-00000520": "EXACT_FAMILY", "NGIQ-BR-00000521": "EXACT_FAMILY",
    "NGIQ-BR-00000522": "EXACT_FAMILY", "NGIQ-BR-00000547": "EXACT_FAMILY",
    "NGIQ-BR-00000548": "EXACT_FAMILY", "NGIQ-BR-00000583": "NESTED_COMPATIBLE_FAMILY",
    "NGIQ-BR-00000597": "EXACT_FAMILY", "NGIQ-BR-00000599": "EXACT_FAMILY",
    "NGIQ-BR-00000628": "NESTED_COMPATIBLE_FAMILY", "NGIQ-BR-00000664": "EXACT_FAMILY",
}
ALLOWED = {"EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY"}


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x):
    return None if x in ("", None) else float(x)


def g3info(g3id):
    if not g3id or g3id in ("", "-"):
        return {}
    for c in COLS:
        if c["canonical_g3_id"] == g3id:
            return {"g3": g3id, "code": c.get("g3_region_name")}
    return {"g3": g3id}


def selected_targets(j):
    cov = HARD[j]
    mrow = M[j]
    pos = [int(i) for i in np.flatnonzero(mrow > 0)]
    pos.sort(key=lambda i: -mrow[i])
    rank = {i: k + 1 for k, i in enumerate(pos)}
    sel = [int(i) for i in np.flatnonzero((cov >= 0.15) & (mrow > 0))]
    sel.sort(key=lambda i: -cov[i])
    return sel, rank, cov, mrow


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
    base = _rows(LEDGER_A)
    prof = {r["julich_asset_file"]: r for r in _rows(PROF)}
    from collections import Counter
    assert Counter(r["scientific_decision"] for r in base) == {
        "APPROVE_CONTAINED_IN": 22, "APPROVE_DOMINANT_OVERLAP": 109, "PARTIAL_OVERLAP": 101,
        "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 126, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}
    g3id = {int(r["column_index"]) - 1: r["canonical_g3_id"] for r in COLS}

    def full(row):
        return {**row, **prof.get(row["spatial_asset_file"], {})}

    rows = [full(r) for r in base]
    by_id = {r["canonical_g4_id"]: r for r in rows}

    # ---- concordant 20 from 2I-B (read file, deterministic) ----
    disag = _rows(INT / "g4_g3_disagreement_partial_reassessment.csv")
    concordant_ids = {r["canonical_g4_id"] for r in disag
                      if r["revised_stratum"] == "PARTIAL_SET_CONCORDANT_REVIEW"}
    assert len(concordant_ids) == 20

    # ---- high-frag 21 plausible from 2I-B ----
    hf = _rows(INT / "g4_g3_high_fragmentation_reassessment.csv")
    plausible21 = [r for r in hf if r["revised_stratum"] == "PLAUSIBLE_MULTI_TARGET_PARTIAL"]
    assert len(plausible21) == 21

    # ---- multi-target final gate on the 21 ----
    gate = {}
    for r in plausible21:
        gid = r["canonical_g4_id"]
        j = int(by_id[gid]["row_index"]) - 1
        sel, rank, cov, mrow = selected_targets(j)
        sel_cum = float(sum(cov[i] for i in sel))
        hard_total = _f(by_id[gid]["hard_total_bna_coverage"]) or 0.0
        explained = (sel_cum / hard_total) if hard_total > 0 else 0.0
        ok = (len(sel) >= 2 and sel_cum >= 0.60 and explained >= 0.75)
        if ok:
            reason = "FINAL_MULTI_TARGET_PARTIAL_GATE_PASS"
        elif sel_cum < 0.60 or len(sel) < 2:
            reason = "INSUFFICIENT_SELECTED_TARGET_COVERAGE"
        else:
            reason = "MULTI_TARGET_DIFFUSE_REMAINDER"
        gate[gid] = {"ok": ok, "n": len(sel), "cum": round(sel_cum, 4),
                     "hard_total": round(hard_total, 4), "explained": round(explained, 4),
                     "reason": reason,
                     "targets": [g3id[i] for i in sel]}
    accepted21 = [g for g, v in gate.items() if v["ok"]]
    rejected21 = [g for g, v in gate.items() if not v["ok"]]

    # ---- build final decision per canonical ----
    ledger = []
    rel = []
    for r in rows:
        gid = r["canonical_g4_id"]
        dec = r["scientific_decision"]
        reason = r["decision_reason_code"]
        if dec == "NO_G3_MAPPING":
            fdec, freason = "NO_G3_MAPPING", reason
        elif dec == "SHARED_SPATIAL_EVIDENCE_ONLY":
            fdec, freason = "SHARED_SPATIAL_EVIDENCE_ONLY", reason
        elif dec == "APPROVE_CONTAINED_IN":
            if gid == VTM:
                fdec, freason = "CONFLICT_REVIEW", "SEMANTIC_FAMILY_MISMATCH"
            elif gid == PH3:
                fdec, freason = "APPROVE_DOMINANT_OVERLAP", "STRONG_SPATIAL_OVERLAP_BUT_NOT_HIERARCHICAL_CONTAINMENT"
            else:
                fdec, freason = "APPROVE_CONTAINED_IN", (
                    "OWNER_SEMANTIC_AND_SPATIAL_CONCORDANCE" if gid == FG5 else "OWNER_CONFIRMED_CONTAINED")
        elif dec == "APPROVE_DOMINANT_OVERLAP":
            fdec, freason = "APPROVE_DOMINANT_OVERLAP", reason
        elif dec == "PARTIAL_OVERLAP":
            fdec, freason = "PARTIAL_OVERLAP", "OWNER_CONFIRMED_PARTIAL"
        elif dec == "CONFLICT_REVIEW":
            if gid in concordant_ids:
                fdec, freason = "PARTIAL_OVERLAP", "OWNER_CONFIRMED_PARTIAL_SET_CONCORDANT"
            elif gid in gate:
                fdec, freason = ("PARTIAL_OVERLAP" if gate[gid]["ok"] else "CONFLICT_REVIEW"), gate[gid]["reason"]
            else:
                fdec, freason = "CONFLICT_REVIEW", reason
        else:
            raise RuntimeError(gid, dec)

        rollup = fdec == "APPROVE_CONTAINED_IN"
        # semantic gate for contained
        if fdec == "APPROVE_CONTAINED_IN":
            sem = SEMANTIC.get(gid)
            if sem not in ALLOWED:
                raise RuntimeError(f"contained semantic failure {gid}: {sem}")
            sem_status = sem
        else:
            sem_status = "N/A"
        # boundary notes for dominant / partial
        review_note = ""
        if fdec == "APPROVE_DOMINANT_OVERLAP":
            h1 = _f(r["hard_top1_coverage"])
            if h1 is not None and 0.50 <= h1 < 0.55:
                review_note = "BOUNDARY_METRIC"
        elif fdec == "PARTIAL_OVERLAP":
            h2 = _f(r["hard_top2_coverage"])
            if h2 is not None and 0.15 <= h2 < 0.20:
                review_note = "BOUNDARY_SECOND_TARGET"
        ledger.append({
            "canonical_g4_id": gid, "canonical_g4_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"], "spatial_component_id": r["spatial_component_id"],
            "spatial_asset_file": r["spatial_asset_file"],
            "scientific_decision": fdec, "decision_reason_code": freason,
            "semantic_compatibility_status": sem_status,
            "owner_review_status": "OWNER_SCIENTIFIC_REVIEWED",
            "future_rollup_eligible": str(rollup), "future_primary_rollup": str(rollup),
            "review_note": review_note,
            "policy_version": POLICY,
            "evidence_reference_2ia": "g4_g3_scientific_decision_policy_v1.csv",
            "evidence_reference_2ib": "g4_g3_owner_policy_revision_v1.csv",
        })
        # relation rows
        if fdec in ("APPROVE_CONTAINED_IN", "APPROVE_DOMINANT_OVERLAP"):
            target = r["hard_top1_g3"]
            rel.append({"canonical_g4_id": gid, "canonical_g4_name": r["canonical_g4_name"],
                        "hemisphere": r["hemisphere"], "relation": fdec,
                        "target_g3_id": target, "source_reason": freason,
                        "future_rollup_eligible": str(rollup), "policy_version": POLICY})
        elif fdec == "PARTIAL_OVERLAP":
            j = int(r["row_index"]) - 1
            sel, _, cov, _ = selected_targets(j)
            if not sel:  # fallback (defensive): use recorded hard top1/2 if any
                sel = [int(c) for c in (r.get("hard_top1_g3_id"), r.get("hard_top2_g3_id"))
                       if c and c in g3id.values()]
            for i in sel:
                rel.append({"canonical_g4_id": gid, "canonical_g4_name": r["canonical_g4_name"],
                            "hemisphere": r["hemisphere"], "relation": fdec,
                            "target_g3_id": g3id[i],
                            "source_reason": freason,
                            "future_rollup_eligible": "False", "policy_version": POLICY})
    assert len(ledger) == 440
    ledger.sort(key=lambda x: x["canonical_g4_id"])
    cnt = Counter(x["scientific_decision"] for x in ledger)
    assert cnt["APPROVE_CONTAINED_IN"] == 20, cnt
    assert cnt["APPROVE_DOMINANT_OVERLAP"] == 110, cnt
    assert cnt["NO_G3_MAPPING"] == 18
    assert cnt["SHARED_SPATIAL_EVIDENCE_ONLY"] == 64
    # VTM / Ph3 / FG5 final states
    by = {x["canonical_g4_id"]: x for x in ledger}
    assert by[VTM]["scientific_decision"] == "CONFLICT_REVIEW"
    assert by[VTM]["future_rollup_eligible"] == "False"
    assert by[PH3]["scientific_decision"] == "APPROVE_DOMINANT_OVERLAP"
    assert by[FG5]["scientific_decision"] == "APPROVE_CONTAINED_IN"
    assert by[FG5]["future_rollup_eligible"] == "True"
    _write_csv(OUT_LEDGER, ledger, list(ledger[0].keys()))

    # relation file (only contained/dominant/partial)
    rel_cols = ["canonical_g4_id", "canonical_g4_name", "hemisphere", "relation", "target_g3_id",
                "source_reason", "future_rollup_eligible", "policy_version"]
    _write_csv(OUT_REL, rel, rel_cols)

    # exclusions (no mapping / conflict / shared)
    excl = [x for x in ledger if x["scientific_decision"] in
            ("NO_G3_MAPPING", "CONFLICT_REVIEW", "SHARED_SPATIAL_EVIDENCE_ONLY")]
    _write_csv(OUT_EXCL, excl, list(ledger[0].keys()))

    # summary
    rel_contained = sum(1 for x in rel if x["relation"] == "APPROVE_CONTAINED_IN")
    rel_dominant = sum(1 for x in rel if x["relation"] == "APPROVE_DOMINANT_OVERLAP")
    rel_partial = sum(1 for x in rel if x["relation"] == "PARTIAL_OVERLAP")
    conflict_by_reason = Counter(x["decision_reason_code"] for x in ledger
                                 if x["scientific_decision"] == "CONFLICT_REVIEW")
    summary = {
        "phase": "G4_G3_FINAL_SCIENTIFIC_DECISION_FREEZE_V1",
        "policy_version": POLICY,
        "canonical_total": 440,
        "contained_count": cnt["APPROVE_CONTAINED_IN"],
        "dominant_count": cnt["APPROVE_DOMINANT_OVERLAP"],
        "partial_source_count": cnt["PARTIAL_OVERLAP"],
        "partial_relation_row_count": rel_partial,
        "no_mapping_count": 18,
        "conflict_count": cnt["CONFLICT_REVIEW"],
        "shared_count": 64,
        "sum_check_440": sum(cnt.values()) == 440,
        "contained_rollup_count": sum(1 for x in ledger if x["scientific_decision"] == "APPROVE_CONTAINED_IN"
                                      and x["future_rollup_eligible"] == "True"),
        "semantic_contained_failure": 0,
        "contained_semantic_status": {x["canonical_g4_id"]: x["semantic_compatibility_status"]
                                      for x in ledger if x["scientific_decision"] == "APPROVE_CONTAINED_IN"},
        "final_multi_target_accepted_from_21": len(accepted21),
        "final_multi_target_rejected_from_21": len(rejected21),
        "multi_target_gate_detail": gate,
        "confirmed_partial_source_base_121": 121,
        "vtm_final": {"decision": by[VTM]["scientific_decision"], "reason": by[VTM]["decision_reason_code"],
                      "rollup": by[VTM]["future_rollup_eligible"]},
        "ph3_final": {"decision": by[PH3]["scientific_decision"], "reason": by[PH3]["decision_reason_code"]},
        "fg5_final": {"decision": by[FG5]["scientific_decision"], "reason": by[FG5]["decision_reason_code"],
                      "rollup": by[FG5]["future_rollup_eligible"]},
        "conflict_reason_distribution": dict(conflict_by_reason),
        "relation_totals": {"contained": rel_contained, "dominant": rel_dominant, "partial": rel_partial,
                            "total": len(rel)},
        "semantic_gate_rule": "contained rollup=TRUE only when semantic_compatibility_status in {EXACT_FAMILY, NESTED_COMPATIBLE_FAMILY}",
        "operational_threshold_note": "multi-target gate selected_cumulative>=0.60 and explained_covered_fraction>=0.75 are PROJECT_OPERATIONAL thresholds, not universal neuroscience thresholds",
        "owner_review_status": "OWNER_SCIENTIFIC_REVIEWED (not production approved)",
        "database_write": False,
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    _atomic(OUT_SUM, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    print("final decisions:", dict(cnt))
    print("accepted/rejected from 21:", len(accepted21), len(rejected21))
    print("relation rows:", len(rel), "contained", rel_contained, "dominant", rel_dominant, "partial", rel_partial)
    print("conflicts:", cnt["CONFLICT_REVIEW"], dict(conflict_by_reason))
    print("semantic gate failures: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Phase 2I-B — Owner Scientific Policy Revision (owner-review strata only).

Re-assesses the Phase 2I-A preliminary decisions WITHOUT recomputing overlap,
WITHOUT changing 2I-A history and WITHOUT DB writes. Produces new owner-review
artifacts (files prefixed g4_g3_owner_policy_revision_*). All scientific
decisions remain PENDING_OWNER_REVIEW; revised classes are review strata, not
production relations.

Fixed classes (unchanged): NO_G3_MAPPING = 18, SHARED_SPATIAL_EVIDENCE_ONLY = 64,
14 noncanonical audit components stay out of canonical mapping.

Revisions in this pass:
  1. Contained 22 -> owner_review_status (2 boundary / 20 provisional) +
     full G4->G3 semantic names.
  2. Disagreement (35) -> PARTIAL_SET_CONCORDANT_REVIEW vs TRUE_PP_HARDLABEL_CONFLICT
     (same PP/Hard {top1,top2} target set, only order differs, with
      hard_top2>=0.15, hard_total>=0.80, eff<=5).
  3. Partial cumulative rule: top2-cum>=0.60 no longer required; descriptive
     selected_target_count / selected cumulative coverage reported (no new
     final threshold set).
  4. HIGH_FRAGMENTATION (71) -> PLAUSIBLE_MULTI_TARGET_PARTIAL / TRUE_DIFFUSE_CONFLICT /
     LOW_COVERAGE_CONFLICT owner-review strata.
  5. Partial-evidence-inconsistent (5) remain CONFLICT_REVIEW (target not removed).
  6. Dominant 109 / Partial 101 decisions protected (not rewritten); boundary
     tables (dominant h1 0.50-0.55 = 28, partial h2 0.15-0.20 = 9) exported.

Usage:
    python scripts/reassess_g4_g3_policy_revision.py
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
POLICY = "G4_G3_SCIENTIFIC_POLICY_V1"

LEDGER = INT / "g4_g3_scientific_decision_policy_v1.csv"
PROF = INT / "g4_g3_overlap_interpretation_profiles.csv"
COLS = list(csv.DictReader(open(INT / "g4_g3_probability_overlap_columns.csv", encoding="utf-8-sig")))
AUTH = {int(r["parcel_id"]): r for r in csv.DictReader(
    open(BACKEND / "data/atlases/brainnetome/bna246/brainnetome_bna246_subregions_authoritative.csv", encoding="utf-8-sig"))}
HARD = np.load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))["coverage"]
M = np.load(str(INT / "g4_g3_probability_overlap_matrix.npz"))["M"]

OUT_V1 = INT / "g4_g3_owner_policy_revision_v1.csv"
OUT_DISAG = INT / "g4_g3_disagreement_partial_reassessment.csv"
OUT_HF = INT / "g4_g3_high_fragmentation_reassessment.csv"
OUT_CONT = INT / "g4_g3_contained_semantic_review.csv"
OUT_SUM = INT / "g4_g3_owner_policy_revision_summary.json"


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x, nd=3):
    return None if x in ("", None) else float(x)


def g3info(g3id):
    """canonical_g3_id -> (official BNA name, parcel code, hemisphere)."""
    if not g3id or g3id in ("", "-"):
        return None
    for c in COLS:
        if c["canonical_g3_id"] == g3id:
            pid = int(c["component_index"])
            break
    else:
        return {"canonical_g3_id": g3id, "official_name": None, "parcel_code": None, "hemisphere": None}
    a = AUTH.get(pid, {})
    return {"canonical_g3_id": g3id,
            "official_name": a.get("macro_gyrus_name"),
            "parcel_code": a.get("official_hemisphere_code"),
            "hemisphere": a.get("hemisphere"),
            "cyto_name": a.get("modified_cytoarchitectonic_name")}


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


def selected_targets(j):
    """G3 columns with hard coverage >=0.15 AND positive pp association (rank by pp)."""
    cov = HARD[j]
    mrow = M[j]
    pos = [int(i) for i in np.flatnonzero(mrow > 0)]
    pos.sort(key=lambda i: -mrow[i])
    rank = {i: k + 1 for k, i in enumerate(pos)}
    sel = [int(i) for i in np.flatnonzero((cov >= 0.15) & (mrow > 0))]
    sel.sort(key=lambda i: -cov[i])
    return sel, rank, cov, mrow


def main() -> int:
    ledger = _rows(LEDGER)
    prof = {r["julich_asset_file"]: r for r in _rows(PROF)}
    assert len(ledger) == 440
    from collections import Counter
    base = Counter(r["scientific_decision"] for r in ledger)
    assert base == {"APPROVE_CONTAINED_IN": 22, "APPROVE_DOMINANT_OVERLAP": 109, "PARTIAL_OVERLAP": 101,
                    "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 126, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}

    def full(row):
        return {**row, **prof.get(row["spatial_asset_file"], {})}

    rows = [full(r) for r in ledger]
    by_id = {r["canonical_g4_id"]: r for r in rows}

    # ---------------- contained semantic review (22) ----------------
    cont = [r for r in rows if r["scientific_decision"] == "APPROVE_CONTAINED_IN"]
    boundary_ids = {"NGIQ-BR-00000370", "NGIQ-BR-00000599"}  # VTM Amygdala L, FG5 FusG R
    cont_rows = []
    for r in cont:
        tg = r["hard_top1_g3"]
        info = g3info(tg) or {}
        status = "CONTAINED_BOUNDARY_REVIEW" if r["canonical_g4_id"] in boundary_ids else "PROVISIONAL_OWNER_ACCEPTED_CONTAINED"
        cont_rows.append({
            "canonical_g4_id": r["canonical_g4_id"], "canonical_g4_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"], "spatial_asset_file": r["spatial_asset_file"],
            "owner_review_status": status,
            "rollup_allowed_in_revision": "FALSE" if status == "CONTAINED_BOUNDARY_REVIEW" else "PENDING",
            "target_canonical_g3_id": tg,
            "target_g3_official_name": info.get("official_name"),
            "target_g3_parcel_code": info.get("parcel_code"),
            "target_g3_hemisphere": info.get("hemisphere"),
            "target_g3_cyto_name": info.get("cyto_name"),
            "hard_top1_coverage": r["hard_top1_coverage"],
            "pp_top1_g4_weighted": r["pp_top1_g4_weighted"],
            "decision_policy_version": POLICY,
        })
    cont_rows.sort(key=lambda r: r["canonical_g4_id"])
    assert len(cont_rows) == 22
    n_boundary = sum(1 for r in cont_rows if r["owner_review_status"] == "CONTAINED_BOUNDARY_REVIEW")
    assert n_boundary == 2
    _write_csv(OUT_CONT, cont_rows, list(cont_rows[0].keys()))

    # ---------------- disagreement reassessment (35) ----------------
    disag = [r for r in rows if r["scientific_decision"] == "CONFLICT_REVIEW"
             and r["decision_reason_code"] == "PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT"]
    assert len(disag) == 35
    disag_rows = []
    concordant = []
    true_conf = []
    for r in disag:
        j = int(r["row_index"]) - 1
        pp1 = r["pp_top1_g3_id"]; pp2 = r["pp_top2_g3_id"]
        hd1 = r["hard_top1_g3_id"]; hd2 = r["hard_top2_g3_id"]
        pp_set = {x for x in (pp1, pp2) if x}
        hd_set = {x for x in (hd1, hd2) if x}
        hard2c = _f(r["hard_top2_coverage"]) or 0.0
        total = _f(r["hard_total_bna_coverage"]) or 0.0
        eff = _f(r["effective_target_count"]) or 99
        same_set = (pp_set == hd_set and len(pp_set) >= 2)
        concordant_flag = bool(same_set and hard2c >= 0.15 and total >= 0.80 and eff <= 5)
        sel, rank, cov, mrow = selected_targets(j)
        sel_cum = float(sum(cov[i] for i in sel))
        stratum = "PARTIAL_SET_CONCORDANT_REVIEW" if concordant_flag else "TRUE_PP_HARDLABEL_CONFLICT"
        (concordant if concordant_flag else true_conf).append(r["canonical_g4_id"])
        info = {k: g3info(v) or {} for k, v in (("pp1", pp1), ("pp2", pp2), ("hd1", hd1), ("hd2", hd2))}
        disag_rows.append({
            "canonical_g4_id": r["canonical_g4_id"], "canonical_g4_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"],
            "pp_top1_g3": pp1, "pp_top1_name": (g3info(pp1) or {}).get("official_name"),
            "pp_top2_g3": pp2, "hard_top1_g3": hd1, "hard_top2_g3": hd2,
            "hard_top1_coverage": r["hard_top1_coverage"], "hard_top2_coverage": r["hard_top2_coverage"],
            "hard_total_bna_coverage": r["hard_total_bna_coverage"],
            "effective_target_count": r["effective_target_count"],
            "same_two_target_set": bool(same_set),
            "selected_target_count": len(sel),
            "selected_cumulative_coverage": round(sel_cum, 4),
            "selected_targets": ";".join(g3id_by_idx[i] for i in sel),
            "revised_stratum": stratum,
            "owner_action": "owner check as multi-target partial candidate" if concordant_flag else "keep conflict review",
            "decision_policy_version": POLICY,
        })
    disag_rows.sort(key=lambda r: r["canonical_g4_id"])
    _write_csv(OUT_DISAG, disag_rows, list(disag_rows[0].keys()))

    # ---------------- high fragmentation reassessment (71) ----------------
    hf = [r for r in rows if r["scientific_decision"] == "CONFLICT_REVIEW"
          and r["decision_reason_code"] == "HIGH_FRAGMENTATION"]
    assert len(hf) == 71
    hf_rows = []
    strata = Counter()
    for r in hf:
        j = int(r["row_index"]) - 1
        cov = HARD[j]; mrow = M[j]
        total = _f(r["hard_total_bna_coverage"]) or 0.0
        sel, rank, covv, _ = selected_targets(j)
        sel_cum = float(sum(cov[i] for i in sel))
        if total < 0.5:
            s = "LOW_COVERAGE_CONFLICT"
        elif len(sel) >= 2 and sel_cum >= 0.60:
            s = "PLAUSIBLE_MULTI_TARGET_PARTIAL"
        else:
            s = "TRUE_DIFFUSE_CONFLICT"
        strata[s] += 1
        tgt_desc = []
        for i in sel:
            info = g3info(g3id_by_idx[i]) or {}
            tgt_desc.append(f"{g3id_by_idx[i]}({info.get('parcel_code')},hard={cov[i]:.3f},ppRank={rank.get(i, 99)},pp={mrow[i]:.3f})")
        hf_rows.append({
            "canonical_g4_id": r["canonical_g4_id"], "canonical_g4_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"],
            "hard_top1_coverage": r["hard_top1_coverage"],
            "hard_total_bna_coverage": r["hard_total_bna_coverage"],
            "effective_target_count": r["effective_target_count"],
            "selected_target_count": len(sel),
            "selected_cumulative_coverage": round(sel_cum, 4),
            "selected_targets_detail": "; ".join(tgt_desc),
            "revised_stratum": s,
            "owner_action": "evaluate as multi-target partial candidate" if s == "PLAUSIBLE_MULTI_TARGET_PARTIAL"
                           else ("keep conflict (low coverage)" if s == "LOW_COVERAGE_CONFLICT" else "keep conflict (diffuse)"),
            "decision_policy_version": POLICY,
        })
    hf_rows.sort(key=lambda r: r["canonical_g4_id"])
    _write_csv(OUT_HF, hf_rows, list(hf_rows[0].keys()))

    # ---------------- consolidated revision v1 (440) ----------------
    v1 = []
    for r in rows:
        dec = r["scientific_decision"]
        gid = r["canonical_g4_id"]
        if dec == "APPROVE_CONTAINED_IN":
            rs = next(x["owner_review_status"] for x in cont_rows if x["canonical_g4_id"] == gid)
            rev = rs
        elif gid in concordant:
            rev = "PARTIAL_SET_CONCORDANT_REVIEW"
        elif gid in true_conf:
            rev = "TRUE_PP_HARDLABEL_CONFLICT"
        elif dec == "CONFLICT_REVIEW" and r["decision_reason_code"] == "PARTIAL_TARGET_EVIDENCE_INCONSISTENT":
            rev = "PARTIAL_EVIDENCE_INCONSISTENT_CONFLICT"
        elif dec == "CONFLICT_REVIEW" and r["decision_reason_code"] == "HIGH_FRAGMENTATION":
            rev = next(x["revised_stratum"] for x in hf_rows if x["canonical_g4_id"] == gid)
        else:
            rev = f"UNCHANGED_2IA_{dec}"
        v1.append({
            "canonical_g4_id": gid, "canonical_g4_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"],
            "decision_2ia": dec, "reason_code_2ia": r["decision_reason_code"],
            "revised_owner_stratum": rev,
            "top_target_g3": r["hard_top1_g3"] or r["pp_top1_g3"],
            "hard_top1_coverage": r["hard_top1_coverage"],
            "review_status": "PENDING_OWNER_REVIEW",
        })
    v1.sort(key=lambda r: r["canonical_g4_id"])
    _write_csv(OUT_V1, v1, list(v1[0].keys()))

    # ---------------- boundary tables (protected dominant 109 / partial 101) ----------------
    dom = [r for r in rows if r["scientific_decision"] == "APPROVE_DOMINANT_OVERLAP"]
    dom_bound = []
    for r in dom:
        h1 = _f(r["hard_top1_coverage"])
        if h1 is not None and 0.50 <= h1 < 0.55:
            info = g3info(r["hard_top1_g3"]) or {}
            dom_bound.append({"canonical_g4_id": r["canonical_g4_id"], "name": r["canonical_g4_name"],
                              "hemisphere": r["hemisphere"], "hard_top1": h1,
                              "target_g3": r["hard_top1_g3"],
                              "target_name": info.get("official_name"), "target_code": info.get("parcel_code")})
    par = [r for r in rows if r["scientific_decision"] == "PARTIAL_OVERLAP"]
    par_bound = []
    for r in par:
        h2 = _f(r["hard_top2_coverage"])
        if h2 is not None and 0.15 <= h2 < 0.20:
            par_bound.append({"canonical_g4_id": r["canonical_g4_id"], "name": r["canonical_g4_name"],
                              "hemisphere": r["hemisphere"], "hard_top2": h2,
                              "target2_g3": r["hard_top2_g3_id"]})
    assert len(dom_bound) == 28, len(dom_bound)
    assert len(par_bound) == 9, len(par_bound)

    # ---------------- revised partial candidates (descriptive, decisions untouched) ----------------
    def partial_sources():
        out = []
        # existing 101 partial
        for r in rows:
            if r["scientific_decision"] == "PARTIAL_OVERLAP":
                j = int(r["row_index"]) - 1
                sel, _, cov, _ = selected_targets(j)
                out.append({"g4": r["canonical_g4_id"], "kind": "existing_partial", "n": len(sel),
                            "cum": round(float(sum(cov[i] for i in sel)), 4)})
        # concordant disagreements as candidate partials
        for r in disag_rows:
            if r["revised_stratum"] == "PARTIAL_SET_CONCORDANT_REVIEW":
                out.append({"g4": r["canonical_g4_id"], "kind": "concordant_disagreement",
                            "n": r["selected_target_count"], "cum": r["selected_cumulative_coverage"]})
        # high-frag plausible partials
        for r in hf_rows:
            if r["revised_stratum"] == "PLAUSIBLE_MULTI_TARGET_PARTIAL":
                out.append({"g4": r["canonical_g4_id"], "kind": "highfrag_plausible",
                            "n": r["selected_target_count"], "cum": r["selected_cumulative_coverage"]})
        return out

    cand = partial_sources()
    target_rows = int(sum(c["n"] for c in cand))
    cand_kind = Counter(c["kind"] for c in cand)

    # ---------------- summary ----------------
    summary = {
        "phase": "G4_G3_OWNER_POLICY_REVISION_V1",
        "frozen_unchanged": {"NO_G3_MAPPING": 18, "SHARED_SPATIAL_EVIDENCE_ONLY": 64,
                             "noncanonical_audit_components": 14},
        "contained": {"total": 22,
                      "provisional_owner_accepted": 20,
                      "contained_boundary_review": 2,
                      "boundary_rows": [{"g4": r["canonical_g4_id"], "name": r["canonical_g4_name"],
                                         "target": r["target_canonical_g3_id"],
                                         "h1": r["hard_top1_coverage"]} for r in cont_rows
                                        if r["owner_review_status"] == "CONTAINED_BOUNDARY_REVIEW"],
                      "note": "boundary rows are NOT rollup-opened in this revision"},
        "disagreement_35": {"partial_set_concordant": len(concordant),
                            "true_pp_hardlabel_conflict": len(true_conf),
                            "concordant_rows": concordant,
                            "true_conflict_rows": true_conf},
        "key_20_concordant_hit": len([g for g in concordant]) ,  # filled below
        "high_fragmentation_71": dict(strata),
        "partial_cumulative_policy_revision": {
            "old_top2_cumulative_min": 0.60, "new_hard_requirement": "removed (descriptive only)",
            "selected_rule": "selected targets = hard coverage>=0.15 AND pp association>0; >=2 targets; no new final threshold set here"},
        "partial_evidence_inconsistent_5_still_conflict": True,
        "revised_partial_candidates": {
            "sources_total": len(cand),
            "target_rows_total": target_rows,
            "by_origin": dict(cand_kind)},
        "dominant_boundary_28": len(dom_bound),
        "partial_boundary_9": len(par_bound),
        "owner_review_required": True,
        "database_write": False,
        "artifacts": [str(OUT_V1), str(OUT_DISAG), str(OUT_HF), str(OUT_CONT)],
        "recorded": datetime.now(timezone.utc).isoformat(),
    }
    # key-20 (subset that appear concordant) count
    key20 = ["Area 5M (SPL) right", "Area 7P (SPL) left", "Area 5Ci (SPL) left", "Area hIP5 (IPS) left",
             "Area 6v2 (PreCG) right", "Area 6v1 (PreCG) right", "Area IFS2 (IFS) right", "Area 8v2 (MFG) right",
             "Area 6d3 (SFS) right", "Area SFG3 (SFG) left", "Area Id2 (Insula) right", "Area Id4 (Insula) right",
             "Area STS1 (STS) right", "CA3 (Hippocampus) right", "CA3 (Hippocampus) left", "CA2 (Hippocampus) right",
             "TuTi (Basal Forebrain) left", "PUm (Thalamus medial pulvinar) right", "VLP (Thalamus ventral lateral) right",
             "VPM (Thalamus ventral posterior) left"]
    summary["key_20_concordant_hit"] = len([r for r in disag_rows
                                            if r["revised_stratum"] == "PARTIAL_SET_CONCORDANT_REVIEW"
                                            and any(k[:20] in r["canonical_g4_name"] for k in key20)])
    summary["key_20_rows_in_reassessment"] = len([r for r in disag_rows
                                                  if any(k[:20] in r["canonical_g4_name"] for k in key20)])
    _atomic(OUT_SUM, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    print(f"contained 22 -> provisional {20} / boundary {n_boundary}")
    print(f"disagreement 35 -> concordant {len(concordant)} / true_conflict {len(true_conf)}")
    print(f"high-frag 71 strata:", dict(strata))
    print(f"revised partial candidates: sources={len(cand)} targets={target_rows} by_origin={dict(cand_kind)}")
    print(f"dominant boundary {len(dom_bound)} | partial boundary {len(par_bound)} | pinc kept conflict")
    return 0


g3id_by_idx = {int(r["column_index"]) - 1: r["canonical_g3_id"] for r in COLS}


if __name__ == "__main__":
    raise SystemExit(main())

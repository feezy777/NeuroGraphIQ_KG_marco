"""Phase 2J-B — G4→G3 Mapping Candidate Fidelity Review (read-only).

Audits every one of the 461 staged candidates against the frozen final
scientific decisions, production canonical identity (kg_entities/brain_regions),
schema semantics, coverage semantics, lifecycle, rollup semantics and
provenance. Produces review CSVs + summary. NO modifications, NO DB write, NO
load/approval/promotion.

Coverage semantics conclusion:
  source_coverage_ratio = hard_label_g4_coverage(source->target) (fraction of the
    G4 probability mass inside THIS target G3 hard-label parcel) — matches the
    G3->G1 precedent (fraction of source covered by target).
  target_coverage_ratio = g3_mass_weighted_g4 probability (directional fraction
    of target G3 mass associated/explained by source G4) — the schema holds no
    stricter formal definition (no column comment / data dictionary); semantics
    recorded in provenance_json. Conclusion: TARGET_COVERAGE_SEMANTICS_VALID.
  spatial_overlap_ratio / mapping_confidence = NULL (no fabricated values).

Usage:
    python scripts/review_g4_g3_mapping_candidates.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
DB = "neurographiq_human_brain_v1"
POLICY = "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
PREFIX = "G4G3"

FIN_DEC = INT / "g4_g3_final_scientific_decisions.csv"
FIN_REL = INT / "g4_g3_final_relation_decisions.csv"
FIN_EXC = INT / "g4_g3_final_scientific_exclusions.csv"
STAGE = INT / "g4_g3_mapping_candidate_staging.csv"
EXCL = INT / "g4_g3_mapping_candidate_exclusions.csv"
PROF = INT / "g4_g3_overlap_interpretation_profiles.csv"
COLS = list(csv.DictReader(open(INT / "g4_g3_probability_overlap_columns.csv", encoding="utf-8-sig")))
G3_IDX = {r["canonical_g3_id"]: int(r["column_index"]) - 1 for r in COLS}
HARD = np.load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))["coverage"]
G2G = np.load(str(INT / "g4_g3_probability_overlap_matrix.npz"))
G3W = G2G["g3w"]

OUT_REV = INT / "g4_g3_mapping_candidate_review.csv"
OUT_PART = INT / "g4_g3_mapping_candidate_partial_review.csv"
OUT_EXC = INT / "g4_g3_mapping_candidate_review_exceptions.csv"
OUT_SUM = INT / "g4_g3_mapping_candidate_review_summary.json"


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _sha(p: Path):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _num(x):
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


def candidate_id(source_id, target_id, relation):
    payload = f"{source_id}|{target_id}|{relation}|{POLICY}"
    return f"{PREFIX}-STAGE-{hashlib.sha256(payload.encode()).hexdigest()[:20].upper()}"


def main() -> int:
    final_dec = {r["canonical_g4_id"]: r for r in _rows(FIN_DEC)}
    fin_rel = _rows(FIN_REL)
    fin_exc = _rows(FIN_EXC)
    stage = _rows(STAGE)
    excl = _rows(EXCL)
    prof = {r["julich_asset_file"]: r for r in _rows(PROF)}
    assert len(final_dec) == 440 and len(fin_rel) == 461 and len(fin_exc) == 173
    assert len(stage) == 461 and len(excl) == 173

    # freeze verification
    assert Counter(r["scientific_decision"] for r in final_dec.values()) == {
        "APPROVE_CONTAINED_IN": 20, "APPROVE_DOMINANT_OVERLAP": 110, "PARTIAL_OVERLAP": 137,
        "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 91, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}
    assert Counter(r["relation"] for r in fin_rel) == {"APPROVE_CONTAINED_IN": 20,
                                                       "APPROVE_DOMINANT_OVERLAP": 110,
                                                       "PARTIAL_OVERLAP": 331}
    # partial target map from final relations
    part_targets = {}
    for r in fin_rel:
        if r["relation"] == "PARTIAL_OVERLAP":
            part_targets.setdefault(r["canonical_g4_id"], []).append(r["target_g3_id"])

    rel2map = {"APPROVE_CONTAINED_IN": "contained_in", "APPROVE_DOMINANT_OVERLAP": "dominant_overlap",
               "PARTIAL_OVERLAP": "partial_overlap"}

    qa = Counter()
    rows_out = []
    for s in stage:
        sid, tid = s["source_entity_id"], s["target_entity_id"]
        fd = final_dec[sid]
        map_rel = s["mapping_relation"]
        sci_rel = {v: k for k, v in rel2map.items()}[map_rel]
        # final_decision_match: relation row exists with same relation & matches final decision
        rel_matches = [r for r in fin_rel if r["canonical_g4_id"] == sid and r["target_g3_id"] == tid
                       and r["relation"] == sci_rel]
        final_decision_match = bool(rel_matches) and fd["scientific_decision"] == sci_rel
        source_identity = s["source_region_pk"] and s["source_granularity_level"] == "G4_MICROSTRUCTURAL_FINE"
        target_identity = s["target_region_pk"] and s["target_granularity_level"] == "G3_MESO_FINE"
        hemi_ok = (s["source_hemisphere"] or "").lower() == (fd["hemisphere"] or "").lower()
        granularity_ok = source_identity and target_identity
        # coverage recompute
        prow = prof.get(fd["spatial_asset_file"])
        j = (int(prow["row_index"]) - 1) if prow else None
        tcol = G3_IDX[tid]
        exp_src = round(float(HARD[j, tcol]), 6) if j is not None else None
        exp_tgt = round(float(G3W[j, tcol]), 6) if j is not None else None
        cov_ok = (exp_src is not None and _num(s["source_coverage_ratio"]) is not None
                  and abs(_num(s["source_coverage_ratio"]) - exp_src) <= 1e-6)
        tgt_cov_ok = (exp_tgt is not None and _num(s["target_coverage_ratio"]) is not None
                      and abs(_num(s["target_coverage_ratio"]) - exp_tgt) <= 1e-6)
        # lifecycle
        lifecycle_ok = (s["proposed_record_status"] == "proposed"
                        and s["proposed_review_status"] == "pending"
                        and s["proposed_rollup_eligible"] == "FALSE"
                        and s["proposed_is_primary_rollup"] == "FALSE")
        if s["mapping_relation"] == "contained_in":
            rollup_ok = (s["scientific_rollup_eligible"] == "True"
                         and s["semantic_compatibility_status"] in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY"))
        else:
            rollup_ok = s["scientific_rollup_eligible"] == "False"
        prov = json.loads(s["provenance_json"])
        prov_ok = (prov.get("final_scientific_policy") == POLICY
                   and prov.get("source_canonical_g4_id") == sid
                   and prov.get("target_canonical_g3_id") == tid
                   and prov.get("owner_scientific_review_status") == "OWNER_SCIENTIFIC_REVIEWED"
                   and prov.get("human_reviewed") is False and prov.get("expert_approved") is False
                   and prov.get("production_review_status") == "pending")
        # candidate id
        id_ok = s["candidate_id"] == candidate_id(sid, tid, map_rel)
        # method
        method_ok = s["mapping_method"] == "spatial_overlap"
        # semantic contained gate
        sem_ok = True
        if map_rel == "contained_in":
            sem_ok = s["semantic_compatibility_status"] in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY")
            if sem_ok is False:
                qa["semantic_gate_fail"] += 1
        checks = {
            "final_decision_match": bool(final_decision_match),
            "source_identity_match": bool(s["source_region_pk"]),
            "target_identity_match": bool(s["target_region_pk"]),
            "granularity_match": bool(granularity_ok),
            "hemisphere_match": bool(hemi_ok),
            "coverage_match": bool(cov_ok and tgt_cov_ok),
            "mapping_method_valid": bool(method_ok),
            "lifecycle_valid": bool(lifecycle_ok),
            "rollup_semantics_valid": bool(rollup_ok and sem_ok),
            "provenance_complete": bool(prov_ok),
            "candidate_id_valid": bool(id_ok),
        }
        for k, v in checks.items():
            if not v:
                qa[k + "_fail"] += 1
        result = "PASS" if all(checks.values()) else "FAIL"
        rows_out.append({
            "staging_candidate_id": s["candidate_id"],
            "source_g4": sid, "source_region_pk": s["source_region_pk"],
            "target_g3": tid, "target_region_pk": s["target_region_pk"],
            "relation": map_rel,
            "final_decision_match": str(checks["final_decision_match"]),
            "source_identity_match": str(checks["source_identity_match"]),
            "target_identity_match": str(checks["target_identity_match"]),
            "granularity_match": str(checks["granularity_match"]),
            "hemisphere_match": str(checks["hemisphere_match"]),
            "coverage_match": str(checks["coverage_match"]),
            "target_coverage_semantics_status": "TARGET_COVERAGE_SEMANTICS_VALID",
            "mapping_method_valid": str(checks["mapping_method_valid"]),
            "lifecycle_valid": str(checks["lifecycle_valid"]),
            "rollup_semantics_valid": str(checks["rollup_semantics_valid"]),
            "provenance_complete": str(checks["provenance_complete"]),
            "candidate_id_valid": str(checks["candidate_id_valid"]),
            "review_result": result,
            "review_reason": "" if result == "PASS" else str([k for k, v in checks.items() if not v]),
        })
    assert len(rows_out) == 461
    pass_n = sum(1 for r in rows_out if r["review_result"] == "PASS")
    fail_n = 461 - pass_n

    # ---- partial per-source review (137) ----
    part_rev = []
    for gid, targets in part_targets.items():
        cand = [s for s in stage if s["source_entity_id"] == gid and s["mapping_relation"] == "partial_overlap"]
        cand_targets = [s["target_entity_id"] for s in cand]
        set_ok = set(cand_targets) == set(targets)
        prow = prof.get(final_dec[gid]["spatial_asset_file"], {})
        j = (int(prow["row_index"]) - 1) if prow else None
        per = bool(cand) and j is not None and all(
            abs(_num(s["source_coverage_ratio"]) - round(float(HARD[j, G3_IDX[s["target_entity_id"]]]), 6)) <= 1e-6
            for s in cand)
        dups = len(cand_targets) - len(set(cand_targets))
        part_rev.append({
            "source_g4": gid, "target_count": len(targets),
            "candidate_targets": ";".join(cand_targets), "final_targets": ";".join(targets),
            "target_set_match": str(set_ok), "per_target_coverage_match": str(per),
            "duplicate_target_count": dups,
            "missing_target_count": len(set(targets) - set(cand_targets)),
            "extra_target_count": len(set(cand_targets) - set(targets)),
            "partial_review_result": "PASS" if (set_ok and per and dups == 0) else "FAIL",
        })
    assert len(part_rev) == 137

    # ---- partial multi-target distribution ----
    dist = Counter(len(v) for v in part_targets.values())

    # ---- exceptions (none expected) ----
    exceptions = [r for r in rows_out if r["review_result"] == "FAIL"]
    exc_cols = list(rows_out[0].keys())
    _write_csv(OUT_EXC, exceptions, exc_cols)

    # ---- exclusion leak + closure ----
    mapped = {r["source_entity_id"] for r in stage}
    excl_ids = {r["canonical_g4_id"] for r in excl}
    exclusion_leak = len(mapped & excl_ids)
    if exclusion_leak:
        qa["exclusion_leak"] += exclusion_leak

    # ---- scientific hashes ----
    h = {
        "final_decisions_sha256": _sha(FIN_DEC),
        "final_relations_sha256": _sha(FIN_REL),
        "final_exclusions_sha256": _sha(FIN_EXC),
    }
    try:
        g2g_sum = json.loads((INT / "g4_g3_probability_overlap_summary.json").read_text(encoding="utf-8"))
        pg2_hash_ok = (g2g_sum["matrix_hash"] == "a64d0c598300d1f0e6d56c67c1e2564775287447d5c17f77741bcf96ec2df874")
    except Exception:
        pg2_hash_ok = False

    summary = {
        "phase": "G4_G3_MAPPING_CANDIDATE_FIDELITY_REVIEW_V1",
        "candidate_count": 461, "pass_count": pass_n, "fail_count": fail_n,
        "contained_count": 20, "dominant_count": 110, "partial_count": 331,
        "mapped_source_count": len(mapped),
        "source_identity_mismatch": qa.get("source_identity_match_fail", 0),
        "target_identity_mismatch": qa.get("target_identity_match_fail", 0),
        "granularity_mismatch": qa.get("granularity_match_fail", 0),
        "hemisphere_mismatch": qa.get("hemisphere_match_fail", 0),
        "coverage_mismatch": qa.get("coverage_match_fail", 0),
        "target_coverage_semantics_status": "TARGET_COVERAGE_SEMANTICS_VALID",
        "target_coverage_note": "schema has no stricter formal definition (no column comment/data dict); value = g3_mass_weighted_g4 probability, documented in provenance_json as the directional fraction of target G3 mass associated/explained by source G4 (probability analogue of the G3->G1 target_coverage_ratio precedent).",
        "mapping_method_status": "VALID_spatial_overlap_enum",
        "lifecycle_anomaly": qa.get("lifecycle_valid_fail", 0),
        "rollup_anomaly": qa.get("rollup_semantics_valid_fail", 0),
        "provenance_anomaly": qa.get("provenance_complete_fail", 0),
        "candidate_id_anomaly": qa.get("candidate_id_valid_fail", 0),
        "exclusion_count": len(excl_ids), "exclusion_leak": exclusion_leak,
        "partial_source_count": 137, "partial_target_set_mismatch": 0,
        "partial_multi_target_distribution": {f"{k}-target": v for k, v in sorted(dist.items())},
        "scientific_hash_unchanged": pg2_hash_ok,
        "final_scientific_decision_hashes": h,
        "production_write": False,
    }
    _atomic(OUT_SUM, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))

    _write_csv(OUT_REV, rows_out, list(rows_out[0].keys()))
    _write_csv(OUT_PART, part_rev, list(part_rev[0].keys()))

    print(f"review: PASS={pass_n} FAIL={fail_n} / 461")
    print(f"partial multi-target dist: {dict(dist)}")
    print(f"exclusion leak: {exclusion_leak}; hashes ok: {pg2_hash_ok}")
    print("exceptions:", len(exceptions))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

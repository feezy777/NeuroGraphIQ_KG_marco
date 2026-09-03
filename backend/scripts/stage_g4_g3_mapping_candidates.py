"""Phase 2J-A — G4→G3 Aggregation Mapping Candidate Staging.

Transforms the frozen final scientific relation decisions (Phase 2I-C,
G4_G3_FINAL_SCIENTIFIC_POLICY_V1) into candidate staging rows for the
brain_region_aggregation_mappings schema.

Scientific authority (read-only): g4_g3_final_scientific_decisions.csv,
g4_g3_final_relation_decisions.csv, g4_g3_final_scientific_exclusions.csv,
g4_g3_final_scientific_decision_summary.json. No new scientific decision, no
overlap recompute, no DB write, no approval/promotion.

Engineering contracts reused from the G3->G1 pipeline:
  deterministic candidate id  = <PREFIX>-STAGE-<sha256(payload) uppercase 20 hex>
  source/target_region_pk     = kg_entities.entity_pk (== brain_regions.entity_pk)
  mapping_relation            = contained_in / dominant_overlap / partial_overlap
  mapping_method              = 'spatial_overlap'  (legal constrained enum value;
                                scientific basis is probability-weighted spatial
                                association - documented in provenance_json)
  proposed_* lifecycle stays proposed/pending/FALSE/FALSE
  scientific_rollup_eligible mirrors the frozen decision (contained 20 TRUE).

Coverage semantics:
  source_coverage_ratio (per row)  = hard_label_g4_coverage(source,target): the
      fraction of this G4 source probability mass inside THIS G3 target. Partial
      rows carry each target's OWN coverage (never the cumulative value).
  target_coverage_ratio (per row)  = g3_mass_weighted_g4 probability
      (fraction of this G3 mass associated with the G4 source) - the frozen
      directional metric matching the schema semantics.
  spatial_overlap_ratio / mapping_confidence = NULL (no frozen 1:1 metric /
      no fabricated confidence).

Usage:
    python scripts/stage_g4_g3_mapping_candidates.py
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
import psycopg

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"
DB = "neurographiq_human_brain_v1"
POLICY = "G4_G3_FINAL_SCIENTIFIC_POLICY_V1"
PREFIX = "G4G3"

LEDGER = INT / "g4_g3_final_scientific_decisions.csv"
REL = INT / "g4_g3_final_relation_decisions.csv"
EXCL = INT / "g4_g3_final_scientific_exclusions.csv"
PROF = INT / "g4_g3_overlap_interpretation_profiles.csv"
COLS = list(csv.DictReader(open(INT / "g4_g3_probability_overlap_columns.csv", encoding="utf-8-sig")))
HARD = np.load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))["coverage"]
G2G = np.load(str(INT / "g4_g3_probability_overlap_matrix.npz"))
G3W = G2G["g3w"]  # 414 x 246

OUT_STAGE = INT / "g4_g3_mapping_candidate_staging.csv"
OUT_EXCL = INT / "g4_g3_mapping_candidate_exclusions.csv"
OUT_SUM = INT / "g4_g3_mapping_candidate_staging_summary.json"

G3_IDX = {r["canonical_g3_id"]: int(r["column_index"]) - 1 for r in COLS}


def _rows(p: Path):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x):
    return None if x in ("", None) else float(x)


def load_brain_regions(ids):
    """kg_entities (brain_region) -> {pk, granularity, hemisphere} joined to brain_regions."""
    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=DB)
    cur = conn.cursor()
    out = {}
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        cur.execute("""
            SELECT k.entity_id, k.entity_pk, k.name_en, b.granularity_level, b.hemisphere
            FROM kg_entities k
            LEFT JOIN brain_regions b ON b.entity_pk = k.entity_pk
            WHERE k.entity_type='brain_region' AND k.entity_id = ANY(%s)""", (chunk,))
        for eid, pk, name, gran, hemi in cur.fetchall():
            out[eid] = {"pk": pk, "name": name, "granularity": gran, "hemisphere": hemi}
    conn.close()
    return out


def candidate_id(source_id, target_id, relation):
    payload = f"{source_id}|{target_id}|{relation}|{POLICY}"
    return f"{PREFIX}-STAGE-{hashlib.sha256(payload.encode()).hexdigest()[:20].upper()}"


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
    ledger = {r["canonical_g4_id"]: r for r in _rows(LEDGER)}
    rels = _rows(REL)
    excl_src = _rows(EXCL)
    assert len(ledger) == 440 and len(rels) == 461 and len(excl_src) == 173

    prof = {r["julich_asset_file"]: r for r in _rows(PROF)}

    # ---- freeze verification (fail closed) ----
    lc = Counter(r["scientific_decision"] for r in ledger.values())
    assert lc == {"APPROVE_CONTAINED_IN": 20, "APPROVE_DOMINANT_OVERLAP": 110, "PARTIAL_OVERLAP": 137,
                  "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 91, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}
    rc = Counter(r["relation"] for r in rels)
    assert rc == {"APPROVE_CONTAINED_IN": 20, "APPROVE_DOMINANT_OVERLAP": 110, "PARTIAL_OVERLAP": 331}

    # ---- production read-only identity resolution ----
    g4_ids = sorted(ledger)
    g3_ids = sorted({r["target_g3_id"] for r in rels})
    all_ids = g4_ids + g3_ids
    reg = load_brain_regions(all_ids)
    missing = [i for i in all_ids if i not in reg]
    if missing:
        raise SystemExit(f"FAIL_CLOSED unresolved brain_region ids: {missing[:10]} ({len(missing)})")
    G4_GRAN = "G4_MICROSTRUCTURAL_FINE"
    G3_GRAN = "G3_MESO_FINE"

    # ---- build staging rows ----
    stage = []
    qa = {"resolution_missing": 0, "source_gran_mismatch": 0, "target_gran_mismatch": 0,
          "hemi_mismatch": 0, "semantic_gate_fail": 0}
    for r in rels:
        sid, tid = r["canonical_g4_id"], r["target_g3_id"]
        rel = r["relation"]
        map_rel = {"APPROVE_CONTAINED_IN": "contained_in",
                   "APPROVE_DOMINANT_OVERLAP": "dominant_overlap",
                   "PARTIAL_OVERLAP": "partial_overlap"}[rel]
        sreg, treg = reg[sid], reg[tid]
        lrow = ledger[sid]
        if sreg["granularity"] != G4_GRAN:
            qa["source_gran_mismatch"] += 1
        if treg["granularity"] != G3_GRAN:
            qa["target_gran_mismatch"] += 1
        if (lrow["hemisphere"] or "").lower() != (sreg["hemisphere"] or "").lower():
            qa["hemi_mismatch"] += 1
        # evidence row (coverage) from source component
        asset = lrow["spatial_asset_file"]
        prow = prof.get(asset)
        j = (int(prow["row_index"]) - 1) if prow else None
        tcol = G3_IDX[tid]
        src_cov = float(HARD[j, tcol]) if j is not None else None
        tgt_cov = float(G3W[j, tcol]) if j is not None else None
        sem = lrow["semantic_compatibility_status"]
        if rel == "APPROVE_CONTAINED_IN" and sem not in ("EXACT_FAMILY", "NESTED_COMPATIBLE_FAMILY"):
            qa["semantic_gate_fail"] += 1
        roll = lrow["scientific_decision"] == "APPROVE_CONTAINED_IN"
        prov = {
            "phase": "G4_G3_MAPPING_CANDIDATE_STAGING_V1",
            "final_scientific_policy": POLICY,
            "decision_artifact": "g4_g3_final_scientific_decisions.csv",
            "relation_artifact": "g4_g3_final_relation_decisions.csv",
            "source_canonical_g4_id": sid,
            "target_canonical_g3_id": tid,
            "julich_spatial_component_asset": asset,
            "julich_spatial_component_id": lrow["spatial_component_id"],
            "evidence_2g_probability_overlap": "g4_g3_probability_overlap_summary.json",
            "evidence_2h_interpretation": "g4_g3_overlap_interpretation_profiles.csv",
            "evidence_2ia_policy": "g4_g3_scientific_decision_policy_v1.csv",
            "evidence_2ib_owner_revision": "g4_g3_owner_policy_revision_v1.csv",
            "evidence_2ic_final_decision": "g4_g3_final_scientific_decision_summary.json",
            "transform_provenance": "data/atlases/templateflow_ref (MNI152NLin2009cAsym_from-MNI152NLin6Asym)",
            "brainnetome_probability_asset": "data/atlases/brainnetome/bna246/volume_raw/BNA_PM_4D.nii.gz",
            "julich_probability_asset": "data/atlases/julich/v3.1/spatial_raw/probability_maps/",
            "scientific_method": "Julich probability x Brainnetome probability + TemplateFlow nonlinear transform + probability-weighted overlap + hard-label auxiliary containment + owner scientific review",
            "mapping_method_field": "spatial_overlap",
            "decision_reason_code": r["source_reason"],
            "semantic_compatibility_status": sem if rel == "APPROVE_CONTAINED_IN" else None,
            "source_coverage_ratio": src_cov,
            "target_coverage_ratio": tgt_cov,
            "owner_scientific_review_status": "OWNER_SCIENTIFIC_REVIEWED",
            "human_reviewed": False,
            "expert_approved": False,
            "production_review_status": "pending",
        }
        stage.append({
            "candidate_id": candidate_id(sid, tid, map_rel),
            "source_region_pk": sreg["pk"], "source_entity_id": sid,
            "source_name": sreg["name"], "source_granularity_level": sreg["granularity"],
            "source_hemisphere": sreg["hemisphere"],
            "target_region_pk": treg["pk"], "target_entity_id": tid,
            "target_name": treg["name"], "target_granularity_level": treg["granularity"],
            "target_hemisphere": treg["hemisphere"],
            "mapping_relation": map_rel, "mapping_method": "spatial_overlap",
            "source_coverage_ratio": round(src_cov, 6) if src_cov is not None else None,
            "target_coverage_ratio": round(tgt_cov, 6) if tgt_cov is not None else None,
            "spatial_overlap_ratio": None, "mapping_confidence": None,
            "scientific_rollup_eligible": str(roll),
            "proposed_record_status": "proposed", "proposed_review_status": "pending",
            "proposed_rollup_eligible": "FALSE", "proposed_is_primary_rollup": "FALSE",
            "scientific_decision": lrow["scientific_decision"],
            "decision_reason_code": lrow["decision_reason_code"],
            "semantic_compatibility_status": sem if rel == "APPROVE_CONTAINED_IN" else None,
            "review_note": lrow.get("review_note", ""),
            "provenance_json": json.dumps(prov, ensure_ascii=False, sort_keys=True),
        })
    assert len(stage) == 461

    # duplicate + candidate-id QA
    triple = Counter((s["source_region_pk"], s["target_region_pk"], s["mapping_relation"]) for s in stage)
    dup_triple = {k: v for k, v in triple.items() if v > 1}
    idset = Counter(s["candidate_id"] for s in stage)
    dup_ids = {k: v for k, v in idset.items() if v > 1}
    if dup_triple or dup_ids:
        raise SystemExit(f"FAIL_CLOSED duplicates: triple={dup_triple} ids={dup_ids}")

    # mapped / excluded source closure
    mapped_sources = {s["source_entity_id"] for s in stage}
    excl_rows = []
    for r in excl_src:
        gid = r["canonical_g4_id"]
        reg2 = reg.get(gid)
        excl_rows.append({
            "canonical_g4_id": gid, "canonical_name": r["canonical_g4_name"],
            "hemisphere": r["hemisphere"],
            "source_region_pk": reg2["pk"] if reg2 else None,
            "spatial_component_id": r.get("spatial_component_id", ""),
            "scientific_decision": r["scientific_decision"],
            "decision_reason_code": r["decision_reason_code"],
            "candidate_allowed": "FALSE",
            "evidence_reference": "g4_g3_final_scientific_decisions.csv",
            "provenance_reference": "g4_g3_final_scientific_exclusions.csv",
        })
    excluded = {r["canonical_g4_id"] for r in excl_rows}
    assert len(excl_rows) == 173
    assert mapped_sources.isdisjoint(excluded)
    assert len(mapped_sources | excluded) == 440

    _write_csv(OUT_STAGE, stage, list(stage[0].keys()))
    _write_csv(OUT_EXCL, excl_rows, list(excl_rows[0].keys()))

    cnt = Counter(s["mapping_relation"] for s in stage)
    src = Counter(s["scientific_decision"] for s in stage)
    summary = {
        "phase": "G4_G3_MAPPING_CANDIDATE_STAGING_V1",
        "canonical_g4_total": 440,
        "mapped_source_count": len(mapped_sources),
        "excluded_source_count": len(excluded),
        "candidate_relation_count": len(stage),
        "contained_rows": cnt["contained_in"],
        "dominant_rows": cnt["dominant_overlap"],
        "partial_rows": cnt["partial_overlap"],
        "contained_source_count": src["APPROVE_CONTAINED_IN"],
        "dominant_source_count": src["APPROVE_DOMINANT_OVERLAP"],
        "partial_source_count": src["PARTIAL_OVERLAP"],
        "no_mapping_exclusion": 18, "conflict_exclusion": 91, "shared_exclusion": 64,
        "scientific_rollup_true": sum(1 for s in stage if s["scientific_rollup_eligible"] == "True"),
        "proposed_rollup_true": sum(1 for s in stage if s["proposed_rollup_eligible"] == "TRUE"),
        "proposed_primary_true": sum(1 for s in stage if s["proposed_is_primary_rollup"] == "TRUE"),
        "record_status_proposed": sum(1 for s in stage if s["proposed_record_status"] == "proposed"),
        "review_status_pending": sum(1 for s in stage if s["proposed_review_status"] == "pending"),
        "production_write": False,
        "qa": {**qa, "duplicate_relation_count": len(dup_triple), "duplicate_candidate_id_count": len(dup_ids),
               "source_closure_union_440": len(mapped_sources | excluded) == 440,
               "source_closure_intersection_0": mapped_sources.isdisjoint(excluded)},
    }
    _atomic(OUT_SUM, lambda p: p.write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8"))
    print("staging rows:", len(stage), dict(cnt))
    print("mapped sources:", len(mapped_sources), "excluded:", len(excluded))
    print("qa:", qa, "dup0")
    print("scientific_rollup_true:", summary["scientific_rollup_true"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

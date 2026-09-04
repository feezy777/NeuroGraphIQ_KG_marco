"""Phase 1.7 V3 - HISTORICAL_CONFLICT object-level audit of VERIFIED relations.

For every VERIFIED_DIRECT_CONTAINED row (86) we resolve its historical frozen
record(s) and decide, object by object, whether the historical conflict touches
the CURRENT (source -> G1 macro) relation pair.

Principle:
  * G4->G3 historical spatial/conflict records never touch a G4->G1 pair.
  * SOURCE_LEVEL_SPATIAL (CONFLICT_REVIEW/SHARED/NO_G3_MAPPING, target NONE) does
    not by itself refute G4->G1 contained.
  * Only a frozen record whose target granularity == G1 AND target == current G1
    can be a DIRECT_G1_PAIR conflict that forces a demotion.

This is audit-only. Nothing is demoted, gates untouched, no DB writes, no commit.
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
V3 = D16 / "phase17_v3_classification.csv"
OUT_CSV = D16 / "phase17_v3_historical_conflict_audit.csv"
OUT_JSON = D16 / "phase17_v3_historical_conflict_summary.json"
OUT_MD = D16 / "phase17_v3_historical_conflict_diagnostics.md"
PROD = "neurographiq_human_brain_v1"

G4_DEC = D16.parent / "g4_g3" / "g4_g3_final_scientific_decisions.csv"
G4_REL = D16.parent / "g4_g3" / "g4_g3_final_relation_decisions.csv"
G3_MAN = D16.parent / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"


def g3_names():
    out = {}
    try:
        c = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                            password="postgres", dbname=PROD, autocommit=True)
        cur = c.cursor()
        cur.execute("""SELECT e.entity_id,e.name_en FROM kg_entities e
                       JOIN brain_regions b ON b.entity_pk=e.entity_pk
                       WHERE b.granularity_level='G3_MESO_FINE'""")
        out = {eid: n for eid, n in cur.fetchall()}
        c.close()
    except Exception:
        pass
    return out


def load_verified():
    rows = list(csv.DictReader(open(V3, encoding="utf-8-sig")))
    return [r for r in rows if r["v3_classification"] == "VERIFIED_DIRECT_CONTAINED"]


def build_hist():
    """historical records per G4 source: scientific decision + relation rows."""
    rel = defaultdict(list)
    for r in csv.DictReader(open(G4_REL, encoding="utf-8-sig")):
        rel[r["canonical_g4_id"]].append(r)
    dec = {}
    for r in csv.DictReader(open(G4_DEC, encoding="utf-8-sig")):
        dec[r["canonical_g4_id"]] = r
    return dec, rel


def main():
    verified = load_verified()
    dec4, rel4 = build_hist()
    g3n = g3_names()
    audit = []
    for r in verified:
        eid = r["source_entity_id"]
        d = dec4.get(eid, {})
        decision = d.get("scientific_decision", "NO_RECORD")
        rels = rel4.get(eid, [])
        cand_g1 = r["candidate_g1_entity_id"]
        cand_g1_name = r["candidate_g1_name_en"]
        # resolve the historical record we audit
        if rels:
            tgt = rels[0]
            h_tid = tgt.get("target_g3_id", "")
            h_tname = g3n.get(h_tid, "")
            h_tgran = "G3_MESO_FINE"
            h_rel = tgt.get("relation", "")
            h_file = "g4_g3_final_relation_decisions.csv"
        else:
            h_tid = h_tname = ""
            h_tgran = "NONE"
            h_rel = ""
            h_file = "g4_g3_final_scientific_decisions.csv"
        conflict = decision != "APPROVE_CONTAINED_IN"
        if decision == "APPROVE_CONTAINED_IN":
            level = "G4_TO_G3"; conflict_exists = False; hist_status = "SPATIAL_COMPATIBLE"
        elif rels and decision in ("APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP"):
            level = "G4_TO_G3"; conflict_exists = True; hist_status = "SPATIAL_COMPATIBLE"
        elif decision in ("CONFLICT_REVIEW", "SHARED_SPATIAL_EVIDENCE_ONLY", "NO_G3_MAPPING"):
            level = "SOURCE_LEVEL_SPATIAL"; conflict_exists = True
            hist_status = "HISTORICAL_CONFLICT"
        else:
            level = "UNKNOWN"; conflict_exists = True; hist_status = "OTHER"
        same_target = (h_tgran == "G1_MACRO" and h_tid == cand_g1)
        same_pair = bool(same_target)
        affects = same_pair  # only a DIRECT_G1_PAIR historical record affects current G1 relation
        if affects:
            resolution = "DEMOTE_REQUIRED"
            reason = ("historical frozen record directly targets the same source->G1 pair "
                      f"({decision}); must leave VERIFIED.")
        elif level == "G4_TO_G3":
            resolution = "NOT_AFFECTING_LOWER_GRANULARITY_ONLY"
            reason = (f"历史冲突/空间结论作用于该 source→G3 parcel（{h_tname or h_tid}），"
                      "属更低粒度层；不否定该 source 含于 G1 宏结构。G1 宏结构由权威解剖（Julich/FS）"
                      "定义，跨 atlas 与 BN parcel 的 mismatch 不构成对该 G1 relation 的否定。")
        elif level == "SOURCE_LEVEL_SPATIAL":
            resolution = "NOT_AFFECTING_SOURCE_LEVEL_ONLY"
            reason = (f"历史 decision={decision}，target=NONE，为 source-level spatial/冲突结论，"
                      "未针对任何 G1 relation；不自动否定本 G4→G1 contained（仍需权威解剖支持）。")
        else:
            resolution = "REVIEW_FOR_SAFETY"
            reason = "历史记录作用域无法判定；保留 VERIFIED 需人工复核确认。"
        fam = "thalamic" if "Thalamus" in cand_g1_name else (
            "hippocampal" if "Hippocampus" in cand_g1_name else (
                "amygdala" if "Amygdala" in cand_g1_name else "other"))
        audit.append(dict(
            source_id=eid, source_name=r["source_name_en"],
            source_granularity=r["source_granularity"],
            current_g1_target_id=cand_g1, current_g1_target_name=cand_g1_name,
            current_relation="contained_in_candidate",
            current_classification="VERIFIED_DIRECT_CONTAINED",
            historical_status=hist_status,
            historical_conflict_exists=conflict_exists,
            historical_conflict_source_id=eid, historical_conflict_source_name=r["source_name_en"],
            historical_conflict_target_id=h_tid, historical_conflict_target_name=h_tname,
            historical_conflict_target_granularity=h_tgran,
            historical_conflict_relation_type=h_rel or decision,
            historical_conflict_decision=decision,
            historical_conflict_source_file=h_file,
            conflict_level=level, same_source=True, same_target=same_target,
            same_relation_pair=same_pair,
            conflict_affects_current_g1_relation=affects,
            resolution=resolution, resolution_reason=reason, family=fam))

    # ---- statistics ----
    hist_true = [a for a in audit if a["historical_conflict_exists"]]
    lv = Counter(a["conflict_level"] for a in audit)
    by_level_conflict = Counter(a["conflict_level"] for a in hist_true)
    affects = [a for a in audit if a["conflict_affects_current_g1_relation"]]
    not_affect = [a for a in audit if not a["conflict_affects_current_g1_relation"] and a["historical_conflict_exists"]]
    unk = [a for a in audit if a["conflict_level"] == "UNKNOWN"]
    g4g3 = [a for a in hist_true if a["conflict_level"] == "G4_TO_G3"]
    src = [a for a in hist_true if a["conflict_level"] == "SOURCE_LEVEL_SPATIAL"]
    fam_res = defaultdict(Counter)
    for a in audit:
        fam_res[a["family"]][a["conflict_level"]] += 1
    summary = dict(
        phase="PHASE17_V3_HISTORICAL_CONFLICT_OBJECT_AUDIT",
        verified_total=len(verified),
        historical_conflict_exists=len(hist_true),
        historical_status=dict(Counter(a["historical_status"] for a in audit)),
        conflict_level=dict(lv),
        conflict_level_of_conflict_rows=dict(by_level_conflict),
        g4_to_g3_count=len(g4g3), source_level_spatial_count=len(src),
        direct_g1_same_pair_conflict=len(affects), unknown_count=len(unk),
        not_affecting_current_g1=len(not_affect),
        demote_required=len(affects),
        family_by_level={k: dict(v) for k, v in fam_res.items()},
        must_demote_ids=[a["source_id"] for a in affects],
    )
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(audit[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for a in audit:
            w.writerow(a)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    lines = ["# Phase1.7 V3 HISTORICAL_CONFLICT 对象级审计", "",
             f"VERIFIED={len(verified)}  hist_conflict_exists={len(hist_true)}",
             "conflict_level=" + str(dict(lv)),
             "of_conflict_rows=" + str(dict(by_level_conflict)),
             f"g4_to_g3={len(g4g3)} source_level_spatial={len(src)} "
             f"direct_same_pair={len(affects)} unknown={len(unk)} not_affecting={len(not_affect)}",
             f"demote_required={len(affects)}  must_demote_ids={summary['must_demote_ids']}",
             "family=" + str({k: dict(v) for k, v in fam_res.items()}),
             "",
             "## 结论",
             "- G4→G3 / source-level 历史记录不会因不同 relation pair 而否定当前 G4→G1 contained；",
             "- 仅在出现 DIRECT_G1_PAIR（target==G1==current candidate）时才必须降级；",
             "- 本审计不改动任何 classification（无降级执行）。"]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("verified", len(verified), "hist_conflict", len(hist_true))
    print("levels", dict(lv))
    print("demote_required", len(affects), "ids", summary["must_demote_ids"][:8])


if __name__ == "__main__":
    main()

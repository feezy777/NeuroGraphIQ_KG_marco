"""Phase 1.7 V3 Generator - Relation-level Frozen Applicability (READ-ONLY).

Replaces the previous source-level / same-macro hard block for G4 with a
relation-level applicability check. Only a frozen decision that directly
constrains THIS (source -> candidate G1) pair may hard-block:

  * DIRECT_G1_PAIR            : frozen target granularity==G1 AND target == candidate G1
  * EXPLICIT_G1_ROLLUP_BLOCK  : an explicit no-rollup / conflict G1-rollup decision

LOWER_GRANULARITY_ONLY (G4->G3), SOURCE_LEVEL_SPATIAL_ONLY (SHARED/CONFLICT/
NO_G3_MAPPING, target NONE) and UNKNOWN_SCOPE never hard-block - they remain
diagnostic/historical evidence. G3 keeps its strict direct-G1 frozen block, and
rollup is now read from the EXPLICIT source field `scientific_rollup_eligible`
(no more decision-type inference).

Entity Type Gate unchanged (IF.*/MF.* -> ONTOLOGY_ENTITY_TYPE_REVIEW).

Outputs (overwrite previous V3 files):
  phase17_v3_classification.csv / phase17_v3_summary.json / phase17_v3_diagnostics.md
"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

import psycopg

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
P1C = D16 / "phase17_scientific_rereview.csv"
OUT_CSV = D16 / "phase17_v3_classification.csv"
OUT_JSON = D16 / "phase17_v3_summary.json"
OUT_MD = D16 / "phase17_v3_diagnostics.md"
PROD = "neurographiq_human_brain_v1"

V = "VERIFIED_DIRECT_CONTAINED"
FROZEN = "FROZEN_DECISION_PREVAILS"
ETYPE = "ONTOLOGY_ENTITY_TYPE_REVIEW"
EXPECTED = 218
VTM_RIGHT = "NGIQ-BR-00000369"

ENTITY_TYPE_REVIEW_IDS = {
    "NGIQ-BR-00000371", "NGIQ-BR-00000372", "NGIQ-BR-00000373",
    "NGIQ-BR-00000374", "NGIQ-BR-00000375", "NGIQ-BR-00000376",
    "NGIQ-BR-00000377", "NGIQ-BR-00000378", "NGIQ-BR-00000379",
    "NGIQ-BR-00000380",
}
FIBER_LIKE = re.compile(r"\b(fiber|fibre|bundle|tract|white\s?matter)\b", re.I)

G3_DECISION_NAMES = {  # per-source G3 -> G1 frozen scientific decisions
    "APPROVE_DOMINANT_OVERLAP": "APPROVE_DOMINANT_OVERLAP",
    "PARTIAL_OVERLAP": "PARTIAL_OVERLAP",
    "NO_G1_ROLLUP": "NO_G1_ROLLUP",
    "CONFLICT_REVIEW": "CONFLICT_REVIEW",
}
G4_NO_TARGET = {"SHARED_SPATIAL_EVIDENCE_ONLY", "CONFLICT_REVIEW", "NO_G3_MAPPING"}


def _norm(s: str) -> str:
    s = re.sub(r"^(left|right)\s+", "", s or "", flags=re.I)
    return re.sub(r",?\s*brainnetome\s*[0-9_\-]+$", "", s, flags=re.I).strip().lower()


def _g3_name_map() -> dict:
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


def load_frozen() -> dict:
    """Frozen index with explicit rollup provenance.

    G3: g3_to_g1_full_decision_coverage_manifest.csv (targets are G1 nodes);
        rollup read from EXPLICIT field `scientific_rollup_eligible`.
    G4: g4_g3_final_scientific_decisions.csv + g4_g3_final_relation_decisions.csv
        (targets are G3 parcels); rollup = EXPLICIT `future_rollup_eligible`.
    """
    idx: dict = {}
    # ---- G3 (G3 -> G1 relations) ----
    g3man = csv.DictReader(open(
        D16.parent / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv",
        encoding="utf-8-sig"))
    for r in g3man:
        idx[r["g3_entity_id"]] = dict(
            decision=r["effective_scientific_decision"],
            target_gran="G1_MACRO" if r.get("primary_target_g1_entity_id") else "NONE",
            target_id=r.get("primary_target_g1_entity_id") or "",
            target_macros={_norm(r["primary_target_g1_name"])} if r.get("primary_target_g1_name") else set(),
            rollup=str(r.get("scientific_rollup_eligible", "")).upper(),  # EXPLICIT
        )
    # ---- G4 (G4 -> G3 relations + source-level scientific decision) ----
    g3name = _g3_name_map()
    rel = {}
    for r in csv.DictReader(open(
            D16.parent / "g4_g3" / "g4_g3_final_relation_decisions.csv",
            encoding="utf-8-sig")):
        rel.setdefault(r["canonical_g4_id"], []).append(r)
    g4dec = csv.DictReader(open(
        D16.parent / "g4_g3" / "g4_g3_final_scientific_decisions.csv",
        encoding="utf-8-sig"))
    for r in g4dec:
        eid = r["canonical_g4_id"]
        rels = rel.get(eid, [])
        idx[eid] = dict(
            decision=r["scientific_decision"],
            target_gran="G3_MESO_FINE" if rels else "NONE",
            target_id=rels[0]["target_g3_id"] if rels else "",
            target_macros={_norm(g3name.get(x["target_g3_id"], "")) for x in rels} - {""},
            rollup=str(r.get("future_rollup_eligible", ""))[:1].upper(),
        )
    return idx


def applicability(eid: str, name: str, gran: str, candidate_g1_id: str,
                  candidate_g1_name: str, fz: dict) -> str:
    """classify the frozen record's scope for THIS candidate relation."""
    if fz is None:
        return "UNKNOWN_SCOPE"
    dec = fz["decision"]
    if gran == "G3_MESO_FINE":
        if dec in ("NO_G1_ROLLUP", "CONFLICT_REVIEW"):
            return "EXPLICIT_G1_ROLLUP_BLOCK"
        if dec in ("APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP"):
            if fz["target_gran"] == "G1_MACRO" and fz["target_id"] == candidate_g1_id:
                return "DIRECT_G1_PAIR"
            return "LOWER_GRANULARITY_ONLY" if fz["target_gran"] == "G3_MESO_FINE" else "UNKNOWN_SCOPE"
        return "UNKNOWN_SCOPE"
    # G4
    if fz["target_gran"] == "G1_MACRO" and fz["target_id"] == candidate_g1_id:
        return "DIRECT_G1_PAIR"
    if fz["target_gran"] == "G3_MESO_FINE":
        return "LOWER_GRANULARITY_ONLY"
    if dec in G4_NO_TARGET:
        return "SOURCE_LEVEL_SPATIAL_ONLY"
    return "UNKNOWN_SCOPE"


def _gate(eid: str, name: str, gran: str, cand_g1_id: str, cand_g1_name: str,
          fz: dict) -> tuple[str | None, str, str, str]:
    """Returns (new_class|None, gate_name, reason, applicability)."""
    # Entity Type Gate - unchanged
    if eid in ENTITY_TYPE_REVIEW_IDS or FIBER_LIKE.search(name):
        return (ETYPE, "ENTITY_TYPE_GATE",
                "IF.*/MF.*（或 fiber/white-matter 类 token）实体类型未冻结，禁止作为 "
                "BrainRegion contained_in 进入 VERIFIED。",
                "ENTITY_TYPE_GATE")
    if fz is None:
        return (None, "", "", "UNKNOWN_SCOPE")
    app = applicability(eid, name, gran, cand_g1_id, cand_g1_name, fz)
    dec = fz["decision"]
    if gran == "G3_MESO_FINE":
        if app == "DIRECT_G1_PAIR" or app == "EXPLICIT_G1_ROLLUP_BLOCK":
            ru = fz["rollup"]
            return (FROZEN, "FROZEN_DECISION_GATE",
                    f"G3→G1 frozen：decision={dec}，rollup_eligible={ru}（manifest "
                    f"显式字段 scientific_rollup_eligible），target==candidate G1 "
                    "→ 禁止提升为 contained_in。",
                    app)
        return (None, "", "", app)
    # G4: only DIRECT_G1_PAIR / EXPLICIT_G1_ROLLUP_BLOCK hard-block
    if app in ("DIRECT_G1_PAIR", "EXPLICIT_G1_ROLLUP_BLOCK"):
        return (FROZEN, "FROZEN_DECISION_GATE",
                f"存在直接针对该 G4→G1 的 frozen {dec}（app={app}），禁止 contained_in。",
                app)
    # LOWER_GRANULARITY_ONLY / SOURCE_LEVEL_SPATIAL_ONLY / UNKNOWN_SCOPE:
    # not applicable to this G4->G1 relation -> no frozen hard block
    return (None, "", "", app)


def evaluate() -> list[dict]:
    base = list(csv.DictReader(open(P1C, encoding="utf-8-sig")))
    if len(base) != EXPECTED:
        raise RuntimeError(f"universe {len(base)} != {EXPECTED}: fail closed")
    frozen = load_frozen()
    out = []
    for r in base:
        eid = r["source_entity_id"]
        if eid == VTM_RIGHT:
            raise RuntimeError("VTM right must NOT be in the 218 universe")
        fz = frozen.get(eid)
        cand_id = r["candidate_g1_entity_id"]
        cand_name = r["candidate_g1_name_en"]
        cls, gate, reason, app = _gate(eid, r["source_name_en"],
                                       r["source_granularity"], cand_id, cand_name, fz)
        row = dict(r)
        row["frozen_decision"] = (fz or {}).get("decision", "")
        row["frozen_applicability"] = app
        row["frozen_rollup_eligible"] = (fz or {}).get("rollup", "")
        row["frozen_rollup_explicit"] = ("TRUE" if (fz or {}).get("rollup") in ("TRUE", "FALSE")
                                         else "NO")
        if cls is None:
            row["v3_classification"] = r["phase17_classification"]
            row["gate"] = "NONE"
            row["gate_reason"] = ""
        else:
            row["v3_classification"] = cls
            row["gate"] = gate
            row["gate_reason"] = reason
        out.append(row)
    return out


def invariants(rows: list[dict]) -> dict:
    """Hard invariants. Every count must be 0 (except universe/missing/dup)."""
    ids = [r["source_entity_id"] for r in rows]
    app_map = {r["source_entity_id"]: r["frozen_applicability"] for r in rows}
    inv = dict(
        direct_g1_frozen_overwritten=0, explicit_no_rollup_overridden=0,
        g3_dominant_promoted=0, g3_no_g1_promoted=0,
        g4_lower_granularity_used_as_hard_block=0,
        source_level_spatial_only_used_as_hard_block=0,
        entity_type_in_verified=0,
        universe_missing=EXPECTED - len(ids),
        universe_duplicate=len(ids) - len(set(ids)))
    for r in rows:
        dec = r["frozen_decision"]
        v3 = r["v3_classification"]
        if v3 != V:
            continue
        if r["source_entity_id"] in ENTITY_TYPE_REVIEW_IDS:
            inv["entity_type_in_verified"] += 1
        if r["source_granularity"] == "G3_MESO_FINE":
            if dec == "APPROVE_DOMINANT_OVERLAP":
                inv["g3_dominant_promoted"] += 1
            if dec == "NO_G1_ROLLUP":
                inv["g3_no_g1_promoted"] += 1
            if app_map[r["source_entity_id"]] in ("DIRECT_G1_PAIR", "EXPLICIT_G1_ROLLUP_BLOCK"):
                inv["direct_g1_frozen_overwritten"] += 1
    # counts of hard blocks that wrongly used inapplicable G4 records (must be 0)
    for r in rows:
        if r["v3_classification"] == FROZEN and r["source_granularity"] == "G4_MICROSTRUCTURAL_FINE":
            if r["frozen_applicability"] in ("LOWER_GRANULARITY_ONLY",):
                inv["g4_lower_granularity_used_as_hard_block"] += 1
            if r["frozen_applicability"] == "SOURCE_LEVEL_SPATIAL_ONLY":
                inv["source_level_spatial_only_used_as_hard_block"] += 1
    return inv


def main() -> None:
    rows = evaluate()
    inv = invariants(rows)
    if any(v > 0 for v in inv.values()):
        raise RuntimeError(f"fail-closed invariants violated: {inv}")
    verified = sum(1 for r in rows if r["v3_classification"] == V)
    review = EXPECTED - verified
    by_cls = Counter(r["v3_classification"] for r in rows)
    by_gran = Counter((r["source_granularity"], r["v3_classification"]) for r in rows)
    app_cnt = Counter(r["frozen_applicability"] for r in rows)
    frozen_rows = [r for r in rows if r["v3_classification"] == FROZEN]
    summary = dict(
        phase="PHASE17_V3_RELATION_LEVEL_APPLICABILITY",
        universe=EXPECTED, verified=verified, review=review,
        verified_by_granularity={
            g: sum(1 for r in rows if r["v3_classification"] == V and r["source_granularity"] == g)
            for g in ("G3_MESO_FINE", "G4_MICROSTRUCTURAL_FINE")},
        review_by_granularity={
            g: sum(1 for r in rows if r["v3_classification"] != V and r["source_granularity"] == g)
            for g in ("G3_MESO_FINE", "G4_MICROSTRUCTURAL_FINE")},
        classification=dict(by_cls),
        classification_by_granularity={f"{g}={c}": n for (g, c), n in by_gran.items()},
        frozen_gate_hard_block_total=len(frozen_rows),
        applicability=dict(app_cnt),
        invariants=inv,
        stg_6_2=[(r["source_entity_id"], r["v3_classification"])
                 for r in rows if r["source_entity_id"] in ("NGIQ-BR-00000085", "NGIQ-BR-00000086")],
        vtm_right_excluded=VTM_RIGHT not in {r["source_entity_id"] for r in rows},
    )
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    diag = [
        "# Phase1.7 V3 Relation-level Frozen Applicability - 诊断",
        "",
        f"universe={EXPECTED} verified={verified} review={review}",
        f"classification={dict(by_cls)}",
        f"frozen hard-block total={len(frozen_rows)} (G3 only expected)",
        f"applicability={dict(app_cnt)}",
        f"invariants={inv}",
        "stg_6_2=" + str(summary["stg_6_2"]),
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(diag))
    print("rows", len(rows), "verified", verified, "review", review)
    print("classes", dict(by_cls))
    print("frozen blocks", len(frozen_rows), "applicability", dict(app_cnt))
    print("inv", inv)


if __name__ == "__main__":
    main()

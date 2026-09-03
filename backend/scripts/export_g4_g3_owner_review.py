"""Phase 2I-B — Owner Scientific Review Evidence EXPORT (no decisions).

Reads Phase 2I-A / 2H artifacts and emits a structured owner-review markdown
(g4_g3_owner_scientific_review_export.md). No decision, no threshold change, no
staging, no DB, no modification of any scientific CSV.

The full per-component evidence (pp cosine/soft-dice/top2/top3, hard top3, QA
flags) lives in g4_g3_overlap_interpretation_profiles.csv and is joined to the
canonical ledger via the Julich spatial asset file.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
INT = BACKEND / "data" / "integration"

LEDGER = INT / "g4_g3_scientific_decision_policy_v1.csv"
REL = INT / "g4_g3_preliminary_relation_decisions.csv"
CONF = INT / "g4_g3_conflict_review_queue.csv"
SHARED = INT / "g4_g3_shared_canonical_decision_exclusions.csv"
NONCAN = INT / "g4_g3_noncanonical_spatial_components.csv"
PROF = INT / "g4_g3_overlap_interpretation_profiles.csv"
SUMMARY = json.load(open(INT / "g4_g3_scientific_decision_policy_summary.json", encoding="utf-8"))
OUT = INT / "g4_g3_owner_scientific_review_export.md"

COV = __import__("numpy").load(str(INT / "g4_g3_hard_label_coverage_matrix.npz"))["coverage"]
M = __import__("numpy").load(str(INT / "g4_g3_probability_overlap_matrix.npz"))["M"]
COLS = list(csv.DictReader(open(INT / "g4_g3_probability_overlap_columns.csv", encoding="utf-8-sig")))
G3 = {int(r["column_index"]) - 1: r["canonical_g3_id"] for r in COLS}


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _f(x, nd=3):
    if x in ("", None):
        return "-"
    return f"{float(x):.{nd}f}"


def _num(x):
    return None if x in ("", None) else float(x)


def main() -> int:
    ledger = _rows(LEDGER)
    prof = _rows(PROF)
    prof_by_asset = {r["julich_asset_file"]: r for r in prof}

    # verify totals
    expected = {"APPROVE_CONTAINED_IN": 22, "APPROVE_DOMINANT_OVERLAP": 109, "PARTIAL_OVERLAP": 101,
                "NO_G3_MAPPING": 18, "CONFLICT_REVIEW": 126, "SHARED_SPATIAL_EVIDENCE_ONLY": 64}
    from collections import Counter
    actual = Counter(r["scientific_decision"] for r in ledger)
    assert len(ledger) == 440 and actual == expected, (len(ledger), actual)
    assert len(_rows(REL)) == 367
    assert len(_rows(CONF)) == 126
    assert len(_rows(SHARED)) == 64
    assert len(_rows(NONCAN)) == 14
    check = expected

    def full(row):
        p = prof_by_asset.get(row["spatial_asset_file"], {})
        return {**row, **p}

    def macro_of_g3(g3id):
        # column -> component_index -> parcel_id -> authoritative macro gyrus
        for c in COLS:
            if c["canonical_g3_id"] == g3id:
                pid = int(c["component_index"])
                break
        else:
            return None
        auth = _auth.get(pid)
        return auth

    L = []
    def w(s=""):
        L.append(s)
    def h(level, text):
        w(("#" * level) + " " + text)
    def table(headers, rows):
        if not rows:
            w("_(none)_")
            return
        widths = [max(len(str(hh)), *(len(str(r[i])) for r in rows)) for i, hh in enumerate(headers)]
        def fmt(r):
            return "| " + " | ".join(str(r[i]).ljust(widths[i]) for i in range(len(headers))) + " |"
        w(fmt(headers)); w("|" + "|".join("-" * (x + 2) for x in widths) + "|")
        for r in rows:
            w(fmt(r))

    h(1, "G4→G3 Owner Scientific Review — Evidence Export (Phase 2I-B)")
    w("")
    w("> Read-only export. Decisions retain Phase 2I-A values (PENDING_OWNER_REVIEW). No decisions/thresholds changed.")

    # ---- 1 Executive counts ----
    h(2, "1. Executive Counts")
    table(["metric", "count"], [
        ["canonical G4", "440"], ["direct decisionable", "376"], ["shared canonical", "64"],
        ["noncanonical spatial components", "14"],
        ["contained", check["APPROVE_CONTAINED_IN"]], ["dominant", check["APPROVE_DOMINANT_OVERLAP"]],
        ["partial", check["PARTIAL_OVERLAP"]], ["no mapping", check["NO_G3_MAPPING"]],
        ["conflict", check["CONFLICT_REVIEW"]], ["shared evidence only", check["SHARED_SPATIAL_EVIDENCE_ONLY"]],
        ["preliminary relation rows", 367],
    ])

    sel = {"contained": [], "no_mapping": [], "disagree": [], "pinc": [], "restconf": [], "partial": [], "dominant": [], "shared": []}
    for row in ledger:
        fr = full(row)
        dec = row["scientific_decision"]
        if dec == "APPROVE_CONTAINED_IN":
            sel["contained"].append(fr)
        elif dec == "NO_G3_MAPPING":
            sel["no_mapping"].append(fr)
        elif dec == "CONFLICT_REVIEW":
            rc = row["decision_reason_code"]
            if rc == "PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT":
                sel["disagree"].append(fr)
            elif rc == "PARTIAL_TARGET_EVIDENCE_INCONSISTENT":
                sel["pinc"].append(fr)
            else:
                sel["restconf"].append(fr)
        elif dec == "PARTIAL_OVERLAP":
            sel["partial"].append(fr)
        elif dec == "APPROVE_DOMINANT_OVERLAP":
            sel["dominant"].append(fr)
        elif dec == "SHARED_SPATIAL_EVIDENCE_ONLY":
            sel["shared"].append(fr)

    # ---- 2 contained full ----
    h(2, "2. 22 Contained — Full Review")
    tab = []
    for i, r in enumerate(sel["contained"], 1):
        tab.append([i, r["canonical_g4_id"], r["canonical_g4_name"][:30], r["hemisphere"],
                    r["pp_top1_g3"], r["hard_top1_g3"],
                    _f(r["hard_top1_coverage"], 3), _f(r["hard_top2_coverage"], 3),
                    _f(r["hard_total_bna_coverage"], 3), _f(r["bna_uncovered_fraction"], 3),
                    _f(r["pp_top1_g4_weighted"], 3), _f(r["pp_top2_g4_weighted"], 3),
                    _f(r["pp_top1_top2_ratio"], 2), _f(r["pp_top1_top2_margin"], 3),
                    _f(r["pp_top1_g3_weighted"], 3), _f(r["pp_top1_cosine"], 3),
                    _f(r["pp_top1_soft_dice"], 3), _f(r["effective_target_count"], 2),
                    r["top1_agreement"], r["decision_reason_code"]])
    table(["#", "G4 id", "G4 name", "hemi", "ppT G3", "hardT G3", "h1", "h2",
           "hardTot", "uncov", "pp1g4w", "pp2g4w", "ppRat", "ppMarg", "pp1g3w",
           "cos", "sdice", "effT", "agree", "reason"], tab)
    assert len(tab) == 22

    # ---- 3 no mapping full ----
    h(2, "3. 18 No G3 Mapping — Full Review")
    tab = []
    for r in sorted(sel["no_mapping"], key=lambda x: (x["decision_reason_code"], x["canonical_g4_id"])):
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:28], r["hemisphere"],
                    r["decision_reason_code"], _f(r["hard_total_bna_coverage"], 4),
                    _f(r["bna_uncovered_fraction"], 4), _f(r["pp_top1_g4_weighted"], 4),
                    _f(r["pp_top1_joint_mass"], 3),
                    r["pp_top1_g3"] if r["pp_top1_g3"] else "-",
                    _f(r["pp_top1_g4_weighted"], 4) if r["pp_top1_g3"] else "-"])
    table(["G4 id", "G4 name", "hemi", "reason", "hardTot", "uncov", "pp1g4w", "ppTop1Joint", "top1G3", "top1score"], tab)
    assert len(tab) == 18

    # ---- 4 disagreements 35 ----
    h(2, "4. 35 PP/Hard Top1 Disagreements — Full")
    tab = []
    for r in sel["disagree"]:
        p, hr = r["pp_top1_g3"], r["hard_top1_g3"]
        same = same_macro_or_homologue(p, hr)
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:22], r["hemisphere"],
                    p, _f(r["pp_top1_g4_weighted"], 3), r.get("pp_top2_g3_id", "-"), _f(r["pp_top2_g4_weighted"], 3),
                    hr, _f(r["hard_top1_coverage"], 3), r.get("hard_top2_g3_id", "-"), _f(r["hard_top2_coverage"], 3),
                    _f(r["hard_total_bna_coverage"], 3), _f(r["bna_uncovered_fraction"], 3),
                    _f(r["effective_target_count"], 2), same])
    table(["G4 id", "G4 name", "hemi", "pp1", "pp1g4w", "pp2", "pp2g4w", "hard1", "h1c",
           "hard2", "h2c", "hardTot", "uncov", "effT", "sameMacro/Homolog"], tab)
    assert len(tab) == 35

    # ---- 5 partial inconsistent 5 ----
    h(2, "5. Partial-Target Evidence Inconsistent (5)")
    tab = []
    for r in sel["pinc"]:
        j = int(r["row_index"]) - 1 if r.get("row_index") else None
        offending = []
        if j is not None:
            cov, mrow = COV[j], M[j]
            tgt = [int(i) for i in np_flatnonzero((cov >= 0.15) & (mrow > 0))]
            pos = [int(i) for i in np_flatnonzero(mrow > 0)]
            pos = sorted(pos, key=lambda i: -mrow[i])
            rank = {i: k + 1 for k, i in enumerate(pos)}
            for i in tgt:
                if rank.get(i, 99) > 3:
                    offending.append(f"{G3[i]}(hard={cov[i]:.2f},ppRank={rank.get(i, 99)})")
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:28], r["hemisphere"],
                    "; ".join(offending) if offending else "see relation/coverage", r["decision_reason_code"]])
    table(["G4 id", "G4 name", "hemi", "offending target(s) [coverage >=0.15 but pp rank >3]", "reason"], tab)
    assert len(tab) == 5

    # ---- 6 remaining conflict 86 ----
    h(2, "6. Remaining Conflict Queue (full, grouped by reason)")
    rest = sorted(sel["restconf"], key=lambda r: r["decision_reason_code"])
    tab = []
    for r in rest:
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:20], r["hemisphere"],
                    r["decision_reason_code"], _f(r["hard_top1_coverage"], 3),
                    _f(r["hard_top2_coverage"], 3), _f(r["hard_total_bna_coverage"], 3),
                    _f(r["bna_uncovered_fraction"], 3), r["pp_top1_g3"],
                    _f(r["pp_top1_g4_weighted"], 3), r.get("pp_top2_g3_id", "-"),
                    _f(r["effective_target_count"], 2)])
    table(["G4 id", "name", "hemi", "reason", "h1", "h2", "hardTot", "uncov", "pp1", "pp1g4w", "pp2", "effT"], tab)
    assert len(tab) == 86

    # ---- 7 partial sources compact ----
    h(2, "7. 101 Partial Sources (compact, one row per source)")
    tab = []
    stats = {2: 0, 3: 0, "4plus": 0}
    for r in sel["partial"]:
        j = int(r["row_index"]) - 1
        cov, mrow = COV[j], M[j]
        pos = [int(i) for i in np_flatnonzero(mrow > 0)]
        pos.sort(key=lambda i: -mrow[i])
        rank = {i: k + 1 for k, i in enumerate(pos)}
        tgt = [int(i) for i in np_flatnonzero((cov >= 0.15) & (mrow > 0))]
        tgt.sort(key=lambda i: -cov[i])
        n = len(tgt)
        stats[n if n <= 3 else "4plus"] = stats.get(n if n <= 3 else "4plus", 0) + 1
        tgt_s = "; ".join(f"{G3[i]}={cov[i]:.2f}" for i in tgt)
        top_cov = sorted(cov[cov > 0])[::-1]
        cum2 = sum(top_cov[:2]); cum3 = sum(top_cov[:3])
        pp1 = G3[pos[0]] if pos else "-"
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:18], r["hemisphere"], n,
                    _f(top_cov[0] if top_cov else 0, 3), _f(top_cov[1] if len(top_cov) > 1 else 0, 3),
                    _f(top_cov[2] if len(top_cov) > 2 else 0, 3), _f(cum2, 3), _f(cum3, 3),
                    pp1, G3[pos[1]] if len(pos) > 1 else "-", G3[pos[2]] if len(pos) > 2 else "-",
                    _f(r["effective_target_count"], 2), r["top1_agreement"],
                    "TRUE" if n >= 3 else "FALSE", tgt_s])
    table(["G4 id", "name", "hemi", "nTgt", "h1", "h2", "h3", "cum2", "cum3", "pp1", "pp2", "pp3",
           "effT", "agree", "3+tgt", "targets (hard>=.15, pp>0)"], tab)
    w("")
    table(["metric", "count"], [["2-target sources", stats.get(2, 0)], ["3-target sources", stats.get(3, 0)],
                                ["4+ target sources", stats.get("4plus", 0)]])
    assert len(tab) == 101

    # ---- 8 dominant 109 ascending hard_top1 ----
    h(2, "8. 109 Dominant Sources (sorted by hard_top1 ascending)")
    dom = sorted(sel["dominant"], key=lambda r: _num(r["hard_top1_coverage"]) or 0)
    tab = []
    for r in dom:
        tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:20], r["hemisphere"], r["hard_top1_g3"],
                    _f(r["hard_top1_coverage"], 3), _f(r["hard_top2_coverage"], 3),
                    _f(r["hard_top1_top2_margin"], 3), _f(r["hard_total_bna_coverage"], 3),
                    _f(r["bna_uncovered_fraction"], 3), _f(r["pp_top1_g4_weighted"], 3),
                    _f(r["pp_top1_top2_ratio"], 2), _f(r["effective_target_count"], 2),
                    r["top1_agreement"]])
    table(["G4 id", "name", "hemi", "target", "h1", "h2", "margin", "hardTot", "uncov", "pp1g4w", "ppRat", "effT", "agree"], tab)
    assert len(tab) == 109

    # ---- 9 shared 24 components ----
    h(2, "9. 24 Shared Spatial Components (component-level, not duplicated)")
    # 24 shared rows = 12 unique Julich areas x 2 hemispheres; each hemisphere-specific
    # probability map is a distinct spatial component (keyed by asset file).
    shared_led = [r for r in _rows(SHARED)]
    bycomp = {}
    for r in shared_led:
        bycomp.setdefault(r["spatial_asset_file"], []).append(r)
    assert len(bycomp) == 24, len(bycomp)
    tab = []
    for asset, leaves in bycomp.items():
        first = leaves[0]
        p = prof_by_asset.get(asset, {})
        comp = p.get("julich_component_id", first["spatial_component_id"])
        region = p.get("julich_region_name", comp)[:34]
        desc = "; ".join(f"{x['canonical_g4_id']}({x['canonical_g4_name'][:18]})" for x in leaves)
        tab.append([comp, region, p.get("julich_hemisphere", first["hemisphere"]), len(leaves),
                    p.get("pp_top1_g3", first["pp_top1_g3"]), p.get("hard_top1_g3", first["hard_top1_g3"]),
                    _f(first["hard_total_bna_coverage"], 3), "SHARED_COMPONENT_LEVEL_ONLY", desc])
    table(["component", "name", "hemi", "nDesc", "ppTop1G3", "hardTop1G3", "hardTot", "evidenceStatus", "canonical descendants"], tab)
    w("")
    w("No component-level score is duplicated into independent leaf-level mappings (440 ledger rows / 367 relation rows unchanged).")

    # ---- 10 noncanonical 14 ----
    h(2, "10. 14 Noncanonical Spatial Components")
    tab = []
    for r in _rows(NONCAN):
        tab.append([r["spatial_component_id"], r["julich_leaf_id"][:44], r["julich_region_name"][:30],
                    r["julich_hemisphere"], "absent from 440-canonical registry",
                    r.get("pp_top1_name", "-"), r.get("pp_top1_g4_weighted", "-"), "FALSE"])
    table(["component", "julich leaf id", "name", "hemi", "why not canonical", "ppTop1G3", "pp1g4w", "prodMapping"], tab)
    assert len(tab) == 14

    # ---- 11 threshold-boundary ----
    h(2, "11. Threshold-Boundary Cases")
    h(3, "A. contained: hard_top1 in [0.80, 0.85)")
    tab = [[r["canonical_g4_id"], r["canonical_g4_name"][:28], _f(r["hard_top1_coverage"], 3)] for r in sel["contained"]
           if 0.80 <= (_num(r["hard_top1_coverage"]) or 0) < 0.85]
    table(["G4 id", "name", "h1"], tab)
    h(3, "B. dominant: hard_top1 in [0.50, 0.55)")
    tab = [[r["canonical_g4_id"], r["canonical_g4_name"][:28], _f(r["hard_top1_coverage"], 3)] for r in sel["dominant"]
           if 0.50 <= (_num(r["hard_top1_coverage"]) or 0) < 0.55]
    table(["G4 id", "name", "h1"], tab)
    h(3, "C. partial: 2nd-target (hard_top2) in [0.15, 0.20)")
    tab = [[r["canonical_g4_id"], r["canonical_g4_name"][:28], _f(r["hard_top2_coverage"], 3)] for r in sel["partial"]
           if (_num(r["hard_top2_coverage"]) is not None and 0.15 <= _num(r["hard_top2_coverage"]) < 0.20)]
    table(["G4 id", "name", "h2"], tab)
    h(3, "D. NO_MAPPING: hard_total in [0.08, 0.15]")
    tab = [[r["canonical_g4_id"], r["canonical_g4_name"][:28], _f(r["hard_total_bna_coverage"], 4)] for r in sel["no_mapping"]
           if _num(r["hard_total_bna_coverage"]) is not None and 0.08 <= _num(r["hard_total_bna_coverage"]) <= 0.15]
    table(["G4 id", "name", "hardTot"], tab)
    h(3, "E. all effective_target_count > 5")
    tab = []
    for r in ledger:
        eff = _num(r["effective_target_count"])
        if eff is not None and eff > 5:
            tab.append([r["canonical_g4_id"], r["canonical_g4_name"][:26], r["hemisphere"],
                        r["scientific_decision"], _f(eff, 2)])
    table(["G4 id", "name", "hemi", "decision", "effT"], tab)

    OUT.write_text("\n".join(L), encoding="utf-8")
    print("wrote", OUT)
    return 0


def np_flatnonzero(x):
    import numpy as np
    return np.flatnonzero(x)


_auth = None
def _load_auth():
    global _auth
    if _auth is None:
        rows = list(csv.DictReader(open(INT / "g4_julich_v31_spatial_component_alignment.csv", encoding="utf-8-sig")))  # unused
        # BNA macro gyrus by parcel
        auth = {}
        for c in COLS:
            auth[c["canonical_g3_id"]] = c
        _auth = auth
    return _auth


def same_macro_or_homologue(g1, g2):
    """Deterministic check using frozen BNA identity only (no anatomy guessing)."""
    if not g1 or not g2:
        return "NOT_EVALUATED"
    a = _load_auth()
    c1 = a.get(g1) or {}
    c2 = a.get(g2) or {}
    if not c1 or not c2:
        return "NOT_EVALUATED"
    code1, code2 = c1["g3_region_name"], c2["g3_region_name"]
    # L/R homologue test on the code pattern (e.g. STG_L_6_1 <-> STG_R_6_1)
    import re
    def swap(c):
        m = re.match(r"^(.*?)_([LR])_(.*)$", c)
        return f"{m.group(1)}_{'R' if m.group(2)=='L' else 'L'}_{m.group(3)}" if m else None
    if swap(code1) == code2 or swap(code2) == code1:
        return "HOMOLOGOUS_LR"
    # same macro gyrus: compare prefix before _L_/_R_
    base = lambda c: re.match(r"^(.*?)_[LR]_", c).group(1) if re.match(r"^(.*?)_[LR]_", c) else c
    if base(code1) == base(code2):
        return "SAME_MACRO"
    return "DIFFERENT_MACRO"


if __name__ == "__main__":
    raise SystemExit(main())

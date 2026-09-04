"""Phase1.7 V3 - two-hop proxy validity & calibration audit (READ-ONLY).

Validates the math used by phase17_v3_spatial_review_audit.py and calibrates the
proxy against the 86 VERIFIED anchors and the ZI/Rt negatives. Nothing is
reclassified; nothing is written to the DB.
"""
from __future__ import annotations

import csv
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
G4 = D16.parent / "g4_g3"
G3 = D16.parent / "g3_to_g1"
OUTV = D16 / "phase17_v3_spatial_proxy_validation.csv"
OUTS = D16 / "phase17_v3_spatial_proxy_validation_summary.json"
OUTM = D16 / "phase17_v3_spatial_proxy_validation_diagnostics.md"
OUTC = D16 / "phase17_v3_spatial_proxy_calibration.csv"
OUTB = D16 / "phase17_v3_spatial_proxy_basal_forebrain_qa.csv"

LK = "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"
V = "VERIFIED_DIRECT_CONTAINED"


def _csv(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def main():
    cls = _csv(D16 / "phase17_v3_classification.csv")
    lk = [r for r in cls if r["v3_classification"] == LK]
    vd = [r for r in cls if r["v3_classification"] == V]
    assert len(lk) == 93 and len(vd) == 86

    # manifests
    g3man = _csv(G3 / "g3_to_g1_full_decision_coverage_manifest.csv")
    g3dec = {}
    for r in g3man:
        g3dec[r["g3_entity_id"]] = r

    ov = _csv(G4 / "g4_g3_probability_overlap_rows.csv")
    comp2g4 = {}
    for r in ov:
        for e in (r.get("canonical_g4_entity_ids") or "").split("|"):
            if e.startswith("NGIQ-BR-"):
                comp2g4.setdefault(r["julich_component_id"], []).append(e)
    comp = defaultdict(lambda: defaultdict(lambda: dict(joint=0.0, dice=0.0, g4w=0.0)))
    g4mass = {}
    for r in _csv(G4 / "g4_g3_probability_overlap_matrix.csv"):
        cid = r["julich_component_id"]
        try:
            j = float(r["joint_weighted_mass_mm3"])
            d = float(r["soft_dice"] or 0)
            w = float(r["g4_mass_weighted_g3_probability"] or 0)
        except ValueError:
            j = d = w = 0.0
        comp[cid][r["canonical_g3_id"]]["joint"] += j
        comp[cid][r["canonical_g3_id"]]["dice"] = max(comp[cid][r["canonical_g3_id"]]["dice"], d)
        comp[cid][r["canonical_g3_id"]]["g4w"] += w
        g4mass[cid] = float(r["g4_probability_mass"] or 0)

    def source_components(eid):
        return [c for c, es in comp2g4.items() if eid in es]

    def ledger(eid):
        comps = source_components(eid)
        tot = cand = other = mapped = unmapped = amb = noncont = 0.0
        g1map = defaultdict(float)
        for cid in comps:
            for g3, m in comp.get(cid, {}).items():
                j = m["joint"]
                tot += j
                d = g3dec.get(g3)
                if d is None:
                    unmapped += j
                    continue
                dec = d["effective_scientific_decision"]
                if dec == "APPROVE_CONTAINED_IN":
                    g1id = d["primary_target_g1_entity_id"]
                    g1map[g1id] += j
                elif dec in ("APPROVE_DOMINANT_OVERLAP", "PARTIAL_OVERLAP"):
                    noncont += j
                else:
                    amb += j
        return dict(comp=len(comps), total=tot, g1map=g1map, contained=sum(g1map.values()),
                    noncont=noncont, amb=amb, unmapped=unmapped)

    rows = []
    for r in lk + vd:
        l = ledger(r["source_entity_id"])
        cand = l["g1map"].get(r["candidate_g1_entity_id"], 0.0)
        other = l["contained"] - cand
        mapped = l["contained"]
        cand_total = cand / l["total"] if l["total"] else None
        cand_mapped = cand / mapped if mapped else None
        rows.append(dict(
            source_id=r["source_entity_id"], source_name=r["source_name_en"],
            v3_classification=r["v3_classification"],
            candidate_g1_id=r["candidate_g1_entity_id"], candidate_g1_name=r["candidate_g1_name_en"],
            spatial_evidence_level="TWO_HOP_G4_G3_G1_PROXY",
            total_overlap_mass=f"{l['total']:.3f}",
            g3_mass_with_valid_g1_mapping=f"{l['contained']:.3f}",
            g3_mass_with_frozen_noncontained_g1=f"{l['noncont']:.3f}",
            g3_mass_with_ambiguous_g1_mapping=f"{l['amb']:.3f}",
            g3_mass_without_any_g1_mapping=f"{l['unmapped']:.3f}",
            candidate_g1_mass=f"{cand:.3f}", other_g1_mass=f"{other:.3f}",
            mapped_mass_fraction=f"{mapped / l['total']:.3f}" if l['total'] else "0",
            unmapped_mass_fraction=f"{l['unmapped'] / l['total']:.3f}" if l['total'] else "0",
            ambiguous_mass_fraction=f"{l['amb'] / l['total']:.3f}" if l['total'] else "0",
            candidate_fraction_of_total=(f"{cand_total:.3f}" if cand_total is not None else "NA"),
            candidate_fraction_of_mapped=(f"{cand_mapped:.3f}" if cand_mapped else "0"),
            normalization_flag="NON_NORMALIZED_OVERLAP_METRIC"))
    # sum-of-joint vs source mass normalization probe
    probe = []
    for cid, m in list(comp.items())[:6]:
        tot = sum(x["joint"] for x in m.values())
        probe.append(dict(component=cid[:40], g4_probability_mass=g4mass[cid],
                          sum_joint_mm3=f"{tot:.2f}"))
    # calibration: candidate_fraction_of_total thresholds vs other-frac
    cal_rows = []
    lk_ids = {x["source_entity_id"] for x in lk}
    vd_ids = {x["source_entity_id"] for x in vd}

    def passes(idset):
        n = 0
        for r in rows:
            if r["source_id"] not in idset:
                continue
            cf = r["candidate_fraction_of_total"]
            if cf == "NA":
                continue
            cf = float(cf)
            oth = float(r["other_g1_mass"]) / float(r["total_overlap_mass"]) \
                if float(r["total_overlap_mass"]) else 1.0
            if cf >= cth and oth <= xth:
                n += 1
        return n

    for cth in (0.5, 0.6, 0.7, 0.8, 0.9):
        for xth in (0.05, 0.10, 0.20):
            cal_rows.append(dict(threshold_candidate=cth, threshold_cross=xth,
                                 pass_93=passes(lk_ids), pass_86_anchors=passes(vd_ids)))
    # basal forebrain QA
    bf = [r for r in rows if "Basal Forebrain" in r["candidate_g1_name"]]
    # ZI / Rt negative proxies
    neg_ids = {"NGIQ-BR-00000707", "NGIQ-BR-00000708", "NGIQ-BR-00000709", "NGIQ-BR-00000710"}
    neg = []
    for r in cls:
        if r["source_entity_id"] in neg_ids:
            l = ledger(r["source_entity_id"])
            cand = l["g1map"].get("NGIQ-BR-00000256") + l["g1map"].get("NGIQ-BR-00000247")
            neg.append(dict(source_id=r["source_entity_id"], source_name=r["source_name_en"],
                            v3=r["v3_classification"],
                            candidate_mass_of_thal_G1=f"{cand:.3f}",
                            contained_mapped=f"{l['contained']:.3f}",
                            candidate_fraction=(f"{(cand / l['total']):.3f}" if l['total'] else "NA")))

    cols = list(rows[0].keys())
    with open(OUTV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(OUTC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cal_rows[0].keys()))
        w.writeheader()
        for r in cal_rows:
            w.writerow(r)
    with open(OUTB, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(bf[0].keys()) if bf else ["source_id"])
        w.writeheader()
        for r in bf:
            w.writerow(r)

    audit_by_id = {r["source_id"]: r for r in rows}

    def fracs(idset):
        out = []
        for eid in idset:
            r = audit_by_id.get(eid)
            if not r:
                continue
            try:
                out.append(float(r["mapped_mass_fraction"]))
            except (ValueError, TypeError):
                pass
        return out

    lkf, vdf = fracs(lk_ids), fracs(vd_ids)
    summary = dict(
        proxy_note="TWO_HOP_G4_G3_G1_PROXY (not direct geometry)",
        normalization_probe=probe,
        metric_normalization="NON_NORMALIZED_OVERLAP_METRIC",
        rows_validated=len(rows), rows_likely=len(lk), rows_verified_anchors=len(vd),
        mapped_coverage_likely_median=(round(statistics.median(lkf), 3) if lkf else None),
        mapped_coverage_verified_median=(round(statistics.median(vdf), 3) if vdf else None),
        mapped_coverage_likely_dist=dict(Counter(round(x, 1) for x in lkf)),
        basal_forebrain_count=len(bf),
        negatives=neg,
        calibration_sample=cal_rows[:4],
    )
    with open(OUTS, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    md = ["# Phase1.7 V3 two-hop proxy validity & calibration", "",
          f"rows validated={len(rows)} (LIKELY 93 + VERIFIED-anchors 86)",
          "metric: NON_NORMALIZED_OVERLAP_METRIC - two-hop G4->G3->G1 proxy only",
          f"mapped coverage median: LIKELY={summary['mapped_coverage_likely_median']} "
          f"VERIFIED={summary['mapped_coverage_verified_median']}",
          "calibration(first rows): " + str(cal_rows[:4]),
          "basal forebrain rows=" + str(len(bf)),
          "negatives=" + str(neg)]
    with open(OUTM, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    print("validated rows", len(rows))
    print("BF rows", len(bf), "neg", neg)
    print("coverage medians lk/vd", summary["mapped_coverage_likely_median"],
          summary["mapped_coverage_verified_median"])


if __name__ == "__main__":
    main()

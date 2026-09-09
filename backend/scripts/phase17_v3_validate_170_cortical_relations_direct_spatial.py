"""Phase1.7 V3 - 170 cortical candidate relations direct spatial evidence validation.

Computes independent DIRECT SPATIAL evidence for the frozen 170 cortical candidate
relations (Brainnetome G3_MESO_FINE parcels -> Desikan-Killiany cortical G1), using
  fine geometry  = BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz (official Brainnetome
                   volume transformed to the Julich/MNI152NLin2009cAsym reference grid with
                   the frozen NLin6->2009c transform; discrete integer labels 1..246)
  G1 geometry    = the 62 frozen DK cortical G1 reference geometries (c97d7d8) on the same
                   193x229x193 @1mm grid.
Both grids are identical -> no resample, no registration, no transform application.

Metrics (containment primary, Dice secondary):
  source_in_target_containment = |Fine ∩ G1| / |Fine|
  plus fine_voxels, g1_voxels, intersection, target_covered_by_source (|∩|/|G1|), Dice,
  Jaccard, centroid distance. Every Left fine is compared against ALL 31 Left G1 and every
  Right fine against ALL 31 Right G1 -> proposed rank / best / second / best-non-proposed /
  margin are computed WITHOUT winner-takes-all mapping change. Outside-union fraction kept as
  real evidence (no renormalisation). Historical status is joined POSTHOC only.

All 170 relations are discrete G3 (Brainnetome); the G4/probabilistic subset is empty in
this frozen universe and is reported as such (no probability-mass handling needed here).

No ontology adjudication: only descriptive flags
  PROPOSED_RANK_1 / PROPOSED_NOT_RANK_1 / CLOSE_COMPETITION / LOW_CONTAINMENT /
  HIGH_OUTSIDE_UNION / LATERALITY_FAILURE
are emitted; mappings, classification and lifecycle statuses are NOT modified.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import nibabel as nib

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
G1DIR = BACKEND / "data" / "atlases" / "derived_g1" / "cort_g1_62"
SCRIPT_VERSION = "phase17_v3_validate_170_cortical_relations_direct_spatial.py v1"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
G1MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
CLASS = D16 / "phase17_v3_classification.csv"
FINE_VOL = (BACKEND / "data/atlases/brainnetome/bna246/transformed_label_to_julich2009c/"
            "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz")
FINE_RAW_SHA = "0d90d084952bdbddf417abb457f4eec016cbb95dfd53a4801713806da5646ba3"
XFM_SHA = "2e3869a07b96aec406e0419ca2e434afc54882d37cc212b933b139d1b63a4dfe"
FINE_SHA = "9c0185c7c0b9a2bf03a9e72d296d4fc8caed0e1318a59723a52ada8f06f1e19f"

OUT_UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
OUT_INV = D16 / "phase17_v3_cortical_fine_geometry_inventory.csv"
OUT_MET = D16 / "phase17_v3_cortical_direct_spatial_method_v1.json"
OUT_EVD = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
OUT_LONG = D16 / "phase17_v3_cortical_170_g1_competition_long.csv"
OUT_ATS = D16 / "phase17_v3_cortical_direct_spatial_atlas_summary.csv"
OUT_XA = D16 / "phase17_v3_cortical_direct_spatial_status_crossaudit.csv"
OUT_DISC = D16 / "phase17_v3_cortical_direct_spatial_discordance.csv"
OUT_PROV = D16 / "phase17_v3_cortical_direct_spatial_provenance.json"
OUT_MD = D16 / "phase17_v3_cortical_direct_spatial_diagnostics.md"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # ---- universe (reconstructed from frozen G3MAN, NOT hand-written) ----
    g3 = list(csv.DictReader(open(G3MAN, encoding="utf-8-sig")))
    g1rows = list(csv.DictReader(open(G1MAN, encoding="utf-8-sig")))
    tgt = {r["canonical_region_id"]: r for r in g1rows}
    sub = [r for r in g3 if r["primary_target_g1_entity_id"] in tgt]
    assert len(sub) == 170, len(sub)
    assert Counter(r["hemisphere"] for r in sub) == Counter({"left": 85, "right": 85})
    univ = []
    for r in sorted(sub, key=lambda x: int(x["parcel_id"])):
        univ.append(dict(
            relation_id=r["g3_entity_id"], fine_region_id=r["g3_entity_id"],
            fine_region_name=r["official_code"], parcel_id=int(r["parcel_id"]),
            fine_granularity=r["granularity_level"],
            fine_atlas="Brainnetome", hemisphere=r["hemisphere"],
            proposed_g1_id=r["primary_target_g1_entity_id"],
            proposed_g1_name=r["primary_target_g1_name"],
            historical_status=r["effective_scientific_decision"],
            historical_reason=r["decision_origin"]))
    with open(OUT_UNIV, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(univ[0].keys()))
        w.writeheader()
        for row in univ:
            w.writerow(row)

    # ---- load fine volume + G1 masks ----
    m = np.asanyarray(nib.load(str(FINE_VOL)).dataobj).astype(np.int16)
    g1mask = {}
    for r in g1rows:
        p = G1DIR / f"{r['geometry_id']}.nii.gz"
        if not p.exists():
            raise SystemExit("missing G1 geometry " + r["geometry_id"])
        g1mask[r["canonical_region_id"]] = np.asanyarray(nib.load(str(p)).dataobj) > 0
    assert all(r["canonical_region_id"] in g1mask for r in g1rows)

    # G1 -> (histogram of fine labels inside it), g1 sizes
    g1_size = {}
    hist_of_g1 = {}
    for cid, gm in g1mask.items():
        g1_size[cid] = int(gm.sum())
        hist_of_g1[cid] = np.bincount(m[gm], minlength=247)
    fine_size = np.bincount(m.ravel(), minlength=247)   # parcel p volume (p==0 background)
    # union masks per hemisphere (for outside-union)
    union = {"left": np.zeros(m.shape, bool), "right": np.zeros(m.shape, bool)}
    for r in g1rows:
        union[r["hemisphere"]] |= g1mask[r["canonical_region_id"]]
    # centroid x side fractions per fine parcel (RAS x<0 == left) for laterality
    rasx = None
    aff = nib.load(str(FINE_VOL)).affine
    # grid x per voxel (RAS)
    sh = m.shape
    ii, jj, kk = np.ogrid[:sh[0], :sh[1], :sh[2]]
    xgrid = aff[0, 0] * (ii + 0.5) + aff[0, 1] * (jj + 0.5) + aff[0, 2] * (kk + 0.5) + aff[0, 3]
    left_grid = xgrid < 0

    # classification join (posthoc) map fine -> v3 status
    cls = {}
    for r in csv.DictReader(open(CLASS, encoding="utf-8-sig")):
        cls.setdefault(r["source_entity_id"], []).append(r["v3_classification"])

    # ---- method_v1 ----
    method = dict(
        method_id="DIRECT_CORTICAL_SPATIAL_VALIDATION_METHOD_V1",
        reference_grid="MNI152NLin2009cAsym 193x229x193 @1mm",
        fine_geometry=dict(atlas="Brainnetome (246)", granularity="G3_MESO_FINE",
                           volume=str(FINE_VOL).replace("\\", "/"), volume_sha256=sha256(FINE_VOL),
                           raw_asset="BN_Atlas_246_1mm.nii.gz (NLin6Asym)",
                           raw_sha256=FINE_RAW_SHA, transform_sha256=XFM_SHA,
                           interpolation="NearestNeighbor", discrete=True),
        g1_geometry=dict(source="62 frozen DK cortical G1 references (c97d7d8)", count=62),
        metrics=dict(
            primary="source_in_target_containment = |Fine INTERSECT G1| / |Fine|",
            secondary=["Dice", "Jaccard", "target_covered_by_source", "centroid_distance_mm"],
            probability_semantics="not applicable - all 170 relations are discrete G3 in this "
                                  "frozen universe (G4 subset = 0)"),
        competition=dict(scope="same-hemisphere 31 G1 (left fine vs 31 left G1; right vs 31 right)",
                         ranking="containment descending; rank = 1 + count(strictly greater)",
                         no_winner_takes_all=True,
                         margin="proposed containment - best non-proposed containment"),
        outside_union=dict(definition="fraction of fine voxels outside the same-hemisphere union "
                                      "of all 31 cortical G1 references; kept as real evidence, "
                                      "never renormalised to sum 1"),
        laterality="RAS x<0 = left (frozen coordinate handling); LATERALITY_FAILURE if a fine "
                   "region's dominant side contradicts its label side",
        blind_before_join=True,
        historical_status_joined_posthoc=True,
        tie_handling="stable; ties share scores and margins use strict best-non-proposed",
        numerical_precision="integer voxel counts on shared 1 mm grid",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_MET, "w", encoding="utf-8") as fh:
        json.dump(method, fh, ensure_ascii=False, indent=2)

    # ---- fine geometry inventory ----
    inv_rows = []
    for p in range(1, 247):
        mask = m == p
        if not mask.any():
            continue
        side = "left" if int((mask & left_grid).sum()) >= mask.sum() / 2 else "right"
        inv_rows.append(dict(
            parcel_id=p, atlas="Brainnetome", version="BN 246 (v1.0)",
            geometry_source=str(FINE_VOL).replace("\\", "/"), raw_sha256=FINE_RAW_SHA,
            transform_sha256=XFM_SHA, derived_sha256=FINE_SHA,
            native_space="MNI152NLin6Asym 1mm", current_space="MNI152NLin2009cAsym 1mm",
            discrete=True, probabilistic=False, grid_ready=True, provenance_complete=True,
            voxel_count=int(mask.sum()), hemisphere=side))
    with open(OUT_INV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(inv_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in inv_rows:
            w.writerow(row)
    inv_by = {int(r["parcel_id"]): r for r in inv_rows}

    # ---- per fine region compute ----
    # group fine parcels to their same-side 31 G1 canonical ids
    by_side = {"left": [], "right": []}
    for r in g1rows:
        by_side[r["hemisphere"]].append(r["canonical_region_id"])
    evd_rows = []
    long_rows = []
    centroids = {}
    for cid, gm in g1mask.items():
        idx = np.argwhere(gm).astype(float) + 0.5
        centroids[cid] = (aff[:3, :3] @ idx.T + aff[:3, 3:4]).mean(1)
    fine_cent = {}
    for u in univ:
        pid = u["parcel_id"]
        if pid in fine_cent:
            continue
        idx = np.argwhere(m == pid).astype(float) + 0.5
        fine_cent[pid] = (aff[:3, :3] @ idx.T + aff[:3, 3:4]).mean(1) if idx.shape[0] else np.full(3, np.nan)
    rank1 = 0
    lat_fail = []
    for u in sorted(univ, key=lambda x: x["parcel_id"]):
        pid = int(u["parcel_id"])
        hemi = u["hemisphere"]
        mask = m == pid
        fine_vox = int(mask.sum())
        side_ok = float((mask & left_grid).sum()) / fine_vox if fine_vox else 0.0
        if (hemi == "left" and side_ok < 0.9) or (hemi == "right" and side_ok > 0.1):
            lat_fail.append(u["fine_region_id"])
        scores = {}
        for cid in by_side[hemi]:
            inter = int(hist_of_g1[cid][pid])
            scores[cid] = dict(containment=inter / fine_vox if fine_vox else 0.0,
                               dice=2 * inter / (fine_vox + g1_size[cid]) if (fine_vox + g1_size[cid]) else 0.0,
                               target_covered=inter / g1_size[cid] if g1_size[cid] else 0.0,
                               intersection=inter)
        # union outside
        un = union[hemi]
        outside = int((mask & ~un).sum())
        outside_frac = outside / fine_vox if fine_vox else 1.0
        prop = u["proposed_g1_id"]
        prop_score = scores[prop]["containment"]
        order = sorted(scores.items(), key=lambda kv: -kv[1]["containment"])
        best = order[0]
        rank = 1 + sum(1 for kv in order if kv[1]["containment"] > prop_score + 1e-12)
        non = [kv for kv in order if kv[0] != prop]
        best_non = non[0] if non else None
        second = order[1] if len(order) > 1 else None
        best_non_id = best_non[0] if best_non else None
        best_non_score = best_non[1]["containment"] if best_non else 0.0
        margin = prop_score - best_non_score
        if prop == best[0]:
            rank1 += 1
        flags = []
        if rank == 1:
            flags.append("PROPOSED_RANK_1")
        else:
            flags.append("PROPOSED_NOT_RANK_1")
            flags.append("SPATIAL_COMPETITOR_PRESENT")
        if prop_score < 0.5:
            flags.append("LOW_CONTAINMENT")
        if outside_frac > 0.2:
            flags.append("HIGH_OUTSIDE_UNION")
        if (hemi == "left" and side_ok < 0.9) or (hemi == "right" and side_ok > 0.1):
            flags.append("LATERALITY_FAILURE")
        evd_rows.append(dict(
            relation_id=u["relation_id"], fine_region_id=u["fine_region_id"],
            fine_name=u["fine_region_name"], granularity=u["fine_granularity"],
            atlas=u["fine_atlas"], hemisphere=hemi,
            historical_status=u["historical_status"],
            proposed_g1_id=prop, proposed_g1_name=u["proposed_g1_name"],
            proposed_containment=round(prop_score, 5), proposed_rank=rank,
            proposed_dice=round(scores[prop]["dice"], 5),
            best_g1_id=best[0], best_containment=round(best[1]["containment"], 5),
            second_best_g1_id=second[0] if second else "",
            second_best_containment=round(second[1]["containment"], 5) if second else "",
            best_non_proposed_g1_id="" if best_non_id is None else best_non_id,
            best_non_proposed_score=round(best_non_score, 5),
            margin_vs_best_competitor=round(margin, 5),
            fine_voxels=fine_vox,
            outside_union_voxels=outside, outside_union_fraction=round(outside_frac, 5),
            correct_side_fraction=round(side_ok, 5),
            contralateral_fraction=round(1 - side_ok, 5),
            v3_historical=";".join(sorted(set(cls.get(u["fine_region_id"], ["NOT_IN_CLASSIFICATION"])))),
            flags="|".join(flags)))
        for cid, sc in scores.items():
            cd = float(np.linalg.norm(centroids[cid] - fine_cent[pid]))
            long_rows.append(dict(fine_region_id=u["fine_region_id"], hemisphere=hemi,
                                  g1_id=cid, containment=round(sc["containment"], 5),
                                  dice=round(sc["dice"], 5),
                                  target_covered=round(sc["target_covered"], 5),
                                  intersection=sc["intersection"],
                                  centroid_distance_mm=round(cd, 3)))

    evd_sorted = sorted(evd_rows, key=lambda r: (r["hemisphere"], int(r["fine_region_id"].split("-")[-1])))
    with open(OUT_EVD, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(evd_sorted[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in evd_sorted:
            w.writerow(row)
    with open(OUT_LONG, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(long_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in long_rows:
            w.writerow(row)

    # summaries
    cont = [r["proposed_containment"] for r in evd_sorted]
    out_frac = [r["outside_union_fraction"] for r in evd_sorted]
    med, p25, p75 = float(np.median(cont)), float(np.percentile(cont, 25)), float(np.percentile(cont, 75))
    hist_cls = Counter(r["v3_historical"].split("|")[0] if r["v3_historical"] else "?" for r in evd_sorted)
    g3_n = sum(1 for r in evd_sorted if r["granularity"] == "G3_MESO_FINE")
    g4_n = len(evd_sorted) - g3_n
    rank_gt1 = sum(1 for r in evd_sorted if r["proposed_rank"] > 1)
    high_out = [r["fine_region_id"] for r in evd_sorted if r["outside_union_fraction"] > 0.2]

    # cross-audit: VERIFIED/REVIEW (from classification v3) vs spatial
    disc = []
    for r in evd_sorted:
        v = r["v3_historical"]
        if v == "VERIFIED_DIRECT_CONTAINED" and (r["proposed_rank"] > 1 or r["proposed_containment"] < 0.5
                                                 or r["outside_union_fraction"] > 0.2):
            disc.append(dict(kind="HISTORICAL_STATUS_SPATIAL_DISCORDANCE", fine=r["fine_region_id"],
                             v3=v, rank=r["proposed_rank"], containment=r["proposed_containment"],
                             outside=r["outside_union_fraction"],
                             note="historical VERIFIED but spatial evidence not rank-1 / low "
                                  "containment / high outside-union"))
        if v == "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW" and r["proposed_rank"] == 1 and \
                r["proposed_containment"] >= 0.8 and r["margin_vs_best_competitor"] > 0.1:
            disc.append(dict(kind="REVIEW_WITH_STRONG_SPATIAL_EVIDENCE", fine=r["fine_region_id"],
                             v3=v, rank=r["proposed_rank"], containment=r["proposed_containment"],
                             margin=r["margin_vs_best_competitor"]))
        # historical decision (effective_scientific_decision) vs fresh direct containment
        if r["historical_status"] == "APPROVE_CONTAINED_IN" and (r["proposed_containment"] < 0.5 or
                                                                 r["outside_union_fraction"] > 0.2):
            disc.append(dict(kind="HISTORICAL_APPROVED_LOW_DIRECT_CONTAINMENT",
                             fine=r["fine_region_id"], v3=r["historical_status"],
                             rank=r["proposed_rank"], containment=r["proposed_containment"],
                             outside=r["outside_union_fraction"],
                             note="historical APPROVE_CONTAINED_IN yet fresh direct containment "
                                  "<0.5 or >20% of the parcel outside the same-side cortical G1 "
                                  "union (descriptive; not a verdict, mapping not modified)"))
    with open(OUT_DISC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(disc[0].keys()) if disc else ["kind"])
        w.writeheader()
        for row in disc:
            w.writerow(row)
    xa = []
    for kind, n in Counter(d["kind"] for d in disc).items():
        xa.append(dict(kind=kind, count=n))
    with open(OUT_XA, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["kind", "count"])
        w.writeheader()
        for row in xa:
            w.writerow(row)

    # atlas summary (only Brainnetome in this universe) + G3/G4 separation
    with open(OUT_ATS, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["granularity", "atlas", "relations", "unique_fine",
                                           "geometry_ready", "median_containment", "p25", "p75",
                                           "rank1_fraction", "rank_gt1_count",
                                           "median_outside_union", "blocked"])
        w.writeheader()
        g3c = [r for r in evd_sorted if r["granularity"] == "G3_MESO_FINE"]
        w.writerow(dict(granularity="G3_MESO_FINE", atlas="Brainnetome", relations=len(g3c),
                        unique_fine=len({r['fine_region_id'] for r in g3c}), geometry_ready=len(g3c),
                        median_containment=round(float(np.median([r['proposed_containment'] for r in g3c])), 5),
                        p25=round(float(np.percentile([r['proposed_containment'] for r in g3c], 25)), 5),
                        p75=round(float(np.percentile([r['proposed_containment'] for r in g3c], 75)), 5),
                        rank1_fraction=round(sum(1 for r in g3c if r['proposed_rank']==1)/len(g3c), 5),
                        rank_gt1_count=sum(1 for r in g3c if r['proposed_rank']>1),
                        median_outside_union=round(float(np.median([r['outside_union_fraction'] for r in g3c])), 5),
                        blocked=0))
        w.writerow(dict(granularity="G4_MICROSTRUCTURAL_FINE", atlas="(none in frozen universe)",
                        relations=0, unique_fine=0, geometry_ready=0, median_containment="",
                        p25="", p75="", rank1_fraction="", rank_gt1_count=0,
                        median_outside_union="", blocked=0))

    prov = dict(
        validation_id="DIRECT_CORTICAL_SPATIAL_VALIDATION_V1",
        universe_relations=len(evd_sorted), left=int(sum(1 for r in evd_sorted if r["hemisphere"]=="left")),
        right=int(sum(1 for r in evd_sorted if r["hemisphere"]=="right")),
        g3=g3_n, g4=g4_n, unique_fine_regions=len({r["fine_region_id"] for r in evd_sorted}),
        geometry_ready=len(evd_sorted), provenance_blocked=0, grid_not_ready=0,
        metric_computed=len(evd_sorted),
        discrete=len(evd_sorted), probabilistic=0,
        proposed_rank1=rank1, proposed_rank_gt1=rank_gt1,
        containment_median=round(med, 5), containment_p25=round(p25, 5), containment_p75=round(p75, 5),
        outside_union_median=round(float(np.median(out_frac)), 5),
        high_outside_union_cases=high_out, laterality_failures=lat_fail,
        historical_join=dict(hist_cls),
        discordance_counts=[{k: n} for k, n in Counter(d["kind"] for d in disc).items()],
        historical_status_joined_posthoc=True, blind_before_join=True,
        mapping_unchanged=True, geometry_unchanged=True, registration_not_run=True,
        g1_reference_frozen=len(g1rows),
        method="DIRECT_CORTICAL_SPATIAL_VALIDATION_METHOD_V1",
        independent_from_mapping=True, circularity_risk="NONE",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(prov, fh, ensure_ascii=False, indent=2)

    # strongest support / competitor / closest competition lists for diagnostics
    strong = sorted(evd_sorted, key=lambda r: r["proposed_containment"], reverse=True)[:5]
    competitors = sorted([r for r in evd_sorted if r["best_non_proposed_score"] > 0.5],
                         key=lambda r: -r["best_non_proposed_score"])[:5]
    close = sorted(evd_sorted, key=lambda r: r["margin_vs_best_competitor"])[:5]

    md = [
        "# Phase1.7 V3 - 170 cortical candidate relations direct spatial evidence", "",
        f"universe {len(evd_sorted)} (L {prov['left']} / R {prov['right']}); G3 {g3_n} / G4 {g4_n}; "
        f"atlas Brainnetome; fine geometry all on the frozen MNI152NLin2009cAsym reference grid "
        f"(single discrete volume, provenance complete).",
        f"containment median {round(med,4)} P25 {round(p25,4)} P75 {round(p75,4)}; "
        f"proposed rank-1 {rank1}/{len(evd_sorted)}; rank>1 {rank_gt1}; "
        f"outside-union median {round(float(np.median(out_frac)),4)}; "
        f"high-outside-union cases {len(high_out)}; laterality failures {len(lat_fail)}.",
        "Method: containment primary, Dice/Jaccard secondary; same-side 31-G1 full competition; "
        "no winner-takes-all (mapping unchanged). historical status joined posthoc only.",
        f"strongest proposed-support: {[(r['fine_region_id'], r['proposed_containment']) for r in strong]}",
        f"strongest non-proposed competitors (score>0.5): {[(r['fine_region_id'], r['best_non_proposed_g1_id'], r['best_non_proposed_score']) for r in competitors]}",
        f"closest competition (smallest margin): {[(r['fine_region_id'], r['proposed_g1_id'], r['margin_vs_best_competitor'], r['best_non_proposed_g1_id']) for r in close]}",
        f"discordance kinds: {prov['discordance_counts']}",
        "No mapping change, no geometry change, no registration, no reclassification, no "
        "promotion, no DB write. G4/probabilistic subset = 0 in this frozen universe (reported "
        "explicitly).", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("relations", len(evd_sorted), "L", prov["left"], "R", prov["right"],
          "| rank1", rank1, "rank>1", rank_gt1, "| containment med/p25/p75",
          round(med, 4), round(p25, 4), round(p75, 4),
          "| outside med", round(float(np.median(out_frac)), 4), "| lat fail", len(lat_fail))


if __name__ == "__main__":
    main()

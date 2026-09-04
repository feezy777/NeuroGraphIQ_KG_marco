"""Phase1.7 V3 - Direct G1 Geometry feasibility & asset inventory (READ-ONLY).

Inventories existing geometry assets (no downloads / no new geometry) and maps
the 93 LIKELY rows to a direct-validation feasibility class.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
OUT1 = D16 / "phase17_v3_direct_g1_geometry_inventory.csv"
OUT2 = D16 / "phase17_v3_direct_g1_geometry_summary.json"
OUT3 = D16 / "phase17_v3_direct_g1_geometry_diagnostics.md"
OUT4 = D16 / "phase17_v3_historical_surface_pipeline_audit.md"
OUT5 = D16 / "phase17_v3_direct_geometry_feasibility_93.csv"
ATL = BACKEND / "data" / "atlases"

# family -> (geometry_class, type, space, path, notes)
FAM = {
    # Desikan-Killiany native surface (fsaverage) cortical gyri
    "Insula": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
               str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Inferior Parietal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                          str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Superior Parietal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                          str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Superior Temporal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                          str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Middle Temporal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                        str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Temporal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                 str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany (STG/MTG etc)"),
    "Fusiform": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                 str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Precentral": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                   str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Postcentral": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                    str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Superior Frontal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                         str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Middle Frontal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                       str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Inferior Frontal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                         str(ATL / "freesurfer" / "fsaverage"),
                         "Desikan pars（无整 IFG 单一 label；pars 为独立 DK 子区）"),
    "Orbitofrontal": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                      str(ATL / "freesurfer" / "fsaverage"), "Desikan med/lat OFC"),
    "Occipital": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                  str(ATL / "freesurfer" / "fsaverage"), "Desikan LOC/Cuneus/Lingual"),
    "Cuneus": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
               str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Precuneus": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                  str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Lingual": ("AUTHORITATIVE_NATIVE_G1_GEOMETRY", "surface label", "fsaverage(FS)",
                str(ATL / "freesurfer" / "fsaverage"), "Desikan-Killiany DK label"),
    "Amygdala": ("NO_GEOMETRY", "n/a", "n/a", "", "aseg volume 不在仓库（仅 Macro96 清单）；需 FS aseg 或外部 volume"),
    "Accumbens": ("NO_GEOMETRY", "n/a", "n/a", "", "aseg volume 不在仓库；BN volume 为 G3 代理（circular 风险）"),
    "Hippocampus": ("NO_GEOMETRY", "n/a", "n/a", "",
                    "aseg volume 不在仓库；BN Hippo volume 为 G3（经 G3→G1 聚合即 circular）"),
    "Thalamus": ("NO_GEOMETRY", "n/a", "n/a", "",
                 "aseg volume 不在仓库；BN Thalamus volume 为 G3（聚合即 circular）"),
    "Basal Forebrain": ("NO_GEOMETRY", "n/a", "n/a", "",
                        "Desikan/aseg/Brainnetome 均无 Basal Forebrain surrogate —— MISSING_REQUIRED_ASSET"),
    "other": ("NO_GEOMETRY", "n/a", "n/a", "", "无法定位家族 → NO_GEOMETRY"),
}


def family_of(name):
    for k in FAM:
        if k == "other":
            continue
        if k in name:
            return k
    return "other"


def main():
    cls = list(csv.DictReader(open(D16 / "phase17_v3_classification.csv", encoding="utf-8-sig")))
    lk = [r for r in cls if r["v3_classification"] == "LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"]
    assert len(lk) == 93
    # inventory rows (dedupe by family, hemisphere merged)
    seen = {}
    inv = []
    for fam, (geom, typ, space, path, note) in sorted(FAM.items()):
        fam_rows = [r for r in lk if family_of(r["candidate_g1_name_en"]) == fam]
        ids = [r["source_entity_id"] for r in fam_rows]
        if geom.startswith("AUTHORITATIVE"):
            compat = "REGISTRATION_REQUIRED"  # fsaverage surface vs Julich MNI volume
        else:
            compat = "INCOMPATIBLE_OR_UNKNOWN"
        inv.append(dict(
            g1_family=fam, g1_name_example=(fam_rows[0]["candidate_g1_name_en"] if fam_rows else ""),
            hemisphere="left/right",
            geometry_available="YES" if geom.startswith("AUTHORITATIVE") else "NO",
            geometry_type=typ, geometry_path=path,
            atlas_name="FreeSurfer Desikan-Killiany" if geom.startswith("AUTHORITATIVE") else "n/a",
            atlas_version="fsaverage (FS 5.3 atlas convention)", coordinate_space=space,
            resolution="surface vertex", surface_or_volume="surface",
            probabilistic_or_discrete="discrete",
            construction_method="atlas-native parcellation",
            geometry_class=geom, is_native_source_geometry="TRUE" if geom.startswith("AUTHORITATIVE_NATIVE") else "FALSE",
            is_derived_geometry="TRUE" if geom == "AUTHORITATIVE_DERIVED_G1_GEOMETRY" else "FALSE",
            derivation_source="", derivation_provenance="",
            depends_on_g3_g1_mapping="FALSE" if geom.startswith("AUTHORITATIVE") else "n/a",
            circularity_risk="LOW" if geom.startswith("AUTHORITATIVE") else ("HIGH" if geom == "PROJECT_DERIVED_G1_GEOMETRY" else "n/a"),
            compatible_with_julich_geometry="NO (surface vs volume)",
            registration_required="YES", resampling_required="YES",
            direct_comparison_feasible="NO_until_bridge" if geom.startswith("AUTHORITATIVE") else "NO",
            scientific_risk=note, notes=f"covered candidates in 93: {len(ids)}"))
    with open(OUT1, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(inv[0].keys()))
        w.writeheader()
        for r in inv:
            w.writerow(r)
    # feasibility rows for 93
    rows93 = []
    for r in lk:
        fam = family_of(r["candidate_g1_name_en"])
        geom = FAM[fam][0]
        if geom.startswith("AUTHORITATIVE"):
            feas, reason, next_act = "REGISTRATION_REQUIRED", \
                "有 DK surface 但 Julich 为 volume（2009c），需 surface/volume 桥接", "构建 surface↔volume 桥后直接验证"
        else:
            feas, reason, next_act = "NO_GEOMETRY", FAM[fam][4], "获取 aseg/权威 volume 或外部资产"
        rows93.append(dict(source_id=r["source_entity_id"], source_name=r["source_name_en"],
                           candidate_g1=r["candidate_g1_name_en"],
                           candidate_g1_geometry_class=geom,
                           feasibility_bucket=feas,
                           geometry_available="YES" if geom.startswith("AUTHORITATIVE") else "NO",
                           geometry_path=FAM[fam][3],
                           space_compatibility="REGISTRATION_REQUIRED",
                           direct_validation_feasible=("YES" if feas == "DIRECT_READY" else "NO"),
                           blocking_reason=reason, recommended_next_action=next_act))
    with open(OUT5, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows93[0].keys()))
        w.writeheader()
        for r in rows93:
            w.writerow(r)
    feas_cnt = Counter(r["feasibility_bucket"] for r in rows93)
    gcls = Counter(r["candidate_g1_geometry_class"] for r in rows93)
    import json
    summary = dict(inventory_families=len(inv), feasibility_93=dict(feas_cnt),
                   geometry_class_93=dict(gcls),
                   note=("cortical G1: DK fsaverage surface 存在(权威原生)，但 Julich volume ↔ surface 需桥接 → "
                         "REGISTRATION_REQUIRED；subcortical(Thal/Hipp/Amyg/NAcc)与 Basal Forebrain: "
                         "aseg/BF volume 缺失 → NO_GEOMETRY"))
    with open(OUT2, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    # diagnostics + historical pipeline audit md
    md = ["# Direct G1 Geometry 可行性 & 资产清单", "",
          "families inventoried=" + str(len(inv)),
          "93 feasibility=" + str(dict(feas_cnt)),
          "geometry class(93)=" + str(dict(gcls)),
          "DIRECT_G1_GEOMETRY (volume, common space with Julich): 未找到；"
          "仅 Desikan-Killiany fsaverage surface（cortical G1）+ Macro96 清单。"]
    with open(OUT3, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md))
    hist = """# 历史 STG / LOcC direct-looking surface overlap pipeline 审计

## 数据来源
- 文件: backend/data/integration/g3_surface_dk_audits/g3_to_dk_surface_overlap_full.csv
  (同时存在于 data/integration/1/g3_to_dk_surface_overlap_full.csv 与
   data/integration/1/single_seed_surface_overlap_validation.csv 等历史副本)
- 列: hemisphere, g3_entity_id, official_code, official_modified_name, seed_mask_code,
  seed_type, g3_vertex_count, dk_label_name/id, dk_vertex_count, intersection_vertex_count,
  source_coverage_ratio, target_coverage_ratio, g1_entity_id, g1_name_en, g1_alignment_status

## source geometry
- Brainnetome (BNA246) 官方 parcel 表面 seed mask (FreeSurfer 表面, fsaverage)

## G1 geometry
- FreeSurfer Desikan-Killiany 表面 label (fsaverage)，作为 cortical G1 宏脑回几何

## 坐标/representation
- 同一 fsaverage 表面；vertex-based overlap；无需 transform/registration（同表面空间）

## 指标
- intersection_vertex_count；source_coverage_ratio (=intersection/g3_vertex_count)，
  target_coverage_ratio (=intersection/dk_vertex_count)

## 是否真正 direct source→G1
- 对 G3→G1：是 —— BN parcel surface 与 DK(G1 gyri) surface 直接同表面比较，
  未经过 G3→G1 mapping 表（DK 即 G1 概念的几何源）。
- 对 G4→G1：否 —— 历史 pipeline 不包含 Julich volume；STG/LOcC 数值是 G3(BN)→DK 结果。

## 是否依赖 Brainnetome G3→G1 mapping / 循环论证
- 否。DK label 为独立权威 G1 几何；overlap 全在表面完成，未用 aggregation 表。
  但当前 canonical G1 集合(Macro96)是否与所用 DK 子标签逐一对齐需要另行核对。

## 数值语义示例 (来自文件 official codes)
- STG_6_1 (seed STG, composite): 与 DK STG label 的 source_coverage 等指标见原文件；
- LOcC_2_x: 原文件中 g1_name_en 命中的 DK label 决定其 G1 alignment。

## 结论
- DIRECT_GEOMETRY_PIPELINE_REUSABLE? 部分可复用（仅针对 G3↔DK 表面；不是 G4 volume↔G1）。
- 对 G4→G1 direct validation 不适用 —— 需另建 Julich(volume,MNI2009c) ↔ G1 geometry 的直接比较。
"""
    with open(OUT4, "w", encoding="utf-8") as fh:
        fh.write(hist)
    print("inventory families", len(inv))
    print("feasibility93", dict(feas_cnt), "class93", dict(gcls))


if __name__ == "__main__":
    main()

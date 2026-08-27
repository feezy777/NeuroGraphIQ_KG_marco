"""Macro Final Connection Evidence Enrichment V1 — 核心逻辑(纯函数,只读分析)。

针对 Final 层(final_canonical_connections,2485 active)的证据质量增强分析:

* evidence coverage audit —— 缺失统计(evidence_summary / evidence_count /
  provenance_json / evidence_reference / confidence)+ confidence 分布桶。
* quality score 重算 —— 五因素(evidence 数量 / 来源多样性 / confidence /
  provenance 完整性 / validation 结果),与 canonical 层旧分对比。
* enriched summary 方案 —— 聚合 mirror 证据(supporting_sources /
  extraction_runs / confidence 分布 / modalities)+ 生成 summary_text。
* 增强优先级 —— A 高优先(count=1 + 低置信 + provenance 不足)/ B 中 /
  C 无需,供后续人工补充决策。

数据语义:
* final 行从 canonical 复制 evidence_summary / provenance_json;真正的
  evidence lineage 在 evidence_summary 内(supporting_records →
  mirror_connection_id / cluster_ids / llm_run_ids)。
* provenance_json 仅含 canonicalization 期 4 键(mapping_method /
  original_confidence / original_connection_ids / original_relation_types)。
* evidence_reference(外部文献/参考)在 Final 层 100% 为空 —— V1 识别为主缺口。
* 本模块零写入:不创建连接、不改 Final KG、不 promotion、不 CN2。

约定输入(脚本层加载):
* final: {id, canonical_connection_id, connection_code, source_region_name,
  target_region_name, connection_type, confidence, evidence_summary(dict),
  provenance_json(dict), evidence_reference(list), validation_run_id,
  promotion_record_id, canonical_quality(旧分 label)}
* validation_map: {canonical_id: {validation_status, failed_rules: [...]}}
* mirror_map: {mirror_connection_id: {id, llm_run_id, source_atlas,
  connection_type, directionality, modality, confidence, evidence_text}}
"""

from __future__ import annotations

from collections import Counter
from statistics import mean

# ---- 常量 ----

# Quality Score 权重(总和 1.0,文档化,可审计)
Q_WEIGHTS = {
    "evidence": 0.30,     # 证据数量
    "sources": 0.20,      # 来源多样性(distinct llm_run_id / source)
    "confidence": 0.15,   # 平均置信度
    "provenance": 0.15,   # provenance 完整性
    "validation": 0.20,   # validation 结果
}
HIGH_THRESHOLD = 0.70
MEDIUM_THRESHOLD = 0.45

# 低置信阈值(优先级分类用):mean confidence < 0.5 视为低
LOW_CONFIDENCE_THRESHOLD = 0.5
# provenance 不足阈值:A 类要求 completeness < 0.8
LOW_PROVENANCE_THRESHOLD = 0.8

# confidence 分布桶
CONFIDENCE_BUCKETS = [
    ("below_0.3", lambda v: v < 0.3),
    ("0.3_to_0.6", lambda v: 0.3 <= v <= 0.6),
    ("above_0.6", lambda v: v > 0.6),
]

# provenance 完整性:evidence_summary 内 lineage 键 + provenance_json 键
SUMMARY_PROV_KEYS = ("supporting_records", "cluster_ids", "llm_run_ids")
PROVENANCE_JSON_KEYS = ("mapping_method", "original_confidence",
                        "original_connection_ids", "original_relation_types")

EVIDENCE_TEXT_SAMPLE_LIMIT = 3    # summary_text 附带的证据文本样例条数


# ---- 1. Evidence Coverage Audit ----

def _confidence_buckets(confs: list[float]) -> dict[str, int]:
    """confidence 值列表 → 分布桶 {'below_0.3': n, '0.3_to_0.6': n, 'above_0.6': n}。"""
    return {label: sum(1 for v in confs if pred(v)) for label, pred in CONFIDENCE_BUCKETS}


def audit_final_evidence(finals: list[dict]) -> dict:
    """Final 层证据覆盖审计(纯统计,零写入)。

    每条 final 判定:
    * 无 evidence_summary:空 dict 或缺失
    * evidence_count=0 / =1(单证据是增强重点)
    * provenance_json 缺失(空 dict)
    * evidence_reference 为空列表
    * confidence 缺失(None)
    汇总输出缺失统计 + confidence 分布 + 缺失组合(多条件同时命中计数)。
    """
    empty_summary = zero_count = single_count = empty_prov = empty_ref = 0
    null_conf = 0
    confs: list[float] = []
    combo: Counter = Counter()
    for f in finals:
        es = f.get("evidence_summary") or {}
        prov = f.get("provenance_json") or {}
        ref = f.get("evidence_reference") or []
        conf = f.get("confidence")
        count = int(es.get("evidence_count") or 0) if isinstance(es, dict) else 0

        if not isinstance(es, dict) or not es:
            empty_summary += 1
        if count == 0:
            zero_count += 1
        if count == 1:
            single_count += 1
        if not isinstance(prov, dict) or not prov:
            empty_prov += 1
        if isinstance(ref, list) and len(ref) == 0:
            empty_ref += 1
        if conf is None or conf == "":
            null_conf += 1
        else:
            confs.append(float(conf))

        flags = []
        if count == 0:
            flags.append("zero_evidence")
        if not prov:
            flags.append("missing_provenance")
        if not ref:
            flags.append("missing_reference")
        if conf is None:
            flags.append("missing_confidence")
        if flags:
            combo[",".join(sorted(flags))] += 1

    return {
        "total_active": len(finals),
        "missing": {
            "no_evidence_summary": empty_summary,
            "evidence_count_zero": zero_count,
            "evidence_count_one": single_count,   # 单证据(增强重点)
            "missing_provenance": empty_prov,
            "missing_evidence_reference": empty_ref,
            "missing_confidence": null_conf,
        },
        "confidence_distribution": _confidence_buckets(confs),
        "confidence_statistics": {
            "count": len(confs),
            "mean": round(mean(confs), 4) if confs else 0,
            "min": round(min(confs), 4) if confs else None,
            "max": round(max(confs), 4) if confs else None,
        },
        "missing_combinations": dict(combo.most_common()),
    }


# ---- 2. Quality Score 重算 ----

def provenance_completeness(summary: dict, prov: dict) -> float:
    """provenance 完整性 0-1(面向"证据链丰富度",供增强优先级判定)。

    * records 元数据完整率:supporting_records 每条含 mirror_connection_id /
      llm_run_id / confidence → 0.4(缺元数据 → 0.2)
    * 来源多样性:min(distinct llm_run_ids, 3)/3 → 0.3
    * sources 分组数:min(len(sources), 2)/2 → 0.15
    * provenance_json 键覆盖率(canonicalization 期 4 键)→ 0.15

    单证据单批次 → 0.4+0.1+0.075+0.15 = 0.725(< 0.8,A 类可命中);
    双批次双来源 → 0.4+0.2+0.15+0.15 = 0.90(≥ 0.8,证据链已丰富)。
    """
    es = summary if isinstance(summary, dict) else {}
    p = prov if isinstance(prov, dict) else {}

    recs = es.get("supporting_records") or []
    if recs:
        rec_ok = 1.0 if all(
            r.get("mirror_connection_id") and r.get("llm_run_id") is not None
            and r.get("confidence") is not None
            for r in recs) else 0.5
    else:
        rec_ok = 0.0
    runs = {str(r) for r in (es.get("llm_run_ids") or []) if r}
    srcs = es.get("sources") or []
    prov_ok = sum(1 for k in PROVENANCE_JSON_KEYS if k in p) / len(PROVENANCE_JSON_KEYS)
    return round(min(1.0,
                     0.4 * rec_ok
                     + 0.3 * min(len(runs), 3) / 3.0
                     + 0.15 * min(len(srcs), 2) / 2.0
                     + 0.15 * prov_ok), 4)


def compute_final_quality_score(
    evidence_count: int,
    llm_run_ids: list[str],
    conf_mean: float | None,
    prov_complete: float,
    validation_passed: bool,
) -> tuple[str, dict]:
    """Final 层 Evidence Quality Score(分析评分,不修改任何字段)。

    因素(权重见 Q_WEIGHTS):
    - S_evidence:证据量,min(count,10)/10
    - S_sources:来源多样性,min(distinct llm_run,3)/3
    - S_confidence:mean confidence(0-1 线性)
    - S_provenance:provenance_completeness(0-1)
    - S_validation:pass→1.0 / fail→0.3 / 无记录→0.5(中性)
    score = Σ W_i × S_i;HIGH ≥ 0.70 / MEDIUM ≥ 0.45 / LOW < 0.45
    """
    s_evidence = min(evidence_count, 10) / 10.0
    runs = {r for r in llm_run_ids if r}
    s_sources = min(len(runs), 3) / 3.0
    s_confidence = float(conf_mean) if conf_mean is not None else 0.0
    s_confidence = max(0.0, min(1.0, s_confidence))
    s_prov = prov_complete
    s_val = 1.0 if validation_passed else (0.3 if validation_passed is not None else 0.5)

    score = round(
        Q_WEIGHTS["evidence"] * s_evidence
        + Q_WEIGHTS["sources"] * s_sources
        + Q_WEIGHTS["confidence"] * s_confidence
        + Q_WEIGHTS["provenance"] * s_prov
        + Q_WEIGHTS["validation"] * s_val, 4)
    label = ("high" if score >= HIGH_THRESHOLD
             else "medium" if score >= MEDIUM_THRESHOLD else "low")
    factors = {
        "score": score,
        "label": label,
        "evidence_count": evidence_count,
        "distinct_llm_run_ids": len(runs),
        "confidence_mean": conf_mean,
        "provenance_completeness": prov_complete,
        "validation_passed": validation_passed,
        "s_evidence": round(s_evidence, 4),
        "s_sources": round(s_sources, 4),
        "s_confidence": round(s_confidence, 4),
        "s_provenance": round(s_prov, 4),
        "s_validation": round(s_val, 4),
        "weights": dict(Q_WEIGHTS),
    }
    return label, factors


def recompute_quality(finals: list[dict], validation_map: dict[str, dict]) -> list[dict]:
    """全量重算:每条 final → 新 label/factors + 旧 canonical 分对比。"""
    out = []
    for f in finals:
        es = f.get("evidence_summary") or {}
        count = int(es.get("evidence_count") or 0)
        runs = es.get("llm_run_ids") or []
        conf_mean = es.get("confidence_mean")
        prov_ok = provenance_completeness(es, f.get("provenance_json") or {})
        vrec = validation_map.get(str(f.get("canonical_connection_id")))
        validated = None if not vrec else vrec.get("validation_status") == "passed"
        label, factors = compute_final_quality_score(
            count, runs, conf_mean, prov_ok, validated)
        old = f.get("canonical_quality")
        out.append({
            "connection_id": str(f.get("id") or ""),
            "canonical_connection_id": str(f.get("canonical_connection_id") or ""),
            "connection_code": f.get("connection_code"),
            "source_region_name": f.get("source_region_name"),
            "target_region_name": f.get("target_region_name"),
            "connection_type": f.get("connection_type"),
            "quality": factors,
            "previous_canonical_label": old,
            "label_change": None if old == label else f"{old}→{label}",
        })
    return out


# ---- 3. Enriched Summary 方案 ----

def build_enriched_summary(final: dict, mirror_rows: list[dict]) -> dict:
    """新 summary 格式(聚合 mirror 证据,零写入)。

    输入:
    * final: {connection_code, source_region_name, target_region_name,
      connection_type, evidence_summary(dict, 含 supporting_records)}
    * mirror_rows: 该 final 支撑的 mirror 行全量(detail 字段:
      llm_run_id / source_atlas / connection_type / directionality /
      modality / confidence / evidence_text)

    输出:
    {
      connection_id, evidence_count, supporting_sources[], extraction_runs[],
      modalities{}, connection_types{}, confidence{min,max,mean},
      summary_text, evidence_texts[](截断样例)
    }
    """
    confs = [float(m.get("confidence")) for m in mirror_rows
             if m.get("confidence") is not None and m.get("confidence") != ""]
    run_ids = sorted({str(m.get("llm_run_id") or "") for m in mirror_rows
                      if m.get("llm_run_id")})
    # 来源分组:(llm_run_id, source_atlas, source_type)
    src_counter: Counter = Counter()
    src_meta: dict[tuple, dict] = {}
    for m in mirror_rows:
        key = (str(m.get("llm_run_id") or "unknown"),
               m.get("source_atlas") or "unknown")
        src_counter[key] += 1
        src_meta.setdefault(key, {"source_type": m.get("source_type") or "llm_extraction"})
    sources = [{
        "source_id": k[0], "source_atlas": k[1],
        "source_type": src_meta[k]["source_type"], "record_count": c,
    } for k, c in src_counter.most_common()]
    mods: Counter = Counter()
    types: Counter = Counter()
    for m in mirror_rows:
        if m.get("modality"):
            mods[str(m.get("modality"))] += 1
        if m.get("connection_type"):
            types[str(m.get("connection_type"))] += 1
    conf_stats = {
        "count": len(confs),
        "min": round(min(confs), 4) if confs else None,
        "max": round(max(confs), 4) if confs else None,
        "mean": round(mean(confs), 4) if confs else None,
    }
    summary_text = build_summary_text(final, len(mirror_rows), sources, run_ids,
                                      conf_stats, dict(mods))
    return {
        "connection_id": str(final.get("id") or ""),
        "connection_code": final.get("connection_code"),
        "source_region_name": final.get("source_region_name"),
        "target_region_name": final.get("target_region_name"),
        "connection_type": final.get("connection_type"),
        "evidence_count": len(mirror_rows),
        "supporting_sources": sources,
        "extraction_runs": run_ids,
        "modalities": dict(mods),
        "connection_types": dict(types),
        "confidence": conf_stats,
        "summary_text": summary_text,
        "evidence_texts": [m.get("evidence_text", "")[:200]
                           for m in mirror_rows[:EVIDENCE_TEXT_SAMPLE_LIMIT]],
    }


def build_summary_text(final: dict, n: int, sources: list[dict],
                       run_ids: list[str], conf: dict, mods: dict) -> str:
    """自然语言摘要:来源 × 批次 × 置信度 × modality 一句话。"""
    src_short = ", ".join(f"{s['source_atlas']}({s['record_count']})" for s in sources[:3])
    if len(sources) > 3:
        src_short += f" 等 {len(sources)} 来源"
    run_txt = f"{len(run_ids)} 个 LLM 提取批次" if run_ids else "无批次信息"
    mod_txt = "/".join(sorted(mods)) if mods else "无modality信息"
    if conf.get("mean") is not None:
        conf_txt = f"置信度 {conf['min']}-{conf['max']}(均值 {conf['mean']})"
    else:
        conf_txt = "无置信度"
    return (f"{final.get('source_region_name')}→{final.get('target_region_name')}"
            f"({final.get('connection_type')}):{n} 条 mirror 证据支撑"
            f"({src_short}),来自 {run_txt},{mod_txt},{conf_txt}。")


# ---- 4. 增强优先级 ----

def classify_enrichment_priority(quality_items: list[dict]) -> dict:
    """优先级分类(A 高优先 / B 中 / C 无需)。

    A:evidence_count==1 AND confidence_mean<0.5 AND provenance<0.8
      —— 单证据 + 低置信 + 溯源不足,最需补充。
    B:evidence_count==1(未达 A)或 quality==low —— 需增强但优先级较低。
    C:其余 —— 已有足够证据支撑。
    """
    a_list, b_list, c_list = [], [], []
    for it in quality_items:
        q = it["quality"]
        entry = {
            "connection_id": it["connection_id"],
            "canonical_connection_id": it["canonical_connection_id"],
            "connection_code": it["connection_code"],
            "source_region_name": it["source_region_name"],
            "target_region_name": it["target_region_name"],
            "connection_type": it["connection_type"],
            "evidence_count": q["evidence_count"],
            "confidence_mean": q["confidence_mean"],
            "provenance_completeness": q["provenance_completeness"],
            "quality_label": q["label"],
            "quality_score": q["score"],
        }
        if (q["evidence_count"] == 1
                and (q["confidence_mean"] or 0) < LOW_CONFIDENCE_THRESHOLD
                and q["provenance_completeness"] < LOW_PROVENANCE_THRESHOLD):
            entry["priority"] = "A"
            entry["reason"] = ("单证据 + 低置信(<0.5) + provenance 不足(<0.8):"
                               "最需文献/LLM 补充")
            a_list.append(entry)
        elif q["evidence_count"] == 1 or q["label"] == "low":
            entry["priority"] = "B"
            entry["reason"] = ("单证据或 quality low:需增强,优先级次之"
                               if q["evidence_count"] == 1
                               else "quality low(多证据但一致性/置信度低)")
            b_list.append(entry)
        else:
            entry["priority"] = "C"
            entry["reason"] = "证据充足(multi-evidence, quality medium/high)"
            c_list.append(entry)

    counts = {"A": len(a_list), "B": len(b_list), "C": len(c_list),
              "total": len(quality_items)}
    return {"A": a_list, "B": b_list, "C": c_list, "counts": counts}


# ---- 5. 组合规划 ----

def plan_final_evidence_enrichment(
    finals: list[dict],
    mirror_map: dict[str, dict],
    validation_map: dict[str, dict],
) -> dict:
    """全流程规划:audit + quality 重算 + summary 方案 + 优先级分类。

    mirror_map: {mirror_connection_id: detail} —— final 的支撑行经
      evidence_summary.supporting_records[].mirror_connection_id 展开。
    """
    audit = audit_final_evidence(finals)
    quality = recompute_quality(finals, validation_map)

    summaries = []
    for f in finals:
        es = f.get("evidence_summary") or {}
        ids = [str(r.get("mirror_connection_id")) for r in (es.get("supporting_records") or [])
               if r.get("mirror_connection_id")]
        rows = [mirror_map[i] for i in ids if i in mirror_map]
        summaries.append(build_enriched_summary(f, rows))

    priority = classify_enrichment_priority(quality)

    old_labels = Counter(it.get("previous_canonical_label") for it in quality)
    new_labels = Counter(it["quality"]["label"] for it in quality)
    return {
        "audit": audit,
        "quality": {
            "total": len(quality),
            "distribution": dict(new_labels),
            "previous_canonical_distribution": dict(old_labels),
            "label_changes": dict(Counter(
                it["label_change"] for it in quality if it["label_change"])),
            "items": quality,
        },
        "summaries": summaries,
        "priority": priority,
    }

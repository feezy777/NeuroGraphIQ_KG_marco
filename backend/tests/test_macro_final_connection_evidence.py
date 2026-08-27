"""Macro Final Connection Evidence Enrichment V1 — 纯函数测试。

覆盖:evidence coverage audit(缺失统计/confidence 桶/缺失组合)、
provenance 完整性(单证据 0.725 / 双批次 0.90)、quality score 五因素重算
(边界 high/medium/low + validation 影响)、enriched summary 聚合
(supporting_sources / extraction_runs / confidence / summary_text)、
A/B/C 优先级分类(单证据+低置信+溯源不足 → A)、全流程规划一致性。
全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_final_connection_evidence_service import (
    LOW_CONFIDENCE_THRESHOLD,
    Q_WEIGHTS,
    audit_final_evidence,
    build_enriched_summary,
    build_summary_text,
    classify_enrichment_priority,
    compute_final_quality_score,
    plan_final_evidence_enrichment,
    provenance_completeness,
    recompute_quality,
)

PROV_OK = {"mapping_method": "x", "original_confidence": 0.9,
           "original_connection_ids": ["a"], "original_relation_types": ["structural"]}


def _summary(count=1, runs=None, conf_mean=0.3, records=None, sources=None):
    runs = runs or [f"run{i}" for i in range(count)]
    records = records if records is not None else [
        {"mirror_connection_id": f"m{i}", "llm_run_id": runs[i % len(runs)],
         "confidence": conf_mean} for i in range(count)]
    return {
        "evidence_count": count, "llm_run_ids": runs, "confidence_mean": conf_mean,
        "supporting_records": records, "cluster_ids": list(range(count)),
        "sources": sources or [{"source_id": r, "source_atlas": "Macro96"}
                               for r in runs],
    }


def _final(cid="f1", ccid="c1", code="ng:cn:t", summary=None, conf=0.5, prov=None,
           ref=None, quality=None):
    return {
        "id": cid, "canonical_connection_id": ccid, "connection_code": code,
        "source_region_name": "Amygdala", "target_region_name": "Hippocampus",
        "connection_type": "structural", "confidence": conf,
        "evidence_summary": summary if summary is not None else _summary(),
        "provenance_json": prov if prov is not None else PROV_OK,
        "evidence_reference": ref if ref is not None else [],
        "canonical_quality": quality,
    }


# ---- 1. coverage audit ----

def test_audit_counts_missing_and_single():
    finals = [
        _final("f1", summary={}, conf=None, prov={}),          # 无 summary + 无 conf + 无 prov
        _final("f2", summary=_summary(count=0, runs=[], conf_mean=None, records=[])),  # count=0
        _final("f3", summary=_summary(count=1)),               # 单证据
        _final("f4", summary=_summary(count=3, runs=["r1", "r2"])),  # 正常
    ]
    a = audit_final_evidence(finals)
    assert a["total_active"] == 4
    assert a["missing"]["no_evidence_summary"] == 1
    assert a["missing"]["evidence_count_zero"] == 2    # f1(空 summary 按 0 计)+ f2
    assert a["missing"]["evidence_count_one"] == 1
    assert a["missing"]["missing_provenance"] == 1
    assert a["missing"]["missing_evidence_reference"] == 4   # ref 默认空列表
    assert a["missing"]["missing_confidence"] == 1


def test_audit_confidence_buckets_and_combos():
    finals = [_final("f%d" % i, conf=c) for i, c in
              enumerate([0.2, 0.5, 0.8, None])]
    a = audit_final_evidence(finals)
    assert a["confidence_distribution"] == {"below_0.3": 1, "0.3_to_0.6": 1, "above_0.6": 1}
    assert a["confidence_statistics"]["mean"] == 0.5
    # 组合键为排序后的 flag 串;f3 同时缺 confidence + reference
    assert any("missing_confidence" in k for k in a["missing_combinations"])
    assert any("missing_reference" in k for k in a["missing_combinations"])


# ---- 2. provenance 完整性 ----

def test_provenance_completeness_single_evidence():
    assert provenance_completeness(_summary(count=1, runs=["r1"]), PROV_OK) == 0.725


def test_provenance_completeness_multi_run_rich():
    s = _summary(count=3, runs=["r1", "r2", "r3"], sources=[
        {"source_id": "r1", "source_atlas": "Macro96"},
        {"source_id": "r2", "source_atlas": "Macro96"}])
    assert provenance_completeness(s, PROV_OK) == 1.0


def test_provenance_completeness_no_records_and_bad_prov():
    assert provenance_completeness({}, {}) == 0.0
    s = _summary(count=1, runs=["r1"], records=[{"mirror_connection_id": "m1"}])
    # 元数据缺 llm_run_id/confidence → rec_ok 0.5;单批次 0.1 + 单来源 0.075 + prov 0.15
    assert provenance_completeness(s, PROV_OK) == 0.525


# ---- 3. quality score ----

def test_quality_score_boundaries():
    # high:count=5 + 3 runs + conf 0.8 + prov 1.0 + pass
    label, f = compute_final_quality_score(5, ["r1", "r2", "r3"], 0.8, 1.0, True)
    assert label == "high" and f["score"] >= 0.70
    # medium:count=3 + 2 runs + conf 0.5 + prov 0.9 + pass
    label, f = compute_final_quality_score(3, ["r1", "r2"], 0.5, 0.9, True)
    assert label == "medium" and 0.45 <= f["score"] < 0.70
    # low:count=1 + 1 run + conf 0.1 + prov 0.725 + pass
    label, f = compute_final_quality_score(1, ["r1"], 0.1, 0.725, True)
    assert label == "low" and f["score"] < 0.45


def test_quality_score_validation_impact():
    _, f_ok = compute_final_quality_score(3, ["r1", "r2"], 0.5, 0.9, True)
    _, f_fail = compute_final_quality_score(3, ["r1", "r2"], 0.5, 0.9, False)
    assert f_fail["score"] < f_ok["score"]
    assert f_fail["s_validation"] == 0.3 and f_ok["s_validation"] == 1.0
    assert sum(Q_WEIGHTS.values()) == 1.0


def test_recompute_quality_with_validation_map():
    finals = [
        _final("f1", ccid="c1", summary=_summary(count=3, runs=["r1", "r2"], conf_mean=0.6),
               quality="medium"),
        _final("f2", ccid="c2", summary=_summary(count=1, runs=["r1"], conf_mean=0.15),
               quality="low"),
    ]
    val = {"c1": {"validation_status": "passed", "failed_rules": []},
           "c2": {"validation_status": "failed", "failed_rules": [{"rule_code": "x"}]}}
    items = recompute_quality(finals, val)
    assert items[0]["previous_canonical_label"] == "medium"
    assert items[1]["quality"]["validation_passed"] is False
    assert items[1]["quality"]["label"] == "low"


# ---- 4. enriched summary ----

def _mirror(i, run="run1", conf=0.3, modality="structural"):
    return {"id": f"m{i}", "llm_run_id": run, "source_atlas": "Macro96",
            "source_type": "llm_extraction", "connection_type": "structural_connection",
            "directionality": "directed", "modality": modality,
            "confidence": conf, "evidence_text": f"evidence text {i}"}


def test_build_enriched_summary_aggregation():
    f = _final("f1", summary=_summary(count=2, runs=["r1", "r2"], conf_mean=0.45))
    rows = [_mirror(1, "r1", 0.3, "structural"), _mirror(2, "r2", 0.6, "functional")]
    s = build_enriched_summary(f, rows)
    assert s["evidence_count"] == 2
    assert len(s["supporting_sources"]) == 2
    assert s["supporting_sources"][0]["source_atlas"] == "Macro96"
    assert s["extraction_runs"] == ["r1", "r2"]
    assert s["confidence"] == {"count": 2, "min": 0.3, "max": 0.6, "mean": 0.45}
    assert s["modalities"] == {"structural": 1, "functional": 1}
    assert "Amygdala→Hippocampus" in s["summary_text"]
    assert "2 条 mirror 证据" in s["summary_text"]
    assert s["evidence_texts"][0].startswith("evidence text")


def test_build_summary_text_empty_cases():
    txt = build_summary_text({"source_region_name": "A", "target_region_name": "B",
                              "connection_type": "structural"}, 0, [], [], {},
                              {})
    assert "0 条 mirror 证据" in txt and "无置信度" in txt


# ---- 5. 优先级分类 ----

def _quality_item(cid, count=1, conf=0.15, prov=0.725, label="low"):
    return {
        "connection_id": cid, "canonical_connection_id": "c" + cid,
        "connection_code": "ng:cn:" + cid, "source_region_name": "A",
        "target_region_name": "B", "connection_type": "structural",
        "quality": {"evidence_count": count, "confidence_mean": conf,
                    "provenance_completeness": prov, "label": label, "score": 0.3},
    }


def test_priority_A_condition_met():
    items = [_quality_item("a1", count=1, conf=0.15, prov=0.725)]  # A 全命中
    p = classify_enrichment_priority(items)
    assert p["counts"] == {"A": 1, "B": 0, "C": 0, "total": 1}
    assert p["A"][0]["priority"] == "A"


def test_priority_A_requires_all_three():
    # 高置信单证据 → B;多证据低置信 → B(非 low 才 C)
    items = [
        _quality_item("a1", count=1, conf=0.8, prov=0.725),   # conf 高 → B
        _quality_item("a2", count=1, conf=0.15, prov=0.95),   # prov 足 → B
        _quality_item("a3", count=3, conf=0.15, prov=0.725, label="medium"),  # C
    ]
    p = classify_enrichment_priority(items)
    assert p["counts"] == {"A": 0, "B": 2, "C": 1, "total": 3}


def test_priority_counts_consistency():
    items = [_quality_item("a%d" % i) for i in range(5)] + \
            [_quality_item("c%d" % i, count=3, conf=0.6, prov=0.9, label="medium")
             for i in range(5)]
    p = classify_enrichment_priority(items)
    assert p["counts"]["total"] == 10
    assert p["counts"]["A"] + p["counts"]["B"] + p["counts"]["C"] == 10


# ---- 6. 全流程规划 ----

def test_plan_full_flow():
    finals = [
        _final("f1", ccid="c1", summary=_summary(count=1, runs=["r1"], conf_mean=0.15),
               quality="low"),
        _final("f2", ccid="c2",
               summary=_summary(count=4, runs=["r1", "r2", "r3"], conf_mean=0.7),
               quality="high"),
    ]
    # _summary 默认 records 的 mirror_connection_id 为 m0..m3
    mirror_map = {f"m{i}": _mirror(i, ("r1" if i % 3 == 0 else "r2" if i % 3 == 1 else "r3"),
                                   0.15 if i == 0 else 0.7)
                  for i in range(4)}
    val = {"c1": {"validation_status": "passed", "failed_rules": []},
           "c2": {"validation_status": "passed", "failed_rules": []}}
    plan = plan_final_evidence_enrichment(finals, mirror_map, val)
    # audit
    assert plan["audit"]["total_active"] == 2
    assert plan["audit"]["missing"]["evidence_count_one"] == 1
    assert plan["audit"]["missing"]["missing_evidence_reference"] == 2
    # quality
    assert plan["quality"]["total"] == 2
    assert plan["quality"]["items"][0]["quality"]["label"] == "low"
    # summary:f1 单证据展开到 mirror m1
    s1 = plan["summaries"][0]
    assert s1["evidence_count"] == 1 and s1["extraction_runs"] == ["r1"]
    s2 = plan["summaries"][1]
    assert s2["evidence_count"] == 4 and len(s2["extraction_runs"]) == 3
    # priority:f1 → A;f2 → C
    assert plan["priority"]["counts"] == {"A": 1, "B": 0, "C": 1, "total": 2}
    # 一致性
    assert sum(plan["priority"]["counts"][k] for k in "ABC") == plan["quality"]["total"]

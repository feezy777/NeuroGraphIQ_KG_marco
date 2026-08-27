"""Macro Evidence Provenance Backfill V1 — 纯函数测试。

覆盖:mirror 来源字段审计(paper/DOI/PMID 结构化缺失、llm_run_id 覆盖、
extraction_runs 过滤、evidence_text 文献线索统计)、evidence_reference 生成
(已知 run → dataset/extraction_run/confidence 统计;unknown run;空置信度)、
按 llm_run_id 分组排序、lineage 展开(final→mirror ids、缺失 lineage、
map 外 id)、幂等规划(to_update 判定、evidence_count 一致性、no_lineage 计数)、
回填后一致性验证(coverage pct / 可追溯性 / 数量一致性)。
全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_evidence_provenance_backfill_service import (
    UNKNOWN_RUN,
    audit_mirror_provenance_fields,
    build_evidence_reference,
    build_evidence_references,
    lineage_refs_for_final,
    plan_provenance_backfill,
    validate_backfill_consistency,
)


def _mirror(i, run="run1", atlas="Macro96", ver="v1", conf=0.3, text="txt"):
    return {"id": f"m{i}", "llm_run_id": run, "batch_id": "b1",
            "source_atlas": atlas, "source_version": ver, "confidence": conf,
            "evidence_text": text}


def _run(rid="run1", task="same_granularity_connection_completion",
         provider="deepseek", model="deepseek-chat", pv="v1"):
    return {"id": rid, "task_type": task, "provider": provider,
            "model_name": model, "prompt_version": pv,
            "prompt_template_key": "k", "status": "completed",
            "source_atlas": "Macro96", "source_version": "v1"}


def _final(fid="f1", ccid="c1", code="ng:cn:1", ref=None, summary=None):
    return {"id": fid, "canonical_connection_id": ccid, "connection_code": code,
            "evidence_reference": ref if ref is not None else [],
            "evidence_summary": summary if summary is not None
            else {"evidence_count": 1}}


def _lineage(cid="c1", mirrors=("m1",), cluster="cl1"):
    return [{"cluster_id": cluster, "mirror_connection_ids": list(mirrors)}]


# ---- 1. mirror 来源字段审计 ----

def test_audit_reports_no_structured_citation_fields():
    mirrors = [_mirror(1, "run1"), _mirror(2, "run1"), _mirror(3, None)]
    a = audit_mirror_provenance_fields(mirrors, [_run()])
    assert a["total_mirror"] == 3
    assert a["structured_fields"]["paper"] is False
    assert a["structured_fields"]["doi"] is False
    assert a["structured_fields"]["pmid"] is False
    assert a["field_coverage"]["llm_run_id"] == "2/3"
    assert a["field_coverage"]["batch_id"] == "3/3"
    assert a["distinct"]["llm_run_ids"] == 1
    assert a["distinct"]["batch_ids"] == 1


def test_audit_filters_runs_and_counts_citations():
    mirrors = [_mirror(1, "run1", text="according to Zhang et al (2020)..."),
               _mirror(2, "run2", text="plain text")]
    runs = [_run("run1"), _run("run2"), _run("run3")]  # run3 不被引用 → 过滤
    a = audit_mirror_provenance_fields(mirrors, runs)
    assert [r["llm_run_id"] for r in a["extraction_runs"]] == ["run1", "run2"]
    assert a["citation_clues_in_evidence_text"]["et_al_mentions"] == 1
    assert a["citation_clues_in_evidence_text"]["doi_or_pmid"] == 0


# ---- 2. evidence_reference 生成 ----

def test_build_evidence_reference_known_run():
    ref = build_evidence_reference("run1", _run(), "Macro96", "v1",
                                   [0.2, 0.4, 0.6], ["m1", "m2"])
    assert ref["source_type"] == "llm_extraction"
    assert ref["source_id"] == "run1"
    assert ref["paper"] == ""
    assert ref["dataset"] == "Macro96 v1"
    assert "same_granularity_connection_completion" in ref["extraction_run"]
    assert ref["confidence"] == "0.4"
    assert ref["confidence_min"] == 0.2 and ref["confidence_max"] == 0.6
    assert ref["confidence_count"] == 3
    assert ref["mirror_connection_ids"] == ["m1", "m2"]


def test_build_evidence_reference_unknown_run():
    ref = build_evidence_reference(UNKNOWN_RUN, None, "Macro96", "v1", [0.3], ["m1"])
    assert ref["source_type"] == "unknown"
    assert ref["extraction_run"] == ""
    assert ref["confidence"] == ""


def test_build_evidence_reference_empty_confs():
    ref = build_evidence_reference("run1", _run(), "Macro96", "v1", [], ["m1"])
    assert ref["confidence"] == ""
    assert ref["confidence_count"] == 0
    assert ref["confidence_min"] is None


def test_build_evidence_references_groups_by_run():
    mirrors = [_mirror(1, "r1", conf=0.2), _mirror(2, "r1", conf=0.4),
               _mirror(3, "r2", conf=0.8), _mirror(4, None)]
    run_map = {"r1": _run("r1"), "r2": _run("r2")}
    refs = build_evidence_references(mirrors, run_map)
    assert len(refs) == 3
    # 排序:known runs 在前(按 source_id),unknown 最后
    assert [r["source_type"] for r in refs] == ["llm_extraction", "llm_extraction", "unknown"]
    r1 = refs[0]
    assert r1["source_id"] == "r1"
    assert r1["confidence"] == "0.3" and r1["mirror_connection_ids"] == ["m1", "m2"]
    assert refs[-1]["source_type"] == "unknown"


# ---- 3. lineage 展开 ----

def test_lineage_refs_for_final_traces_mirrors():
    f = _final("f1", "c1")
    lr = _lineage("c1", ["m1", "m2", "m3"])
    mirror_map = {"m1": _mirror(1, "r1"), "m2": _mirror(2, "r1"),
                  "m3": _mirror(3, "r2")}
    info = lineage_refs_for_final(f, lr, mirror_map, {"r1": _run("r1"), "r2": _run("r2")})
    assert info["traced_mirror_ids"] == ["m1", "m2", "m3"]
    assert info["missing"]["no_lineage"] is False
    assert info["missing"]["lineage_mirror_ids_missing_in_map"] == []
    assert len(info["references"]) == 2  # r1 + r2


def test_lineage_refs_for_final_no_lineage():
    f = _final("f1", "c1")
    info = lineage_refs_for_final(f, [], {}, {})
    assert info["traced_mirror_ids"] == []
    assert info["references"] == []
    assert info["missing"]["no_lineage"] is True


def test_lineage_refs_for_final_mirror_missing_in_map():
    f = _final("f1", "c1")
    lr = _lineage("c1", ["m1", "mX"])  # mX 不在 mirror_map
    info = lineage_refs_for_final(f, lr, {"m1": _mirror(1, "r1")},
                                  {"r1": _run("r1")})
    assert info["traced_mirror_ids"] == ["m1"]
    assert info["missing"]["lineage_mirror_ids_missing_in_map"] == ["mX"]


# ---- 4. 幂等规划 ----

def test_plan_marks_update_and_counts():
    finals = [_final("f1", "c1", summary={"evidence_count": 2}),
              _final("f2", "c2", summary={"evidence_count": 1})]
    lineage_map = {"c1": _lineage("c1", ["m1", "m2"]),
                   "c2": _lineage("c2", ["m3"])}
    mirror_map = {"m1": _mirror(1, "r1"), "m2": _mirror(2, "r1"),
                  "m3": _mirror(3, "r2")}
    run_map = {"r1": _run("r1"), "r2": _run("r2")}
    plan = plan_provenance_backfill(finals, lineage_map, mirror_map, run_map)
    assert plan["counts"]["total"] == 2
    assert plan["counts"]["to_update"] == 2
    assert plan["counts"]["no_lineage"] == 0
    assert plan["counts"]["count_mismatch"] == 0
    i0 = plan["items"][0]
    assert i0["will_update"] is True
    assert i0["evidence_count_traced"] == 2
    assert i0["evidence_count_summary"] == 2
    assert i0["count_consistent"] is True
    assert len(i0["references"]) == 1  # 同 run 合并


def test_plan_idempotent_when_reference_already_set():
    # 用生成器构造现值(与目标完全一致)→ 应判 unchanged
    ref = build_evidence_reference("r1", _run("r1"), "Macro96", "v1", [0.3], ["m1"])
    finals = [_final("f1", "c1", ref=[ref], summary={"evidence_count": 1})]
    lineage_map = {"c1": _lineage("c1", ["m1"])}
    mirror_map = {"m1": _mirror(1, "r1")}
    plan = plan_provenance_backfill(finals, lineage_map, mirror_map, {"r1": _run("r1")})
    assert plan["counts"]["to_update"] == 0
    assert plan["counts"]["unchanged"] == 1
    assert plan["items"][0]["will_update"] is False


def test_plan_counts_no_lineage_and_mismatch():
    finals = [_final("f1", "c1", summary={"evidence_count": 3}),   # no lineage
              _final("f2", "c2", summary={"evidence_count": 5})]   # traced 2 ≠ 5
    lineage_map = {"c2": _lineage("c2", ["m1", "m2"])}
    mirror_map = {"m1": _mirror(1, "r1"), "m2": _mirror(2, "r1")}
    plan = plan_provenance_backfill(finals, lineage_map, mirror_map, {"r1": _run("r1")})
    assert plan["counts"]["no_lineage"] == 1
    # count_mismatch 含 no_lineage(f1:0≠3)+ 真 mismatch(f2:2≠5)= 2
    assert plan["counts"]["count_mismatch"] == 2
    assert plan["items"][0]["missing"]["no_lineage"] is True
    assert plan["items"][1]["count_consistent"] is False


def test_plan_unknown_run_groups_into_unknown_reference():
    finals = [_final("f1", "c1", summary={"evidence_count": 1})]
    lineage_map = {"c1": _lineage("c1", ["m1"])}
    mirror_map = {"m1": _mirror(1, None)}   # 无 llm_run_id
    plan = plan_provenance_backfill(finals, lineage_map, mirror_map, {})
    assert plan["counts"]["to_update"] == 1
    assert plan["items"][0]["references"][0]["source_type"] == "unknown"


# ---- 5. 回填后一致性验证 ----

def test_validate_consistency_full_coverage():
    items = [
        {"references": [{"mirror_connection_ids": ["m1"]}], "count_consistent": True},
        {"references": [{"mirror_connection_ids": ["m2"]}], "count_consistent": True},
    ]
    v = validate_backfill_consistency(items)
    assert v["total_final"] == 2
    assert v["coverage"]["with_references"] == 2
    assert v["coverage"]["coverage_pct"] == 100.0
    assert v["lineage_consistency"]["all_references_traceable"] is True
    assert v["evidence_count_consistency"]["consistent"] == 2


def test_validate_consistency_partial():
    items = [
        {"references": [], "count_consistent": False},              # 无引用
        {"references": [{"mirror_connection_ids": []}], "count_consistent": False},
        {"references": [{"mirror_connection_ids": ["m1"]}], "count_consistent": True},
    ]
    v = validate_backfill_consistency(items)
    assert v["coverage"]["with_references"] == 2
    assert v["coverage"]["coverage_pct"] == round(100 * 2 / 3, 2)
    assert v["lineage_consistency"]["references_with_mirror_ids"] == 1
    assert v["lineage_consistency"]["all_references_traceable"] is False
    assert v["evidence_count_consistency"]["consistent"] == 1
    assert v["evidence_count_consistency"]["mismatch"] == 2

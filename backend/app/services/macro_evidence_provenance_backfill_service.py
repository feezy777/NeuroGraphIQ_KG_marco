"""Macro Evidence Provenance Backfill V1 — 核心逻辑(纯函数规划 + 幂等回填方案)。

目标:将 Mirror 层已有证据来源信息(llm_run_id / batch_id / source_atlas /
source_version / extraction metadata)经 lineage 上卷为 Final 层
final_canonical_connections.evidence_reference(JSONB 数组),使每条 Final
Connection 具备完整可追溯的证据来源引用。

链路:final ↓ canonical ↓ canonical_connection_lineage(cluster ↓
mirror_connection_ids)↓ mirror_region_connections ↓ llm_extraction_runs

数据语义(2026-08-25 探查确认):
* mirror_region_connections 无 paper/DOI/PMID 结构化字段 —— "来源" =
  (llm_run_id 提取批次, source_atlas+source_version 数据集, batch_id 导入批次,
   provider+model+prompt_version 提取元数据);文献线索仅存于 evidence_text
  自然语言(66/2000 条含 "et al",无 DOI/PMID 模式)。
* final 2485 全部可经 lineage 追溯(untraced=0);lineage 4087 行全含
  mirror_connection_ids;mirror 5716/5720 有 llm_run_id(4 条无 → unknown)。
* 本模块零事实变更:只回填 evidence_reference 一个字段;不创建/修改连接、
  不动 source/target/type/direction、不 promotion、不 CN2、不调 LLM。

evidence_reference 元素格式:
{
  source_type, source_id(llm_run_id), paper("",镜像层无文献), dataset(atlas+version),
  extraction_run(run 描述), confidence(mean), confidence_min/max/count,
  mirror_connection_ids[](可追溯)
}
"""

from __future__ import annotations

from collections import Counter
from statistics import mean

UNKNOWN_RUN = "unknown"


def _conf_stats(confs: list[float]) -> dict:
    """mirror 行 confidence 列表 → 统计(min/max/mean/count)。空 → count=0。"""
    vals = [float(c) for c in confs if c is not None and c != ""]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "mean": round(mean(vals), 4),
    }


# ---- 1. mirror 来源字段审计 ----

def audit_mirror_provenance_fields(
    mirror_rows: list[dict],
    run_rows: list[dict],
) -> dict:
    """mirror 层证据来源字段可用性审计(任务 1,纯统计)。

    mirror_rows: {llm_run_id, batch_id, resource_id, source_atlas,
    source_version, confidence, evidence_text}
    run_rows: {id, task_type, provider, model_name, prompt_version, status}
    """
    n = len(mirror_rows)
    run_ids = {str(m.get("llm_run_id")) for m in mirror_rows if m.get("llm_run_id")}
    batch_ids = {str(m.get("batch_id")) for m in mirror_rows if m.get("batch_id")}
    atlases = Counter(str(m.get("source_atlas") or "") for m in mirror_rows)
    texts = [str(m.get("evidence_text") or "") for m in mirror_rows
             if m.get("evidence_text")]
    return {
        "total_mirror": n,
        "structured_fields": {
            "paper": False, "doi": False, "pmid": False,
            "note": ("mirror_region_connections / llm_extraction_runs / "
                     "llm_extraction_items 均无 paper/DOI/PMID 结构化字段"),
        },
        "field_coverage": {
            "llm_run_id": f"{sum(1 for m in mirror_rows if m.get('llm_run_id'))}/{n}",
            "batch_id": f"{sum(1 for m in mirror_rows if m.get('batch_id'))}/{n}",
            "source_atlas": f"{sum(1 for m in mirror_rows if m.get('source_atlas'))}/{n}",
            "confidence": f"{sum(1 for m in mirror_rows if m.get('confidence') is not None)}/{n}",
            "evidence_text": f"{len(texts)}/{n}",
        },
        "distinct": {
            "llm_run_ids": len(run_ids), "batch_ids": len(batch_ids),
            "source_atlases": len(atlases),
        },
        "extraction_runs": [
            {"llm_run_id": str(r.get("id") or ""),
             "task_type": r.get("task_type"), "provider": r.get("provider"),
             "model_name": r.get("model_name"),
             "prompt_version": r.get("prompt_version"), "status": r.get("status")}
            for r in sorted(run_rows, key=lambda r: str(r.get("id") or ""))
            if str(r.get("id") or "") in run_ids
        ],
        "citation_clues_in_evidence_text": {
            "sample_size": len(texts),
            "et_al_mentions": sum(1 for t in texts if "et al" in t.lower()),
            "year_in_parens": sum(1 for t in texts
                                  if any(c.isdigit() for c in t) and "(" in t),
            "doi_or_pmid": 0,
            "note": "文献线索仅存在于 evidence_text 自然语言,未结构化",
        },
        "batch_ids": sorted(batch_ids),
    }


# ---- 2. evidence_reference 生成 ----

def build_evidence_reference(
    run_id: str,
    run_meta: dict | None,
    atlas: str,
    version: str,
    confs: list[float],
    mirror_ids: list[str],
) -> dict:
    """单来源组 → evidence_reference 元素。

    run_meta: llm_extraction_runs 行 {task_type, provider, model_name,
    prompt_version, prompt_template_key, batch_id, source_atlas, source_version}
    run_id == UNKNOWN_RUN → source_type='unknown'(无批次信息的 mirror 行)。
    """
    stats = _conf_stats(confs)
    if run_id == UNKNOWN_RUN or not run_meta:
        return {
            "source_type": "unknown",
            "source_id": run_id,
            "paper": "",
            "dataset": f"{atlas} {version}".strip(),
            "extraction_run": "",
            "confidence": "",
            "confidence_count": stats.get("count", 0),
            "mirror_connection_ids": mirror_ids,
        }
    run_desc = (f"{run_meta.get('task_type') or 'extraction'}"
                f" {run_meta.get('model_name') or run_meta.get('provider') or ''}"
                f" (prompt {run_meta.get('prompt_version') or '?'})").strip()
    dataset = (run_meta.get("source_atlas") or atlas or "unknown") + " " \
              + (run_meta.get("source_version") or version or "").strip()
    return {
        "source_type": "llm_extraction",
        "source_id": run_id,
        "paper": "",
        "dataset": dataset.strip(),
        "extraction_run": run_desc,
        "confidence": str(stats.get("mean") or ""),
        "confidence_count": stats.get("count", 0),
        "confidence_min": stats.get("min"),
        "confidence_max": stats.get("max"),
        "mirror_connection_ids": mirror_ids,
    }


def build_evidence_references(mirror_rows: list[dict], run_meta_map: dict[str, dict]) -> list[dict]:
    """一组 mirror 行 → evidence_reference 数组(按 llm_run_id 分组)。"""
    groups: dict[str, dict] = {}
    for m in mirror_rows:
        rid = str(m.get("llm_run_id") or UNKNOWN_RUN)
        g = groups.setdefault(rid, {"confs": [], "ids": [], "atlas": "", "version": ""})
        g["confs"].append(m.get("confidence"))
        if m.get("id"):
            g["ids"].append(str(m["id"]))
        g["atlas"] = m.get("source_atlas") or g["atlas"]
        g["version"] = m.get("source_version") or g["version"]
    refs = []
    for rid in sorted(groups):
        g = groups[rid]
        refs.append(build_evidence_reference(
            rid, run_meta_map.get(rid), g["atlas"], g["version"],
            g["confs"], sorted(g["ids"])))
    # 稳定的确定性排序:有 run 的在前,unknown 最后,同 run 按 id
    refs.sort(key=lambda r: (r["source_type"] != "llm_extraction",
                             r["source_id"]))
    return refs


def lineage_refs_for_final(
    final: dict,
    lineage_rows: list[dict],
    mirror_map: dict[str, dict],
    run_meta_map: dict[str, dict],
) -> dict:
    """单条 final → {references, traced_mirror_ids, missing}。

    final: {id, canonical_connection_id, ...}
    lineage_rows: 该 canonical 的全部 lineage 行 {cluster_id, mirror_connection_ids}
    mirror_map: {mirror_id: {llm_run_id, source_atlas, source_version, confidence}}
    """
    traced: list[str] = []
    for lr in lineage_rows:
        for mid in lr.get("mirror_connection_ids") or []:
            sid = str(mid)
            if sid in mirror_map:
                traced.append(sid)
    mirror_rows = [mirror_map[i] for i in traced]
    refs = build_evidence_references(mirror_rows, run_meta_map)
    return {
        "final_id": str(final.get("id") or ""),
        "canonical_connection_id": str(final.get("canonical_connection_id") or ""),
        "connection_code": final.get("connection_code"),
        "traced_mirror_ids": traced,
        "references": refs,
        "missing": {
            "no_lineage": not lineage_rows,
            "lineage_mirror_ids_missing_in_map": (
                [str(mid) for lr in lineage_rows for mid in (lr.get("mirror_connection_ids") or [])
                 if str(mid) not in mirror_map]),
        },
    }


# ---- 3. 回填规划(幂等) ----

def plan_provenance_backfill(
    finals: list[dict],
    lineage_map: dict[str, list[dict]],
    mirror_map: dict[str, dict],
    run_meta_map: dict[str, dict],
) -> dict:
    """全量回填规划:每条 final → 目标 references + 幂等差异。

    finals: {id, canonical_connection_id, connection_code, evidence_reference,
    evidence_summary}
    lineage_map: {canonical_id: [lineage rows]}
    mirror_map: {mirror_id: {llm_run_id, source_atlas, source_version, confidence}}
    run_meta_map: {llm_run_id: run 行}

    returns {
      items: [{final_id, ..., references, will_update(bool), evidence_count,
               summary_evidence_count, count_consistent(bool)}],
      counts: {total, to_update, unchanged, no_lineage, count_mismatch}
    }
    """
    items = []
    no_lineage = count_mismatch = 0
    for f in finals:
        lineage_rows = lineage_map.get(str(f.get("canonical_connection_id"))) or []
        info = lineage_refs_for_final(f, lineage_rows, mirror_map, run_meta_map)
        refs = info["references"]
        if not lineage_rows:
            no_lineage += 1
        es = f.get("evidence_summary") or {}
        summary_count = int(es.get("evidence_count") or 0) if isinstance(es, dict) else 0
        traced_count = len(info["traced_mirror_ids"])
        consistent = traced_count == summary_count if summary_count else (traced_count == 0)
        if not consistent:
            count_mismatch += 1
        current = f.get("evidence_reference") or []
        changed = [r for r in refs if r not in current] or [r for r in current if r not in refs]
        will_update = bool(changed)
        items.append({
            "final_id": info["final_id"],
            "canonical_connection_id": info["canonical_connection_id"],
            "connection_code": info["connection_code"],
            "references": refs,
            "traced_mirror_ids": info["traced_mirror_ids"],
            "evidence_count_traced": traced_count,
            "evidence_count_summary": summary_count,
            "count_consistent": consistent,
            "missing": info["missing"],
            "will_update": will_update,
        })
    counts = {
        "total": len(items),
        "to_update": sum(1 for i in items if i["will_update"]),
        "unchanged": sum(1 for i in items if not i["will_update"]),
        "no_lineage": no_lineage,
        "count_mismatch": count_mismatch,
    }
    return {"items": items, "counts": counts}


# ---- 4. 回填后一致性验证(纯逻辑) ----

def validate_backfill_consistency(items: list[dict]) -> dict:
    """回填后一致性(模拟验证,纯函数)。

    * coverage:references 非空条数
    * lineage 一致性:每条 reference 的 mirror_connection_ids 非空(可追溯)
    * evidence_count 一致性:traced_mirror_ids 数 == summary evidence_count 的比例
    """
    covered = sum(1 for i in items if i["references"])
    ref_with_ids = sum(
        1 for i in items for r in i["references"] if r.get("mirror_connection_ids"))
    total_refs = sum(len(i["references"]) for i in items)
    consistent = sum(1 for i in items if i["count_consistent"])
    by_ref_count: Counter = Counter(len(i["references"]) for i in items)
    return {
        "total_final": len(items),
        "coverage": {
            "with_references": covered,
            "coverage_pct": round(100 * covered / len(items), 2) if items else 0,
            "reference_count_distribution": dict(sorted(by_ref_count.items())),
        },
        "lineage_consistency": {
            "total_references": total_refs,
            "references_with_mirror_ids": ref_with_ids,
            "all_references_traceable": ref_with_ids == total_refs,
        },
        "evidence_count_consistency": {
            "consistent": consistent,
            "mismatch": len(items) - consistent,
            "consistent_pct": round(100 * consistent / len(items), 2) if items else 0,
        },
    }

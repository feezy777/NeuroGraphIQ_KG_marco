"""Macro Candidate Connection Ranking V1 —— 论文驱动候选连接优先级排序。

输入 paper_region_pair_candidates(17,609 行,按无向对聚合),
关联 paper_region_evidence_segments + paper_sources,
对每个 (source_region_id, target_region_id) 计算五因素评分并分级 A/B/C。

约束(用户要求):
* 不创建 canonical connection / 不修改 final_canonical_connections /
  不进入 validation/review/promotion —— 只生成 candidate ranking 数据
* 无 LLM / 无外部 API —— 纯规则确定性计算

评分模型(全部确定,可测试):
  score = paper_support_score × evidence_source_score × proximity_score
          × (1 + keyword_bonus)

  1. paper_support_score = 2^(paper_count-1)     # 1篇=1, 2篇=2, 3篇=4 ...
     ≥6 篇饱和 32(指数增长 + 饱和帽,防长尾爆炸)
  2. evidence_source_score = 该 pair 证据句的最强来源权重
     fulltext 1.0 / abstract 0.8 / title 0.5
  3. proximity_score = 最强共现级别权重
     same_sentence 1.0 / same_section 0.7 / same_paper 0.4
  4. keyword_bonus = 0.1 × min(关键词命中数, 5), 关键词词边界检测
     (projection/projects/connect/connectivity/connected/tract/fiber/
      pathway/bundle/functional connectivity/correlation/association)
  5. evidence_count = 候选行数(每条候选 = 一条证据句,含 title 源)

优先级(用户定义):
  A = 多篇论文(≥2) + same_sentence 证据 + 连接关键词
  B = 非 A 非 C
  C = 单论文且无 same_sentence 无关键词(低价值共现)

可追溯链(每一条 ranking 全量可追溯):
  ranking → candidate_pair(paper_region_pair_candidates.id) →
  evidence_segment(paper_region_evidence_segments,按 paper_id+句文本匹配) →
  paper_source
"""

from __future__ import annotations

import re

# ---- 常量 ----

GENERATION_METHOD = "paper_candidate_ranking_v1"
ASSERTION_TYPE = "candidate"
SOURCE_TYPE = "literature"

CONNECTION_KEYWORDS = [
    "projection", "projects", "connect", "connectivity", "connected",
    "tract", "fiber", "pathway", "bundle",
    "functional connectivity", "correlation", "association",
]

# 证据来源权重(fulltext > abstract > title)
SOURCE_WEIGHT = {
    "paper_fulltext": 1.0,
    "paper_abstract": 0.8,
    "title": 0.5,
}
# title 源无对应 segment,缺省即 title
DEFAULT_SOURCE = "title"

# 共现级别权重(same_sentence > same_section > same_paper)
PROXIMITY_WEIGHT = {
    "same_sentence": 1.0,
    "same_section": 0.7,
    "same_paper": 0.4,
}

PAPER_EXPONENT_BASE = 2.0
PAPER_SATURATION = 6       # paper_count ≥ 6 → 2^5 = 32 饱和
KEYWORD_BONUS_PER_HIT = 0.1
KEYWORD_BONUS_CAP = 5
SCORE_ROUND = 4

LEVEL_A_PAPERS = 2         # A 级: ≥2 篇论文
PRIORITY_A = "A"
PRIORITY_B = "B"
PRIORITY_C = "C"

# ---- 纯函数 ----

def paper_support_score(paper_count: int) -> float:
    """论文支持分: 2^(n-1) 指数增长,≥PAPER_SATURATION 篇饱和 2^5=32。"""
    if paper_count < 1:
        return 0.0
    exponent = min(paper_count - 1, PAPER_SATURATION - 1)
    return float(PAPER_EXPONENT_BASE ** exponent)


def detect_keywords(text: str) -> list[str]:
    """证据句中的连接关键词(词边界;短语 'functional connectivity' 子串)。"""
    if not text:
        return []
    lower = text.lower()
    hits: list[str] = []
    for kw in CONNECTION_KEYWORDS:
        if " " in kw:
            if kw in lower:
                hits.append(kw)
        elif re.search(rf"\b{re.escape(kw)}\b", lower):
            hits.append(kw)
    return hits


def keyword_bonus(keyword_hits: list[str]) -> float:
    """关键词加成: 0.1 × 命中数,最多 0.5。"""
    return KEYWORD_BONUS_PER_HIT * min(len(keyword_hits), KEYWORD_BONUS_CAP)


def rank_priority(paper_count: int, has_same_sentence: bool,
                  has_keyword: bool) -> str:
    """A/B/C 分级(用户定义):
    A = ≥2 篇论文 + same_sentence 证据 + 连接关键词
    C = 单论文 且 无 same_sentence 且 无关键词(低价值共现)
    B = 其余
    """
    if paper_count >= LEVEL_A_PAPERS and has_same_sentence and has_keyword:
        return PRIORITY_A
    if paper_count >= 2 or has_same_sentence or has_keyword:
        return PRIORITY_B
    return PRIORITY_C


def _pair_key(source_region_id: str, target_region_id: str) -> tuple[str, str]:
    """无向对按 region_id 排序(与 discovery 阶段一致)。"""
    if str(source_region_id) <= str(target_region_id):
        return str(source_region_id), str(target_region_id)
    return str(target_region_id), str(source_region_id)


def link_evidence_segments(pair_rows: list[dict], segments: list[dict]) -> dict:
    """candidate_pair → evidence_segment 关联表。

    键 (paper_id, evidence_sentence) 精确匹配(evidence 可追溯性由
    discovery 阶段逐字断言保证);无匹配 = title 源(无 segment)。
    """
    seg_map: dict[tuple[str, str], dict] = {}
    for seg in segments:
        key = (str(seg["paper_id"]), seg["sentence_text"])
        if key not in seg_map:
            seg_map[key] = seg
    return seg_map


def aggregate_pair_rows(pair_rows: list[dict],
                        seg_map: dict[tuple[str, str], dict] | None = None
                        ) -> dict:
    """同一无向对的所有候选行 → 一条 ranking 计算。

    输入 pair_rows: paper_region_pair_candidates 行 dicts(同 pair 全部论文),
    每行必含 paper_id / evidence_sentence / cooccurrence / id。
    seg_map: (paper_id, sentence_text) → segment,None 时全部视为 title 源。
    """
    seg_map = seg_map or {}
    paper_ids = sorted({str(r["paper_id"]) for r in pair_rows})
    paper_count = len(paper_ids)

    source_scores: list[float] = []
    proximities: list[float] = []
    keyword_set: set[str] = set()
    segment_ids: list[str | None] = []
    paper_sources: list[str] = []
    for row in pair_rows:
        seg = seg_map.get((str(row["paper_id"]), row["evidence_sentence"]))
        source = seg["source_type"] if seg else DEFAULT_SOURCE
        source_scores.append(SOURCE_WEIGHT.get(source, SOURCE_WEIGHT[DEFAULT_SOURCE]))
        proximities.append(PROXIMITY_WEIGHT.get(row["cooccurrence"], 0.4))
        keyword_set.update(detect_keywords(row["evidence_sentence"]))
        segment_ids.append(str(seg["id"]) if seg else None)
        paper_sources.append(source)

    keywords = [k for k in CONNECTION_KEYWORDS if k in keyword_set]
    has_same_sentence = "same_sentence" in {
        str(r["cooccurrence"]) for r in pair_rows}
    score = (
        paper_support_score(paper_count)
        * max(source_scores)
        * max(proximities)
        * (1.0 + keyword_bonus(keywords))
    )
    source_dist: dict[str, int] = {}
    for s in paper_sources:
        source_dist[s] = source_dist.get(s, 0) + 1

    return {
        "paper_count": paper_count,
        "evidence_count": len(pair_rows),
        "paper_support_score": round(paper_support_score(paper_count), SCORE_ROUND),
        "evidence_source_score": max(source_scores),
        "proximity_score": max(proximities),
        "keyword_hits": keywords,
        "keyword_bonus": round(keyword_bonus(keywords), SCORE_ROUND),
        "has_same_sentence": has_same_sentence,
        "score": round(score, SCORE_ROUND),
        "priority_level": rank_priority(paper_count, has_same_sentence,
                                        bool(keywords)),
        "paper_ids": paper_ids,
        "segment_ids": segment_ids,
        "paper_sources": paper_sources,
        "source_distribution": source_dist,
        "segment_examples": [
            r["evidence_sentence"][:200] for r in
            sorted(pair_rows, key=lambda x: -PROXIMITY_WEIGHT.get(
                x["cooccurrence"], 0.4))[:2]],
    }


def build_ranking_row(source_region_id: str, target_region_id: str,
                      pair_rows: list[dict],
                      seg_map: dict[tuple[str, str], dict] | None = None,
                      pmid_by_paper: dict[str, str | None] | None = None
                      ) -> dict:
    """聚合计算 + 组装完整 ranking 行(含 provenance_json)。"""
    src, tgt = _pair_key(source_region_id, target_region_id)
    agg = aggregate_pair_rows(pair_rows, seg_map)
    pmid_by_paper = pmid_by_paper or {}

    paper_entries = []
    for row, seg_id, source in zip(pair_rows, agg["segment_ids"],
                                   agg["paper_sources"]):
        paper_entries.append({
            "paper_id": str(row["paper_id"]),
            "pmid": pmid_by_paper.get(str(row["paper_id"])),
            "candidate_pair_id": str(row["id"]),
            "evidence_segment_id": seg_id,
            "source_type": source,
            "cooccurrence": str(row["cooccurrence"]),
            "evidence_sentence_snippet": row["evidence_sentence"][:120],
        })

    ranking_reason = {
        "paper_support_score": agg["paper_support_score"],
        "evidence_source_score": agg["evidence_source_score"],
        "proximity_score": agg["proximity_score"],
        "keyword_hits": agg["keyword_hits"],
        "keyword_bonus": agg["keyword_bonus"],
        "has_same_sentence": agg["has_same_sentence"],
        "paper_ids": agg["paper_ids"],
        "source_distribution": agg["source_distribution"],
        "segment_examples": agg["segment_examples"],
    }
    provenance_json = {
        "source_table": "paper_region_pair_candidates",
        "trace_chain": ["ranking", "candidate_pair",
                        "evidence_segment", "paper_source"],
        "paper_entries": paper_entries,
    }
    return {
        "source_region_id": src,
        "target_region_id": tgt,
        "candidate_pair_ids": [str(r["id"]) for r in pair_rows],
        "paper_count": agg["paper_count"],
        "evidence_count": agg["evidence_count"],
        "score": agg["score"],
        "priority_level": agg["priority_level"],
        "ranking_reason": ranking_reason,
        "provenance_json": provenance_json,
        "assertion_type": ASSERTION_TYPE,
        "source_type": SOURCE_TYPE,
        "generation_method": GENERATION_METHOD,
    }


# ---- 幂等 INSERT ----

INSERT_RANKING_SQL = """\
INSERT INTO paper_connection_candidate_rankings
    (source_region_id, target_region_id, candidate_pair_ids, paper_count,
     evidence_count, score, priority_level, ranking_reason, provenance_json,
     assertion_type, source_type, generation_method)
VALUES (:source_region_id, :target_region_id, :candidate_pair_ids,
        :paper_count, :evidence_count, :score, :priority_level,
        :ranking_reason, :provenance_json, :assertion_type, :source_type,
        :generation_method)
ON CONFLICT (source_region_id, target_region_id) DO NOTHING
"""

# ---- 报告辅助 ----

def summarize_rankings(rankings: list[dict]) -> dict:
    """等级分布 + 总数(报告用)。"""
    counts = {"A": 0, "B": 0, "C": 0}
    for r in rankings:
        counts[r["priority_level"]] = counts.get(r["priority_level"], 0) + 1
    return {
        "total_rankings": len(rankings),
        "priority_distribution": counts,
    }

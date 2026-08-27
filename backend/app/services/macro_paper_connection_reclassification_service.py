"""Macro Paper-Connection Evidence Reclassification V1(纯函数规则 + 幂等 SQL)。

重新评估 connection_paper_evidence 的 104 条 paper-connection 关联,
建立三类(用户定义):
* A: direct_evidence    → evidence_relation_type='direct_support'
    论文原文明确描述两个 brain region 之间 connection/projection/
    connectivity/pathway —— 判定:该 (paper, connection) 在
    paper_connection_evidence_segments 中有 status='extracted' 行
    (摘要级或全文级,规则已保证同句双命中+连接语义词)
* B: supporting_literature → 'context_support'
    论文研究相关脑区或功能,但未证明该 connection —— 判定:标题 /
    摘要 / 全文(缓存 XML 可解析时)提及 source 或 target 任一端
    (复用 region resolver,词边界 + 大写缩写规则防误报)
* C: invalid_association → 'invalid'
    论文与 connection 无直接关系 —— 判定:以上信号均无

约束(用户要求):
* 不删除原始 connection_paper_evidence 行(只回填新列)
* 保留原始 match_method / doi / pmid / confidence(不动 provenance_json
  / evidence_reference / confidence)
* 禁止修改 Final Connection / ontology / paper_sources

优先级:extracted segment 判定高于提及信号(即使摘要也提及 → 仍
direct_support)。信号组合记录在 detail 中供报告展示。
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from app.services.macro_paper_evidence_segments_service import (
    STATUS_EXTRACTED,
    _find_first,
    region_terms,
)
from app.services.macro_paper_fulltext_evidence_service import parse_jats_xml

RELATION_DIRECT = "direct_support"
RELATION_CONTEXT = "context_support"
RELATION_INVALID = "invalid"


def _mentions_any(terms: list[str], text: str | None) -> bool:
    """文本是否命中任一词(词边界/大写缩写规则由 _find_first 保证)。"""
    if not text:
        return False
    found, _ = _find_first(terms, text)
    return found is not None


def _mentions_side(terms: list[str], text: str | None) -> str | None:
    """提及的一端名(terms 列表首词),未提及 → None。"""
    if not text:
        return None
    found, _ = _find_first(terms, text)
    return found


def scan_fulltext_mentions(xml_text: str | None, source_terms: list[str],
                           target_terms: list[str]) -> dict:
    """全文(缓存 XML)中两端任一端的提及情况。

    返回 {source_mentioned: bool, target_mentioned: bool}；
    XML 为空或解析失败 → 均 False(无全文信号,不误判)。
    """
    if not xml_text:
        return {"source_mentioned": False, "target_mentioned": False}
    try:
        parsed = parse_jats_xml(xml_text)
    except ET.ParseError:
        return {"source_mentioned": False, "target_mentioned": False}
    src = tgt = False
    for section in parsed["sections"]:
        for paragraph in section["paragraphs"]:
            if src and tgt:
                break
            if not src and _mentions_any(source_terms, paragraph):
                src = True
            if not tgt and _mentions_any(target_terms, paragraph):
                tgt = True
    return {"source_mentioned": src, "target_mentioned": tgt}


def classify_link(*, segment_statuses: list[str],
                  title: str | None, abstract: str | None,
                  fulltext_xml: str | None,
                  source_name: str, target_name: str,
                  source_aliases: list[str],
                  target_aliases: list[str]) -> dict:
    """单条关联 → {relation_type, detail}。

    判定优先级:
    1. extracted segment(摘要级或全文级)→ direct_support
    2. 标题/摘要/全文提及任一端 → context_support
    3. 无信号 → invalid
    """
    source_terms = region_terms(source_name, source_aliases)
    target_terms = region_terms(target_name, target_aliases)

    # 1. direct_support:已有证据链 extracted segment
    if any(s == STATUS_EXTRACTED for s in segment_statuses):
        return {"relation_type": RELATION_DIRECT,
                "detail": {"basis": "extracted_segment"}}

    # 2. context_support:研究相关脑区(标题/摘要/全文提及任一端)
    detail: dict = {}
    s_title = _mentions_side(source_terms, title)
    t_title = _mentions_side(target_terms, title)
    s_abs = _mentions_side(source_terms, abstract)
    t_abs = _mentions_side(target_terms, abstract)
    ft = scan_fulltext_mentions(fulltext_xml, source_terms, target_terms)
    signals: list[str] = []
    if s_title or t_title:
        signals.append("title_mentions")
    if s_abs or t_abs:
        signals.append("abstract_mentions")
    if ft["source_mentioned"] or ft["target_mentioned"]:
        signals.append("fulltext_mentions")
    if signals:
        detail["basis"] = "+".join(sorted(signals))
        detail["title"] = {"source": s_title, "target": t_title}
        detail["abstract"] = {"source": s_abs, "target": t_abs}
        detail["fulltext"] = ft
        return {"relation_type": RELATION_CONTEXT, "detail": detail}

    # 3. invalid:无任何信号
    return {"relation_type": RELATION_INVALID,
            "detail": {"basis": "no_mention_signal"}}


# ---- SQL(幂等回填,不删行) ----

UPDATE_RELATION_TYPE_SQL = """\
UPDATE connection_paper_evidence
   SET evidence_relation_type = :relation_type,
       updated_at = now()
 WHERE id = :link_id
   AND evidence_relation_type IS DISTINCT FROM :relation_type
 RETURNING id"""

SELECT_LINKS_SQL = """\
SELECT l.id, l.connection_id, l.paper_id, e.pmid, e.title,
       e.enrichment_json->>'abstract',
       l.provenance_json->>'match_method',
       l.evidence_reference->>'doi',
       l.confidence,
       fc.connection_type,
       r1.canonical_name_en, r2.canonical_name_en,
       r1.id, r2.id
FROM connection_paper_evidence l
JOIN paper_sources e ON e.id = l.paper_id
JOIN final_canonical_connections fc ON fc.id = l.connection_id
LEFT JOIN canonical_brain_regions r1 ON r1.id = fc.source_region_id
LEFT JOIN canonical_brain_regions r2 ON r2.id = fc.target_region_id
ORDER BY e.pmid, l.connection_id"""

SELECT_SEGMENT_STATUS_SQL = """\
SELECT paper_id, connection_id, evidence_source_type, status
FROM paper_connection_evidence_segments
WHERE status = :status"""

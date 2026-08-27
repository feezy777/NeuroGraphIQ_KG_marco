"""Macro Paper Full Text Evidence Extraction V1(纯函数规则 + 幂等 SQL)。

基于 3 篇 Europe PMC fullTextXML(JATS)论文,建立正文级 evidence
segment 抽取能力 —— 复用摘要级 region resolver,扩展到全文章节。

约束(用户要求):
* 不修改已有摘要证据(摘要段 evidence_source_type='paper_abstract' 不动)
* 新增来源区分:evidence_source_type='paper_fulltext' + section_name
* 只保存论文原文真实文本 —— 禁止 LLM 生成不存在的证据
* 只允许关联已有 connection_paper_evidence 中的 connection
* 连接语义词是命中必要条件:connection/projection/connectivity/tract/
  pathway/connected/innervation 等

抽取规则(确定性):
1. JATS 解析:title / abstract(Abstract 节) / body sec(嵌套 title 传播)
   → 每段落按句切分(section_name = 最近 sec title;Figure/Table caption
   归入 Figure/Table)
2. region 词表复用摘要级 region_terms(canonical 名 + 别名)
3. 同句双命中 + 连接语义词:
   - +方向支持(source 在 target 前)→ 0.90
   - 无方向 → 0.85
4. 相邻句(±1)各含一端 + 连接语义词 → 0.65(证据句 = 含连接词的句子)
5. 无连接语义词 → 不命中(正文严格规则,宁可少不可错)

输出 segment(与摘要级同构 + 来源列):
  {paper_id, connection_id, evidence_text, section_name,
   matched_regions, confidence, source_type:"paper_fulltext"}
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from app.services.macro_paper_evidence_segments_service import (
    EXTRACTION_METHOD,
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
    _find_first,
    region_terms,
    split_sentences,
)

SOURCE_TYPE_FULLTEXT = "paper_fulltext"
SOURCE_TYPE_ABSTRACT = "paper_abstract"

# 连接语义词表(用户列举 + 扩展;词干子串匹配)
FULLTEXT_CONNECT_WORDS = (
    "connection", "connectivity", "connected", "projection",
    "projecting", "project", "tract", "pathway", "innervation",
    "innervat", "input", "afferent", "efferent", "terminat",
    "fiber", "fibre", "synapse", "synaptic", "activated",
)

# 非正文段落标签(仅标题/脚注等,不作为证据句)
_SKIP_TAG = {"title", "abstract-title", "kwd-group", "fn-group",
             "ref-list", "ack", "bio", "funding-group"}


def _local(tag: str) -> str:
    """去命名空间(无命名空间 XML 直接返回;兼容带 xmlns 的)。"""
    return tag.split("}")[-1]


def _text(node) -> str:
    return "".join(node.itertext()).strip()


def parse_jats_xml(xml_text: str) -> dict:
    """fullTextXML → {title, sections: [{name, paragraphs: [str]}]}。

    section_name = 最近 sec title(嵌套传播);无 title 用父级;
    figure/table-wrap 的 caption 段落归入 'Figure'/'Table'。
    """
    root = ET.fromstring(xml_text)
    title = ""
    title_el = root.find(".//article-title")
    if title_el is not None:
        title = _text(title_el)

    sections: list[dict] = []
    by_name: dict[str, list[str]] = {}

    def _emit(name: str, paragraph: str) -> None:
        by_name.setdefault(name, []).append(paragraph)

    def _walk(node: ET.Element, current_title: str) -> None:
        for child in node:
            tag = _local(child.tag)
            if tag in _SKIP_TAG:
                continue
            if tag == "sec":
                t_el = child.find("title")
                title = _text(t_el) if t_el is not None else current_title
                _walk(child, title or current_title)
            elif tag == "p":
                text = _text(child)
                if text:
                    _emit(current_title or "Body", text)
            elif tag in ("fig", "table-wrap", "boxed-text"):
                label = _text(child.find("label")) if child.find("label") \
                    is not None else ""
                if tag == "fig":
                    name = (label if label.lower().startswith(("figure", "fig"))
                            else f"Figure {label}".strip())
                else:
                    name = (label if label.lower().startswith("table")
                            else f"Table {label}".strip())
                _walk(child, name)
            else:
                _walk(child, current_title)

    # abstract → Abstract 节
    abstract = root.find(".//abstract")
    if abstract is not None:
        for p in abstract.findall(".//p"):
            text = _text(p)
            if text:
                _emit("Abstract", text)
    # body → 章节段落
    body = root.find(".//body")
    if body is not None:
        _walk(body, "")
    for name in by_name:
        sections.append({"name": name, "paragraphs": by_name[name]})
    return {"title": title, "sections": sections}


def _has_connect_word(*sentences: str) -> bool:
    joined = " ".join(sentences).lower()
    return any(w in joined for w in FULLTEXT_CONNECT_WORDS)


def find_fulltext_evidence(sections: list[dict], source_terms: list[str],
                           target_terms: list[str]) -> dict | None:
    """全部章节中找最佳命中(confidence 优先,同分取最早段落/句子)。

    规则:
    * 同句双命中 + 连接词 → 0.90(方向支持) / 0.85
    * 相邻句(±1)各含一端 + 连接词 → 0.65
    * 无连接词 → 不命中
    """
    best = None

    def _candidate(sentence: str, section: str, pidx: int, sidx: int,
                   s_term: str, t_term: str, s_pos: int, t_pos: int,
                   confidence: float) -> dict:
        return {"sentence": sentence, "section_name": section,
                "paragraph_index": pidx + 1, "sentence_index": sidx + 1,
                "matched_source": s_term, "matched_target": t_term,
                "source_pos": s_pos, "target_pos": t_pos,
                "confidence": confidence}

    for section in sections:
        name = section["name"]
        for pidx, paragraph in enumerate(section["paragraphs"]):
            sents = split_sentences(paragraph)
            for i, sent in enumerate(sents):
                s_term, s_pos = _find_first(source_terms, sent)
                t_term, t_pos = _find_first(target_terms, sent)
                if s_term and t_term:
                    if not _has_connect_word(sent):
                        continue  # 正文规则:连接语义词是必要条件
                    conf = 0.90 if s_pos < t_pos else 0.85
                    cand = _candidate(sent, name, pidx, i, s_term, t_term,
                                      s_pos, t_pos, conf)
                else:
                    # 相邻句(±1):本句含一端,邻句含另一端,任一句含连接词
                    other = None
                    for j in (i - 1, i + 1):
                        if not (0 <= j < len(sents)):
                            continue
                        if s_term:  # 本句 source → 邻句找 target
                            t2, _ = _find_first(target_terms, sents[j])
                            if t2 and _has_connect_word(sent, sents[j]):
                                other = _candidate(
                                    sents[j] if _has_connect_word(sents[j])
                                    else sent, name, pidx, j, s_term, t2,
                                    s_pos, -1, 0.65)
                                break
                        elif t_term:  # 本句 target → 邻句找 source
                            s2, _ = _find_first(source_terms, sents[j])
                            if s2 and _has_connect_word(sent, sents[j]):
                                other = _candidate(
                                    sents[j] if _has_connect_word(sents[j])
                                    else sent, name, pidx, j, s2, t_term,
                                    -1, t_pos, 0.65)
                                break
                    if other is None:
                        continue
                    cand = other
                if best is None or cand["confidence"] > best["confidence"] \
                        or (cand["confidence"] == best["confidence"]
                            and (cand["paragraph_index"],
                                 cand["sentence_index"])
                            < (best["paragraph_index"],
                               best["sentence_index"])):
                    best = cand
    return best


def build_fulltext_segment(paper_id: str, connection_id: str, pmid: str,
                           connection_type: str, xml_text: str | None,
                           source_name: str, target_name: str,
                           source_aliases: list[str],
                           target_aliases: list[str]) -> dict:
    """单条关联 → 正文级 segment(extracted)或 no_direct_evidence 行。

    xml_text 为空 → no_direct_evidence(无全文来源)。
    """
    base = {
        "paper_id": paper_id,
        "connection_id": connection_id,
        "evidence_source_type": SOURCE_TYPE_FULLTEXT,
        "extraction_method": EXTRACTION_METHOD,
    }
    now = datetime.now(timezone.utc).isoformat()
    if not xml_text:
        return {
            **base,
            "evidence_text": None,
            "evidence_location": None,
            "section_name": None,
            "confidence": None,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "provenance_json": {
                "source": "paper_fulltext", "paper_id": paper_id,
                "pmid": pmid, "extraction_method": EXTRACTION_METHOD,
                "status": STATUS_NO_DIRECT_EVIDENCE,
                "reason": "no_fulltext_xml",
                "connection_type": connection_type, "generated_at": now,
            },
        }
    try:
        parsed = parse_jats_xml(xml_text)
    except ET.ParseError:
        return {
            **base,
            "evidence_text": None, "evidence_location": None,
            "section_name": None, "confidence": None,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "provenance_json": {
                "source": "paper_fulltext", "paper_id": paper_id,
                "pmid": pmid, "extraction_method": EXTRACTION_METHOD,
                "status": STATUS_NO_DIRECT_EVIDENCE,
                "reason": "xml_parse_error",
                "connection_type": connection_type, "generated_at": now,
            },
        }
    match = find_fulltext_evidence(
        parsed["sections"], region_terms(source_name, source_aliases),
        region_terms(target_name, target_aliases))
    if match is None:
        return {
            **base,
            "evidence_text": None, "evidence_location": None,
            "section_name": None, "confidence": None,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "provenance_json": {
                "source": "paper_fulltext", "paper_id": paper_id,
                "pmid": pmid, "extraction_method": EXTRACTION_METHOD,
                "status": STATUS_NO_DIRECT_EVIDENCE,
                "reason": "no_direct_evidence",
                "connection_type": connection_type, "generated_at": now,
            },
        }
    return {
        **base,
        "evidence_text": match["sentence"],  # 原文真实文本
        "evidence_location": (
            f"fulltext:{match['section_name']}"
            f":paragraph:{match['paragraph_index']}"
            f":sentence:{match['sentence_index']}"),
        "section_name": match["section_name"],
        "confidence": match["confidence"],
        "status": STATUS_EXTRACTED,
        "matched_regions": {"source": match["matched_source"],
                            "target": match["matched_target"]},
        "source_type": SOURCE_TYPE_FULLTEXT,
        "provenance_json": {
            "source": "paper_fulltext", "paper_id": paper_id,
            "pmid": pmid, "extraction_method": EXTRACTION_METHOD,
            "status": STATUS_EXTRACTED,
            "connection_type": connection_type,
            "matched_terms": {"source": match["matched_source"],
                              "target": match["matched_target"]},
            "section_name": match["section_name"],
            "paragraph_index": match["paragraph_index"],
            "sentence_index": match["sentence_index"],
            "generated_at": now,
        },
    }


# ---- SQL(幂等) ----

INSERT_FULLTEXT_SEGMENT_SQL = """\
INSERT INTO paper_connection_evidence_segments
    (paper_id, connection_id, evidence_text, evidence_location,
     extraction_method, confidence, provenance_json, status,
     evidence_source_type, section_name)
VALUES (:paper_id, :connection_id, :evidence_text, :evidence_location,
        :extraction_method, :confidence, :provenance_json, :status,
        :evidence_source_type, :section_name)
ON CONFLICT (paper_id, connection_id, evidence_source_type) DO NOTHING
RETURNING id"""

SELECT_FULLTEXT_SEGMENTS_SQL = """\
SELECT paper_id, connection_id, status, evidence_source_type
FROM paper_connection_evidence_segments"""

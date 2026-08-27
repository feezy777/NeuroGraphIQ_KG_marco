"""Macro Paper Evidence Extraction V1(纯函数规则 + 幂等 SQL)。

建立 Paper → Evidence → Connection 可解释证据链:
  论文摘要(enrichment_json.abstract)中的原文句子作为连接证据片段。

约束(用户要求):
* evidence_text 必须是论文摘要中的原文片段 —— 禁止生成不存在的原文
* 数据来源:paper_sources.enrichment_json.abstract(只处理已有关联的论文)
* 摘要没有明确支持句 → 不生成 evidence_text,标记 status='no_direct_evidence'
* provenance 必须记录:source=paper_abstract / paper_id / pmid /
  extraction_method
* 规则 + LLM 均可 —— 本阶段采用纯规则(确定性、幂等、可解释)

规则(确定性):
1. region 词表 = canonical 名 + 别名(canonical_region_aliases 全语言),
   小写整串包含匹配(≥2 字符,防单字母误报)
2. 支持句 = 同一句同时包含 source 词和 target 词(至少各一命中)
3. 无支持句 → no_direct_evidence(status,evidence_text=NULL)
4. confidence 分级:
   - 0.85  同句双命中 + 连接动词
   - 0.90  同句双命中 + 连接动词 + 方向支持(source 在 target 前)
   - 0.70  同句双命中(无连接动词)
   - 0.60  全部命中词为缩写(≤3 字符,如 SPL/IPL/HIPP)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

EXTRACTION_METHOD = "rule_paper_abstract_v1"
STATUS_EXTRACTED = "extracted"
STATUS_NO_DIRECT_EVIDENCE = "no_direct_evidence"

# 摘要分句:句号/问号/感叹号 + 空白(保留原句文本,禁止改写)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# 连接动词词干(小写子串匹配;词干前缀覆盖单复数/派生形式)
CONNECTION_VERBS = (
    "project", "projection", "terminat", "input", "innervat",
    "connect", "pathway", "tract", "fiber", "fibre", "afferent",
    "efferent", "synapse", "synaptic", "activ", "link", "communicate",
    "receive", "send", "supply",
)

MIN_TERM_LEN = 2  # 词表最短长度(别名如 'CB' 保留,但缩写会降 confidence)
ABBREV_LEN = 3  # 命中词 ≤3 字符视为缩写


def split_sentences(abstract: str) -> list[str]:
    """摘要 → 句子列表(原文逐字,去首尾空白,过滤空句)。"""
    return [s.strip() for s in _SENTENCE_SPLIT.split(abstract or "")
            if s and s.strip()]


def region_terms(name: str, aliases: list[str]) -> list[str]:
    """region 词表:canonical 名 + 别名(小写;去重;≥2 字符)。"""
    terms = []
    for t in [name] + list(aliases or []):
        t = (t or "").strip().lower()
        if len(t) >= MIN_TERM_LEN and t not in terms:
            terms.append(t)
    return terms


def _is_abbrev(term: str) -> bool:
    return len(term) <= ABBREV_LEN


def _has_connection_verb(sentence: str) -> bool:
    sl = sentence.lower()
    return any(v in sl for v in CONNECTION_VERBS)


_ABBREV_CASED_RE_CACHE: dict[str, "re.Pattern"] = {}


def _find_first(terms: list[str], sentence: str) -> tuple[str | None, int]:
    """句子中首个命中词及其位置。

    匹配规则:
    * ≥4 字符词:小写整串包含(保留派生形式召回,如 'cingulate cortex')
    * ≤3 字符缩写(SPL/IPL/CU/ST/IT):必须在原文中**大写独立成词** ——
      解剖缩写论文书写均为大写;防 'cued' 命中 'cu'、'distinctive' 命中
      'st'、代词 'it' 命中 'IT'(Inferior temporal)等误报
    """
    sl = sentence.lower()
    best, best_pos = None, -1
    for t in terms:
        if len(t) <= ABBREV_LEN:
            pattern = _ABBREV_CASED_RE_CACHE.get(t)
            if pattern is None:
                pattern = re.compile(
                    r"(?<![A-Za-z0-9])" + re.escape(t.upper())
                    + r"(?![A-Za-z0-9])")
                _ABBREV_CASED_RE_CACHE[t] = pattern
            m = pattern.search(sentence)
            if not m:
                continue  # 缩写未大写独立成词 → 跳过(误报防护)
            pos = m.start()
        else:
            pos = sl.find(t)
            if pos == -1:
                continue
        if best_pos == -1 or pos < best_pos:
            best, best_pos = t, pos
    return best, best_pos


def find_support_sentence(abstract: str, source_terms: list[str],
                          target_terms: list[str]) -> dict | None:
    """返回第一个同时含 source 词 + target 词的原句。

    None → 摘要没有明确支持句(→ no_direct_evidence)。
    """
    for idx, sentence in enumerate(split_sentences(abstract)):
        s_term, s_pos = _find_first(source_terms, sentence)
        t_term, t_pos = _find_first(target_terms, sentence)
        if s_term and t_term:
            return {
                "sentence": sentence,
                "sentence_index": idx + 1,  # 1-based
                "matched_source": s_term,
                "matched_target": t_term,
                "source_pos": s_pos,
                "target_pos": t_pos,
            }
    return None


def score_confidence(support: dict) -> float:
    """confidence 分级(规则见模块 docstring)。"""
    conf = 0.70  # 同句双命中
    if _has_connection_verb(support["sentence"]):
        conf = 0.85
        # 方向支持:source 词在 target 词前(如 'amygdala projects to hippocampus')
        if support["source_pos"] < support["target_pos"]:
            conf = 0.90
    # 全部命中词为缩写 → 降级(SPL/IPL 等 3 字母缩写易误报)
    if (_is_abbrev(support["matched_source"])
            and _is_abbrev(support["matched_target"])):
        conf = min(conf, 0.60)
    return round(conf, 2)


def build_provenance(paper_id: str, pmid: str, connection_type: str,
                     support: dict | None,
                     generated_at: str | None = None) -> dict:
    """provenance:用户指定 source=paper_abstract + paper_id + pmid +
    extraction_method,附匹配细节。"""
    if support is None:
        return {
            "source": "paper_abstract",
            "paper_id": paper_id,
            "pmid": pmid,
            "extraction_method": EXTRACTION_METHOD,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "reason": "no_direct_evidence",
            "connection_type": connection_type,
            "generated_at": generated_at or
            datetime.now(timezone.utc).isoformat(),
        }
    return {
        "source": "paper_abstract",
        "paper_id": paper_id,
        "pmid": pmid,
        "extraction_method": EXTRACTION_METHOD,
        "status": STATUS_EXTRACTED,
        "connection_type": connection_type,
        "matched_terms": {
            "source": support["matched_source"],
            "target": support["matched_target"],
        },
        "sentence_index": support["sentence_index"],
        "generated_at": generated_at or
        datetime.now(timezone.utc).isoformat(),
    }


def build_segment(paper_id: str, connection_id: str, pmid: str,
                  connection_type: str, abstract: str | None,
                  source_name: str, target_name: str,
                  source_aliases: list[str], target_aliases: list[str]) -> dict:
    """单条关联 → 证据片段(extracted)或 no_direct_evidence 标记行。

    abstract 为空 → status='no_direct_evidence'(无来源,不生成)。
    """
    if not abstract:
        return {
            "paper_id": paper_id,
            "connection_id": connection_id,
            "evidence_text": None,
            "evidence_location": None,
            "extraction_method": EXTRACTION_METHOD,
            "confidence": None,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "provenance_json": build_provenance(
                paper_id, pmid, connection_type, None),
        }
    support = find_support_sentence(
        abstract, region_terms(source_name, source_aliases),
        region_terms(target_name, target_aliases))
    if support is None:
        return {
            "paper_id": paper_id,
            "connection_id": connection_id,
            "evidence_text": None,
            "evidence_location": None,
            "extraction_method": EXTRACTION_METHOD,
            "confidence": None,
            "status": STATUS_NO_DIRECT_EVIDENCE,
            "provenance_json": build_provenance(
                paper_id, pmid, connection_type, None),
        }
    return {
        "paper_id": paper_id,
        "connection_id": connection_id,
        "evidence_text": support["sentence"],  # 摘要原文,逐字
        "evidence_location": f"abstract:sentence:{support['sentence_index']}",
        "extraction_method": EXTRACTION_METHOD,
        "confidence": score_confidence(support),
        "status": STATUS_EXTRACTED,
        "provenance_json": build_provenance(
            paper_id, pmid, connection_type, support),
    }


# ---- SQL(幂等) ----

INSERT_SEGMENT_SQL = """\
INSERT INTO paper_connection_evidence_segments
    (paper_id, connection_id, evidence_text, evidence_location,
     extraction_method, confidence, provenance_json, status)
VALUES (:paper_id, :connection_id, :evidence_text, :evidence_location,
        :extraction_method, :confidence, :provenance_json, :status)
ON CONFLICT (paper_id, connection_id) DO NOTHING
RETURNING id"""

SELECT_SEGMENTS_SQL = """\
SELECT paper_id, connection_id, status FROM paper_connection_evidence_segments"""

SELECT_SEGMENT_ALIASES_SQL = """\
SELECT region_id, alias FROM canonical_region_aliases"""

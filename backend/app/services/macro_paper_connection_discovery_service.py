"""Macro Paper-driven Connection Discovery V1(纯函数规则 + 幂等 SQL)。

论文驱动的候选连接发现(candidate 层,不写 final):
  paper_sources(title/abstract/fulltext 段落 + fullTextXML 缓存)
  → 脑区实体识别(51 区词表:canonical 名 + 别名,含左右半球解析)
  → 同论文 region pair 候选(paper_region_cooccurrence_v1)
  → 命中句证据库(原文 + 上下文,evidence lineage 可追溯)

约束(用户要求):
* 不修改 final_canonical_connections / canonical_connections / paper_sources
* 不直接创建 Connection —— 所有新发现只进 candidate 层候选表
* 本阶段只生成候选,不判断真假(assertion_type='candidate')
* 无外部 API / 无 LLM —— 纯规则,确定性,幂等

规则(确定性):
1. 词表 = Macro96 51 canonical 区名 + 别名(canonical_region_aliases
   全语言);≥2 字符;≤3 字符缩写必须在原文**大写独立成词**
   (防代词 it / 子串 cued 等误报,复用摘要证据链规则)
2. 句子内重叠命中 → 最长词优先;同词多区 → 高置信优先
3. laterality:命中词前后 ~30 字符窗口内 left/right 词元
4. pair 共现级别:same_sentence 0.80 / same_section 0.60 / same_paper 0.40;
   同论文同对合并一条(region_id 排序无向),取最强共现
5. evidence segment:每个命中句保存原文 + 同节前/后句 + 全部命中区
   (sentence_text 逐字,禁止改写)
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.services.macro_paper_evidence_segments_service import (
    _SENTENCE_SPLIT,
)

# 分句(discovery 专用):句号后下一个词以大写/数字/引号开头才切分。
# 防 'i.e.' / 'e.g.' / 'et al.' 的句号误切(v1 共享分句的已知局限,
# 本阶段不改变既有摘要证据链行为)。
SENTENCE_SPLIT_V2 = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(‘“])")


def split_sentences(text: str) -> list[str]:
    """句子列表(原文逐字,去首尾空白,过滤空句)。"""
    return [s.strip() for s in SENTENCE_SPLIT_V2.split(text or "")
            if s and s.strip()]

# ---- 常量 ----

GENERATION_METHOD = "paper_region_cooccurrence_v1"
CREATED_METHOD = "paper_region_ner_v1"
ASSERTION_TYPE = "candidate"
SOURCE_TYPE = "literature"

MATCH_SOURCE_TITLE = "title"
MATCH_SOURCE_ABSTRACT = "abstract"
MATCH_SOURCE_FULLTEXT = "fulltext"

SECTION_TITLE = "Title"       # title 源固定节名
SECTION_ABSTRACT = "Abstract"  # abstract 源固定节名

LAT_UNSPECIFIED = "unspecified"

# kind → confidence(mention 级)
KIND_CONFIDENCE = {
    "canonical": 0.95,   # canonical 名命中
    "alias_en": 0.85,    # en 别名命中
    "alias_cn": 0.80,    # cn 别名命中
    "alias_abbr": 0.60,  # ≤3 字符缩写(大写独立成词已保证)
}

# pair 共现级别 → confidence
COOCCURRENCE_CONFIDENCE = {
    "same_sentence": 0.80,
    "same_section": 0.60,
    "same_paper": 0.40,
}
COOCCURRENCE_ORDER = ["same_sentence", "same_section", "same_paper"]

MIN_TERM_LEN = 2
ABBREV_LEN = 3

# laterality 词元(词边界,命中窗口内搜索)
_LAT_PATTERN = re.compile(r"\b(left|right)s?\-?(hemisphere|sided|side)?\b")
_LAT_WINDOW_CHARS = 30

_ABBREV_RE_CACHE: dict[str, "re.Pattern"] = {}


def _abbrev_pattern(term: str) -> "re.Pattern":
    """缩写:原文大小写独立成词(词边界)。

    按别名原始书写匹配('IT' 匹配 'IT' 不匹配代词 'It';'Hipp' 匹配
    规范书写 'Hipp';小写变体不召回 —— 保守防误报,解剖缩写论文书写
    均为规范形式)。
    """
    pattern = _ABBREV_RE_CACHE.get(term)
    if pattern is None:
        pattern = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(term)
            + r"(?![A-Za-z0-9])")
        _ABBREV_RE_CACHE[term] = pattern
    return pattern


def build_region_lexicon(regions: list[dict]) -> dict[str, list[tuple[str, str]]]:
    """region 列表 → 合并词表 {term(保留原始大小写): [(region_id, kind)]}。

    regions: [{region_id, canonical_name_en, aliases: [(alias, kind)]}]
    合并规则:同词多区全部保留(命中时取最高置信);
    ≥2 字符。缩写判定按**原始词**长度 ≤3 且 ASCII 字母
    (中文 3 字符别名如 '杏仁体' 不按缩写处理;'Hipp' 原始 3 字符
    按缩写,小写化后 4 字符仍保持缩写语义)。
    """
    lexicon: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for region in regions:
        rid = region["region_id"]
        name = (region["canonical_name_en"] or "").strip()
        if len(name) >= MIN_TERM_LEN:
            lexicon[name].append((rid, "canonical"))
        for alias, kind in region.get("aliases", []):
            alias = (alias or "").strip()
            if len(alias) < MIN_TERM_LEN:
                continue
            eff_kind = kind
            if (len(alias) <= ABBREV_LEN
                    and alias.isascii() and alias.isalpha()):
                eff_kind = "alias_abbr"
            if alias not in lexicon:
                lexicon[alias] = []
            lexicon[alias].append((rid, eff_kind))
    # 去重(同一 region 同词只留一个 kind 入口,取高置信)
    for term, entries in lexicon.items():
        seen: dict[str, tuple[str, str]] = {}
        for rid, kind in entries:
            prev = seen.get(rid)
            if prev is None or KIND_CONFIDENCE[kind] > KIND_CONFIDENCE[prev[1]]:
                seen[rid] = (rid, kind)
        lexicon[term] = sorted(seen.values(), key=lambda e: e[0])
    return dict(lexicon)


def _term_confidence(kind: str) -> float:
    return KIND_CONFIDENCE[kind]


def scan_sentence(sentence: str, lexicon: dict) -> list[dict]:
    """句子 → 全部非重叠命中 [{region_id, matched_term(小写), kind,
    confidence, pos, end}]。

    匹配:≥4 字符词(或中文/非 ASCII)小写整串包含;
    ≤3 字符 ASCII 缩写(原始词判定)大写独立成词。
    重叠消解:区间重叠保留最长词(相同长度保留高置信 region)。
    """
    if not sentence:
        return []
    sl = sentence.lower()
    raw_hits: list[dict] = []
    for term_raw, entries in lexicon.items():
        # 缩写判定:原始词 ≤3 ASCII 字母(如 CSF),或任一条目来自
        # alias_abbr(如 'Hipp' 4 字符缩写也按大写独立成词匹配)
        is_abbrev = ((len(term_raw) <= ABBREV_LEN
                      and term_raw.isascii() and term_raw.isalpha())
                     or any(k == "alias_abbr" for _, k in entries))
        t = term_raw.lower()
        if is_abbrev:
            pattern = _abbrev_pattern(term_raw)
            for m in pattern.finditer(sentence):
                for rid, kind in entries:
                    raw_hits.append({
                        "region_id": rid, "matched_term": t,
                        "kind": kind,
                        "confidence": _term_confidence(kind),
                        "pos": m.start(), "end": m.end(),
                    })
        else:
            pos = sl.find(t)
            while pos != -1:
                for rid, kind in entries:
                    raw_hits.append({
                        "region_id": rid, "matched_term": t,
                        "kind": kind,
                        "confidence": _term_confidence(kind),
                        "pos": pos, "end": pos + len(t),
                    })
                pos = sl.find(t, pos + 1)
    if not raw_hits:
        return []

    # 重叠消解:按 pos 排序贪心,区间重叠时保留更长词(或同长高置信)
    raw_hits.sort(key=lambda h: (h["pos"], -(h["end"] - h["pos"]),
                                 -h["confidence"]))
    selected: list[dict] = []
    for hit in raw_hits:
        overlap = False
        for i, sel in enumerate(selected):
            if hit["pos"] < sel["end"] and sel["pos"] < hit["end"]:
                overlap = True
                if (hit["end"] - hit["pos"] > sel["end"] - sel["pos"]):
                    selected[i] = hit  # 长词替换短词
                break
        if not overlap:
            selected.append(hit)
    selected.sort(key=lambda h: h["pos"])
    return selected


def detect_laterality(sentence: str, pos: int, end: int) -> str:
    """命中词前后 ~30 字符窗口内的 left/right 词元 → 半球。

    无命中 → unspecified。窗口内先出现的词元获胜。
    """
    window = sentence[max(0, pos - _LAT_WINDOW_CHARS):end + _LAT_WINDOW_CHARS]
    m = _LAT_PATTERN.search(window)
    if not m:
        return LAT_UNSPECIFIED
    return m.group(1)  # left / right


# ---- 句子结构化 ----

def iter_source_sentences(source: str, section_name: str,
                          text: str, start_id: int = 0) -> tuple[list[dict], int]:
    """单一文本源 → ([句子], 末句序号)。

    sentence_id 为 (source, section) 内连续 1-based 序号,
    start_id 传入已有句数 → 跨段落连续编号(防止同节多段 sentence_id 撞车)。
    """
    sentences = []
    counter = start_id
    for s in split_sentences(text):
        counter += 1
        sentences.append({
            "source": source, "section_name": section_name,
            "sentence_id": counter, "text": s,
        })
    return sentences, counter


def iter_title_sentences(title: str) -> list[dict]:
    """title 源(固定节名 'Title',单句)。"""
    sentences, _ = iter_source_sentences(
        MATCH_SOURCE_TITLE, SECTION_TITLE, title)
    return sentences


def iter_abstract_sentences(paragraphs: list[str]) -> list[dict]:
    """abstract 段落 → 句子(节名固定 'Abstract',跨段连续编号)。"""
    out: list[dict] = []
    counter = 0
    for p in paragraphs:
        sentences, counter = iter_source_sentences(
            MATCH_SOURCE_ABSTRACT, SECTION_ABSTRACT, p, counter)
        out.extend(sentences)
    return out


def iter_fulltext_sentences(sections: list[dict]) -> list[dict]:
    """fulltext 节段落 → 句子(section_name=节名;节内跨段连续编号)。"""
    out: list[dict] = []
    for section in sections:
        name = section.get("name", "") or "Body"
        counter = 0
        for p in section.get("paragraphs", []):
            sentences, counter = iter_source_sentences(
                MATCH_SOURCE_FULLTEXT, name, p, counter)
            out.extend(sentences)
    return out


# ---- 论文级发现 ----

def _section_of(sentence: dict) -> str:
    return sentence["section_name"] or ""


def discover_paper_sentences(sentences: list[dict],
                             lexicon: dict) -> tuple[list[dict], list[dict]]:
    """句子列表 → (hits_by_sentence, mentions)。

    hits_by_sentence: **全部句子**(含空 hits,供上下文查找)
      {**sentence, hits: [...非重叠命中,附 laterality] | []}
    mentions: 每 (paper, region, source, section, sentence) 一条,
      同句同区多词命中聚合为首现词 + 最高置信。
    """
    hits_by_sentence: list[dict] = []
    mentions: list[dict] = []
    for sentence in sentences:
        hits = scan_sentence(sentence["text"], lexicon)
        enriched = []
        for hit in hits:
            laterality = detect_laterality(
                sentence["text"], hit["pos"], hit["end"])
            enriched.append({**hit, "laterality": laterality})
        hits_by_sentence.append({**sentence, "hits": enriched})
        if not enriched:
            continue
        # 聚合:同句同区多条 → 首现词,最高置信
        by_region: dict[str, dict] = {}
        for hit in enriched:
            prev = by_region.get(hit["region_id"])
            if prev is None:
                by_region[hit["region_id"]] = hit
            elif hit["confidence"] > prev["confidence"]:
                by_region[hit["region_id"]] = hit
        for region_id, hit in by_region.items():
            mentions.append({
                "region_id": region_id,
                "matched_term": hit["matched_term"],
                "match_source": sentence["source"],
                "sentence_id": sentence["sentence_id"],
                "section_name": _section_of(sentence),
                "laterality": hit["laterality"],
                "confidence": hit["confidence"],
                "sentence_text": sentence["text"],
            })
    return hits_by_sentence, mentions


def _cooccurrence_hits(hits_by_sentence: list[dict]) -> dict:
    """句子命中 → {(r1, r2): {level, evidence_sentence, section_name,
    sentence_id, source}}。

    对每对区域:先找同句 → 再找同节 → 最后跨节(论文级首现句)。
    每对取最强级别,evidence_sentence 为该级别最早证据句。
    仅统计有命中的句子(空 hits 句子不参与)。
    """
    pairs: dict[tuple[str, str], dict] = {}
    hit_sentences = [s for s in hits_by_sentence if s["hits"]]

    def _reg_ids(rids: list[str]) -> tuple[str, str]:
        return tuple(sorted(rids))

    # 论文级首现句(跨节证据用)
    first_seen: dict[str, dict] = {}
    for sentence in hit_sentences:
        for hit in sentence["hits"]:
            if hit["region_id"] not in first_seen:
                first_seen[hit["region_id"]] = sentence

    # 同节句子分组
    by_section: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for sentence in hit_sentences:
        by_section[(sentence["source"], _section_of(sentence))].append(sentence)

    def _record(r1: str, r2: str, level: str, sentence: dict) -> None:
        key = _reg_ids([r1, r2])
        order = COOCCURRENCE_ORDER.index(level)
        prev = pairs.get(key)
        if prev is None or order < COOCCURRENCE_ORDER.index(prev["level"]):
            pairs[key] = {
                "level": level,
                "evidence_sentence": sentence["text"],
                "section_name": _section_of(sentence),
                "sentence_id": sentence["sentence_id"],
                "source": sentence["source"],
            }

    # 同句
    for sentence in hit_sentences:
        rids = list({h["region_id"] for h in sentence["hits"]})
        for i in range(len(rids)):
            for j in range(i + 1, len(rids)):
                _record(rids[i], rids[j], "same_sentence", sentence)
    # 同节不同句
    for sentences in by_section.values():
        rids = list({h["region_id"] for s in sentences
                     for h in s["hits"]})
        for i in range(len(rids)):
            for j in range(i + 1, len(rids)):
                _record(rids[i], rids[j], "same_section", sentences[0])
    # 跨节(论文级首现句)
    all_rids = list(first_seen.keys())
    for i in range(len(all_rids)):
        for j in range(i + 1, len(all_rids)):
            _record(all_rids[i], all_rids[j], "same_paper",
                    first_seen[all_rids[i]])
    return pairs


def _context_of(hits_by_sentence: list[dict],
                sentence_id: int, section_name: str) -> tuple[str | None, str | None]:
    """同节内证据句的前/后句(最近邻,**含无命中句** —— 上下文是原文)。

    无前/后句(同节首句/末句)→ None。
    """
    same_section = [s for s in hits_by_sentence
                    if _section_of(s) == section_name
                    and s["sentence_id"] != sentence_id]
    before = [s for s in same_section if s["sentence_id"] < sentence_id]
    after = [s for s in same_section if s["sentence_id"] > sentence_id]
    ctx_before = max(before, key=lambda s: s["sentence_id"])["text"] \
        if before else None
    ctx_after = min(after, key=lambda s: s["sentence_id"])["text"] \
        if after else None
    return ctx_before, ctx_after


def build_paper_discovery(hits_by_sentence: list[dict],
                          mentions: list[dict],
                          paper_id: str) -> dict:
    """论文级发现结果 → {mentions(带 paper_id), pairs, segments}。

    pairs: 每对一条 {source_region_id, target_region_id(排序), evidence_sentence,
      context_before/after, section_name, matched_terms, cooccurrence,
      confidence, generation_method, assertion_type, source_type}
    segments: 每个命中句一条 {paper_id, sentence_id, sentence_text,
      context_before/after, section_name, source_type, matched_regions}
    """
    # 句子 → 段落上下文(同节相邻命中句)
    pairs = _cooccurrence_hits(hits_by_sentence)

    pair_rows = []
    for (r1, r2), info in pairs.items():
        ctx_before, ctx_after = _context_of(
            hits_by_sentence, info["sentence_id"], info["section_name"])
        # matched_terms:两端各自在该论文的首现 mention
        src_hit = tgt_hit = None
        for m in mentions:
            if m["region_id"] == r1 and src_hit is None:
                src_hit = m
            if m["region_id"] == r2 and tgt_hit is None:
                tgt_hit = m
        pair_rows.append({
            "paper_id": paper_id,
            "source_region_id": r1, "target_region_id": r2,
            "evidence_sentence": info["evidence_sentence"],
            "context_before": ctx_before,
            "context_after": ctx_after,
            "section_name": info["section_name"],
            "matched_terms": {
                "source": {"term": src_hit["matched_term"],
                           "sentence_id": src_hit["sentence_id"],
                           "laterality": src_hit["laterality"]},
                "target": {"term": tgt_hit["matched_term"],
                           "sentence_id": tgt_hit["sentence_id"],
                           "laterality": tgt_hit["laterality"]},
            },
            "generation_method": GENERATION_METHOD,
            "assertion_type": ASSERTION_TYPE,
            "source_type": SOURCE_TYPE,
            "cooccurrence": info["level"],
            "confidence": COOCCURRENCE_CONFIDENCE[info["level"]],
        })

    segment_rows = []
    for sentence in hits_by_sentence:
        if not sentence["hits"]:
            continue  # 无命中句不建 segment
        if sentence["source"] == MATCH_SOURCE_TITLE:
            continue  # title 源无 source_type 定义(只进 mentions)
        source_type = ("paper_abstract" if sentence["source"]
                       == MATCH_SOURCE_ABSTRACT else "paper_fulltext")
        ctx_before, ctx_after = _context_of(
            hits_by_sentence, sentence["sentence_id"],
            _section_of(sentence))
        segment_rows.append({
            "paper_id": paper_id,
            "sentence_id": sentence["sentence_id"],
            "sentence_text": sentence["text"],
            "context_before": ctx_before,
            "context_after": ctx_after,
            "section_name": _section_of(sentence),
            "source_type": source_type,
            "matched_regions": [{
                "region_id": h["region_id"],
                "matched_term": h["matched_term"],
                "laterality": h["laterality"],
                "confidence": h["confidence"],
            } for h in sentence["hits"]],
            "created_method": CREATED_METHOD,
        })

    return {
        "mentions": [{
            "paper_id": paper_id, **m,
            "created_method": CREATED_METHOD,
        } for m in mentions],
        "pairs": pair_rows,
        "segments": segment_rows,
    }


# ---- SQL(幂等 INSERT,不删不更新) ----

INSERT_MENTION_SQL = """\
INSERT INTO paper_region_mentions
    (paper_id, region_id, matched_term, match_source, sentence_id,
     section_name, laterality, confidence, created_method)
VALUES (:paper_id, :region_id, :matched_term, :match_source,
        :sentence_id, :section_name, :laterality, :confidence,
        :created_method)
ON CONFLICT (paper_id, region_id, match_source, sentence_id, section_name)
DO NOTHING
RETURNING id"""

INSERT_PAIR_SQL = """\
INSERT INTO paper_region_pair_candidates
    (paper_id, source_region_id, target_region_id, evidence_sentence,
     context_before, context_after, section_name, matched_terms,
     generation_method, assertion_type, source_type, cooccurrence,
     confidence)
VALUES (:paper_id, :source_region_id, :target_region_id,
        :evidence_sentence, :context_before, :context_after,
        :section_name, :matched_terms, :generation_method,
        :assertion_type, :source_type, :cooccurrence, :confidence)
ON CONFLICT (paper_id, source_region_id, target_region_id)
DO NOTHING
RETURNING id"""

INSERT_SEGMENT_SQL = """\
INSERT INTO paper_region_evidence_segments
    (paper_id, sentence_id, sentence_text, context_before, context_after,
     section_name, source_type, matched_regions, created_method)
VALUES (:paper_id, :sentence_id, :sentence_text, :context_before,
        :context_after, :section_name, :source_type, :matched_regions,
        :created_method)
ON CONFLICT (paper_id, source_type, section_name, sentence_id)
DO NOTHING
RETURNING id"""

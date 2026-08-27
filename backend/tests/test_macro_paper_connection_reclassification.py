"""Macro Paper-Connection Evidence Reclassification 测试(纯函数,不碰 DB)。

覆盖:三级分类判定(extracted segment → direct_support / 标题·摘要·全文
提及 → context_support / 无信号 → invalid)、direct 优先于提及信号、
全文信号(含解析失败降级)、缩写词边界复用(代词 it 不误报)、
幂等 UPDATE SQL 形状(不删行)。
"""

from app.services.macro_paper_connection_reclassification_service import (
    RELATION_CONTEXT,
    RELATION_DIRECT,
    RELATION_INVALID,
    UPDATE_RELATION_TYPE_SQL,
    classify_link,
    scan_fulltext_mentions,
)
from app.services.macro_paper_evidence_segments_service import (
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
)

JATS = """<?xml version="1.0"?>
<article><body>
  <sec><title>Results</title>
    <p>The amygdala projects to the hippocampus.</p>
  </sec>
</body></article>"""

JATS_NO_HIT = """<?xml version="1.0"?>
<article><body>
  <sec><title>Methods</title>
    <p>Participants were scanned with a 3T MRI.</p>
  </sec>
</body></article>"""


def _link(*, segments=None, title=None, abstract=None, fulltext=None,
          sname="Amygdala", tname="Hippocampus", s_alias=None, t_alias=None):
    return classify_link(
        segment_statuses=segments if segments is not None else [],
        title=title, abstract=abstract, fulltext_xml=fulltext,
        source_name=sname, target_name=tname,
        source_aliases=[s_alias] if s_alias else [],
        target_aliases=[t_alias] if t_alias else [])


# ---- A: direct_support ----

def test_direct_from_abstract_extracted_segment():
    r = _link(segments=[STATUS_EXTRACTED],
              abstract="Amygdala projects to the hippocampus.",
              title="Amygdala projections")
    assert r["relation_type"] == RELATION_DIRECT
    assert r["detail"]["basis"] == "extracted_segment"


def test_direct_priority_over_mention_signals():
    """extracted segment 优先:即使标题/摘要也提及 → 仍 direct_support。"""
    r = _link(segments=[STATUS_EXTRACTED],
              title="Amygdala and hippocampus study",
              abstract="Amygdala and hippocampus were examined.")
    assert r["relation_type"] == RELATION_DIRECT


def test_direct_from_fulltext_extracted_segment():
    r = _link(segments=[STATUS_NO_DIRECT_EVIDENCE, STATUS_EXTRACTED])
    assert r["relation_type"] == RELATION_DIRECT


# ---- B: context_support ----

def test_context_abstract_mentions_target():
    r = _link(abstract="The parahippocampal region was examined.",
              tname="Parahippocampal")
    assert r["relation_type"] == RELATION_CONTEXT
    assert r["detail"]["basis"] == "abstract_mentions"
    assert r["detail"]["abstract"] == {"source": None,
                                       "target": "parahippocampal"}


def test_context_title_only():
    r = _link(title="Cerebellar contributions to cognition",
              sname="Cerebellum", s_alias="cerebella")
    assert r["relation_type"] == RELATION_CONTEXT
    assert r["detail"]["basis"] == "title_mentions"
    assert r["detail"]["title"]["source"] == "cerebella"  # 命中的是别名


def test_context_fulltext_only():
    """标题摘要都无信号,但全文提及 target → context(3 篇全文论文场景)。"""
    r = _link(title="Face processing", abstract="ATL was activated.",
              fulltext=JATS)
    assert r["relation_type"] == RELATION_CONTEXT
    assert r["detail"]["basis"] == "fulltext_mentions"
    assert r["detail"]["fulltext"] == {"source_mentioned": True,
                                       "target_mentioned": True}


def test_context_multiple_signals():
    r = _link(title="Cerebellum anatomy",
              abstract="The cerebellum is involved in ataxia.",
              sname="Cerebellum")
    assert r["relation_type"] == RELATION_CONTEXT
    assert r["detail"]["basis"] == "abstract_mentions+title_mentions"


# ---- C: invalid ----

def test_invalid_no_signals():
    r = _link(title="Cholinergic pathways in the brain",
              abstract="The ascending reticular activating system was studied.")
    assert r["relation_type"] == RELATION_INVALID
    assert r["detail"]["basis"] == "no_mention_signal"


def test_invalid_no_abstract_no_title_hit():
    r = _link(title="Reward processing in humans", abstract=None)
    assert r["relation_type"] == RELATION_INVALID


# ---- 全文信号边界 ----

def test_fulltext_parse_failure_no_signal():
    """XML 解析失败 → 不产生全文信号(不误判)。"""
    ft = scan_fulltext_mentions("<article><body>", ["amygdala"],
                                ["hippocampus"])
    assert ft == {"source_mentioned": False, "target_mentioned": False}
    r = _link(fulltext="<article><body>")
    assert r["relation_type"] == RELATION_INVALID


def test_fulltext_no_mention_no_signal():
    ft = scan_fulltext_mentions(JATS_NO_HIT, ["amygdala"], ["hippocampus"])
    assert ft == {"source_mentioned": False, "target_mentioned": False}


# ---- 缩写词边界复用(IT 代词不误报) ----

def test_abbrev_pronoun_not_counted_as_mention():
    """'It remains debated...' 的 'It' 不命中 IT(Inferior temporal)。

    source 提及(研究相关脑区)→ context_support,但 target 不因代词计提及。
    """
    r = _link(abstract="The amygdala projects to the cortex. "
                       "It remains debated whether this is direct.",
              tname="Inferior temporal", t_alias="IT")
    assert r["relation_type"] == RELATION_CONTEXT  # source 提及
    assert r["detail"]["abstract"]["source"] == "amygdala"
    assert r["detail"]["abstract"]["target"] is None  # 'It' 未命中 IT


def test_abbrev_uppercase_counted_as_mention():
    r = _link(abstract="The amygdala projects to IT and adjacent areas.",
              tname="Inferior temporal", t_alias="IT")
    assert r["relation_type"] == RELATION_CONTEXT
    assert r["detail"]["abstract"]["target"] == "it"


# ---- 幂等 SQL 形状(不删行) ----

def test_update_sql_idempotent_shape():
    assert "UPDATE connection_paper_evidence" in UPDATE_RELATION_TYPE_SQL
    assert "evidence_relation_type IS DISTINCT FROM" in UPDATE_RELATION_TYPE_SQL
    assert "WHERE id = :link_id" in UPDATE_RELATION_TYPE_SQL
    assert "RETURNING id" in UPDATE_RELATION_TYPE_SQL
    assert "DELETE" not in UPDATE_RELATION_TYPE_SQL

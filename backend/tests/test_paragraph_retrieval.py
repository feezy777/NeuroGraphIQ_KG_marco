"""Semantic windowing tests for paragraph retrieval (LLM semantic recall)."""

from app.services.paragraph_retrieval import build_semantic_windows


def _para(pid, text, scope="body", idx=0):
    return {"paragraph_id": pid, "passage_text": text, "source_scope": scope, "paragraph_index": idx}


def test_merges_short_paragraphs_into_blocks():
    paras = [
        _para("p1", "A" * 300, "abstract", 0),
        _para("p2", "B" * 300, "body", 1),
        _para("p3", "C" * 300, "body", 2),
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) == 1
    assert blocks[0]["block_id"] == "p1"
    assert len(blocks[0]["paragraphs"]) == 3


def test_split_long_text_into_multiple_blocks():
    paras = [_para("p1", "X" * 1000, "body", 0), _para("p2", "Y" * 1000, "body", 1)]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) >= 2
    # 块内段落保序、不重复
    all_pids = [p["paragraph_id"] for b in blocks for p in b["paragraphs"]]
    assert all_pids == ["p1", "p2"]


def test_abstract_first():
    paras = [
        _para("p-body", "B" * 600, "body", 0),
        _para("p-abs", "A" * 600, "abstract", 1),
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    # 摘要优先:abstract 段落进第一块
    assert blocks[0]["paragraphs"][0]["source_scope"] == "abstract"


def test_max_windows_cap():
    paras = [_para(f"p{i}", "Z" * 800, "body", i) for i in range(80)]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    assert len(blocks) == 60

### Task 4: extract_passage_two_stage 接入语义块 + 回退

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`extract_passage_two_stage`,约 2402 行;`_extract_from_paper_with_retry` 调用链)

**Interfaces:**
- Consumes: Task 1 的 `build_semantic_windows`、Task 2/3 的 locate/judge
- Produces: 全文语义块 → locate → judge;0 命中回退关键词窗口单阶段

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_paper_evidence_extraction.py`:

```python
def test_two_stage_uses_semantic_blocks_and_falls_back():
    from app.services.paragraph_retrieval import build_semantic_windows
    claim = {"claim_text": "X projects to Y", "structured_claim": {}, "function_term": "connect",
             "claim_components": [], "claim_version": "v1"}
    paras = [
        {"paragraph_id": "p1", "passage_text": "X terminates in Y as shown by tracing.", "section_title": "Results", "paragraph_index": 0, "source_scope": "body"},
        {"paragraph_id": "p2", "passage_text": "Unrelated cell culture methods.", "section_title": "Methods", "paragraph_index": 1, "source_scope": "body"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[
        {"paragraph_id": "b_p1", "relevance": 0.9, "passage_text": "X terminates in Y as shown by tracing.", "section": "Results"},
    ])):
        with patch.object(pes, "judge_candidates", new=AsyncMock(return_value={
            "overall_direction": "supports", "paper_relevance": 0.9,
            "assessment": "支持", "evidence_dimension": "existence",
            "passages": [{"paragraph_id": "p1", "passage": "X terminates in Y as shown by tracing.", "direction": "supports", "confidence": 0.8}],
        })):
            result = _run(pes.extract_passage_two_stage(claim=claim, title="t", windows=blocks))
    assert result["overall_direction"] == "supports"
    assert len(result["passages"]) == 1


def test_two_stage_falls_back_when_locate_empty():
    from app.services.paragraph_retrieval import build_semantic_windows
    claim = {"claim_text": "X projects to Y", "structured_claim": {}, "function_term": "connect",
             "claim_components": [], "claim_version": "v1"}
    paras = [
        {"paragraph_id": "p1", "passage_text": "X projects to Y in macaque.", "section_title": "Abstract", "paragraph_index": 0, "source_scope": "abstract"},
    ]
    blocks = build_semantic_windows(paras, target_chars=800, max_windows=60)
    with patch.object(pes, "locate_candidates", new=AsyncMock(return_value=[])):
        with patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value={
            "overall_direction": "partial", "paper_relevance": 0.4, "assessment": "a",
            "passages": [{"paragraph_id": "p1", "passage": "X projects to Y in macaque.", "direction": "partial", "confidence": 0.3}],
        })):
            result = _run(pes.extract_passage_two_stage(claim=claim, title="t", windows=blocks))
    assert result["overall_direction"] == "partial"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py -q -k two_stage`
Expected: FAIL(locate 对 blocks 结构返回空或序列化失败)

- [ ] **Step 3: 实现**

`extract_passage_two_stage` 改造:

```python
async def extract_passage_two_stage(
    *,
    claim: dict,
    title: str = "",
    windows: list[dict],
    on_stage: ExtractionStageCallback | None = None,
) -> dict:
    """Semantic recall:全文语义块 → LLM 定位 → 命中块严格判定。

    无命中时回退关键词评分窗口(top10)单阶段提取。
    """
    # Stage 1: LLM 语义高召回(对全文语义块)
    await _emit_extraction_stage(on_stage, "locating")
    candidates = await locate_candidates(claim, windows, title)

    if not candidates:
        # 回退:关键词评分窗口 top10 单阶段
        await _emit_extraction_stage(on_stage, "judging")
        result = await extract_passage_from_paper(
            claim=claim, title=title, windows=windows
        )
        result.setdefault("llm_model", get_settings().ontology_residual_model)
        return result

    # Stage 2: 命中块 + 邻块上下文,严格判定
    await _emit_extraction_stage(on_stage, "judging")
    # 构造 judge 输入:命中块全文(含邻块拼接)
    judge_candidates_input = _build_judge_input(windows, candidates)
    result = await judge_candidates(claim, judge_candidates_input, title)

    if result["overall_direction"] == "not_found" and candidates:
        result["_stage1_candidates"] = len(candidates)
        result["_stage1_top_relevance"] = candidates[0]["relevance"] if candidates else 0

    result["_two_stage"] = True
    result["_stage1_candidates"] = len(candidates)
    return result
```

新增 helper `_build_judge_input(blocks, hits)`(拼接命中块 + 前后邻块全文):

```python
def _build_judge_input(blocks: list[dict], hits: list[dict]) -> list[dict]:
    """命中块全文 + 前后各 1 个邻块,供 judge 严格判定。"""
    bid_hit = {h.get("paragraph_id") or h.get("block_id"): h for h in hits}
    ordered = list(blocks)
    idx_of = {b.get("block_id"): i for i, b in enumerate(ordered) if b.get("block_id")}
    out: list[dict] = []
    seen: set[str] = set()
    for b in blocks:
        bid = b.get("block_id")
        if bid not in bid_hit:
            continue
        span_ids = [bid]
        i = idx_of.get(bid)
        if i is not None:
            for nb in (ordered[i - 1], ordered[i + 1]) if i > 0 and i + 1 < len(ordered) else ([ordered[i - 1]] if i > 0 else [ordered[i + 1]]):
                if nb is not None and nb.get("block_id") not in seen:
                    span_ids.append(nb.get("block_id"))
        text = " ".join((p.get("passage_text") or "") for b2 in ordered if b2.get("block_id") in span_ids for p in (b2.get("paragraphs") or []))
        out.append({"paragraph_id": bid, "passage_text": text, "section_title": (b.get("paragraphs") or [{}])[0].get("section_title", "")})
        seen.update(span_ids)
        if len(out) >= 6:
            break
    return out
```

注意:Task 3 的 judge 已改用 `candidates[:6]` + `passage_text`;locate 返回的 passage_text 是块全文,此处用邻块拼接。

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_extraction.py
git commit -m "feat(evidence): two-stage extraction on semantic blocks with keyword-window fallback"
```

---


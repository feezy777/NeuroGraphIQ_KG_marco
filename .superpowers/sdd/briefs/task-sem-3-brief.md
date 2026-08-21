### Task 3: judge_candidates 严格化(要素核对,共现不算证据)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`_JUDGE_USER` prompt + `judge_candidates` 输入与输出处理,约 2290-2400 行)

**Interfaces:**
- Consumes: Task 2 命中块(带 passage_text/section)
- Produces: judge 仅对要素匹配段落给证据;共现降级为 not_found 或空 supported_components

- [ ] **Step 1: 写失败测试(断言新 prompt 指令与严格判定)**

追加到 `tests/test_paper_evidence_extraction.py`:

```python
def test_judge_user_prompt_requires_component_match():
    # prompt 必须包含要素核对与「共现不算证据」指令
    assert "至少" in pes._JUDGE_USER and "supported_components" in pes._JUDGE_USER
    assert "共现" in pes._JUDGE_USER  # 或等价表述「仅同时出现」
```

(prompt 是常量,直接断言指令存在;同时按新 prompt 语义验证 mock LLM 输出 not_found 时 judge 返回 not_found。)

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py -q -k judge_user_prompt`
Expected: FAIL(当前 prompt 无严格指令)

- [ ] **Step 3: 实现**

`_JUDGE_USER` 替换为严格版(核心变化:要素至少两项匹配才给证据;共现不算):

```python
_JUDGE_USER = """待验证的知识主张："{claim}"
结构化主张：{structured}
主张要素：{components}

以下是从论文中筛选出的候选段落。请严格判断，只有段落**实质支持/反对**该主张时才作为证据返回。

规则：
1. passage 逐字复制原文。
2. **要素核对**：对每段检查源脑区(source_region)、靶脑区(target_region)、关系(relation)是否出现（含同义词/缩写/上位结构）。
   - source_region 与 target_region 同段且存在连接/功能描述 → supports/partial
   - 仅出现单个脑区+功能描述 → partial（source_match/target_match 只标匹配项）
   - **仅两个脑区名称共现、无任何连接/功能/临床关联 → 不算证据**（passages 不返回该段，或在 assessment 说明）
3. direction：明确支持=supports；部分关联=partial；明确反对=contradicts；正反混杂=mixed。
4. evidence_level：direct（实验直接证明）/ indirect（合理推断）/ interpretive（Discussion 解读）/ background（Introduction 背景）。
5. evidence_pattern：direct_statement/tracing/tractography/functional_connectivity/anatomical_description/clinical_analysis。
6. not_found：当没有段落实质支持或反对该主张时使用（仅共现不算实质）。
7. supported_components 只列实际匹配的要素。

只返回一个纯JSON：
{{"overall_direction":"supports|partial|contradicts|mixed|not_found","paper_relevance":0.5,
 "assessment":"<1-2句中文>","evidence_dimension":"function|existence|mixed",
 "not_found_reason":"<仅not_found时填写>",
 "passages":[{{"paragraph_id":"<id>","section":"<section>","passage":"<英文原文>",
 "direction":"partial","evidence_level":"background","reason":"<中文>",
 "confidence":0.4,"semantic_confidence":0.4,
 "supported_components":["source_region","target_region"],
 "evidence_dimension":"function","evidence_pattern":"functional_connectivity",
 "source_match":true,"target_match":true,"relation_match":true,
 "direction_match":true,"species_match":true}}]}}

论文标题：{title}
候选段落：
{candidates}"""
```

`judge_candidates` 输入:改为「命中块(完整文本) + 前后邻块」——调用方(Task 4)传 `candidates` 为块列表;judge 内序列化块全文(不做 500 截断,但每块 ≤800 字天然受限):

```python
    candidate_lines = []
    for i, c in enumerate(candidates[:6]):
        text = (c.get("passage_text") or "")
        candidate_lines.append(f"<id={c.get('paragraph_id') or c.get('block_id')}> {text}")
```

(judge 命中块 passage_text 来自 Task 2 的 locate 返回——locate 返回 block_id + 块全文;为给 judge 邻块上下文,调用方拼接。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_extraction.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_extraction.py
git commit -m "feat(evidence): strict judge — component match required, co-occurrence is not evidence"
```

---


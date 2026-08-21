### Task 1: 语义分块函数

**Files:**
- Modify: `backend/app/services/paragraph_retrieval.py`(新增 `build_semantic_windows`)
- Test: `backend/tests/test_paragraph_retrieval.py`(若存在则追加;先 grep)

**Interfaces:**
- Produces: `build_semantic_windows(paragraphs: list[dict], target_chars: int = 800, max_windows: int = 60) -> list[dict]`,每块 `{block_id, paragraphs: [...]}`;Task 2 使用。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 test_paragraph_retrieval.py(不存在则新建,含 import)
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paragraph_retrieval.py -q -k semantic`
Expected: FAIL(ImportError:`cannot import name 'build_semantic_windows'`)

- [ ] **Step 3: 实现**

`paragraph_retrieval.py` 末尾追加:

```python
def build_semantic_windows(
    paragraphs: list[dict],
    target_chars: int = 800,
    max_windows: int = 60,
) -> list[dict]:
    """跨段合并为语义块(保持段落完整、保序)。每块 {block_id, paragraphs}。

    - 摘要段落总在最前(第一块起始);
    - 段落到 target_chars 上限即封块,单段超过上限单独成块;
    - 最多 max_windows 块(超出丢弃尾部,返回可处理的上限)。
    """
    ordered = list(paragraphs)
    # abstract 优先置前
    ordered.sort(key=lambda p: 0 if p.get("source_scope") == "abstract" else 1)

    blocks: list[dict] = []
    current: list[dict] = []
    current_len = 0
    for para in ordered:
        text = para.get("passage_text") or ""
        length = len(text)
        if current and current_len + length > target_chars and current_len >= 1:
            blocks.append({
                "block_id": current[0].get("paragraph_id") or f"block_{len(blocks)}",
                "paragraphs": current,
            })
            current = []
            current_len = 0
            if len(blocks) >= max_windows:
                break
        current.append(para)
        current_len += length
    if current and len(blocks) < max_windows:
        blocks.append({
            "block_id": current[0].get("paragraph_id") or f"block_{len(blocks)}",
            "paragraphs": current,
        })
    return blocks[:max_windows]
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paragraph_retrieval.py -q`
Expected: 全部通过(含新增 4 例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paragraph_retrieval.py backend/tests/test_paragraph_retrieval.py
git commit -m "feat(evidence): build_semantic_windows — paragraph blocks for LLM semantic recall"
```

---


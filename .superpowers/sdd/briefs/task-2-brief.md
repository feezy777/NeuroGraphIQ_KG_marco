### Task 2: `mirror_live_display_name_parts` 中英双名解析

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(在 `mirror_live_display_name` 函数之后新增)
- Test: `backend/tests/test_paper_evidence_display_parts.py`(新建)

**Interfaces:**
- Produces: `mirror_live_display_name_parts(target_type: str, get) -> tuple[str | None, str | None]` — `get` 为列名取值回调(ORM 行 `getattr`,SQL 行 `mapping.get`);中文缺失仅英文、英文缺失仅中文、皆缺 `(None, None)`。Task 5/7 使用。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_display_parts.py`:

```python
# -*- coding: utf-8 -*-
"""mirror_live_display_name_parts:中英文双名解析(纯函数,不触库)。"""

from app.services.paper_evidence_service import mirror_live_display_name_parts as parts


def _get(mapping):
    return lambda c: mapping.get(c)


def test_connection_both_languages():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
        "connection_type": "projection",
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en == "Amygdala → Hippocampus"


def test_connection_cn_missing_keeps_en():
    get = _get({
        "source_region_name_cn": None, "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": "Hippocampus",
    })
    cn, en = parts("connection", get)
    assert cn is None
    assert en == "Amygdala → Hippocampus"


def test_connection_en_missing_keeps_cn():
    get = _get({
        "source_region_name_cn": "杏仁核", "source_region_name_en": "Amygdala",
        "target_region_name_cn": "海马", "target_region_name_en": None,
    })
    cn, en = parts("connection", get)
    assert cn == "杏仁核 → 海马"
    assert en is None


def test_connection_all_missing():
    get = _get({"source_region_name_cn": "", "source_region_name_en": None,
                "target_region_name_cn": "", "target_region_name_en": ""})
    assert parts("connection", get) == (None, None)


def test_circuit_cn_en():
    get = _get({"name_cn": "默认模式网络", "circuit_name": "Default Mode Network"})
    assert parts("circuit", get) == ("默认模式网络", "Default Mode Network")


def test_circuit_cn_only():
    get = _get({"name_cn": "默认模式网络", "circuit_name": None})
    assert parts("circuit", get) == ("默认模式网络", None)


def test_circuit_step_en_only():
    get = _get({"step_name": "input step", "role": "relay"})
    cn, en = parts("circuit_step", get)
    assert cn is None
    assert en == "input step · relay"


def test_circuit_function_cn_en():
    get = _get({"function_term_cn": "记忆巩固", "function_term_en": "memory consolidation"})
    assert parts("circuit_function", get) == ("记忆巩固", "memory consolidation")


def test_region_function_cn_en():
    get = _get({"function_term": "memory consolidation",
                "region_name_cn": "海马", "region_name_en": "Hippocampus"})
    cn, en = parts("region_function", get)
    assert cn == "memory consolidation · 海马"
    assert en == "memory consolidation · Hippocampus"


def test_projection_function_cn_en():
    get = _get({"function_term_cn": "恐惧消退", "function_term": "fear extinction"})
    assert parts("projection_function", get) == ("恐惧消退", "fear extinction")


def test_unknown_type_returns_none_pair():
    assert parts("unknown_type", _get({})) == (None, None)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q`
Expected: FAIL(ImportError:`cannot import name 'mirror_live_display_name_parts'`)

- [ ] **Step 3: 实现**

在 `paper_evidence_service.py` 的 `mirror_live_display_name`(约 727 行)之后新增:

```python
def mirror_live_display_name_parts(target_type: str, get) -> tuple[str | None, str | None]:
    """镜像行中英文双名解析:(cn, en)。各自独立缺失为 None;无法解析返回 (None, None)。

    get 为列名取值回调(ORM 行 getattr / SQL 行 mapping.get),与 mirror_live_display_name 共用规则。
    """
    if target_type in ("connection", "projection"):
        # 注(修订):cn 只取中文列(不做英文兜底),任一侧缺中文则 cn=None,由前端整体回退英文
        src_cn = _clean_text(get("source_region_name_cn"))
        tgt_cn = _clean_text(get("target_region_name_cn"))
        src_en = _clean_text(get("source_region_name_en"))
        tgt_en = _clean_text(get("target_region_name_en"))
        cn = f"{src_cn} → {tgt_cn}" if src_cn and tgt_cn else None
        en = f"{src_en} → {tgt_en}" if src_en and tgt_en else None
        return cn, en
    if target_type == "circuit":
        return _clean_text(get("name_cn")) or None, _clean_text(get("circuit_name")) or None
    if target_type == "circuit_step":
        parts_ = [_clean_text(get("step_name")), _clean_text(get("role"))]
        en = " · ".join(p for p in parts_ if p) or None
        return None, en
    if target_type == "circuit_function":
        return _clean_text(get("function_term_cn")) or None, _clean_text(get("function_term_en")) or None
    if target_type == "region_function":
        term = _clean_text(get("function_term"))
        region_cn = _pick_cn_en(get, "region_name_cn", "region_name_en")
        region_en = _clean_text(get("region_name_en"))
        cn = f"{term} · {region_cn}" if term and region_cn else None
        en = f"{term} · {region_en}" if term and region_en else (term or None)
        return cn, en
    if target_type == "projection_function":
        return _clean_text(get("function_term_cn")) or None, _clean_text(get("function_term")) or None
    return None, None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_display_parts.py
git commit -m "feat(evidence): mirror_live_display_name_parts cn/en pair resolver"
```

---


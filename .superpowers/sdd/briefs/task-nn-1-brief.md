### Task 1: 非神经靶标分类器

**Files:**
- Create: `backend/app/services/evidence_target_classifier.py`
- Test: `backend/tests/test_evidence_target_classifier.py`

**Interfaces:**
- Produces: `classify_target(region_name_cn: str | None, region_name_en: str | None) -> str`(返回 `'neural' | 'non_neural' | 'unknown'`;Task 2 使用)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_evidence_target_classifier.py`:

```python
# -*- coding: utf-8 -*-
"""非神经靶标分类器:脑室/脑脊液/脑膜/脉络丛识别,正常脑区不误伤。"""

from app.services.evidence_target_classifier import classify_target


def test_lateral_ventricle_en():
    assert classify_target(None, "Lateral ventricle") == "non_neural"


def test_ventricle_cn():
    assert classify_target("侧脑室", None) == "non_neural"


def test_third_fourth_ventricle():
    assert classify_target("第三脑室", "Third ventricle") == "non_neural"


def test_cistern_cn_en():
    assert classify_target(None, "Suprasellar cistern") == "non_neural"
    assert classify_target("环池", None) == "non_neural"


def test_csf_subarachnoid():
    assert classify_target(None, "Cerebrospinal fluid") == "non_neural"
    assert classify_target(None, "Subarachnoid space") == "non_neural"


def test_meninges():
    assert classify_target(None, "Dura mater") == "non_neural"
    assert classify_target(None, "Pia mater") == "non_neural"
    assert classify_target("硬脑膜", None) == "non_neural"


def test_choroid_plexus():
    assert classify_target(None, "Choroid plexus") == "non_neural"
    assert classify_target("脉络丛", None) == "non_neural"


def test_falk_tentorium():
    assert classify_target(None, "Falx cerebri") == "non_neural"
    assert classify_target(None, "Tentorium cerebelli") == "non_neural"


def test_real_region_not_mistaken():
    assert classify_target("杏仁核", "Amygdala") == "unknown"
    assert classify_target("前扣带皮层", "Anterior cingulate cortex") == "unknown"
    assert classify_target(None, "Primary somatosensory area, layer 4") == "unknown"


def test_none_inputs():
    assert classify_target(None, None) == "unknown"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_classifier.py -q`
Expected: FAIL(ImportError:`cannot import name 'classify_target'`)

- [ ] **Step 3: 实现**

创建 `backend/app/services/evidence_target_classifier.py`:

```python
"""非神经靶标分类器。

识别「脑区 → 非神经结构」(如侧脑室)这类解剖学上不可能的连接靶标。
纯函数、无 DB;未命中返回 unknown(按神经处理,不误杀)。
"""

from __future__ import annotations

# 非神经结构关键词(子串匹配,大小写不敏感;中文按原样匹配)
_NON_NEURAL_KEYWORDS: tuple[str, ...] = (
    # 脑室系统
    "ventricle", "脑室",
    # 脑脊液/蛛网膜下腔/池
    "cistern", "csf", "cerebrospinal", "subarachnoid", "脑脊液", "蛛网膜下腔", "池",
    # 脑膜
    "meninges", "dura", "pia mater", "arachnoid", "脑膜", "硬脑膜", "软脑膜",
    # 脉络丛
    "choroid plexus", "脉络丛",
    # 硬膜结构
    "falx", "tentorium", "大脑镰", "小脑幕",
)


def classify_target(region_name_cn: str | None, region_name_en: str | None) -> str:
    """判定靶标是否为非神经结构。返回 'neural' | 'non_neural' | 'unknown'。

    - 命中非神经关键词(中英任一)→ 'non_neural';
    - 未命中 → 'unknown'(按神经处理,不误杀;本版本不做神经白名单确认)。
    """
    haystacks = [region_name_en or "", region_name_cn or ""]
    for kw in _NON_NEURAL_KEYWORDS:
        lowered = kw.lower()
        for h in haystacks:
            if lowered in h.lower():
                return "non_neural"
    return "unknown"
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_classifier.py -q`
Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/evidence_target_classifier.py backend/tests/test_evidence_target_classifier.py
git commit -m "feat(evidence): non-neural target classifier (ventricle/CSF/meninges/plexus)"
```

---


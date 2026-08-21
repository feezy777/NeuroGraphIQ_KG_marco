### Task 5: 晋升跳过治理边

**Files:**
- Modify: `backend/app/services/mirror_promotion_service.py`(或实际晋升入口,先 grep `promotion_status` / `awaiting_promotion` 找到晋升处理函数)

**Interfaces:**
- Consumes: item 的 `preprocess_outcome`('non_neural_target' / 'evidence_negated')
- Produces: 晋升流程跳过这两类对象(不入 final_kg)

- [ ] **Step 1: 定位晋升入口**

Run: `grep -rn "promotion_status" backend/app/services/mirror_promotion_service.py | head -5`(或实际文件名;若文件不存在,`grep -rln "awaiting_promotion" backend/app/services/` 找晋升服务)

- [ ] **Step 2: 写失败测试**

按晋升服务现有测试文件(如 `tests/test_mirror_promotion*.py`)追加:构造 `preprocess_outcome='non_neural_target'` 的对象 → 晋升调用应跳过(不产生 final 行);`evidence_negated` 同理;`no_evidence_found` 不跳过(仍可晋升?——按 spec:无证据不跳过,但晋升需要证据……实际晋升条件以现有服务为准:仅当有 review/evidence 才可晋升。测试断言:治理边即使有 review 也不晋升)。

具体测试以晋升服务实际签名为准(计划落地时按现有测试模式写)。

- [ ] **Step 3: 实现**

晋升处理函数(定位到实际函数)中,对象查询或晋升判定处加入:

```python
            if outcome in ("non_neural_target", "evidence_negated"):
                # 治理边:结构性不存在 / 证据否定 → 永久跳过晋升
                continue  # 或按现有循环结构跳过该对象
```

(`outcome` 来自 item.preprocess_outcome;查询已含该列。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_mirror_promotion*.py -q`
Expected: 全部通过(含新增用例)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/<晋升服务>.py backend/tests/<晋升测试>.py
git commit -m "feat(evidence): promotion skips structurally-impossible and negated edges"
```

---


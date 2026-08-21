### Task 11: 清理与全量回归

**Files:**
- Delete: `frontend/src/pages/data-center/evidence-workbench/`(目录清空后删除;若 types 仍被 data-center 其他文件引用,先改引用)
- Modify: `frontend/src/pages/data-center/PaperEvidencePanel.tsx`(若引用 workbench 组件则改路径或删除——检查)
- Test: 后端 `tests/test_paper_evidence*.py` + `test_paper_library_api.py`;前端全部

- [ ] **Step 1: 检查残留引用**

Run: `cd frontend/src && grep -rn "evidence-workbench" .`
Expected: 无输出(有则改路径到 evidence-center/components)

- [ ] **Step 2: 删除旧目录**

```bash
git rm -r frontend/src/pages/data-center/evidence-workbench
```

- [ ] **Step 3: 全量验证**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_evidence*.py tests/test_paper_library_api.py tests/test_paper_retrieval_phase2.py -q   # 期望全绿
cd frontend && npx vitest run && npm run build   # 期望全绿
```

- [ ] **Step 4: 提交**

```bash
git commit -am "refactor(evidence-center): 清理旧 evidence-workbench 目录"
```

---


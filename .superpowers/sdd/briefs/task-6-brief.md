### Task 6: 统一任务端点 label 改用对象名

**Files:**
- Modify: `backend/app/routers/unified_tasks.py`(`_paper_evidence`,约 228-258 行)

**Interfaces:**
- Consumes: Task 5 的 `display_name_cn/display_name_en`

- [ ] **Step 1: 修改 label**

将 `_paper_evidence` 中的:

```python
                    label=f"论文佐证 · {item['target_type']}",
```

替换为:

```python
                    label=(
                        item.get("display_name_cn")
                        or item.get("display_name_en")
                        or f"论文佐证 · {item['target_type']}"
                    ),
```

- [ ] **Step 2: 运行相关测试确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q -k "unified or tasks_runs"`
Expected: 无失败(若环境无该关键字测试,0 收集也算通过;随后跑 Task 12 全量回归兜底)

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/unified_tasks.py
git commit -m "feat(evidence): unified task label uses object display name"
```

---


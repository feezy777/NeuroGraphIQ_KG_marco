### Task 12: 样式 + 全量验收

**Files:**
- Modify: `frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 10/11 的 `evidence-task-card-title`、`evidence-task-card-meta`、`evidence-task-card-confidence`、`evidence-task-card-remark`、`evidence-task-filter-chips`、`evidence-left-hint`

- [ ] **Step 1: 追加样式**

`frontend/src/styles.css` 末尾追加:

```css
/* ── 佐证任务对象卡(一对一)── */
.evidence-task-card-title {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-task-card-meta {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-top: 4px;
}
.evidence-task-card-confidence {
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--accent, #1a73e8);
}
.evidence-task-card-remark {
  margin-top: 4px;
  font-size: 0.8rem;
  color: var(--text-muted, #8a94a6);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-task-filter-chips {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
}
.evidence-left-hint {
  padding: 12px;
  margin-bottom: 10px;
  border-radius: 8px;
  background: var(--bg-soft, #f3f6fa);
  color: var(--text-muted, #8a94a6);
  font-size: 0.85rem;
}
```

- [ ] **Step 2: 前端全量测试**

Run: `cd frontend && npx vitest run`
Expected: 全部通过(含新增 14 个用例)

- [ ] **Step 3: 前端构建**

Run: `cd frontend && npm run build`
Expected: 0 TypeScript 错误

- [ ] **Step 4: 后端全量回归**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`
Expected: 全部通过(约 294 个用例)

- [ ] **Step 5: 手工验收(启动中的前后端)**

1. 打开 http://localhost:5173 → 验证中心 → 佐证任务:
   - 卡片标题为「中文 (英文)」,副行类型+置信度,状态徽章;
   - 排序:处理中→待验证→已完成→失败,组内置信度升序;
   - 点卡片 → 跳到证据候选页,URL 含 `module=candidates&task_id=…&target_*`,左栏显示 Claim;
   - 「已取消」「空任务」卡片不再出现。
2. 创建批量预处理 → 消息「任务已创建(N 个对象任务)」,列表出现 N 张对象卡。
3. 数据中心「论文佐证」入口行为不变。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/styles.css
git commit -m "style(evidence-ui): object task card + filter chips + left hint styles"
```

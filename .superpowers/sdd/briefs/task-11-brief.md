### Task 11: 创建对话框消息 + 左栏 Claim 面板 + 页面测试更新

**Files:**
- Modify: `frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx`(成功消息)
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`(tasks 左栏改 ClaimSummaryPanel + 空态提示;删除 TaskPendingQueue import)
- Test: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`

**Interfaces:**
- Consumes: Task 8 的 `task_ids`

- [ ] **Step 1: 对话框消息**

`CreateBatchTaskDialog.tsx` 中:

```typescript
      setMessage(`任务已创建（${r.target_count} 个对象）`)
```

替换为:

```typescript
      setMessage(`任务已创建（${r.task_ids?.length ?? r.target_count} 个对象任务）`)
```

- [ ] **Step 2: 左栏改 Claim 面板**

`EvidenceCenterPage.tsx`:
1. 删除 `import { TaskPendingQueue } from './components/TaskPendingQueue'`。
2. 将 tasks 左栏分支(约 94-96 行):

```tsx
            {state.module === 'tasks' ? (
              <TaskPendingQueue />
            ) : state.module === 'review' || state.module === 'promotion' ? (
```

替换为:

```tsx
            {state.module === 'tasks' ? (
              <>
                {!candidateClaim && (
                  <div className="evidence-left-hint" data-testid="evidence-left-hint">
                    点击任务卡片查看验证事实
                  </div>
                )}
                <ClaimSummaryPanel
                  claimText={candidateClaim?.claimText ?? ''}
                  components={candidateClaim?.components ?? []}
                  targetType={candidateClaim?.targetType ?? ''}
                  granularity={candidateClaim?.granularity ?? null}
                />
              </>
            ) : state.module === 'review' || state.module === 'promotion' ? (
```

(TaskPendingQueue 组件文件保留,不再被页面引用。)

- [ ] **Step 3: 更新页面测试**

`EvidenceCenterPage.test.tsx`:

1. `TASK_FIXTURE` 补字段:

```typescript
  target_id: 'r1-r2', display_name_cn: 'R1→R2', display_name_en: 'R1→R2',
  display_confidence: 0.2, display_name_source: 'mirror_live', display_confidence_source: 'mirror_live',
  work_status: 'awaiting_review',
  item_counts: { total: 1, processing: 0, pending: 0, awaiting_review: 1, completed: 0, skipped: 0, failed: 0, cancelled: 0 },
  capabilities: { can_continue_review: true, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false },
```

2. 「tasks 布局」用例(`it('tasks 布局:左栏待处理队列…')`)替换为:

```tsx
  it('tasks 布局:左栏 Claim 面板(空态提示),右栏已处理面板', async () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-processed-panel')).toBeTruthy())
    expect(screen.getByTestId('evidence-left-hint')).toBeTruthy()
    expect(screen.getByText('点击任务卡片查看验证事实')).toBeTruthy()
    fireEvent.click(screen.getByText('证据候选'))
    await waitFor(() => expect(screen.getByTestId('evidence-queue-panel')).toBeTruthy())
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })
```

3. 「中栏对象点击 → 选中来源任务并打开工作区」用例替换为(卡片点击跳转在模块测试已覆盖,页面级验证接线):

```tsx
  it('任务卡点击 → 页面切换到 candidates 模块并带 task/target 参数', async () => {
    const taskA = { ...TASK_FIXTURE, id: 'ta' }
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [taskA], total: 1 })
    vi.mocked(listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    window.location.hash = '#/evidence-center?module=tasks'
    render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByTestId('evidence-task-card-ta')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-card-ta'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=ta')
    expect(window.location.hash).toContain('target_id=r1-r2')
  })
```

4. 「tasks 三栏常显」用例中 `getAllByText('R1→R2')` 的断言保留(标题来自卡片),其余不动。

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.tsx frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx
git commit -m "feat(evidence-ui): tasks left column Claim panel; batch dialog counts object tasks"
```

---


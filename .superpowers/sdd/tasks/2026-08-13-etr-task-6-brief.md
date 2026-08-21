# Task 6: 已完成区 + 回退重新审查（含前端 API wrapper）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 6（BASE: 9d30427）

**Files:**
- Modify: `frontend/src/api/endpoints.ts`（在 `completePaperEvidenceTaskItem` 定义之后追加 `reopenPaperEvidenceTaskItem`;**文件工作树中有未提交改动,必须保留,只做追加**）
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`（已完成折叠区 + 两步确认回退）
- Modify: `frontend/src/pages/evidence-center/components/TaskItemQueue.test.tsx`（追加已完成区用例）
- Modify: `frontend/src/styles.css`（文件末尾追加已完成区样式;**有未提交改动,只追加**）

**Interfaces:**
- Consumes: Task 1 后端端点;Task 5 `TaskItemQueue`。
- Produces: `reopenPaperEvidenceTaskItem(taskId, itemId) => Promise<{ task_id; item_id; status }>`;已完成区 toggle `data-testid="evidence-queue-done-toggle"`、条目 `data-testid="evidence-queue-done-item-{target_id}"`、回退按钮 `data-testid="evidence-queue-reopen-{target_id}"`。

## Steps

### Step 1: 追加失败测试

在 `TaskItemQueue.test.tsx` 的 describe 块内追加（`makeItem/queueItemIds` 辅助函数已存在）:

```tsx
  it('已完成折叠区:展开显示 completed 条目,按完成时间倒序', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [
        makeItem({ id: 'a', target_id: 'done-old', status: 'completed', updated_at: '2026-08-09T00:00:00Z' }),
        makeItem({ id: 'b', target_id: 'done-new', status: 'completed', updated_at: '2026-08-12T00:00:00Z' }),
        makeItem({ id: 'c', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
      ],
    })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    const { container } = render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('live')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    await waitFor(() => expect(screen.getByText('done-new')).toBeTruthy())
    const doneIds = Array.from(container.querySelectorAll('[data-testid^="evidence-queue-done-item-"]'))
      .map(el => (el as HTMLElement).dataset.testid ?? '')
    expect(doneIds).toEqual(['evidence-queue-done-item-done-new', 'evidence-queue-done-item-done-old'])
  })

  it('回退两步确认:第一次点击变确认态,第二次调用 reopen 并刷新队列', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems)
      .mockResolvedValueOnce({
        items: [
          makeItem({ id: 'a', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
          makeItem({ id: 'b', target_id: 'done-1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' }),
        ],
      })
      .mockResolvedValueOnce({
        items: [
          makeItem({ id: 'a', target_id: 'live', status: 'awaiting_review', current_confidence: 0.5 }),
          makeItem({ id: 'b', target_id: 'done-1', status: 'awaiting_review', current_confidence: 0.6 }),
        ],
      })
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('live')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    const reopenBtn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(reopenBtn())
    expect(reopenBtn().textContent).toContain('确认回退?')
    fireEvent.click(reopenBtn())
    await waitFor(() => expect(vi.mocked(endpoints.reopenPaperEvidenceTaskItem)).toHaveBeenCalledWith('t1', 'b'))
    await waitFor(() => expect(screen.getAllByTestId('evidence-queue-item-done-1')).toHaveLength(1))
  })

  it('回退接口失败 → 错误提示,已完成区不变', async () => {
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({
      items: [makeItem({ id: 'b', target_id: 'done-1', status: 'completed', updated_at: '2026-08-12T00:00:00Z' })],
    })
    vi.mocked(endpoints.reopenPaperEvidenceTaskItem).mockRejectedValueOnce(new Error('boom'))
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    render(<EvidenceCenterProvider><TaskItemQueue /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('evidence-queue-done-toggle')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-queue-done-toggle'))
    const btn = () => screen.getByTestId('evidence-queue-reopen-done-1')
    fireEvent.click(btn())
    fireEvent.click(btn())
    await waitFor(() => expect(screen.getByText(/回退失败/)).toBeTruthy())
    expect(screen.getByTestId('evidence-queue-done-item-done-1')).toBeTruthy()
  })
```

注意:回退成功后条目回到待处理区,其 testid 变为 `evidence-queue-item-done-1`(待处理区前缀)。

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: FAIL —— 找不到 `evidence-queue-done-toggle`(3 条新增失败)

### Step 3: 前端 API wrapper

在 `frontend/src/api/endpoints.ts` 的 `completePaperEvidenceTaskItem` 定义之后追加:

```ts
export const reopenPaperEvidenceTaskItem = (taskId: string, itemId: string) =>
  postJson<{ task_id: string; item_id: string; status: string }>(
    `/api/ontology/evidence/batch/${taskId}/items/${itemId}/reopen`,
  )
```

### Step 4: TaskItemQueue 追加已完成区

`frontend/src/pages/evidence-center/components/TaskItemQueue.tsx`:

imports 变更 —— lucide 改 `import { ChevronDown, ChevronRight, Inbox } from 'lucide-react'`;endpoints import 加 `reopenPaperEvidenceTaskItem`:

```tsx
import {
  listPaperEvidenceTaskItems,
  reopenPaperEvidenceTaskItem,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
```

组件内 state 区追加:

```tsx
  const [doneOpen, setDoneOpen] = useState(false)
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
```

`unfinished/filtered` memo 之后追加:

```tsx
  const doneItems = useMemo(
    () => items.filter(it => it.status === 'completed').sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')),
    [items],
  )

  const handleReopen = useCallback(async (item: PaperEvidenceTaskItem) => {
    if (confirmId !== item.id) {
      setConfirmId(item.id)
      window.setTimeout(() => {
        setConfirmId(prev => (prev === item.id ? null : prev))
      }, 3000)
      return
    }
    setConfirmId(null)
    setReopeningId(item.id)
    setActionError(null)
    try {
      await reopenPaperEvidenceTaskItem(taskId ?? '', item.id)
      await loadItems()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, taskId, loadItems])
```

JSX:在待处理区(`filtered.length > 0` 块)之后、根 div 结束标签之前插入:

```tsx
      <div className="evidence-queue-done" data-testid="evidence-queue-done">
        <button
          type="button"
          className="evidence-queue-done-toggle"
          data-testid="evidence-queue-done-toggle"
          onClick={() => setDoneOpen(o => !o)}
        >
          <span>已完成 {doneItems.length}</span>
          {doneOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {doneOpen && (
          <>
            {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>回退失败:{actionError}</div>}
            {doneItems.length === 0 && <span className="ew-meta">暂无已完成对象</span>}
            {doneItems.map(item => (
              <div key={item.id} className="evidence-queue-done-item" data-testid={`evidence-queue-done-item-${item.target_id}`}>
                <div className="evidence-queue-done-main">
                  <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
                  <span className="evidence-conn-card-type">{item.target_type}</span>
                  <span className="evidence-task-chip evidence-task-chip-ok">已完成</span>
                </div>
                <button
                  type="button"
                  className="btn btn-xs"
                  data-testid={`evidence-queue-reopen-${item.target_id}`}
                  disabled={reopeningId === item.id}
                  onClick={() => void handleReopen(item)}
                >
                  {reopeningId === item.id ? '回退中…' : (confirmId === item.id ? '确认回退?' : '回退重新审查')}
                </button>
              </div>
            ))}
          </>
        )}
      </div>
```

### Step 5: styles.css 文件末尾追加

```css
/* ── 佐证任务右栏:已完成折叠区 ── */
.evidence-queue-done { border-top: 1px dashed var(--border); padding-top: 8px; display: flex; flex-direction: column; gap: 8px; }
.evidence-queue-done-toggle {
  display: flex; align-items: center; gap: 4px; border: none; background: none;
  color: var(--text-muted); font-size: 12px; cursor: pointer; padding: 0;
}
.evidence-queue-done-item {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--white);
}
.evidence-queue-done-main { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
```

### Step 6: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: PASS —— 8 passed

## 硬约束

- **不要执行任何 git 操作**——提交由控制器做外科式处理。
- 只允许改动上述 4 个文件。不改后端、不改候选/审核/晋升模块。
- endpoints.ts 与 styles.css 已有其他未提交改动,必须保留,只做本任务指定的追加。
- 测试断言不要检查 `module=tasks` URL 字符串。

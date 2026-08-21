### Task 5: 佐证任务模块(EvidenceTasksModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`
- Test: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`

**Interfaces:**
- Consumes: `useEvidenceCenter().openTask/openTarget`;`listPaperEvidenceTasks`/`getPaperEvidenceTask`(endpoints.ts:5586/5588);`CreateBatchTaskDialog`(components/)
- Produces: 状态分组列表(待处理/预处理中/待人工审核/已审核/已完成/失败),列:label/target_type/current_confidence/evidenceCount/preprocess/review/status;按钮:开始人工处理(openTarget)、创建批量预处理(对话框)、打开已有任务(openTask)、跳转待审核

- [ ] **Step 1: 写失败测试**(mock `listPaperEvidenceTasks`)

`EvidenceTasksModule.test.tsx`(关键断言):
```tsx
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  getPaperEvidenceTask: vi.fn(),
}))

const TASK = {
  id: 't1', target_type: 'connection', name: '任务一', status: 'pending',
  total_items: 2, processed_items: 0, awaiting_review_items: 2, failed_items: 0,
  review_status: 'not_started', granularity_level: 'macro',
  estimated_target_count: 2, materialized_target_count: 2,
  scope: 'filter', mode: 'existence', max_papers_per_object: 3,
  created_at: '2026-08-10T00:00:00Z', created_by: null,
  started_at: null, finished_at: null, error_message: null, materialization_status: 'completed',
  materialization_cursor: null, materialization_error: null, confidence_lt: null,
  only_oa: false, stop_after_strong_support: false, summary: null,
  scope_type: 'filter', filter_snapshot: null, versions: null,
}

describe('EvidenceTasksModule', () => {
  afterEach(() => cleanup())
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [TASK], total: 1 })
  })

  it('渲染任务列表与状态分组', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    expect(screen.getByText('待处理')).toBeTruthy()
    expect(screen.getByText('connection')).toBeTruthy()
  })

  it('创建批量预处理打开对话框', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('创建批量预处理')).toBeTruthy())
    fireEvent.click(screen.getByText('创建批量预处理'))
    expect(screen.getByTestId('create-batch-dialog')).toBeTruthy()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
Expected: FAIL

- [ ] **Step 3: 实现模块**

`EvidenceTasksModule.tsx` 核心(状态分组 + 操作):
```tsx
import { useCallback, useEffect, useState } from 'react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'

const STATUS_GROUPS = [
  { key: 'pending', label: '待处理', match: (t: PaperEvidenceTask) => t.status === 'pending' },
  { key: 'preprocessing', label: '预处理中', match: (t: PaperEvidenceTask) => ['running', 'paused'].includes(t.status) },
  { key: 'awaiting', label: '待人工审核', match: (t: PaperEvidenceTask) => t.awaiting_review_items > 0 },
  { key: 'reviewed', label: '已审核', match: (t: PaperEvidenceTask) => t.review_status === 'completed' },
  { key: 'done', label: '已完成', match: (t: PaperEvidenceTask) => t.status === 'completed' && t.awaiting_review_items === 0 },
  { key: 'failed', label: '失败', match: (t: PaperEvidenceTask) => t.failed_items > 0 || t.status === 'failed' },
]
```
渲染:分组标题 + 任务行(对象名/target_type/confidence 缺省显示任务级字段/evidenceCount=awaiting_review_items+processed_items 等);每行按钮:开始人工处理(`openTarget(task.target_type, 首条 target_id)`——简化:该任务首批待审对象经 `getPaperEvidenceTask` 取 items 后 openTarget)/打开任务(openTask)/跳转待审核(openTask)。

- [ ] **Step 4: 运行测试确认通过 + build**

- [ ] **Step 5: 提交**

```bash
git commit -am "feat(evidence-center): 佐证任务模块"
```

---


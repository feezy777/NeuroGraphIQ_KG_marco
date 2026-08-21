# Task 2: 前端纯工具（队列排序/筛选分组 + 任务列表排序）

来源：`docs/superpowers/plans/2026-08-13-evidence-tasks-page-redesign.md` Task 2（BASE: 57d7831）

**Files:**
- Create: `frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts`
- Modify: `frontend/src/pages/evidence-center/components/taskStatus.ts`（文件末尾追加任务排序工具）
- Test: `frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts`（新建）

**Interfaces（Task 3/4/5 依赖，签名必须完全一致）:**
- `UNFINISHED_ITEM_STATUSES: string[]`
- `isUnfinishedItem(item: PaperEvidenceTaskItem): boolean`
- `sortByConfidenceAsc(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[]`（null 置信度最前，升序，label 兜底 target_id 稳定排序）
- `TARGET_TYPE_GROUPS: { key: 'circuit'|'connection'|'function'; label: string; types: string[] }[]`
- `groupOf(targetType: string): 'circuit'|'connection'|'function'|'other'`
- `taskSortRank(t: { status: string; awaiting_review_items: number }): number`（0=进行中 1=有等待审核 2=其他）

## Steps

### Step 1: 写失败测试

```tsx
// frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts
import { describe, expect, it } from 'vitest'
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'
import { groupOf, isUnfinishedItem, sortByConfidenceAsc, TARGET_TYPE_GROUPS, UNFINISHED_ITEM_STATUSES } from './taskItemQueueUtils'
import { taskSortRank } from './taskStatus'

function makeItem(overrides: Partial<PaperEvidenceTaskItem>): PaperEvidenceTaskItem {
  return {
    id: 'i', target_type: 'connection', target_id: 't', status: 'pending', pmid: null, title: null,
    passage: null, direction: null, confidence: null, evidence_id: null, error_message: null,
    updated_at: null, label: 'L', current_confidence: null, attempt_count: 0, last_error_code: null,
    last_error_message: null, preprocess_outcome: null, paper_id: null, model_direction: null,
    candidate_papers: null, review_draft: null, claim_text_snapshot: null, claim_components_snapshot: null,
    passages_json: null, last_error: null, retry_count: 0, ...overrides,
  }
}

describe('taskItemQueueUtils', () => {
  it('未完成状态集合判定', () => {
    for (const s of UNFINISHED_ITEM_STATUSES) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(true)
    for (const s of ['completed', 'skipped', 'failed', 'cancelled']) expect(isUnfinishedItem(makeItem({ status: s }))).toBe(false)
  })

  it('置信度排序:null 最前,升序,同值按 label', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'a', label: 'a', current_confidence: 0.9 }),
      makeItem({ id: 'b', label: 'b', current_confidence: null }),
      makeItem({ id: 'c', label: 'c', current_confidence: 0.4 }),
      makeItem({ id: 'd', label: 'd', current_confidence: 0.4, target_id: 'td' }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['b', 'c', 'd', 'a'])
  })

  it('排序在同置信度下按 label 稳定排序,label 缺失兜底 target_id', () => {
    const sorted = sortByConfidenceAsc([
      makeItem({ id: 'x', label: 'Beta', current_confidence: 0.5 }),
      makeItem({ id: 'y', label: null, target_id: 'zzz', current_confidence: 0.5 }),
      makeItem({ id: 'z', label: 'Alpha', current_confidence: 0.5 }),
    ])
    expect(sorted.map(i => i.id)).toEqual(['z', 'x', 'y'])
  })

  it('类型分组映射:回路/连接/功能/其他', () => {
    expect(groupOf('circuit')).toBe('circuit')
    expect(groupOf('circuit_step')).toBe('circuit')
    expect(groupOf('circuit_function')).toBe('circuit')
    expect(groupOf('connection')).toBe('connection')
    expect(groupOf('projection')).toBe('connection')
    expect(groupOf('region_function')).toBe('function')
    expect(groupOf('projection_function')).toBe('function')
    expect(groupOf('unknown_type')).toBe('other')
    expect(TARGET_TYPE_GROUPS.map(g => g.label)).toEqual(['回路', '连接', '功能'])
  })

  it('任务列表排序秩:进行中 < 有等待审核 < 其他', () => {
    expect(taskSortRank({ status: 'running', awaiting_review_items: 0 })).toBe(0)
    expect(taskSortRank({ status: 'paused', awaiting_review_items: 2 })).toBe(0)
    expect(taskSortRank({ status: 'completed', awaiting_review_items: 3 })).toBe(1)
    expect(taskSortRank({ status: 'completed', awaiting_review_items: 0 })).toBe(2)
    expect(taskSortRank({ status: 'failed', awaiting_review_items: 0 })).toBe(2)
  })
})
```

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskItemQueueUtils.test.ts`
Expected: FAIL —— Cannot find module './taskItemQueueUtils'

### Step 3: 实现工具文件

```ts
// frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts
import type { PaperEvidenceTaskItem } from '../../../api/endpoints'

/** 未完成(仍待处理)的任务项状态集合 —— 进入待处理队列 */
export const UNFINISHED_ITEM_STATUSES = [
  'pending', 'searching', 'fetching', 'retrieving', 'extracting', 'verifying', 'awaiting_review',
]

export function isUnfinishedItem(item: PaperEvidenceTaskItem): boolean {
  return UNFINISHED_ITEM_STATUSES.includes(item.status)
}

/** 待处理队列排序:置信度升序(低置信度最优先),null 置信度排最前,同置信度按 label(兜底 target_id)稳定排序 */
export function sortByConfidenceAsc(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[] {
  return [...items].sort((a, b) => {
    const ca = a.current_confidence
    const cb = b.current_confidence
    const labelA = a.label || a.target_id
    const labelB = b.label || b.target_id
    if (ca == null && cb == null) return labelA.localeCompare(labelB)
    if (ca == null) return -1
    if (cb == null) return 1
    if (ca !== cb) return ca - cb
    return labelA.localeCompare(labelB)
  })
}

export type TargetTypeGroup = 'circuit' | 'connection' | 'function' | 'other'

/** 队列类型筛选分组:回路 / 连接 / 功能(PRD R4 映射) */
export const TARGET_TYPE_GROUPS: { key: 'circuit' | 'connection' | 'function'; label: string; types: string[] }[] = [
  { key: 'circuit', label: '回路', types: ['circuit', 'circuit_step', 'circuit_function'] },
  { key: 'connection', label: '连接', types: ['connection', 'projection'] },
  { key: 'function', label: '功能', types: ['region_function', 'projection_function'] },
]

export function groupOf(targetType: string): TargetTypeGroup {
  const g = TARGET_TYPE_GROUPS.find(x => x.types.includes(targetType))
  return g ? g.key : 'other'
}
```

在 `frontend/src/pages/evidence-center/components/taskStatus.ts` 末尾追加：

```ts
/** 进行中任务状态(任务列表置顶排序第一组) */
export const IN_PROGRESS_TASK_STATUSES = ['pending', 'running', 'paused']

/** 任务列表排序秩:0=进行中,1=有等待审核,2=其他;同组内按创建时间倒序 */
export function taskSortRank(t: { status: string; awaiting_review_items: number }): number {
  if (IN_PROGRESS_TASK_STATUSES.includes(t.status)) return 0
  if (t.awaiting_review_items > 0) return 1
  return 2
}
```

### Step 4: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/components/taskItemQueueUtils.test.ts`
Expected: PASS —— 5 passed

### Step 5: 提交

```bash
git add frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts frontend/src/pages/evidence-center/components/taskItemQueueUtils.test.ts frontend/src/pages/evidence-center/components/taskStatus.ts
git commit -m "feat(evidence-center): 队列排序/类型分组与任务列表排序纯工具 + 单测"
```

## 硬约束

- 只允许改动上述 3 个文件。工作树中有大量其他未提交改动，**绝不可 `git add -A` / `git add .`**，提交必须按上面列出的精确路径。
- 不修改任何其他文件（包括 backend）。
- 提交消息不加 Co-Authored-By。
- `PaperEvidenceTaskItem` 类型已在 `frontend/src/api/endpoints.ts` 中定义，直接 import type。

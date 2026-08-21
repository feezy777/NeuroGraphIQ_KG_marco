### Task 3: EvidenceCenterContext(状态 + URL 同步 + sessionStorage)

**Files:**
- Create: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`
- Create: `frontend/src/pages/evidence-center/evidenceCenterUrl.ts`(URL 解析/构建纯函数)
- Test: `frontend/src/pages/evidence-center/evidenceCenterUrl.test.ts`(纯函数)

**Interfaces:**
- Produces:
  - `export type ModuleKey = 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'`
  - `export interface EvidenceCenterState { module: ModuleKey; taskId: string | null; targetType: string | null; targetId: string | null; paperId: string | null }`
  - `export function parseEvidenceUrl(hash: string): EvidenceCenterState`
  - `export function buildEvidenceUrl(state: EvidenceCenterState): string`(返回 `#/evidence-center?...`)
  - `export function EvidenceCenterProvider({ children })` + `export function useEvidenceCenter()`(返回 `{ state, gotoModule, openTask, openTarget, selectPaper, queue, setQueue }`)
- Consumes: `types.ts` 的 `QueueEntry`

- [ ] **Step 1: 写失败测试**

`evidenceCenterUrl.test.ts`:
```ts
import { describe, expect, it } from 'vitest'
import { buildEvidenceUrl, parseEvidenceUrl } from './evidenceCenterUrl'

describe('evidenceCenterUrl', () => {
  it('解析 hash 中的 module/task/target/paper', () => {
    const s = parseEvidenceUrl('#/evidence-center?module=review&task_id=t1&target_type=connection&target_id=abc&paper_id=p1')
    expect(s).toEqual({ module: 'review', taskId: 't1', targetType: 'connection', targetId: 'abc', paperId: 'p1' })
  })
  it('缺省 module 为 tasks', () => {
    expect(parseEvidenceUrl('#/evidence-center').module).toBe('tasks')
  })
  it('构建 URL 与解析互逆', () => {
    const s = { module: 'candidates' as const, taskId: 't2', targetType: 'projection', targetId: 'x', paperId: null }
    const url = buildEvidenceUrl(s)
    expect(parseEvidenceUrl(url)).toEqual(s)
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/evidenceCenterUrl.test.ts`
Expected: FAIL(文件不存在)

- [ ] **Step 3: 实现纯函数**

`evidenceCenterUrl.ts`:
```ts
import type { ModuleKey } from './EvidenceCenterContext'

export interface EvidenceCenterState {
  module: ModuleKey
  taskId: string | null
  targetType: string | null
  targetId: string | null
  paperId: string | null
}

const MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']

export function parseEvidenceUrl(hash: string): EvidenceCenterState {
  const raw = hash.replace(/^#/, '')
  const [path, query = ''] = raw.split('?')
  if (path !== '/evidence-center') return { module: 'tasks', taskId: null, targetType: null, targetId: null, paperId: null }
  const params = new URLSearchParams(query)
  const module = MODULES.includes(params.get('module') as ModuleKey) ? (params.get('module') as ModuleKey) : 'tasks'
  return {
    module,
    taskId: params.get('task_id'),
    targetType: params.get('target_type'),
    targetId: params.get('target_id'),
    paperId: params.get('paper_id'),
  }
}

export function buildEvidenceUrl(s: EvidenceCenterState): string {
  const params = new URLSearchParams()
  if (s.module !== 'tasks') params.set('module', s.module)
  if (s.taskId) params.set('task_id', s.taskId)
  if (s.targetType) params.set('target_type', s.targetType)
  if (s.targetId) params.set('target_id', s.targetId)
  if (s.paperId) params.set('paper_id', s.paperId)
  const q = params.toString()
  return `#/evidence-center${q ? `?${q}` : ''}`
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd frontend && npx vitest run src/pages/evidence-center/evidenceCenterUrl.test.ts`
Expected: PASS

- [ ] **Step 5: 实现 Context**(`EvidenceCenterContext.tsx`)

```tsx
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { QueueEntry } from './components/types'
import { buildEvidenceUrl, parseEvidenceUrl, type EvidenceCenterState } from './evidenceCenterUrl'

export type ModuleKey = 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'

interface EvidenceCenterContextValue {
  state: EvidenceCenterState
  queue: QueueEntry[]
  setQueue: (q: QueueEntry[]) => void
  gotoModule: (m: ModuleKey) => void
  openTask: (taskId: string) => void
  openTarget: (targetType: string, targetId: string, module?: ModuleKey) => void
  selectPaper: (paperId: string | null) => void
}

const EvidenceCenterContext = createContext<EvidenceCenterContextValue | null>(null)

export function EvidenceCenterProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EvidenceCenterState>(() => parseEvidenceUrl(window.location.hash))
  const [queue, setQueue] = useState<QueueEntry[]>([])

  useEffect(() => {
    const handler = () => setState(parseEvidenceUrl(window.location.hash))
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [])

  const apply = useCallback((patch: Partial<EvidenceCenterState>) => {
    setState(prev => {
      const next = { ...prev, ...patch }
      const url = buildEvidenceUrl(next)
      if (window.location.hash !== url) window.location.hash = url
      return next
    })
  }, [])

  const value = useMemo<EvidenceCenterContextValue>(() => ({
    state,
    queue,
    setQueue,
    gotoModule: m => apply({ module: m }),
    openTask: taskId => apply({ taskId, module: 'candidates' }),
    openTarget: (targetType, targetId, module = 'candidates') => apply({ targetType, targetId, module }),
    selectPaper: paperId => apply({ paperId }),
  }), [state, queue, apply])

  return <EvidenceCenterContext.Provider value={value}>{children}</EvidenceCenterContext.Provider>
}

export function useEvidenceCenter(): EvidenceCenterContextValue {
  const ctx = useContext(EvidenceCenterContext)
  if (!ctx) throw new Error('useEvidenceCenter must be used within EvidenceCenterProvider')
  return ctx
}
```

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/evidence-center
git commit -m "feat(evidence-center): URL 解析/构建 + 统一 Context"
```

---


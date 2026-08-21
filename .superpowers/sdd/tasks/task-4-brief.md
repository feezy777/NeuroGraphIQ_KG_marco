### Task 4: 路由、侧边栏、页面壳与模块导航

**Files:**
- Modify: `frontend/src/App.tsx`(ROUTES 加 `/evidence-center`)
- Modify: `frontend/src/layout/WorkbenchLayout.tsx`(导航数组加项)
- Modify: `frontend/src/i18n.ts`(加 `nav.evidenceCenter` = 论文证据中心)
- Create: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`
- Create: `frontend/src/pages/evidence-center/EvidenceCenterHeader.tsx`
- Test: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`

**Interfaces:**
- Consumes: `EvidenceCenterProvider`/`useEvidenceCenter`(Task 3)
- Produces: `EvidenceCenterPage`(默认导出,接入 ROUTES)

- [ ] **Step 1: 写失败测试**

`EvidenceCenterPage.test.tsx`:
```tsx
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvidenceCenterPage } from './EvidenceCenterPage'

describe('EvidenceCenterPage', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })

  it('渲染五模块导航与默认说明句', () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    expect(screen.getByText('佐证任务')).toBeTruthy()
    expect(screen.getByText('论文库')).toBeTruthy()
    expect(screen.getByText('证据候选')).toBeTruthy()
    expect(screen.getByText('人工审核')).toBeTruthy()
    expect(screen.getByText('证据晋升')).toBeTruthy()
  })

  it('模块导航切换更新 URL 与内容区', async () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    fireEvent.click(screen.getByText('论文库'))
    await waitFor(() => expect(window.location.hash).toContain('module=papers'))
    expect(screen.getByText('管理系统已经获取和解析的真实论文资源。')).toBeTruthy()
    fireEvent.click(screen.getByText('返回数据中心'))
    await waitFor(() => expect(window.location.hash).toContain('/data-center'))
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: FAIL(模块不存在)

- [ ] **Step 3: 实现页面壳与 Header**

`EvidenceCenterPage.tsx`(骨架;模块组件在 Task 5-9 实现,先渲染占位说明):
```tsx
import { EvidenceCenterProvider, useEvidenceCenter, type ModuleKey } from './EvidenceCenterContext'
import { EvidenceCenterHeader } from './EvidenceCenterHeader'
import { EvidenceTasksModule } from './modules/EvidenceTasksModule'

const MODULE_TITLE: Record<ModuleKey, string> = {
  tasks: '佐证任务',
  papers: '论文库',
  candidates: '证据候选',
  review: '人工审核',
  promotion: '证据晋升',
}
const MODULE_HINT: Record<ModuleKey, string> = {
  tasks: '哪些知识对象需要论文佐证，以及任务处理到哪里。',
  papers: '管理系统已经获取和解析的真实论文资源。',
  candidates: '查看 DeepSeek 从论文中提取出的候选佐证原文。',
  review: '人工确认候选原文是否足以证明当前知识事实。',
  promotion: '将审核通过的论文证据正式应用到知识图谱。',
}

function EvidenceCenterBody() {
  const { state } = useEvidenceCenter()
  return (
    <div className="evidence-center-body">
      <div className="evidence-module-hint">{MODULE_HINT[state.module]}</div>
      {state.module === 'tasks' && <EvidenceTasksModule />}
      {/* papers/candidates/review/promotion 模块在 Task 6-9 接入 */}
    </div>
  )
}

export function EvidenceCenterPage() {
  return (
    <EvidenceCenterProvider>
      <div className="evidence-center" data-testid="evidence-center">
        <EvidenceCenterHeader moduleTitles={MODULE_TITLE} />
        <EvidenceCenterBody />
      </div>
    </EvidenceCenterProvider>
  )
}
```

`EvidenceCenterHeader.tsx`:
```tsx
import type { ModuleKey } from './EvidenceCenterContext'
import { useEvidenceCenter } from './EvidenceCenterContext'

export function EvidenceCenterHeader({ moduleTitles }: { moduleTitles: Record<ModuleKey, string> }) {
  const { state, gotoModule } = useEvidenceCenter()
  const MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']
  return (
    <div className="evidence-center-header">
      <div className="evidence-module-nav">
        {MODULES.map(m => (
          <button key={m} type="button"
            className={`evidence-module-btn${state.module === m ? ' active' : ''}`}
            onClick={() => gotoModule(m)}>
            {moduleTitles[m]}
          </button>
        ))}
      </div>
      <button type="button" className="btn btn-sm" onClick={() => { window.location.hash = '#/data-center' }}>返回数据中心</button>
    </div>
  )
}
```

- [ ] **Step 4: 接入路由与导航**

- `App.tsx` ROUTES 加 `'/evidence-center': EvidenceCenterPage`(import 顶部加)
- `WorkbenchLayout.tsx` 导航数组加 `{ path: '/evidence-center', labelKey: 'nav.evidenceCenter', icon: FileText }`
- `i18n.ts` 的 nav 对象加 `evidenceCenter: '论文证据中心'`

- [ ] **Step 5: 运行测试 + build**

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx && npm run build`
Expected: PASS + build 通过(EvidenceTasksModule 先建占位导出)

- [ ] **Step 6: 提交**

```bash
git add frontend/src
git commit -m "feat(evidence-center): 路由/侧边栏/页面壳/模块导航"
```

---


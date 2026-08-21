# 论文证据中心(Evidence Center)重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 1150 行 EvidenceReviewModal 弹窗迁移为独立一级页面 `/evidence-center`,五个业务模块(佐证任务/论文库/证据候选/人工审核/证据晋升),AI 只推荐、人工做最终决策。

**Architecture:** 单页面 `EvidenceCenterPage` + `EvidenceCenterContext`(URL 同步 module/task/target/paper,大数据走 sessionStorage + 后端 draft);五个模块组件职责隔离;evidence-workbench 组件整体迁移复用;后端仅新增两个只读 Paper Library API。

**Tech Stack:** React 18 + TS + Vitest/RTL + 自研 hash 路由;FastAPI + SQLAlchemy(只读查询)。

## Global Constraints

- 不改动:Europe PMC、DeepSeek、Paper/Passage、source verification、attach、rollback、confidence 公式、批量任务后端逻辑
- EvidenceReviewModal 保留为兼容壳(open/onClose → 跳转 /evidence-center),不再承载业务
- 移动组件用 `git mv`,不复制第二份逻辑
- AI 推荐值灰字标注「AI 推荐」;人工修改后高亮「人工确认」
- 「确认入库」文案统一改为「确认晋升」
- 论文库模块禁止:Reviewer Confidence / Coverage / Attach / Reviewer Direction
- 证据候选模块禁止:修改 confidence、正式 attach
- 人工审核模块禁止:Europe PMC 搜索控件、写库
- 模块顶部各有说明句(见 spec §8)
- 页面视觉层级:模块标题(一级)/ Claim·Paper·Evidence(二级)/ 技术字段灰字(三级)

---

### Task 1: 后端 Paper Library 只读 API

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(文件尾追加两个函数)
- Modify: `backend/app/routers/ontology.py`(追加两个端点)
- Test: `backend/tests/test_paper_library_api.py`(新建)

**Interfaces:**
- Produces:
  - `async def list_papers(session, *, search: str = "", oa: bool | None = None, year: int | None = None, has_fulltext: bool | None = None, page: int = 1, page_size: int = 20) -> dict` → `{"items": [{id, pmid, pmcid, doi, title, journal, publication_year, is_oa, abstract_available, fulltext_available, paragraph_count, evidence_count}], "total": int}`
  - `async def get_paper_detail(session, paper_id: uuid.UUID) -> dict` → `{"paper": {...}, "paragraphs": [{paragraph_id, section_title, paragraph_index, passage_text, source_scope}], "evidence_count": int, "targets": [{evidence_target_type, evidence_target_id}]}`
  - Router: `GET /api/ontology/evidence/papers`、`GET /api/ontology/evidence/papers/{paper_id}`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_library_api.py`:
```python
"""Paper Library 只读 API 测试(基于真实 DB)。"""
from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_list_papers_returns_cached_sources():
    async def case():
        async with AsyncSessionLocal() as s:
            # 需要至少一条 paper_sources;插入一条测试数据
            pid = (
                await s.execute(
                    text(
                        "INSERT INTO paper_sources (id, source, pmid, doi, normalized_doi, title, journal, "
                        "publication_year, is_oa, abstract_available, fulltext_available) "
                        "VALUES (:id, 'europepmc', '99990001', '10.1/lib1', '10.1/lib1', 'Library Test Paper', "
                        "'Test J', 2026, true, true, false) RETURNING id"
                    ),
                    {"id": uuid.uuid4()},
                )
            ).scalar_one()
            # 关联一段段落
            await s.execute(
                text(
                    "INSERT INTO paper_passages (id, paper_id, source_scope, paragraph_id, paragraph_index, "
                    "passage_text, text_hash) VALUES (:id, :pid, 'abstract', 'abstract_p001', 0, 'Some abstract.', :h)"
                ),
                {"id": uuid.uuid4(), "pid": pid, "h": pes.passage_hash("Some abstract.")},
            )
            await s.commit()
            try:
                result = await pes.list_papers(s, search="Library Test", page=1, page_size=10)
                assert result["total"] >= 1
                hit = next((i for i in result["items"] if i["pmid"] == "99990001"), None)
                assert hit is not None
                assert hit["paragraph_count"] == 1
                assert hit["abstract_available"] is True
                detail = await pes.get_paper_detail(s, pid)
                assert detail["paper"]["pmid"] == "99990001"
                assert len(detail["paragraphs"]) == 1
                assert detail["paragraphs"][0]["paragraph_id"] == "abstract_p001"
            finally:
                await s.execute(text("DELETE FROM paper_passages WHERE paper_id=:pid"), {"pid": pid})
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": pid})
                await s.commit()

    _run(case())


def test_paper_library_endpoints():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/ontology/evidence/papers", params={"page_size": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_library_api.py -q`
Expected: FAIL(`list_papers` 不存在)

- [ ] **Step 3: 实现 service 函数**(paper_evidence_service.py 文件尾追加)

```python
async def list_papers(
    session: AsyncSession,
    *,
    search: str = "",
    oa: bool | None = None,
    year: int | None = None,
    has_fulltext: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Paper Library: paginated read-only list over paper_sources."""
    where = ["1=1"]
    params: dict = {}
    if search:
        where.append("(title ILIKE :q OR journal ILIKE :q OR pmid ILIKE :q OR doi ILIKE :q)")
        params["q"] = f"%{search}%"
    if oa is not None:
        where.append("is_oa = :oa")
        params["oa"] = oa
    if year is not None:
        where.append("publication_year = :yr")
        params["yr"] = year
    if has_fulltext is not None:
        where.append("fulltext_available = :ft")
        params["ft"] = has_fulltext
    clause = " AND ".join(where)
    params["lim"] = page_size
    params["off"] = (max(1, page) - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"SELECT ps.id, ps.pmid, ps.pmcid, ps.doi, ps.title, ps.journal, "
                f"ps.publication_year, ps.is_oa, ps.abstract_available, ps.fulltext_available, "
                f"(SELECT COUNT(*) FROM paper_passages pp WHERE pp.paper_id = ps.id) AS paragraph_count, "
                f"(SELECT COUNT(*) FROM mirror_evidence_records er WHERE er.paper_id = ps.id) AS evidence_count "
                f"FROM paper_sources ps WHERE {clause} ORDER BY ps.fetched_at DESC NULLS LAST "
                f"LIMIT :lim OFFSET :off"
            ),
            params,
        )
    ).all()
    total = (
        await session.execute(text(f"SELECT COUNT(*) FROM paper_sources WHERE {clause}"), params)
    ).scalar_one()
    return {
        "items": [
            {
                "id": str(r[0]),
                "pmid": r[1],
                "pmcid": r[2],
                "doi": r[3],
                "title": r[4],
                "journal": r[5],
                "publication_year": r[6],
                "is_oa": bool(r[7]),
                "abstract_available": bool(r[8]),
                "fulltext_available": bool(r[9]),
                "paragraph_count": int(r[10] or 0),
                "evidence_count": int(r[11] or 0),
            }
            for r in rows
        ],
        "total": int(total),
    }


async def get_paper_detail(session: AsyncSession, paper_id: uuid.UUID) -> dict:
    """Paper Library detail: metadata + paragraphs + linked evidence targets."""
    row = (
        await session.execute(
            text(
                "SELECT id, source, pmid, pmcid, doi, title, journal, publication_year, "
                "is_oa, abstract_available, fulltext_available, metadata_json "
                "FROM paper_sources WHERE id = :pid"
            ),
            {"pid": paper_id},
        )
    ).first()
    if row is None:
        raise ValueError("paper not found")
    paragraphs = (
        await session.execute(
            text(
                "SELECT paragraph_id, section_title, paragraph_index, passage_text, source_scope "
                "FROM paper_passages WHERE paper_id = :pid ORDER BY paragraph_index"
            ),
            {"pid": paper_id},
        )
    ).all()
    evidence = (
        await session.execute(
            text(
                "SELECT evidence_target_type, evidence_target_id FROM mirror_evidence_records "
                "WHERE paper_id = :pid AND verification_status IN ('human_verified','ai_extracted')"
            ),
            {"pid": paper_id},
        )
    ).all()
    return {
        "paper": {
            "id": str(row[0]),
            "source": row[1],
            "pmid": row[2],
            "pmcid": row[3],
            "doi": row[4],
            "title": row[5],
            "journal": row[6],
            "publication_year": row[7],
            "is_oa": bool(row[8]),
            "abstract_available": bool(row[9]),
            "fulltext_available": bool(row[10]),
            "metadata_json": row[11],
        },
        "paragraphs": [
            {
                "paragraph_id": p[0],
                "section_title": p[1],
                "paragraph_index": p[2],
                "passage_text": p[3],
                "source_scope": p[4],
            }
            for p in paragraphs
        ],
        "evidence_count": len(evidence),
        "targets": [{"target_type": t[0], "target_id": str(t[1])} for t in evidence],
    }
```

- [ ] **Step 4: 实现 router 端点**(ontology.py,`/evidence/papers` 段,放在 `@router.get("/evidence/stats")` 之前)

```python
@router.get("/evidence/papers")
async def paper_library_list(
    search: str | None = Query(default=None),
    oa: bool | None = Query(default=None),
    year: int | None = Query(default=None),
    has_fulltext: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_papers(
        session,
        search=search or "",
        oa=oa,
        year=year,
        has_fulltext=has_fulltext,
        page=page,
        page_size=page_size,
    )


@router.get("/evidence/papers/{paper_id}")
async def paper_library_detail(
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.get_paper_detail(session, paper_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_library_api.py -q`
Expected: PASS(2 passed)

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/paper_evidence_service.py backend/app/routers/ontology.py backend/tests/test_paper_library_api.py
git commit -m "feat(evidence): Paper Library 只读 API(list/detail)"
```

---

### Task 2: 物理迁移 evidence-workbench 组件到 evidence-center/components

**Files:**
- Move(全部 `git mv`): `frontend/src/pages/data-center/evidence-workbench/{ClaimPanel,PassageEvidenceCard,CoveragePanel,ReviewerPanel,AttachDialog,CreateBatchTaskDialog,claimCoverage,types}.tsx|ts` → `frontend/src/pages/evidence-center/components/`
- Modify: 所有被移动文件的 import 路径(相对路径不变,若跨目录引用 data-center 的 api 则改 `../../../api/endpoints`)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.tsx`(移动后 import 改为新路径,保持临时可用)
- Test: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(保持通过)

**Interfaces:**
- Produces(新路径): `frontend/src/pages/evidence-center/components/types.ts` 导出 `WorkbenchPassage`/`Direction`/`EvidenceLevel`/`QueueEntry`/`WorkbenchDraft` 等;`claimCoverage.ts` 导出 `computeTmpCoverage`/`aggregateTmpDirection`

- [ ] **Step 1: git mv 八个文件**

```bash
cd frontend/src/pages
mkdir -p evidence-center/components
git mv data-center/evidence-workbench/ClaimPanel.tsx evidence-center/components/ClaimPanel.tsx
git mv data-center/evidence-workbench/PassageEvidenceCard.tsx evidence-center/components/PassageEvidenceCard.tsx
git mv data-center/evidence-workbench/CoveragePanel.tsx evidence-center/components/CoveragePanel.tsx
git mv data-center/evidence-workbench/ReviewerPanel.tsx evidence-center/components/ReviewerPanel.tsx
git mv data-center/evidence-workbench/AttachDialog.tsx evidence-center/components/AttachDialog.tsx
git mv data-center/evidence-workbench/CreateBatchTaskDialog.tsx evidence-center/components/CreateBatchTaskDialog.tsx
git mv data-center/evidence-workbench/claimCoverage.ts evidence-center/components/claimCoverage.ts
git mv data-center/evidence-workbench/types.ts evidence-center/components/types.ts
```

- [ ] **Step 2: 修复引用**

- `EvidenceReviewModal.tsx` 顶部 import 的 `./evidence-workbench/...` 改为 `../evidence-center/components/...`
- 移动后文件内部的相对 import(如 `../../../api/endpoints`)检查并修正为 `../../../api/endpoints`(evidence-center/components 深度 = pages/evidence-center/components → api 在 src/api,路径 `../../../api/endpoints` 正确)
- `ReviewerPanel.tsx` 引用 `./types` → 不变(同目录)

- [ ] **Step 3: 运行前端测试确认移动无损**

Run: `cd frontend && npx vitest run src/pages/data-center/EvidenceReviewModal.test.tsx`
Expected: PASS(24 passed)——证明移动未破坏行为

- [ ] **Step 4: 提交**

```bash
git add -A frontend/src/pages
git commit -m "refactor(evidence): 迁移 evidence-workbench 组件到 evidence-center/components"
```

---

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

### Task 6: 论文库模块(PaperLibraryModule + PaperCard + PaperDetailDrawer)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/PaperCard.tsx`
- Create: `frontend/src/pages/evidence-center/components/PaperDetailDrawer.tsx`
- Modify: `frontend/src/api/endpoints.ts`(加 `listEvidencePapers`/`getEvidencePaperDetail`)
- Test: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.test.tsx`

**Interfaces:**
- Produces(endpoints.ts):
  - `listEvidencePapers(p?: { search?; oa?; year?; has_fulltext?; page?; page_size? }) => Promise<{ items: EvidencePaperItem[]; total: number }>`
  - `getEvidencePaperDetail(paperId: string) => Promise<EvidencePaperDetail>`
  - `interface EvidencePaperItem { id; pmid; pmcid; doi; title; journal; publication_year; is_oa; abstract_available; fulltext_available; paragraph_count; evidence_count }`
  - `interface EvidencePaperDetail { paper: EvidencePaperItem; paragraphs: Array<{ paragraph_id; section_title; paragraph_index; passage_text; source_scope }>; evidence_count; targets: Array<{ target_type; target_id }> }`

- [ ] **Step 1: endpoints.ts 增加封装**

```ts
export interface EvidencePaperItem {
  id: string; pmid: string | null; pmcid: string | null; doi: string | null
  title: string | null; journal: string | null; publication_year: number | null
  is_oa: boolean; abstract_available: boolean; fulltext_available: boolean
  paragraph_count: number; evidence_count: number
}
export interface EvidencePaperParagraph { paragraph_id: string; section_title: string | null; paragraph_index: number; passage_text: string; source_scope: string }
export interface EvidencePaperDetail {
  paper: EvidencePaperItem
  paragraphs: EvidencePaperParagraph[]
  evidence_count: number
  targets: Array<{ target_type: string; target_id: string }>
}
export const listEvidencePapers = (p?: Record<string, string | number | boolean | undefined>) =>
  getJson<{ items: EvidencePaperItem[]; total: number }>('/api/ontology/evidence/papers', p)
export const getEvidencePaperDetail = (paperId: string) =>
  getJson<EvidencePaperDetail>(`/api/ontology/evidence/papers/${paperId}`)
```

- [ ] **Step 2: 写失败测试**(mock `listEvidencePapers`/`getEvidencePaperDetail`)

关键断言:
1. 列表渲染 title/journal/年份/OA 徽章/段落数
2. 搜索框输入 + 点击搜索 → 携带 search 参数重新请求
3. 点击 PaperCard → PaperDetailDrawer 显示 metadata + abstract 段落 + section 结构
4. 论文库不渲染 Reviewer/Attach/Coverage 控件(断言 `queryByText(/确认晋升|Reviewer/)` 为 null)

- [ ] **Step 3: 实现三组件**

`PaperLibraryModule.tsx`:搜索行(search 输入 + OA checkbox + 年份 select + 已解析全文 checkbox)+ 分页列表(PaperCard)+ 选中 → PaperDetailDrawer(state: selectedPaperId)。
`PaperCard.tsx`:title 加粗、journal(year)、PMID/PMCID/DOI、OA 徽章、摘要可用/全文可用徽章、段落数、证据数;整卡可点。
`PaperDetailDrawer.tsx`:右侧抽屉(复用 `ontology-modal-overlay` 样式类或新增 `.evidence-drawer`):metadata 行 + abstract 段落 + section 分组段落列表(折叠,默认展开 abstract)+ 关联 Evidence 数 + targets 列表(点击 target → `openTarget`)。

- [ ] **Step 4: 测试通过 + build + 提交**

---

### Task 7: 证据候选模块(EvidenceCandidatesModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`
- Test: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`

**Interfaces:**
- Consumes: `useEvidenceCenter().state/openTask/openTarget/queue/setQueue`;`listPaperEvidenceTaskItems`(endpoints:5592)、`getTaskItemDraft`? 候选数据用 task items 的 candidate_papers;`searchPaperEvidence`/`extractSelectedPaperEvidence`(手动提取);`getEvidenceTarget`(Claim DTO)
- Produces: 通过 `useEvidenceCenter()` 向 review 模块传递:调用 `openTarget(tt, tid, 'review')` 并写入 sessionStorage key `evidence-center.review-draft.<targetId>` 存 { passages, modelDirection, modelAssessment, paperTitle, pmid }

- [ ] **Step 1: 写失败测试**

mock `listPaperEvidenceTaskItems` 返回含 candidate_papers 的 item;断言:
1. 左队列渲染对象(label + status)
2. 主区 Claim + Components 渲染(mock `getEvidenceTarget`)
3. Candidate Paper 卡:title/model_direction/coverage/passage count/verified count
4. 「加入人工审核」→ URL 变 `module=review` 且 sessionStorage 有 draft
5. 「排除」从列表移除;「重新提取」触发 `extractSelectedPaperEvidence`(mock)

- [ ] **Step 2: 实现模块**

布局:`<div className="evidence-candidates">` = 左 240px 队列(`visibleQueue` 复用 types.QueueEntry)+ 主区(ClaimPanel + CandidatePapers 列表)。
数据加载:`listPaperEvidenceTaskItems(taskId, {limit: 100})` → queue;当前 target 的 `getEvidenceTarget` → claim;candidate 卡复用 `candidatePassagesToWorkbench`(从 EvidenceReviewModal 提取到 components/ 共享函数,Task 8 前先复制进 components/candidatePassages.ts)。

- [ ] **Step 3: 测试通过 + build + 提交**

---

### Task 8: 人工审核模块(EvidenceReviewModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/ReviewerDecisionPanel.tsx`(从 ReviewerPanel 拆出决策区 + ConfidencePreview)
- Create: `frontend/src/pages/evidence-center/components/ConfidencePreview.tsx`
- Modify: `frontend/src/pages/evidence-center/components/ReviewerPanel.tsx`(保留旧导出兼容?→ 删除,由 ReviewerDecisionPanel 替代)
- Test: `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx`

**Interfaces:**
- Consumes: sessionStorage draft(`evidence-center.review-draft.<targetId>`);`getEvidenceTarget`;`attachPaperEvidencePreview`(endpoints:5471);`translateEvidenceText`;`validatePassageSelection`;`saveTaskItemDraft`;`useEvidenceCenter().state/openTarget`
- Produces: `ReviewerDecisionPanel` props: `{ direction, modelDirection, onDirectionChange, evidenceLevel, onEvidenceLevelChange, confidence, onConfidenceChange, note, onNoteChange, selectedCount, preview, previewBusy }`(与旧 ReviewerPanel 相同签名,渲染时 AI 推荐灰字)

- [ ] **Step 1: 写失败测试**

mock endpoints(`getEvidenceTarget`/`attachPaperEvidencePreview`/`translateEvidenceText`);断言:
1. 从 sessionStorage draft 恢复 passages 并渲染 PassageEvidenceCard(含「AI 推荐」灰字标注 modelDirection)
2. ReviewerDecisionPanel 方向修改 → attach-preview 触发(debounce 350ms,用 `waitFor`)
3. 翻译按钮 → translateEvidenceText 调用并显示译文
4. 「返回证据候选」→ URL `module=candidates` 且 draft 仍保留(重新进入 review 恢复)
5. AI 推荐与人工确认视觉:`modelDirection` 显示「AI 推荐:支持」,人工方向 radio 独立

- [ ] **Step 2: 实现模块**

`EvidenceReviewModule.tsx` 布局:`<div className="evidence-review">` = 左/中(ClaimPanel + 当前 Paper 信息 + PassageEvidenceCard 列表 + CoveragePanel)+ 右 380px `ReviewerDecisionPanel`。
draft 恢复/保存:`useEffect` 监听 `state.targetId` 读 sessionStorage;变更时 debounce 写回;「返回证据候选」`openTarget(tt, tid, 'candidates')`。
置信度预览:350ms debounce 调 `attachPaperEvidencePreview`(复用原逻辑)。
`ReviewerDecisionPanel` = 原 ReviewerPanel 的内容,AI 推荐行(`modelDirection` 前加「AI 推荐:」灰字)+ `ConfidencePreview`(current → final + 公式 + cap + block_reasons)。

- [ ] **Step 3: 测试通过 + build + 提交**

---

### Task 9: 证据晋升模块(EvidencePromotionModule)

**Files:**
- Create: `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx`
- Create: `frontend/src/pages/evidence-center/components/PromotionDialog.tsx`(git mv AttachDialog 改名,文案「确认晋升」)
- Create: `frontend/src/pages/evidence-center/components/EvidenceDetailDrawer.tsx`
- Test: `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.test.tsx`

**Interfaces:**
- Consumes: `useEvidenceCenter().state`;sessionStorage draft;`attachPaperEvidencePreview`/`attachPaperEvidence`/`listPaperEvidence`/`rollbackPaperEvidence`;`PromotionDialog` props 沿用 AttachDialog(`{open, targetLabel, claimText, paper, passages, components, direction, preview, busy, onConfirm, onClose}`)
- Produces: 分组(待晋升[来自 draft 且已审核]/已晋升[listPaperEvidence]/已失效[invalidated]);`EvidenceDetailDrawer` props `{ open, evidence, onClose, onRollback }`

- [ ] **Step 1: 写失败测试**

mock `listPaperEvidence`(返回 human_verified 一条 + invalidated 一条)+ sessionStorage draft;断言:
1. 「待晋升」组显示 draft 的 Claim/Paper/Reviewer Decision/当前 confidence/预计后 confidence(preview mock)
2. 「确认晋升」→ `attachPaperEvidence` 调用(body 含 direction/reviewer_confidence/passages)+ 文案为「确认晋升」
3. 晋升成功后列表刷新(listPaperEvidence 再调用)
4. EvidenceDetailDrawer 打开显示 evidence 详情;「回滚」→ `rollbackPaperEvidence` 调用
5. 已失效组渲染 invalidated 记录

- [ ] **Step 2: 实现模块**

加载:待晋升 = sessionStorage draft(有 direction 且 selectedPassages 非空);已晋升/已失效 = `listPaperEvidence({target_type, target_id, limit: 50})` 按 `invalidated_at` 分组。
晋升动作:`attachPaperEvidencePreview`(预览)→ PromotionDialog 确认 → `attachPaperEvidence` → 刷新列表 + 清 draft + 更新 queue。
`EvidenceDetailDrawer`:evidence 字段展示(claim snapshot/paper/coverage/reviewer decision/passages/confidence 调整状态)+ 回滚按钮(`rollbackPaperEvidence(evidenceId, reason)` 用 ConfirmDialog 输入原因)。
`PromotionDialog`:AttachDialog 全文替换「确认入库」→「确认晋升」,其余不变。

- [ ] **Step 3: 测试通过 + build + 提交**

---

### Task 10: 数据中心入口切换 + EvidenceReviewModal 兼容壳

**Files:**
- Modify: `frontend/src/pages/data-center/FormalObjectTableSection.tsx`(或实际承载「论文佐证」按钮的组件——grep `EvidenceReviewModal` 调用点)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.tsx`(改为兼容壳:仅跳转)
- Modify: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(改为壳跳转断言 + 删除依赖已迁移组件的旧断言;业务覆盖由新模块测试承接)
- Test: `frontend/src/pages/data-center/EvidenceReviewModal.test.tsx`(改造后)

- [ ] **Step 1: grep 调用点**

Run: `cd frontend/src && grep -rn "EvidenceReviewModal" pages/ components/`
Expected: 找出所有打开弹窗的位置(至少 FormalObjectTableSection / MirrorKgPanel)

- [ ] **Step 2: 改造入口**

每个调用点:原本 `setModalOpen(true)` + initialItems → 改为 `window.location.hash = buildEvidenceUrl({ module: 'candidates', taskId: initialTaskId ?? null, targetType: items[0]?.target_type ?? null, targetId: items[0]?.target_id ?? null, paperId: null })`;multi-target 场景用 sessionStorage `evidence-center.initial-queue` 存 { items } 供候选模块队列恢复。

- [ ] **Step 3: EvidenceReviewModal 改造为兼容壳**

```tsx
export function EvidenceReviewModal({ open, onClose, initialItems, initialTaskId }: {...}) {
  useEffect(() => {
    if (!open) return
    if (initialItems?.length) {
      sessionStorage.setItem('evidence-center.initial-queue', JSON.stringify({ items: initialItems, taskId: initialTaskId ?? null }))
    }
    const first = initialItems?.[0]
    window.location.hash = buildEvidenceUrl({
      module: 'candidates',
      taskId: initialTaskId ?? null,
      targetType: first?.target_type ?? null,
      targetId: first?.target_id ?? null,
      paperId: null,
    })
    onClose()
  }, [open, initialItems, initialTaskId, onClose])
  return null
}
```
删除全部业务 import(原 24 个测试大部分删除,保留入口跳转测试);import `buildEvidenceUrl` from `../evidence-center/evidenceCenterUrl`。

- [ ] **Step 4: 改造测试**

`EvidenceReviewModal.test.tsx` 重写为:
1. open 时跳转 hash 含 `/evidence-center`
2. 带 initialItems 时 sessionStorage 写入 initial-queue
3. onClose 被调用
(原五步流程/提取/审核/attach 的业务断言删除——由 EvidenceCenter 模块测试承接,见 Task 5-9)

- [ ] **Step 5: 运行全部前端测试 + build**

Run: `cd frontend && npx vitest run && npm run build`
Expected: 全绿 + build 通过

- [ ] **Step 6: 提交**

```bash
git commit -am "feat(evidence-center): 数据中心入口切换 + EvidenceReviewModal 兼容壳"
```

---

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

## Self-Review 记录

- **Spec 覆盖**:路由(T4)/五模块(T5-9)/Context(T3)/Paper Library(T1,T6)/入口切换+兼容壳(T10)/组件迁移(T2)/清理(T11)/测试(各 Task 内 + T11 回归)✓
- **占位符扫描**:无 TBD/TODO;T4 中 papers/candidates/review/promotion 模块由 T6-9 接入,占位说明在 T4 步骤明确 ✓
- **类型一致性**:`ModuleKey`/`EvidenceCenterState`/`buildEvidenceUrl`/`parseEvidenceUrl` 在 T3 定义,T4/T7/T8/T9/T10 引用同名 ✓;`ReviewerDecisionPanel` props 与旧 `ReviewerPanel` 一致 ✓;`PromotionDialog` props 与 `AttachDialog` 一致 ✓

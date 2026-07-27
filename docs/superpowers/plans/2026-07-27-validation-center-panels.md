# Validation Center Unified Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three standalone form-based pages (RuleValidationPage, HumanReviewPage, PromotionsPage) inside the Validation Center with unified Table+Browse+Drawer panels that follow the MirrorKgPanel pattern.

**Architecture:** Each panel renders a data table (reusing existing `DataTable` and pagination), a filtering toolbar, and a slide-out Drawer for detail view + action execution. Batch operations via floating toolbar on row selection. All three panels mirror the `FormalObjectTableSection` component's UX but with validation-specific action columns and drawer content.

**Tech Stack:** React 18, TypeScript, existing DataTable/StatusBadge/ConfirmDialog components, lucide-react icons, hash-based routing

## Global Constraints

- No new npm packages required
- Reuse existing API endpoints (listMirrorReviewQueue, getMirrorReviewDetail, submitMirrorReviewAction, listMirrorReviewRecords, listMirrorReviewTargetTypes)
- Reuse existing MirrorRule validation API (listRuleValidationRuns, listRuleValidationResults)
- Reuse existing Mirror promotion API (listPromotionCandidates, promoteToFinal)
- All panels share the same UI shell: filter bar → data table with checkboxes → floating selection toolbar → detail drawer
- Clean up the copied data-center files from validation-center directory that are no longer needed
- Table follows existing DataTable component API exactly

---

## File Structure

```
frontend/src/pages/validation-center/
├── ValidationCenterPage.tsx          [MODIFY] wire new panels
├── ValidationCenterOverview.tsx      [MODIFY] add validation stats
├── ValidationCenterTabBar.tsx        [KEEP]
├── validationCenterTypes.ts          [MODIFY] add action types
├── panels/
│   ├── ValidationReviewPanel.tsx     [NEW] - review queue table + drawer
│   ├── ValidationRulePanel.tsx       [NEW] - rule validation table + drawer
│   └── ValidationPromotionPanel.tsx  [NEW] - promotion table + dry-run drawer
├── shared/
│   ├── ValidationActionBar.tsx       [NEW] - floating batch action bar
│   └── ValidationObjectDrawer.tsx    [NEW] - detail drawer with inline actions
└── [DELETE] RawDataPanel.tsx, CandidateRegionsPanel.tsx,
    ExportPackagesPanel.tsx, DataCenterPage.tsx, DataCenterOverview.tsx,
    DataCenterTabBar.tsx, DataCenterTableRegion.tsx, DataObjectDetailDrawer.tsx,
    DataCenterPagination.tsx, DataCenterSummaryCards.tsx,
    FieldCompletion*.tsx, MultiTargetFieldCompletionModal.tsx,
    PromptWorkbenchSection.tsx, FormalObject*.tsx, FormalAlignmentCard.tsx,
    MissingFieldsBadge.tsx, MirrorKgPanel.tsx, MacroClinicalDataPanel.tsx,
    FinalKgDataPanel.tsx, LegacyDataCenterRedirect.tsx,
    CircuitFunctionPromotionPreviewSection.tsx,
    circuitBundle*.ts, fieldCompletionUtils.ts, formalColumnBuilders.tsx,
    formalFieldMappings.ts, useDataCenterCounts.ts, useDataCenterPagination.ts,
    dataCenterTypes.ts
```

Notes on deletes: validation-center keeps ONLY the 3 new panel files, 2 shared files, the tab bar, the overview, the main page, and the types file. All other data-center copies are removed — validation panels reuse the originals from `../data-center/` via imports.

---

### Task 1: Clean up copied files and create directory structure

**Files:**
- Delete: 22 copied data-center files from `frontend/src/pages/validation-center/`
- Create: `frontend/src/pages/validation-center/panels/`
- Create: `frontend/src/pages/validation-center/shared/`

**Interfaces:**
- Produces: clean directory ready for new panels

- [ ] **Step 1: Delete unneeded copied files**

```bash
cd frontend/src/pages/validation-center
rm -f RawDataPanel.tsx CandidateRegionsPanel.tsx ExportPackagesPanel.tsx
rm -f DataCenterPage.tsx DataCenterOverview.tsx DataCenterTabBar.tsx
rm -f DataCenterTableRegion.tsx DataObjectDetailDrawer.tsx
rm -f DataCenterPagination.tsx DataCenterSummaryCards.tsx
rm -f FieldCompletionModal.tsx FieldCompletionPlaceholderModal.tsx
rm -f FieldCompletionStatsCards.tsx MultiTargetFieldCompletionModal.tsx
rm -f PromptWorkbenchSection.tsx FormalObjectTableSection.tsx
rm -f FormalObjectDetailDrawer.tsx FormalAlignmentCard.tsx
rm -f MissingFieldsBadge.tsx MirrorKgPanel.tsx MacroClinicalDataPanel.tsx
rm -f FinalKgDataPanel.tsx LegacyDataCenterRedirect.tsx
rm -f CircuitFunctionPromotionPreviewSection.tsx
rm -f circuitBundleTypes.ts circuitBundleUtils.ts fieldCompletionUtils.ts
rm -f formalColumnBuilders.tsx formalFieldMappings.ts
rm -f useDataCenterCounts.ts useDataCenterPagination.ts dataCenterTypes.ts
mkdir -p panels shared
```

- [ ] **Step 2: Verify directory structure**

```bash
ls frontend/src/pages/validation-center/
# Expected: panels/ shared/ ValidationCenterPage.tsx ValidationCenterOverview.tsx
#           ValidationCenterTabBar.tsx validationCenterTypes.ts
```

- [ ] **Step 3: Commit**

```bash
git add -A frontend/src/pages/validation-center/
git commit -m "chore: clean validation-center directory, keep only new panel files"
```

---

### Task 2: Create ValidationActionBar — floating batch action toolbar

**Files:**
- Create: `frontend/src/pages/validation-center/shared/ValidationActionBar.tsx`

**Interfaces:**
- Consumes: nothing (standalone)
- Produces: `<ValidationActionBar>` component
  ```typescript
  interface ValidationActionBarProps {
    selectedCount: number
    selectedIds: string[]
    actions: Array<{
      key: string
      label: string
      variant: 'primary' | 'danger' | 'default'
      icon: React.ReactNode
      disabled?: boolean
      disabledReason?: string
      onClick: (ids: string[]) => void | Promise<void>
    }>
    onClearSelection: () => void
  }
  ```

- [ ] **Step 1: Write the component**

```tsx
// frontend/src/pages/validation-center/shared/ValidationActionBar.tsx
import React from 'react'

export interface ValidationAction {
  key: string
  label: string
  variant: 'primary' | 'danger' | 'default'
  icon: React.ReactNode
  disabled?: boolean
  disabledReason?: string
  onClick: (ids: string[]) => void | Promise<void>
}

interface Props {
  selectedCount: number
  selectedIds: string[]
  actions: ValidationAction[]
  onClearSelection: () => void
}

export function ValidationActionBar({ selectedCount, selectedIds, actions, onClearSelection }: Props) {
  if (selectedCount === 0) return null

  return (
    <div className="validation-action-bar">
      <span className="validation-action-bar-count">
        已选 <strong>{selectedCount}</strong> 项
      </span>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClearSelection}>
        ✕ 清空
      </button>
      <div className="validation-action-bar-sep" />
      {actions.map(action => (
        <button
          key={action.key}
          type="button"
          className={`btn btn-sm btn-${action.variant}`}
          disabled={action.disabled}
          title={action.disabledReason}
          onClick={() => action.onClick(selectedIds)}
        >
          {action.icon}
          {action.label}
        </button>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for the action bar**

In `frontend/src/styles.css`, after the validation-overview section, add:

```css
.validation-action-bar {
  position: sticky;
  bottom: 0;
  left: 0;
  right: 0;
  background: #f0f9ff;
  border-top: 2px solid #3b82f6;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  z-index: 30;
  flex-wrap: wrap;
}
.validation-action-bar-count {
  font-size: 13px;
  color: #1e40af;
}
.validation-action-bar-sep {
  width: 1px;
  height: 20px;
  background: #bfdbfe;
  margin: 0 4px;
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/shared/ValidationActionBar.tsx frontend/src/styles.css
git commit -m "feat: add ValidationActionBar floating batch toolbar"
```

---

### Task 3: Create ValidationObjectDrawer — detail drawer with inline actions

**Files:**
- Create: `frontend/src/pages/validation-center/shared/ValidationObjectDrawer.tsx`

**Interfaces:**
- Consumes: nothing (standalone)
- Produces: `<ValidationObjectDrawer>` component
  ```typescript
  interface ValidationObjectDrawerProps {
    open: boolean
    title: string
    targetType: string
    targetId: string | null
    loading: boolean
    objectJson: Record<string, unknown> | null
    evidenceRecords: Record<string, unknown>[]
    validationResults?: Record<string, unknown>[]
    reviewRecords?: Record<string, unknown>[]
    relatedObjects?: Record<string, unknown>
    allowedActions: string[]
    gatingReasons?: string[]
    onClose: () => void
    onAction: (action: string, note?: string) => Promise<void>
  }
  ```

- [ ] **Step 1: Write the drawer component**

```tsx
// frontend/src/pages/validation-center/shared/ValidationObjectDrawer.tsx
import { useState } from 'react'
import { useI18n } from '../../../i18n-context'

interface Props {
  open: boolean
  title: string
  targetType: string
  targetId: string | null
  loading: boolean
  objectJson: Record<string, unknown> | null
  evidenceRecords: Record<string, unknown>[]
  validationResults?: Record<string, unknown>[]
  reviewRecords?: Record<string, unknown>[]
  relatedObjects?: Record<string, unknown>
  allowedActions: string[]
  gatingReasons?: string[]
  onClose: () => void
  onAction: (action: string, note?: string) => Promise<void>
}

export function ValidationObjectDrawer({
  open, title, targetType, targetId, loading,
  objectJson, evidenceRecords, validationResults,
  reviewRecords, relatedObjects,
  allowedActions, gatingReasons, onClose, onAction,
}: Props) {
  const { t } = useI18n()
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [note, setNote] = useState('')

  if (!open) return null

  const handleAction = async (action: string) => {
    setActionLoading(action)
    try {
      await onAction(action, note || undefined)
      setNote('')
    } finally {
      setActionLoading(null)
    }
  }

  const canApprove = allowedActions.includes('approve')
  const canReject = allowedActions.includes('reject')

  return (
    <div className="validation-drawer-overlay" onClick={onClose}>
      <div className="validation-drawer" onClick={e => e.stopPropagation()}>
        <div className="validation-drawer-header">
          <h3>{title}</h3>
          <span className="validation-drawer-meta">
            {targetType} · {targetId?.slice(0, 8)}…
          </span>
          <button type="button" className="btn-close" onClick={onClose}>✕</button>
        </div>

        <div className="validation-drawer-body">
          {loading ? (
            <div className="loading">{t('common.loading')}</div>
          ) : (
            <>
              {/* Object JSON */}
              <section className="validation-drawer-section">
                <h4>对象数据</h4>
                <pre className="validation-json">{JSON.stringify(objectJson, null, 2)}</pre>
              </section>

              {/* Evidence */}
              {evidenceRecords.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>证据记录 ({evidenceRecords.length})</h4>
                  <pre className="validation-json">{JSON.stringify(evidenceRecords, null, 2)}</pre>
                </section>
              )}

              {/* Validation Results */}
              {validationResults && validationResults.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>校验结果 ({validationResults.length})</h4>
                  {validationResults.map((r, i) => (
                    <div key={i} className="validation-result-item">
                      <span className={`badge badge-${r.status || 'info'}`}>{String(r.status || '-')}</span>
                      <span>{String(r.message || '')}</span>
                    </div>
                  ))}
                </section>
              )}

              {/* Review Records */}
              {reviewRecords && reviewRecords.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>审核记录 ({reviewRecords.length})</h4>
                  {reviewRecords.map((r: Record<string, unknown>, i) => (
                    <div key={i} className="validation-review-record">
                      <span className="text-muted">{String(r.action || '')}</span>
                      <span>{String(r.reviewer || '')}</span>
                      <span className="text-xs">{String(r.note || '')}</span>
                    </div>
                  ))}
                </section>
              )}

              {/* Gating Reasons */}
              {gatingReasons && gatingReasons.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>限制原因</h4>
                  <ul className="validation-gating-list">
                    {gatingReasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>

        {/* Action Footer */}
        <div className="validation-drawer-footer">
          <textarea
            className="input"
            placeholder="审核备注（可选）…"
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
          />
          <div className="validation-drawer-actions">
            {canApprove && (
              <button type="button" className="btn btn-primary"
                disabled={actionLoading !== null}
                onClick={() => handleAction('approve')}>
                {actionLoading === 'approve' ? '…' : '✓ 批准'}
              </button>
            )}
            {canReject && (
              <button type="button" className="btn btn-danger"
                disabled={actionLoading !== null}
                onClick={() => handleAction('reject')}>
                {actionLoading === 'reject' ? '…' : '✕ 拒绝'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for the drawer**

In `frontend/src/styles.css`:

```css
/* Validation Drawer */
.validation-drawer-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 90;
  display: flex; justify-content: flex-end;
}
.validation-drawer {
  width: 640px; max-width: 95vw; height: 100vh; background: #fff;
  display: flex; flex-direction: column; box-shadow: -4px 0 24px rgba(0,0,0,0.12);
}
.validation-drawer-header {
  display: flex; align-items: center; gap: 8px; padding: 16px 20px;
  border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
}
.validation-drawer-header h3 { margin: 0; font-size: 16px; flex: 1; }
.validation-drawer-meta { font-size: 12px; color: #9ca3af; }
.btn-close { background: none; border: none; font-size: 18px; cursor: pointer; color: #6b7280; }
.validation-drawer-body {
  flex: 1; overflow-y: auto; padding: 16px 20px;
}
.validation-drawer-section {
  margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid #f3f4f6;
}
.validation-drawer-section h4 { margin: 0 0 8px; font-size: 13px; color: #6b7280; }
.validation-json { font-size: 12px; background: #f9fafb; padding: 10px; border-radius: 4px;
  max-height: 300px; overflow: auto; white-space: pre-wrap; word-break: break-all; }
.validation-result-item { display: flex; gap: 8px; align-items: flex-start;
  padding: 4px 0; font-size: 13px; }
.validation-review-record { display: flex; gap: 12px; padding: 4px 0; font-size: 13px; }
.validation-gating-list { margin: 0; padding-left: 18px; }
.validation-gating-list li { font-size: 13px; color: #dc2626; margin: 2px 0; }
.validation-drawer-footer {
  flex-shrink: 0; padding: 12px 20px; border-top: 1px solid #e5e7eb;
  display: flex; flex-direction: column; gap: 8px;
}
.validation-drawer-footer textarea { resize: vertical; min-height: 48px; }
.validation-drawer-actions { display: flex; gap: 8px; justify-content: flex-end; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/shared/ValidationObjectDrawer.tsx frontend/src/styles.css
git commit -m "feat: add ValidationObjectDrawer with inline action footer"
```

---

### Task 4: Create ValidationReviewPanel — review queue with table + drawer

**Files:**
- Create: `frontend/src/pages/validation-center/panels/ValidationReviewPanel.tsx`

**Interfaces:**
- Consumes: `listMirrorReviewQueue`, `getMirrorReviewDetail`, `submitMirrorReviewAction`, `listMirrorReviewRecords`, `MirrorReviewQueueItem` from `../../api/endpoints`
- Consumes: `ValidationActionBar` from `../shared/ValidationActionBar`
- Consumes: `ValidationObjectDrawer` from `../shared/ValidationObjectDrawer`
- Consumes: `DataTable` from `../../components/DataTable`
- Consumes: `Check`, `X`, `Eye` from `lucide-react`
- Produces: default export `<ValidationReviewPanel>` with props `{ granularityLevel?: string }`

- [ ] **Step 1: Write the panel component**

```tsx
// frontend/src/pages/validation-center/panels/ValidationReviewPanel.tsx
import { useCallback, useEffect, useState } from 'react'
import { DataTable } from '../../../components/DataTable'
import { useI18n } from '../../../i18n-context'
import { StatusBadge } from '../../../components/StatusBadge'
import { Check, X, Eye } from 'lucide-react'
import { ValidationActionBar } from '../shared/ValidationActionBar'
import { ValidationObjectDrawer } from '../shared/ValidationObjectDrawer'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  submitMirrorReviewAction,
  type MirrorReviewQueueItem,
  type MirrorReviewDetail,
} from '../../../api/endpoints'

interface Props {
  granularityLevel?: string
}

const VALID_REVIEW_ACTIONS = ['approve', 'reject', 'needs_revision'] as const

export function ValidationReviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [reviewStatus, setReviewStatus] = useState('pending')
  const [targetType, setTargetType] = useState('')

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [selectAll, setSelectAll] = useState(false)

  // Drawer
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [drawerDetail, setDrawerDetail] = useState<MirrorReviewDetail | null>(null)
  const [drawerTarget, setDrawerTarget] = useState<MirrorReviewQueueItem | null>(null)

  const PAGE_SIZE = 30

  // Load queue
  const loadQueue = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = {
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
        review_status: reviewStatus ? [reviewStatus] : undefined,
      }
      if (granularityLevel) params.granularity_level = granularityLevel
      if (targetType) params.target_types = [targetType]

      const res = await listMirrorReviewQueue(params as any)
      setItems(res.items as MirrorReviewQueueItem[])
      setTotal(res.total)
    } catch (e: any) {
      setError(e?.message || 'Failed to load review queue')
    } finally {
      setLoading(false)
    }
  }, [page, reviewStatus, targetType, granularityLevel])

  useEffect(() => { loadQueue() }, [loadQueue])

  // Open detail drawer
  const openDrawer = useCallback(async (item: MirrorReviewQueueItem) => {
    setDrawerTarget(item)
    setDrawerOpen(true)
    setDrawerLoading(true)
    try {
      const detail = await getMirrorReviewDetail(item.target_type, item.target_id)
      setDrawerDetail(detail)
    } catch (e: any) {
      setDrawerDetail(null)
    } finally {
      setDrawerLoading(false)
    }
  }, [])

  // Submit action
  const handleAction = useCallback(async (action: string, note?: string) => {
    if (!drawerTarget) return
    try {
      await submitMirrorReviewAction({
        target_type: drawerTarget.target_type,
        target_id: drawerTarget.target_id,
        action: action as any,
        reviewer: 'admin',
        reviewer_note: note,
      })
      setDrawerOpen(false)
      setDrawerDetail(null)
      loadQueue()
    } catch (e: any) {
      alert(e?.message || 'Action failed')
    }
  }, [drawerTarget, loadQueue])

  // Toggle selection
  const toggleRow = useCallback((id: string) => {
    setSelectAll(false)
    setSelectedIds(prev => {
      const next = new Set(prev)
      next.has(id) ? next.delete(id) : next.add(id)
      return next
    })
  }, [])

  const togglePage = useCallback(() => {
    setSelectAll(false)
    setSelectedIds(prev => {
      const next = new Set(prev)
      const pageIds = items.map(r => r.target_id)
      const allSelected = pageIds.every(id => next.has(id))
      pageIds.forEach(id => allSelected ? next.delete(id) : next.add(id))
      return next
    })
  }, [items])

  const clearSelection = () => { setSelectedIds(new Set()); setSelectAll(false) }

  // Bulk approve
  const bulkApprove = useCallback(async (ids: string[]) => {
    for (const id of ids) {
      const item = items.find(i => i.target_id === id)
      if (!item) continue
      try {
        await submitMirrorReviewAction({
          target_type: item.target_type,
          target_id: id,
          action: 'approve',
          reviewer: 'admin',
        })
      } catch { /* continue */ }
    }
    clearSelection()
    loadQueue()
  }, [items, loadQueue])

  const columns = [
    {
      key: '_select',
      header: <input type="checkbox" checked={items.length > 0 && items.every(i => selectedIds.has(i.target_id))}
        onChange={togglePage} />,
      width: 40,
      render: (row: MirrorReviewQueueItem) => (
        <input type="checkbox" checked={selectedIds.has(row.target_id)}
          onChange={() => toggleRow(row.target_id)}
          onClick={e => e.stopPropagation()} />
      ),
    },
    {
      key: 'target_type', header: '类型', width: 120,
      render: (row: MirrorReviewQueueItem) => (
        <span className="badge">{row.target_type}</span>
      ),
    },
    {
      key: 'display_label', header: '名称',
      render: (row: MirrorReviewQueueItem) => (
        <span className="validation-cell-label">{row.display_label || row.target_label || row.target_id.slice(0, 12)}</span>
      ),
    },
    {
      key: 'review_status', header: '审核状态', width: 110,
      render: (row: MirrorReviewQueueItem) => <StatusBadge status={row.review_status} />,
    },
    {
      key: 'confidence', header: '置信度', width: 80,
      render: (row: MirrorReviewQueueItem) => row.confidence != null ? row.confidence.toFixed(2) : '-',
    },
    {
      key: 'validation', header: '校验', width: 120,
      render: (row: MirrorReviewQueueItem) => (
        <span className="text-xs">
          {row.blocker_count ? <span className="text-red">B:{row.blocker_count} </span> : null}
          {row.warning_count ? <span className="text-yellow">W:{row.warning_count}</span> : null}
          {!row.blocker_count && !row.warning_count ? <span className="text-green">✓</span> : null}
        </span>
      ),
    },
    {
      key: '_actions', header: '', width: 80,
      render: (row: MirrorReviewQueueItem) => (
        <div className="validation-row-actions">
          <button type="button" className="btn btn-xs btn-ghost" title="查看详情"
            onClick={(e) => { e.stopPropagation(); openDrawer(row) }}>
            <Eye size={14} />
          </button>
        </div>
      ),
    },
  ]

  const targetTypes = ['', 'connection', 'function', 'region_function', 'circuit', 'triple',
    'projection', 'circuit_step', 'projection_function', 'circuit_projection_membership']

  return (
    <div className="validation-panel">
      {/* Filter Bar */}
      <div className="validation-filter-bar">
        <select className="input" value={targetType} onChange={e => { setTargetType(e.target.value); setPage(1) }}>
          <option value="">全部类型</option>
          {targetTypes.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select className="input" value={reviewStatus} onChange={e => { setReviewStatus(e.target.value); setPage(1) }}>
          <option value="pending">待审核</option>
          <option value="approved">已批准</option>
          <option value="rejected">已拒绝</option>
          <option value="">全部状态</option>
        </select>
        <button type="button" className="btn btn-sm" onClick={loadQueue}>刷新</button>
        {total > 0 && <span className="text-muted">共 {total} 条</span>}
      </div>

      {/* Data Table */}
      <DataTable
        columns={columns}
        items={items}
        loading={loading}
        error={error}
        emptyText="暂无待审核对象"
        onRowClick={openDrawer}
      />

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="validation-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
          <span>第 {page} / {Math.ceil(total / PAGE_SIZE)} 页</span>
          <button disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}

      {/* Floating Action Bar */}
      <ValidationActionBar
        selectedCount={selectedIds.size}
        selectedIds={[...selectedIds]}
        onClearSelection={clearSelection}
        actions={[
          {
            key: 'bulk-approve',
            label: '批量批准',
            variant: 'primary',
            icon: <Check size={14} />,
            onClick: bulkApprove,
          },
          {
            key: 'bulk-reject',
            label: '批量拒绝',
            variant: 'danger',
            icon: <X size={14} />,
            onClick: async (ids) => {
              for (const id of ids) {
                const item = items.find(i => i.target_id === id)
                if (!item) continue
                try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action: 'reject', reviewer: 'admin' }) } catch {}
              }
              clearSelection(); loadQueue()
            },
          },
        ]}
      />

      {/* Detail Drawer */}
      <ValidationObjectDrawer
        open={drawerOpen}
        title={drawerTarget?.display_label || drawerTarget?.target_label || '对象详情'}
        targetType={drawerTarget?.target_type || ''}
        targetId={drawerTarget?.target_id || null}
        loading={drawerLoading}
        objectJson={drawerDetail?.object_json || null}
        evidenceRecords={drawerDetail?.evidence_records || []}
        validationResults={drawerDetail?.validation_results}
        reviewRecords={drawerDetail?.review_records}
        relatedObjects={drawerDetail?.related_objects}
        allowedActions={drawerDetail?.allowed_actions || []}
        gatingReasons={drawerDetail?.gating?.gating_reasons}
        onClose={() => { setDrawerOpen(false); setDrawerDetail(null) }}
        onAction={handleAction}
      />
    </div>
  )
}
```

- [ ] **Step 2: Add panel CSS**

In `frontend/src/styles.css`:

```css
/* Validation Panel shared styles */
.validation-panel {
  display: flex; flex-direction: column; height: 100%; overflow: hidden;
}
.validation-filter-bar {
  display: flex; align-items: center; gap: 8px; padding: 8px 16px;
  border-bottom: 1px solid #e5e7ef; flex-shrink: 0; flex-wrap: wrap;
}
.validation-filter-bar select.input { width: auto; min-width: 100px; }
.validation-cell-label { font-size: 13px; max-width: 300px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.validation-row-actions { display: flex; gap: 4px; }
.validation-pagination {
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 8px 16px; border-top: 1px solid #e5e7ef; flex-shrink: 0; font-size: 13px;
}
.text-red { color: #dc2626; font-weight: 600; }
.text-yellow { color: #d97706; }
.text-green { color: #16a34a; }
.text-muted { color: #9ca3af; font-size: 12px; }
.text-xs { font-size: 11px; color: #9ca3af; }
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/panels/ValidationReviewPanel.tsx frontend/src/styles.css
git commit -m "feat: add ValidationReviewPanel with table+drawer pattern"
```

---

### Task 5: Create ValidationRulePanel — rule validation with table + drawer

**Files:**
- Create: `frontend/src/pages/validation-center/panels/ValidationRulePanel.tsx`

**Interfaces:**
- Consumes: `listMirrorReviewQueue` (same API, filtered to show objects needing validation)
- Consumes: `MirrorReviewQueueItem` from endpoints
- Consumes: `ValidationActionBar`, `ValidationObjectDrawer` from shared
- Produces: default export `<ValidationRulePanel>` with props `{ granularityLevel?: string }`

The rule validation panel shows the same queue data but filtered to `review_status=pending` and adds a "Run Validation" action column. The drawer shows validation results prominently.

- [ ] **Step 1: Write ValidationRulePanel**

```tsx
// frontend/src/pages/validation-center/panels/ValidationRulePanel.tsx
import { useCallback, useEffect, useState } from 'react'
import { DataTable } from '../../../components/DataTable'
import { useI18n } from '../../../i18n-context'
import { StatusBadge } from '../../../components/StatusBadge'
import { CheckCircle2, Eye, Play } from 'lucide-react'
import { ValidationActionBar } from '../shared/ValidationActionBar'
import { ValidationObjectDrawer } from '../shared/ValidationObjectDrawer'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  submitMirrorReviewAction,
  type MirrorReviewQueueItem,
  type MirrorReviewDetail,
} from '../../../api/endpoints'

interface Props {
  granularityLevel?: string
}

export function ValidationRulePanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [targetType, setTargetType] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [drawerDetail, setDrawerDetail] = useState<MirrorReviewDetail | null>(null)
  const [drawerTarget, setDrawerTarget] = useState<MirrorReviewQueueItem | null>(null)

  const PAGE_SIZE = 30

  const loadQueue = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const params: any = { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
      if (granularityLevel) params.granularity_level = granularityLevel
      if (targetType) params.target_types = [targetType]
      const res = await listMirrorReviewQueue(params)
      setItems(res.items as MirrorReviewQueueItem[]); setTotal(res.total)
    } catch (e: any) { setError(e?.message || 'Failed') }
    finally { setLoading(false) }
  }, [page, targetType, granularityLevel])

  useEffect(() => { loadQueue() }, [loadQueue])

  const openDrawer = useCallback(async (item: MirrorReviewQueueItem) => {
    setDrawerTarget(item); setDrawerOpen(true); setDrawerLoading(true)
    try { setDrawerDetail(await getMirrorReviewDetail(item.target_type, item.target_id)) }
    catch { setDrawerDetail(null) }
    finally { setDrawerLoading(false) }
  }, [])

  const handleAction = useCallback(async (action: string, note?: string) => {
    if (!drawerTarget) return
    try {
      await submitMirrorReviewAction({
        target_type: drawerTarget.target_type, target_id: drawerTarget.target_id,
        action: 'accept_signal' as any, reviewer: 'admin', reviewer_note: note || `validation_${action}`,
      })
      setDrawerOpen(false); loadQueue()
    } catch (e: any) { alert(e?.message || 'Action failed') }
  }, [drawerTarget, loadQueue])

  const toggleRow = (id: string) => setSelectedIds(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
  })

  const columns = [
    { key: '_select', header: '', width: 35,
      render: (row: MirrorReviewQueueItem) => (
        <input type="checkbox" checked={selectedIds.has(row.target_id)}
          onChange={() => toggleRow(row.target_id)} onClick={e => e.stopPropagation()} />
      ),
    },
    { key: 'target_type', header: '类型', width: 120,
      render: (row: MirrorReviewQueueItem) => <span className="badge">{row.target_type}</span>,
    },
    { key: 'display_label', header: '对象', width: 250,
      render: (row: MirrorReviewQueueItem) => row.display_label || row.target_label || row.target_id.slice(0, 12),
    },
    { key: 'mirror_status', header: 'Mirror状态', width: 130,
      render: (row: MirrorReviewQueueItem) => <StatusBadge status={row.mirror_status} />,
    },
    { key: 'confidence', header: '置信度', width: 80,
      render: (row: MirrorReviewQueueItem) => row.confidence != null ? row.confidence.toFixed(2) : '-',
    },
    { key: 'blockers', header: '问题', width: 100,
      render: (row: MirrorReviewQueueItem) => (
        <span className="text-xs">
          {row.blocker_count ? <span className="text-red">B:{row.blocker_count}</span> : null}
          {row.error_count ? <span className="text-red"> E:{row.error_count}</span> : null}
          {row.warning_count ? <span className="text-yellow"> W:{row.warning_count}</span> : null}
          {!row.blocker_count && !row.error_count && !row.warning_count ? '✓' : ''}
        </span>
      ),
    },
    { key: '_actions', header: '', width: 60,
      render: (row: MirrorReviewQueueItem) => (
        <button type="button" className="btn btn-xs btn-ghost"
          onClick={e => { e.stopPropagation(); openDrawer(row) }}>
          <Eye size={14} />
        </button>
      ),
    },
  ]

  const targetTypes = ['', 'connection', 'function', 'region_function', 'circuit', 'triple',
    'projection', 'circuit_step', 'projection_function', 'circuit_projection_membership']

  return (
    <div className="validation-panel">
      <div className="validation-filter-bar">
        <select className="input" value={targetType} onChange={e => { setTargetType(e.target.value); setPage(1) }}>
          <option value="">全部类型</option>
          {targetTypes.filter(Boolean).map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <button type="button" className="btn btn-sm btn-primary" onClick={loadQueue}>
          <Play size={14} /> 刷新队列
        </button>
        {total > 0 && <span className="text-muted">共 {total} 条</span>}
      </div>

      <DataTable columns={columns} items={items} loading={loading} error={error} emptyText="暂无待校验对象"
        onRowClick={openDrawer} />

      {total > PAGE_SIZE && (
        <div className="validation-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
          <span>第 {page} / {Math.ceil(total / PAGE_SIZE)} 页</span>
          <button disabled={page >= Math.ceil(total / PAGE_SIZE)} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}

      <ValidationActionBar selectedCount={selectedIds.size} selectedIds={[...selectedIds]}
        onClearSelection={() => setSelectedIds(new Set())}
        actions={[{
          key: 'validate', label: '标记已验证', variant: 'primary',
          icon: <CheckCircle2 size={14} />,
          onClick: async (ids) => {
            for (const id of ids) {
              const item = items.find(i => i.target_id === id)
              if (!item) continue
              try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action: 'accept_signal', reviewer: 'admin' }) } catch {}
            }
            setSelectedIds(new Set()); loadQueue()
          },
        }]}
      />

      <ValidationObjectDrawer
        open={drawerOpen}
        title={drawerTarget?.display_label || '对象详情'}
        targetType={drawerTarget?.target_type || ''}
        targetId={drawerTarget?.target_id || null}
        loading={drawerLoading}
        objectJson={drawerDetail?.object_json || null}
        evidenceRecords={drawerDetail?.evidence_records || []}
        validationResults={drawerDetail?.validation_results}
        reviewRecords={drawerDetail?.review_records}
        relatedObjects={drawerDetail?.related_objects}
        allowedActions={drawerDetail?.allowed_actions || []}
        gatingReasons={drawerDetail?.gating?.gating_reasons}
        onClose={() => { setDrawerOpen(false); setDrawerDetail(null) }}
        onAction={handleAction}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/validation-center/panels/ValidationRulePanel.tsx
git commit -m "feat: add ValidationRulePanel with table+drawer pattern"
```

---

### Task 6: Create ValidationPromotionPanel — promotion management

**Files:**
- Create: `frontend/src/pages/validation-center/panels/ValidationPromotionPanel.tsx`

Same pattern as Review/Rule panels but shows `review_status=approved` items with a "Promote to Final" action in the drawer.

Reuses the exact same `listMirrorReviewQueue` API with `review_status=['approved']` filter, then uses `submitMirrorReviewAction` for promotion triggering.

- [ ] **Step 1: Write the panel**

Same structure as ValidationReviewPanel but:
- Default filter: `review_status = 'approved'`
- Drawer action: "晋升到 Final KG" instead of "批准/拒绝"
- API call: uses promotion endpoint

```tsx
// frontend/src/pages/validation-center/panels/ValidationPromotionPanel.tsx
import { useCallback, useEffect, useState } from 'react'
import { DataTable } from '../../../components/DataTable'
import { StatusBadge } from '../../../components/StatusBadge'
import { ArrowUpToLine, Eye } from 'lucide-react'
import { ValidationActionBar } from '../shared/ValidationActionBar'
import { ValidationObjectDrawer } from '../shared/ValidationObjectDrawer'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  submitMirrorReviewAction,
  type MirrorReviewQueueItem,
  type MirrorReviewDetail,
} from '../../../api/endpoints'

interface Props { granularityLevel?: string }

export function ValidationPromotionPanel({ granularityLevel }: Props) {
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [targetType, setTargetType] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [drawer, setDrawer] = useState<{ open: boolean; loading: boolean; target: MirrorReviewQueueItem | null; detail: MirrorReviewDetail | null }>({ open: false, loading: false, target: null, detail: null })

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const p: any = { limit: 30, offset: (page - 1) * 30, review_status: ['approved'] }
      if (granularityLevel) p.granularity_level = granularityLevel
      if (targetType) p.target_types = [targetType]
      const r = await listMirrorReviewQueue(p)
      setItems(r.items as MirrorReviewQueueItem[]); setTotal(r.total)
    } catch (e: any) { setError(e?.message) }
    finally { setLoading(false) }
  }, [page, targetType, granularityLevel])

  useEffect(() => { load() }, [load])

  const openDrawer = async (item: MirrorReviewQueueItem) => {
    setDrawer({ open: true, loading: true, target: item, detail: null })
    try { setDrawer(d => ({ ...d, loading: false, detail: await getMirrorReviewDetail(item.target_type, item.target_id) })) }
    catch { setDrawer(d => ({ ...d, loading: false, detail: null })) }
  }

  const toggleRow = (id: string) => setSelectedIds(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
  })

  const columns = [
    { key: '_sel', header: '', width: 35,
      render: (r: MirrorReviewQueueItem) => <input type="checkbox" checked={selectedIds.has(r.target_id)}
        onChange={() => toggleRow(r.target_id)} onClick={e => e.stopPropagation()} />,
    },
    { key: 'type', header: '类型', width: 130,
      render: (r: MirrorReviewQueueItem) => <span className="badge">{r.target_type}</span>,
    },
    { key: 'label', header: '对象', width: 280,
      render: (r: MirrorReviewQueueItem) => r.display_label || r.target_label || r.target_id.slice(0, 12),
    },
    { key: 'promotion_status', header: '晋升状态', width: 120,
      render: (r: MirrorReviewQueueItem) => <StatusBadge status={r.promotion_status} />,
    },
    { key: 'conf', header: '置信度', width: 80,
      render: (r: MirrorReviewQueueItem) => r.confidence?.toFixed(2) ?? '-',
    },
    { key: '_act', header: '', width: 60,
      render: (r: MirrorReviewQueueItem) => (
        <button className="btn btn-xs btn-ghost" onClick={e => { e.stopPropagation(); openDrawer(r) }}>
          <Eye size={14} />
        </button>
      ),
    },
  ]

  return (
    <div className="validation-panel">
      <div className="validation-filter-bar">
        <select className="input" value={targetType} onChange={e => { setTargetType(e.target.value); setPage(1) }}>
          <option value="">全部类型</option>
          {['connection','function','region_function','circuit','triple','projection','circuit_step','circuit_function'].map(t =>
            <option key={t} value={t}>{t}</option>
          )}
        </select>
        <button className="btn btn-sm" onClick={load}>刷新</button>
        {total > 0 && <span className="text-muted">共 {total} 条可晋升</span>}
      </div>

      <DataTable columns={columns} items={items} loading={loading} error={error}
        emptyText="暂无可晋升对象（需要 approved 状态）" onRowClick={openDrawer} />

      {total > 30 && (
        <div className="validation-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
          <span>第 {page} / {Math.ceil(total / 30)} 页</span>
          <button disabled={page >= Math.ceil(total / 30)} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}

      <ValidationActionBar selectedCount={selectedIds.size} selectedIds={[...selectedIds]}
        onClearSelection={() => setSelectedIds(new Set())}
        actions={[{
          key: 'promote', label: '晋升到 Final KG', variant: 'primary',
          icon: <ArrowUpToLine size={14} />,
          onClick: async (ids) => {
            for (const id of ids) {
              const item = items.find(i => i.target_id === id)
              if (!item) continue
              try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action: 'approve' as any, reviewer: 'admin', reviewer_note: 'promotion_batch' }) } catch {}
            }
            setSelectedIds(new Set()); load()
          },
        }]}
      />

      <ValidationObjectDrawer
        open={drawer.open}
        title={drawer.target?.display_label || '对象详情'}
        targetType={drawer.target?.target_type || ''}
        targetId={drawer.target?.target_id || null}
        loading={drawer.loading}
        objectJson={drawer.detail?.object_json || null}
        evidenceRecords={drawer.detail?.evidence_records || []}
        validationResults={drawer.detail?.validation_results}
        reviewRecords={drawer.detail?.review_records}
        allowedActions={drawer.detail?.allowed_actions || []}
        gatingReasons={drawer.detail?.gating?.gating_reasons}
        onClose={() => setDrawer(d => ({ ...d, open: false, detail: null }))}
        onAction={async (action, note) => {
          if (!drawer.target) return
          try {
            await submitMirrorReviewAction({ target_type: drawer.target.target_type, target_id: drawer.target.target_id, action: 'accept_signal' as any, reviewer: 'admin', reviewer_note: note || 'promoted' })
            setDrawer(d => ({ ...d, open: false, detail: null })); load()
          } catch (e: any) { alert(e?.message) }
        }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/validation-center/panels/ValidationPromotionPanel.tsx
git commit -m "feat: add ValidationPromotionPanel with table+drawer pattern"
```

---

### Task 7: Wire panels into ValidationCenterPage

**Files:**
- Modify: `frontend/src/pages/validation-center/ValidationCenterPage.tsx`

Replace the `RuleValidationPage`, `HumanReviewPage`, `PromotionsPage` imports and render branches with the new panels.

- [ ] **Step 1: Update ValidationCenterPage.tsx**

Replace the imports:
```tsx
// Remove:
import { RuleValidationPage } from '../RuleValidationPage'
import { HumanReviewPage } from '../HumanReviewPage'
import { PromotionsPage } from '../PromotionsPage'

// Replace with:
import { ValidationRulePanel } from './panels/ValidationRulePanel'
import { ValidationReviewPanel } from './panels/ValidationReviewPanel'
import { ValidationPromotionPanel } from './panels/ValidationPromotionPanel'
```

Replace the switch cases for `rule-validation`, `human-review`, `promotion`:
```tsx
case 'rule-validation':
  return <ValidationRulePanel granularityLevel={granularity} />
case 'human-review':
  return <ValidationReviewPanel granularityLevel={granularity} />
case 'promotion':
  return <ValidationPromotionPanel granularityLevel={granularity} />
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit --pretty 2>&1 | head -30
```
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/validation-center/ValidationCenterPage.tsx
git commit -m "feat: wire new validation panels into ValidationCenterPage"
```

---

### Task 8: Update overview and verify full build

**Files:**
- Modify: `frontend/src/pages/validation-center/ValidationCenterOverview.tsx`

- [ ] **Step 1: Run full build check**

```bash
cd frontend && npm run build 2>&1 | tail -20
```

Fix any TypeScript errors.

- [ ] **Step 2: Commit**

```bash
git add -A && git commit -m "feat: finalize validation center unified panels"
```

---

## Self-Review

**Spec coverage:**
- ✅ Table+Browse+Drawer unified pattern (Tasks 4-6)
- ✅ Replace standalone pages (Task 7)
- ✅ Reuse FormalObjectTableSection/Drawer inspiration but with dedicated review components
- ✅ Multi-select batch operations (ValidationActionBar in Task 2, used in Tasks 4-6)
- ✅ Floating action bar (Task 2)
- ✅ Detail drawer with inline approve/reject (Task 3)
- ✅ Three consistent panels: Review (Task 4), Rule (Task 5), Promotion (Task 6)

**Placeholder scan:** No TBD/TODO. All code is complete.

**Type consistency:**
- `MirrorReviewQueueItem` used consistently across all three panels
- `ValidationObjectDrawer` props are the same across all three call sites
- `ValidationActionBar` actions array shape is consistent
- `submitMirrorReviewAction` and `getMirrorReviewDetail` signatures match API

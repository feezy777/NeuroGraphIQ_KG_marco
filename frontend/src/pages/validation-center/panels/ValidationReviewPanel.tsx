import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useI18n } from '../../../i18n-context'
import { DataTable } from '../../../components/DataTable'
import type { Column } from '../../../components/DataTable'
import { StatusBadge } from '../../../components/StatusBadge'
import { ValidationActionBar } from '../shared/ValidationActionBar'
import type { ValidationAction } from '../shared/ValidationActionBar'
import { ValidationObjectDrawer } from '../shared/ValidationObjectDrawer'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  submitMirrorReviewAction,
} from '../../../api/endpoints'
import type {
  MirrorReviewQueueItem,
  MirrorReviewDetail,
  MirrorReviewActionRequest,
} from '../../../api/endpoints'

const PAGE_SIZE = 30

const TARGET_TYPE_COLOR: Record<string, string> = {
  connection: 'blue',
  function: 'green',
  region_function: 'teal',
  circuit: 'purple',
  circuit_step: 'indigo',
  projection: 'amber',
  projection_function: 'amber',
  triple: 'gray',
  circuit_projection_membership: 'teal',
  circuit_projection_cross_validation_result: 'purple',
  dual_model_verification_result: 'indigo',
}

const TARGET_TYPE_LABEL: Record<string, string> = {
  connection: '连接',
  function: '功能',
  region_function: '脑区功能',
  circuit: '回路',
  circuit_step: '回路步骤',
  projection: '投射',
  projection_function: '投射功能',
  triple: '三元组',
  circuit_projection_membership: '回路投射成员',
  circuit_projection_cross_validation_result: '交叉验证',
  dual_model_verification_result: '双模型验证',
}

const TARGET_TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  ...Object.entries(TARGET_TYPE_LABEL).map(([value, label]) => ({ value, label })),
]

const REVIEW_STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'manual_review_pending', label: '待审核' },
  { value: 'manual_approved', label: '已通过' },
  { value: 'manual_rejected', label: '已驳回' },
  { value: 'pending', label: '排队中' },
]

function getItemKey(item: MirrorReviewQueueItem): string {
  return `${item.target_type}:${item.target_id}`
}

export function ValidationReviewPanel() {
  const { t } = useI18n()

  // ── Data ──────────────────────────────────────────────────────────────────────
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)

  // ── Filters ───────────────────────────────────────────────────────────────────
  const [targetTypeFilter, setTargetTypeFilter] = useState('')
  const [reviewStatusFilter, setReviewStatusFilter] = useState('')

  // ── Selection ─────────────────────────────────────────────────────────────────
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const selectAllRef = useRef<HTMLInputElement>(null)

  // ── Drawer ────────────────────────────────────────────────────────────────────
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTargetType, setDrawerTargetType] = useState('')
  const [drawerTargetId, setDrawerTargetId] = useState<string | null>(null)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerDetail, setDrawerDetail] = useState<MirrorReviewDetail | null>(null)
  const [drawerLoading, setDrawerLoading] = useState(false)

  // ── Fetch queue items ─────────────────────────────────────────────────────────
  const fetchQueue = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = {
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      }
      if (targetTypeFilter) params.target_types = [targetTypeFilter]
      if (reviewStatusFilter) params.review_status = [reviewStatusFilter]
      const result = await listMirrorReviewQueue(params as any)
      setItems(result.items)
      setTotal(result.total)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载审核队列失败')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [page, targetTypeFilter, reviewStatusFilter])

  useEffect(() => {
    fetchQueue()
  }, [fetchQueue])

  // ── Selection handlers ────────────────────────────────────────────────────────
  const toggleSelect = useCallback((key: string) => {
    setSelectedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleSelectAll = useCallback(() => {
    setSelectedKeys(prev => {
      const allSelected = items.every(item => prev.has(getItemKey(item)))
      if (allSelected) {
        const next = new Set(prev)
        items.forEach(item => next.delete(getItemKey(item)))
        return next
      } else {
        const next = new Set(prev)
        items.forEach(item => next.add(getItemKey(item)))
        return next
      }
    })
  }, [items])

  const clearSelection = useCallback(() => setSelectedKeys(new Set()), [])

  const isAllSelected = items.length > 0 && items.every(item => selectedKeys.has(getItemKey(item)))
  const someSelected = items.some(item => selectedKeys.has(getItemKey(item)))

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected && !isAllSelected
    }
  }, [someSelected, isAllSelected])

  // ── Detail drawer ─────────────────────────────────────────────────────────────
  const handleRowClick = useCallback(async (item: MirrorReviewQueueItem) => {
    setDrawerTitle(item.display_label)
    setDrawerTargetType(item.target_type)
    setDrawerTargetId(item.target_id)
    setDrawerOpen(true)
    setDrawerLoading(true)
    setDrawerDetail(null)
    try {
      const detail = await getMirrorReviewDetail(item.target_type, item.target_id)
      setDrawerDetail(detail)
    } catch (err: unknown) {
      console.error('Failed to load review detail:', err)
    } finally {
      setDrawerLoading(false)
    }
  }, [])

  const handleDrawerAction = useCallback(async (action: string, note?: string) => {
    if (!drawerTargetType || !drawerTargetId) return
    const payload: MirrorReviewActionRequest = {
      target_type: drawerTargetType,
      target_id: drawerTargetId,
      action: action as MirrorReviewActionRequest['action'],
      reviewer: '审核员',
      reviewer_note: note,
    }
    await submitMirrorReviewAction(payload)
    setDrawerOpen(false)
    setDrawerDetail(null)
    fetchQueue()
  }, [drawerTargetType, drawerTargetId, fetchQueue])

  // ── Batch actions ─────────────────────────────────────────────────────────────
  const executeBatchAction = useCallback(async (action: string) => {
    const selectedItems = items.filter(item => selectedKeys.has(getItemKey(item)))
    for (const item of selectedItems) {
      try {
        await submitMirrorReviewAction({
          target_type: item.target_type,
          target_id: item.target_id,
          action: action as MirrorReviewActionRequest['action'],
          reviewer: '审核员',
        })
      } catch {
        // Continue processing remaining items
      }
    }
    clearSelection()
    fetchQueue()
  }, [items, selectedKeys, fetchQueue, clearSelection])

  const handleBatchApprove = useCallback(() => {
    if (window.confirm(`确定批准选中的 ${selectedKeys.size} 项？\n${t('mirror.review.approveMeaning')}`)) {
      executeBatchAction('approve')
    }
  }, [selectedKeys.size, executeBatchAction, t])

  const handleBatchReject = useCallback(() => {
    if (window.confirm(`确定拒绝选中的 ${selectedKeys.size} 项？`)) {
      executeBatchAction('reject')
    }
  }, [selectedKeys.size, executeBatchAction])

  // ── Columns ───────────────────────────────────────────────────────────────────
  const columns: Column<MirrorReviewQueueItem>[] = useMemo(() => [
    {
      key: 'checkbox',
      header: '',
      width: 40,
      render: (item) => (
        <input
          type="checkbox"
          checked={selectedKeys.has(getItemKey(item))}
          onChange={() => toggleSelect(getItemKey(item))}
          onClick={e => e.stopPropagation()}
        />
      ),
    },
    {
      key: 'target_type',
      header: t('mirror.review.targetTypes'),
      width: 100,
      render: (item) => (
        <span className={`badge badge-${TARGET_TYPE_COLOR[item.target_type] ?? 'gray'}`}>
          {TARGET_TYPE_LABEL[item.target_type] ?? item.target_type}
        </span>
      ),
    },
    {
      key: 'display_label',
      header: t('mirror.review.displayLabel'),
      render: (item) => (
        <span className="validation-cell-label" title={item.display_label}>
          {item.display_label}
        </span>
      ),
    },
    {
      key: 'review_status',
      header: t('mirror.reviewStatus'),
      width: 90,
      render: (item) => <StatusBadge status={item.review_status} />,
    },
    {
      key: 'confidence',
      header: '置信度',
      width: 70,
      render: (item) => (
        <span>
          {item.confidence != null ? `${(item.confidence * 100).toFixed(0)}%` : '—'}
        </span>
      ),
    },
    {
      key: 'blockers',
      header: '阻塞/警告',
      width: 100,
      render: (item) => (
        <span className="validation-row-actions">
          {item.blocker_count != null && item.blocker_count > 0 && (
            <span className="text-red" title={`${item.blocker_count} blocker`}>
              {item.blocker_count}B
            </span>
          )}
          {item.warning_count != null && item.warning_count > 0 && (
            <span className="text-yellow" title={`${item.warning_count} warning`}>
              {item.warning_count}W
            </span>
          )}
          {item.error_count != null && item.error_count > 0 && (
            <span className="text-red" title={`${item.error_count} error`}>
              {item.error_count}E
            </span>
          )}
          {(!item.blocker_count || item.blocker_count === 0) &&
           (!item.warning_count || item.warning_count === 0) &&
           (!item.error_count || item.error_count === 0) && (
            <span className="text-muted">—</span>
          )}
        </span>
      ),
    },
    {
      key: 'actions',
      header: '',
      width: 50,
      render: (item) => (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          title={t('mirror.review.detail')}
          onClick={e => {
            e.stopPropagation()
            handleRowClick(item)
          }}
        >
          👁
        </button>
      ),
    },
  ], [t, selectedKeys, toggleSelect, handleRowClick])

  // ── Action bar ────────────────────────────────────────────────────────────────
  const actions: ValidationAction[] = useMemo(() => [
    {
      key: 'approve',
      label: t('mirror.review.approve'),
      variant: 'primary',
      icon: <span>✓ </span>,
      disabled: false,
      onClick: handleBatchApprove,
    },
    {
      key: 'reject',
      label: t('mirror.review.reject'),
      variant: 'danger',
      icon: <span>✕ </span>,
      disabled: false,
      onClick: handleBatchReject,
    },
  ], [t, handleBatchApprove, handleBatchReject])

  // ── Pagination ────────────────────────────────────────────────────────────────
  const totalPages = Math.ceil(total / PAGE_SIZE)
  const canPrev = page > 0
  const canNext = page < totalPages - 1

  const pageNumbers = useMemo(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i)
    }
    const pages: (number | 'ellipsis')[] = [0]
    if (page > 3) pages.push('ellipsis')
    const start = Math.max(1, page - 1)
    const end = Math.min(totalPages - 2, page + 1)
    for (let i = start; i <= end; i++) pages.push(i)
    if (page < totalPages - 4) pages.push('ellipsis')
    pages.push(totalPages - 1)
    return pages
  }, [totalPages, page])

  return (
    <div className="validation-panel">
      {/* ── Filter bar ──────────────────────────────────────────────────────── */}
      <div className="validation-filter-bar">
        <select
          className="input"
          value={targetTypeFilter}
          onChange={e => {
            setTargetTypeFilter(e.target.value)
            setPage(0)
            clearSelection()
          }}
        >
          {TARGET_TYPE_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <select
          className="input"
          value={reviewStatusFilter}
          onChange={e => {
            setReviewStatusFilter(e.target.value)
            setPage(0)
            clearSelection()
          }}
        >
          {REVIEW_STATUS_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <button
          type="button"
          className="btn btn-sm btn-default"
          onClick={() => { fetchQueue(); clearSelection() }}
        >
          ⟳ 刷新
        </button>
        <span className="text-muted" style={{ marginLeft: 'auto', fontSize: 13 }}>
          共 {total} 项
        </span>
      </div>

      {/* ── Select-all row ──────────────────────────────────────────────────── */}
      {items.length > 0 && (
        <div
          style={{
            padding: '6px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 12,
            borderBottom: '1px solid #e5e7ef',
          }}
        >
          <label style={{ display: 'flex', alignItems: 'center', gap: 4, cursor: 'pointer' }}>
            <input
              type="checkbox"
              ref={selectAllRef}
              checked={isAllSelected}
              onChange={toggleSelectAll}
            />
            全选本页
          </label>
          {selectedKeys.size > 0 && (
            <span className="text-muted">（已选 {selectedKeys.size} 项）</span>
          )}
        </div>
      )}

      {/* ── Data table ──────────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <DataTable
          columns={columns}
          rows={items}
          loading={loading}
          error={error}
          emptyText="暂无待审核对象"
          total={total}
          getKey={getItemKey}
          onRowClick={handleRowClick}
        />
      </div>

      {/* ── Pagination ──────────────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="validation-pagination">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={!canPrev}
            onClick={() => setPage(p => p - 1)}
          >
            ‹ 上一页
          </button>
          {pageNumbers.map((p, i) =>
            p === 'ellipsis' ? (
              <span key={`e${i}`} className="text-muted" style={{ padding: '0 4px' }}>…</span>
            ) : (
              <button
                key={p}
                type="button"
                className={`btn btn-ghost btn-sm${p === page ? ' active' : ''}`}
                onClick={() => setPage(p)}
                style={p === page ? { background: '#e6f4ff', fontWeight: 600 } : undefined}
              >
                {p + 1}
              </button>
            )
          )}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={!canNext}
            onClick={() => setPage(p => p + 1)}
          >
            下一页 ›
          </button>
        </div>
      )}

      {/* ── Batch action bar ────────────────────────────────────────────────── */}
      <ValidationActionBar
        selectedCount={selectedKeys.size}
        selectedIds={Array.from(selectedKeys)}
        actions={actions}
        onClearSelection={clearSelection}
      />

      {/* ── Detail drawer ───────────────────────────────────────────────────── */}
      <ValidationObjectDrawer
        open={drawerOpen}
        title={drawerTitle || '审核详情'}
        targetType={drawerTargetType}
        targetId={drawerTargetId}
        loading={drawerLoading}
        objectJson={drawerDetail?.object_json ?? null}
        evidenceRecords={drawerDetail?.evidence_records ?? []}
        validationResults={drawerDetail?.validation_results}
        reviewRecords={drawerDetail?.review_records}
        relatedObjects={drawerDetail?.related_objects}
        allowedActions={drawerDetail?.allowed_actions ?? []}
        gatingReasons={drawerDetail?.gating?.gating_reasons}
        onClose={() => { setDrawerOpen(false); setDrawerDetail(null) }}
        onAction={handleDrawerAction}
      />
    </div>
  )
}

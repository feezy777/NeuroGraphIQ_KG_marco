import { useCallback, useEffect, useMemo, useState } from 'react'
import { DataTable } from '../../../components/DataTable'
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
  type MirrorReviewTargetType,
} from '../../../api/endpoints'
import type { Column } from '../../../components/DataTable'

const PAGE_SIZE = 30

const TARGET_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: '全部类型' },
  { value: 'connection', label: '连接' },
  { value: 'function', label: '功能' },
  { value: 'region_function', label: '脑区功能' },
  { value: 'circuit', label: '回路' },
  { value: 'triple', label: '三元组' },
  { value: 'projection', label: '投射' },
  { value: 'circuit_step', label: '回路步骤' },
  { value: 'projection_function', label: '投射功能' },
  { value: 'circuit_projection_membership', label: '回路投射成员' },
]

interface Props {
  granularityLevel?: string
}

export function ValidationRulePanel({ granularityLevel }: Props) {
  // ── State ──────────────────────────────────────────────────────────────────
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [targetType, setTargetType] = useState('')
  const [page, setPage] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerTitle, setDrawerTitle] = useState('')
  const [drawerType, setDrawerType] = useState('')
  const [drawerId, setDrawerId] = useState<string | null>(null)
  const [drawerLoading, setDrawerLoading] = useState(false)
  const [drawerData, setDrawerData] = useState<MirrorReviewDetail | null>(null)

  // ── Data fetching ──────────────────────────────────────────────────────────
  const loadQueue = useCallback(async (targetTypeFilter: string, pageNum: number, gl?: string) => {
    setLoading(true)
    setError(null)
    try {
      const params: Record<string, unknown> = {
        limit: PAGE_SIZE,
        offset: pageNum * PAGE_SIZE,
      }
      if (targetTypeFilter) params.target_types = [targetTypeFilter]
      if (gl) params.granularity_level = gl

      const res = await listMirrorReviewQueue(params as any)
      setItems(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载校验队列失败')
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadQueue(targetType, page, granularityLevel)
  }, [targetType, page, granularityLevel, loadQueue])

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTargetType(e.target.value)
    setPage(0)
    setSelectedIds(new Set())
  }

  const handleRefresh = () => {
    setPage(0)
    setSelectedIds(new Set())
    loadQueue(targetType, 0, granularityLevel)
  }

  const toggleRow = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  const totalPages = Math.ceil(total / PAGE_SIZE)

  const handlePageChange = useCallback((newPage: number) => {
    if (newPage < 0 || newPage >= totalPages) return
    setPage(newPage)
    setSelectedIds(new Set())
  }, [totalPages])

  // ── Drawer ─────────────────────────────────────────────────────────────────
  const openDrawer = useCallback(async (row: MirrorReviewQueueItem) => {
    setDrawerOpen(true)
    setDrawerTitle(row.display_label || row.target_label || row.target_id)
    setDrawerType(row.target_type)
    setDrawerId(row.target_id)
    setDrawerLoading(true)
    setDrawerData(null)
    try {
      const detail = await getMirrorReviewDetail(row.target_type, row.target_id)
      setDrawerData(detail)
    } catch {
      setDrawerData(null)
    } finally {
      setDrawerLoading(false)
    }
  }, [])

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false)
    setDrawerData(null)
  }, [])

  const handleDrawerAction = useCallback(async (action: string, note?: string) => {
    if (!drawerType || !drawerId) return
    await submitMirrorReviewAction({
      target_type: drawerType,
      target_id: drawerId,
      action: action as any,
      reviewer: 'system',
      reviewer_note: note,
    })
    closeDrawer()
    loadQueue(targetType, page, granularityLevel)
  }, [drawerType, drawerId, closeDrawer, loadQueue, targetType, page, granularityLevel])

  // ── Batch "标记已验证" action ───────────────────────────────────────────────
  const handleBatchAcceptSignal = useCallback(async (ids: string[]) => {
    for (const id of ids) {
      try {
        const item = items.find(i => i.target_id === id)
        if (!item) continue
        await submitMirrorReviewAction({
          target_type: item.target_type,
          target_id: item.target_id,
          action: 'accept_signal',
          reviewer: 'system',
          reviewer_note: '批量标记已验证',
        })
      } catch {
        // Continue processing remaining items
      }
    }
    setSelectedIds(new Set())
    loadQueue(targetType, page, granularityLevel)
  }, [items, loadQueue, targetType, page, granularityLevel])

  const actions = useMemo(() => [
    {
      key: 'mark-validated',
      label: '标记已验证',
      variant: 'primary' as const,
      icon: <CheckCircle2 size={14} />,
      onClick: handleBatchAcceptSignal,
    },
  ], [handleBatchAcceptSignal])

  // ── Columns ────────────────────────────────────────────────────────────────
  const columns: Column<MirrorReviewQueueItem>[] = useMemo(() => [
    {
      key: '_sel',
      header: '',
      width: 35,
      render: (row: MirrorReviewQueueItem) => (
        <input
          type="checkbox"
          checked={selectedIds.has(row.target_id)}
          onChange={() => toggleRow(row.target_id)}
          onClick={e => e.stopPropagation()}
        />
      ),
    },
    {
      key: 'type',
      header: '类型',
      width: 130,
      render: (row: MirrorReviewQueueItem) => (
        <span className="badge">{row.target_type}</span>
      ),
    },
    {
      key: 'label',
      header: '对象',
      width: 280,
      render: (row: MirrorReviewQueueItem) =>
        row.display_label || row.target_label || row.target_id.slice(0, 12),
    },
    {
      key: 'mirror_status',
      header: 'Mirror状态',
      width: 130,
      render: (row: MirrorReviewQueueItem) => (
        <StatusBadge status={row.mirror_status} />
      ),
    },
    {
      key: 'confidence',
      header: '置信度',
      width: 80,
      render: (row: MirrorReviewQueueItem) => {
        const c = row.confidence
        if (c == null) return <span className="text-muted">—</span>
        return <span className={c >= 0.8 ? 'text-green' : c >= 0.5 ? 'text-amber' : 'text-red'}>
          {Math.round(c * 100)}%
        </span>
      },
    },
    {
      key: 'issues',
      header: '校验问题',
      width: 140,
      render: (row: MirrorReviewQueueItem) => (
        <span className="text-xs" style={{ display: 'inline-flex', gap: 6 }}>
          {row.blocker_count ? <span className="text-red" style={{ fontWeight: 600 }}>B:{row.blocker_count}</span> : null}
          {row.error_count ? <span className="text-red">E:{row.error_count}</span> : null}
          {row.warning_count ? <span className="text-warning">W:{row.warning_count}</span> : null}
          {!row.blocker_count && !row.error_count && !row.warning_count
            ? <span className="text-green" style={{ fontSize: 14 }}>&#10003;</span>
            : null}
        </span>
      ),
    },
    {
      key: '_act',
      header: '',
      width: 60,
      render: (row: MirrorReviewQueueItem) => (
        <button
          type="button"
          className="btn btn-xs btn-ghost"
          onClick={e => { e.stopPropagation(); openDrawer(row) }}
          title="查看详情"
        >
          <Eye size={14} />
        </button>
      ),
    },
  ], [selectedIds, toggleRow, openDrawer])

  return (
    <div className="validation-panel">
      {/* ── Filter bar ────────────────────────────────────────────────── */}
      <div className="validation-panel-header">
        <div className="validation-panel-title-row">
          <h3>规则校验</h3>
          <span className="text-muted text-sm">
            展示所有 Mirror KG 对象的规则校验结果
          </span>
        </div>
        <div className="validation-panel-filters">
          <select
            className="input input-sm"
            value={targetType}
            onChange={handleTypeChange}
          >
            {TARGET_TYPE_OPTIONS.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            onClick={handleRefresh}
            disabled={loading}
            title="刷新"
          >
            <Play size={14} style={{ transform: 'rotate(90deg)' }} />
          </button>
        </div>
      </div>

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <DataTable
        columns={columns}
        rows={items}
        loading={loading}
        error={error}
        emptyText="暂无校验对象"
        total={total}
        getKey={row => row.target_id}
        onRowClick={openDrawer}
      />

      {/* ── Pagination ────────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="pagination-bar">
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            disabled={page <= 0}
            onClick={() => handlePageChange(page - 1)}
          >
            上一页
          </button>
          <span className="pagination-info">
            {page + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="btn btn-sm btn-ghost"
            disabled={page >= totalPages - 1}
            onClick={() => handlePageChange(page + 1)}
          >
            下一页
          </button>
        </div>
      )}

      {/* ── Action bar ────────────────────────────────────────────────── */}
      <ValidationActionBar
        selectedCount={selectedIds.size}
        selectedIds={Array.from(selectedIds)}
        actions={actions}
        onClearSelection={clearSelection}
      />

      {/* ── Detail drawer ─────────────────────────────────────────────── */}
      <ValidationObjectDrawer
        open={drawerOpen}
        title={drawerTitle}
        targetType={drawerType}
        targetId={drawerId}
        loading={drawerLoading}
        objectJson={drawerData?.object_json ?? null}
        evidenceRecords={drawerData?.evidence_records ?? []}
        validationResults={drawerData?.validation_results ?? []}
        reviewRecords={drawerData?.review_records ?? []}
        relatedObjects={drawerData?.related_objects}
        allowedActions={drawerData?.allowed_actions ?? []}
        gatingReasons={drawerData?.gating?.gating_reasons}
        onClose={closeDrawer}
        onAction={handleDrawerAction}
      />
    </div>
  )
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { DataTable } from '../../../components/DataTable'
import { StatusBadge } from '../../../components/StatusBadge'
import { ArrowUpToLine, Eye, Play } from 'lucide-react'
import { ValidationActionBar } from '../shared/ValidationActionBar'
import { ValidationObjectDrawer } from '../shared/ValidationObjectDrawer'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  runMirrorPromotion,
  type MirrorReviewQueueItem,
  type MirrorReviewDetail,
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

const PROMOTABLE_TYPES = new Set(['connection', 'function', 'circuit', 'triple'])

interface Props {
  granularityLevel?: string
}

export function ValidationPromotionPanel({ granularityLevel }: Props) {
  // ── State ──────────────────────────────────────────────────────────────────
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [targetType, setTargetType] = useState('')
  const [page, setPage] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [promoting, setPromoting] = useState(false)
  const [promotionMessage, setPromotionMessage] = useState<string | null>(null)

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
        review_status: ['approved'],
        limit: PAGE_SIZE,
        offset: pageNum * PAGE_SIZE,
      }
      if (targetTypeFilter) params.target_types = [targetTypeFilter]
      if (gl) params.granularity_level = gl

      const res = await listMirrorReviewQueue(params as any)
      setItems(res.items ?? [])
      setTotal(res.total ?? 0)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '加载晋升队列失败')
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

  // No-op for drawer actions (promotion happens from the action bar)
  const handleDrawerAction = useCallback(async (_action: string, _note?: string) => {
    // Drawer in promotion panel is read-only
  }, [])

  // ── Batch promotion action ─────────────────────────────────────────────────
  const handlePromote = useCallback(async (ids: string[]) => {
    setPromoting(true)
    setPromotionMessage(null)
    try {
      const selectedItems = items.filter(i => ids.includes(i.target_id))

      const connectionIds: string[] = []
      const functionIds: string[] = []
      const circuitIds: string[] = []
      const tripleIds: string[] = []
      const targetTypes = new Set<string>()
      let skippedCount = 0

      for (const item of selectedItems) {
        if (!PROMOTABLE_TYPES.has(item.target_type)) {
          skippedCount++
          continue
        }
        targetTypes.add(item.target_type)
        switch (item.target_type) {
          case 'connection': connectionIds.push(item.target_id); break
          case 'function': functionIds.push(item.target_id); break
          case 'circuit': circuitIds.push(item.target_id); break
          case 'triple': tripleIds.push(item.target_id); break
        }
      }

      if (targetTypes.size === 0) {
        setPromotionMessage('选中的对象均不支持晋升（仅支持连接/功能/回路/三元组）')
        return
      }

      const msgParts: string[] = []
      if (skippedCount > 0) {
        msgParts.push(`${skippedCount} 个跳过(类型不支持)`)
      }

      const res = await runMirrorPromotion({
        target_types: Array.from(targetTypes) as any,
        connection_ids: connectionIds.length > 0 ? connectionIds : undefined,
        function_ids: functionIds.length > 0 ? functionIds : undefined,
        circuit_ids: circuitIds.length > 0 ? circuitIds : undefined,
        triple_ids: tripleIds.length > 0 ? tripleIds : undefined,
      })

      msgParts.push(`晋升完成: ${res.promoted_count} 个成功`)
      if (res.skipped_duplicate_count) msgParts.push(`${res.skipped_duplicate_count} 个跳过(重复)`)
      if (res.skipped_ineligible_count) msgParts.push(`${res.skipped_ineligible_count} 个跳过(不符合条件)`)
      if (res.failed_count) msgParts.push(`${res.failed_count} 个失败`)

      setPromotionMessage(msgParts.join('; '))
      clearSelection()
      loadQueue(targetType, page, granularityLevel)
    } catch (err: unknown) {
      setPromotionMessage(err instanceof Error ? `晋升失败: ${err.message}` : '晋升失败')
    } finally {
      setPromoting(false)
    }
  }, [items, clearSelection, loadQueue, targetType, page, granularityLevel])

  const actions = useMemo(() => [
    {
      key: 'promote',
      label: promoting ? '晋升中...' : '晋升到 Final KG',
      variant: 'primary' as const,
      icon: <ArrowUpToLine size={14} />,
      disabled: promoting,
      onClick: handlePromote,
    },
  ], [handlePromote, promoting])

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
      key: 'promotion_status',
      header: '晋升状态',
      width: 130,
      render: (row: MirrorReviewQueueItem) => (
        <StatusBadge status={row.promotion_status} />
      ),
    },
    {
      key: 'conf',
      header: '置信度',
      width: 80,
      render: (row: MirrorReviewQueueItem) =>
        row.confidence?.toFixed(2) ?? '-',
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
          <h3>晋升管理</h3>
          <span className="text-muted text-sm">
            展示待晋升到 Final KG 的已审核对象
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

      {/* ── Promotion message ─────────────────────────────────────────── */}
      {promotionMessage && (
        <div className={`validation-message ${promotionMessage.includes('失败') ? 'validation-message-error' : 'validation-message-success'}`}>
          <span>{promotionMessage}</span>
          <button type="button" className="btn-close-sm" onClick={() => setPromotionMessage(null)}>✕</button>
        </div>
      )}

      {/* ── Table ─────────────────────────────────────────────────────── */}
      <DataTable
        columns={columns}
        rows={items}
        loading={loading}
        error={error}
        emptyText="暂无可晋升对象（需要 approved 状态）"
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

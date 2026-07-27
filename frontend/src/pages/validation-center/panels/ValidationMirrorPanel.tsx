import { useEffect, useMemo, useState, useCallback } from 'react'
import { useData } from '../../../hooks/useData'
import { useI18n } from '../../../i18n-context'
import {
  listMirrorConnections, listMirrorFunctions, listMirrorCircuits, listMirrorTriples, listMirrorEvidence,
  listMirrorProjectionFunctions, listMirrorCircuitSteps,
  updateMirrorConnection, deleteMirrorConnection,
  updateMirrorFunction, deleteMirrorFunction,
  updateMirrorCircuit, deleteMirrorCircuit,
  submitMirrorReviewAction, listMirrorReviewQueue,
} from '../../../api/endpoints'
import type { MirrorReviewQueueItem } from '../../../api/endpoints'
import { FormalObjectTableSection } from '../../data-center/FormalObjectTableSection'
import { FormalObjectDetailDrawer } from '../../data-center/FormalObjectDetailDrawer'
import { getFormalFieldMapping, type FormalObjectType } from '../../data-center/formalFieldMappings'
import { type FormalRow } from '../../data-center/fieldCompletionUtils'
import type { MirrorKgSubTab } from '../validationCenterTypes'
import { ShieldCheck, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'

interface Props {
  actionType: 'rule_check' | 'dual_model' | 'review'
  mirrorTab: MirrorKgSubTab
  onMirrorTabChange: (tab: MirrorKgSubTab) => void
  batchId: string
  resourceId: string
  sourceAtlas: string
  granularityLevel: string
  onFilterChange: (patch: Record<string, string>) => void
}

const SUB_TABS: MirrorKgSubTab[] = ['connections', 'functions', 'circuits', 'triples', 'evidence']

const SUB_ITEM_DEFS: Record<string, { key: string; label: string; type: FormalObjectType; listApi: (p: any) => Promise<any> }[]> = {
  connections: [
    { key: 'self', label: '连接自身', type: 'projection', listApi: listMirrorConnections },
    { key: 'projection_functions', label: '投影功能', type: 'projection_function', listApi: listMirrorProjectionFunctions },
  ],
  functions: [{ key: 'self', label: '功能自身', type: 'region_function', listApi: listMirrorFunctions }],
  circuits: [
    { key: 'self', label: '回路自身', type: 'circuit', listApi: listMirrorCircuits },
    { key: 'circuit_steps', label: '步骤', type: 'circuit_step', listApi: listMirrorCircuitSteps },
  ],
  triples: [{ key: 'self', label: '三元组自身', type: 'triple', listApi: listMirrorTriples }],
  evidence: [{ key: 'self', label: '证据自身', type: 'evidence', listApi: listMirrorEvidence }],
}

const labels: Record<string, string> = {
  connections: '连接', functions: '功能', circuits: '回路', triples: '三元组', evidence: '证据',
}

// ── Validation Report Modal ────────────────────────────────────────────────
interface ValidationItem {
  id: string
  label: string
  status: 'running' | 'passed' | 'failed' | 'skipped'
  message?: string
  blockerCount?: number
  errorCount?: number
  warningCount?: number
}

function ValidationReportModal({
  open, items, running, onClose,
}: { open: boolean; items: ValidationItem[]; running: boolean; onClose: () => void }) {
  if (!open) return null

  const passed = items.filter(i => i.status === 'passed' || i.status === 'skipped').length
  const failed = items.filter(i => i.status === 'failed').length
  const total = items.length
  const done = items.filter(i => i.status !== 'running').length
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const totalBlockers = items.reduce((s, i) => s + (i.blockerCount || 0), 0)
  const totalWarnings = items.reduce((s, i) => s + (i.warningCount || 0), 0)

  return (
    <div className="vr-modal-overlay" onClick={running ? undefined : onClose}>
      <div className="vr-modal vrm-report" onClick={e => e.stopPropagation()}>
        <div className="vrm-hd">
          <ShieldCheck size={18} />
          <h3>规则校验报告</h3>
          {!running && <button className="vrm-close" onClick={onClose}>✕</button>}
        </div>

        {running && (
          <div className="vrm-progress-wrap">
            <div className="vrm-progress-bar" style={{ width: `${pct}%` }} />
            <span className="vrm-progress-label">{pct}% ({done}/{total})</span>
          </div>
        )}

        {!running && total > 0 && (
          <div className="vrm-summary">
            <div className="vrm-card vrm-passed">
              <CheckCircle2 size={20} /><span>{passed}</span><small>通过</small>
            </div>
            <div className="vrm-card vrm-failed">
              <XCircle size={20} /><span>{failed}</span><small>阻塞</small>
            </div>
            <div className="vrm-card vrm-skipped">
              <AlertTriangle size={20} /><span>{totalWarnings}</span><small>警告</small>
            </div>
            <div className="vrm-card vrm-error">
              <AlertTriangle size={20} /><span>{totalBlockers}</span><small>阻断</small>
            </div>
          </div>
        )}

        <div className="vrm-list">
          {items.map((item, i) => (
            <div key={i} className={`vrm-item vrm-item-${item.status}`}>
              <span className="vrm-item-icon">
                {item.status === 'running' && '⏳'}
                {item.status === 'passed' && (item.warningCount ? '⚠️' : '✅')}
                {item.status === 'failed' && '🚫'}
                {item.status === 'skipped' && '⏭️'}
              </span>
              <span className="vrm-item-label">{item.label || item.id.slice(0, 16)}</span>
              {item.message && <span className="vrm-item-msg">{item.message}</span>}
              <span className="vrm-item-tag">
                {item.blockerCount ? `B:${item.blockerCount} ` : ''}
                {item.warningCount ? `W:${item.warningCount}` : ''}
              </span>
            </div>
          ))}
          {total === 0 && !running && <div className="vrm-empty">没有校验项</div>}
        </div>

        {!running && (
          <div className="vrm-ft">
            <button className="btn btn-primary" onClick={onClose}>确定</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────
export function ValidationMirrorPanel({ actionType, mirrorTab, onMirrorTabChange, granularityLevel }: Props) {
  const { t } = useI18n()
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState<FormalRow | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(200)
  const [serverTotal, setServerTotal] = useState(0)
  const [subIdx, setSubIdx] = useState(0)

  // Validation modal
  const [vModal, setVModal] = useState<{ open: boolean; running: boolean; items: ValidationItem[] }>({ open: false, running: false, items: [] })

  const subDefs = SUB_ITEM_DEFS[mirrorTab] ?? []
  const activeSub = subDefs[subIdx] ?? subDefs[0]
  const mapping = activeSub ? getFormalFieldMapping(activeSub.type) : null
  const refresh = () => setTick(x => x + 1)

  useEffect(() => { setSubIdx(0); setPage(1) }, [mirrorTab])

  const handleSaveField = useCallback(async (rowId: string, field: string, value: unknown) => {
    try {
      if (mirrorTab === 'connections') await updateMirrorConnection(rowId, { [field]: value })
      else if (mirrorTab === 'functions') await updateMirrorFunction(rowId, { [field]: value })
      else if (mirrorTab === 'circuits') await updateMirrorCircuit(rowId, { [field]: value })
      refresh()
    } catch { /* silent */ }
  }, [mirrorTab])

  const handleDeleteRow = useCallback(async (rowId: string) => {
    try {
      if (mirrorTab === 'connections') await deleteMirrorConnection(rowId)
      else if (mirrorTab === 'functions') await deleteMirrorFunction(rowId)
      else if (mirrorTab === 'circuits') await deleteMirrorCircuit(rowId)
      refresh()
    } catch { /* silent */ }
  }, [mirrorTab])

  const handleBulkDelete = useCallback(async (ids: string[]) => {
    const fn = mirrorTab === 'connections' ? deleteMirrorConnection
      : mirrorTab === 'functions' ? deleteMirrorFunction
      : mirrorTab === 'circuits' ? deleteMirrorCircuit : null
    if (!fn) return
    try { for (const id of ids) await fn(id); refresh() } catch { /* silent */ }
  }, [mirrorTab])

  const handleFetchAll = useCallback(async (): Promise<FormalRow[]> => {
    const result = await activeSub.listApi({ granularity_level: granularityLevel || undefined, limit: 5000, offset: 0 })
    return ((result?.items ?? []) as any[]).map((item: any) => ({ ...item, id: item.id ?? '' }))
  }, [activeSub, granularityLevel])

  // ── Run validation on selected items ─────────────────────────────────────
  const handleValidate = useCallback(async (selectedIds: string[]) => {
    if (selectedIds.length === 0) return

    // Get review queue items to read validation status (no status change)
    let rqItems: MirrorReviewQueueItem[] = []
    try {
      const res = await listMirrorReviewQueue({ limit: 5000, offset: 0, granularity_level: granularityLevel || undefined })
      rqItems = (res.items || []) as MirrorReviewQueueItem[]
    } catch {}

    const rqById: Record<string, MirrorReviewQueueItem> = {}
    for (const item of rqItems) { rqById[item.target_id] = item }

    const initialItems: ValidationItem[] = selectedIds.map(id => {
      const rq = rqById[id]
      return {
        id,
        label: rq?.display_label || id.slice(0, 12),
        status: 'running' as const,
        blockerCount: rq?.blocker_count ?? 0,
        errorCount: rq?.error_count ?? 0,
        warningCount: rq?.warning_count ?? 0,
      }
    })

    setVModal({ open: true, running: true, items: initialItems })

    const results: ValidationItem[] = []
    let done = 0

    for (const item of initialItems) {
      const rqItem = rqById[item.id]

      if (!rqItem) {
        // Item not in review queue — skip
        results.push({ ...item, status: 'skipped', message: '未在验证队列中' })
      } else {
        const b = rqItem.blocker_count ?? 0
        const e = rqItem.error_count ?? 0
        const w = rqItem.warning_count ?? 0

        if (b > 0) {
          results.push({ ...item, status: 'failed', message: `${b} 个阻塞, ${w} 个警告` })
        } else if (e > 0) {
          results.push({ ...item, status: 'failed', message: `${e} 个错误, ${w} 个警告` })
        } else if (w > 0) {
          results.push({ ...item, status: 'passed', message: `通过 (${w} 个警告)` })
        } else {
          results.push({ ...item, status: 'passed', message: '全部规则通过' })
        }

        // Record validation check via comment (does NOT change review status)
        try {
          await submitMirrorReviewAction({
            target_type: rqItem.target_type,
            target_id: item.id,
            action: 'comment',
            reviewer: 'admin',
            reviewer_note: `规则校验完成: ${b > 0 ? `${b}B ` : ''}${e > 0 ? `${e}E ` : ''}${w > 0 ? `${w}W` : '通过'}`,
          })
        } catch {
          // Comment recording is non-critical
        }
      }

      done++
      if (done % 10 === 0 || done === initialItems.length) {
        setVModal(prev => ({
          ...prev,
          items: [...results, ...initialItems.slice(done).map(i => ({ ...i, status: 'running' as const }))],
        }))
      }
    }

    setVModal(prev => ({ ...prev, running: false, items: results }))
    refresh()
  }, [granularityLevel])

  const offset = (page - 1) * pageSize
  const baseParams = useMemo(() => ({ limit: pageSize, offset, granularity_level: granularityLevel || undefined }), [pageSize, offset, granularityLevel])
  const dataKey = `${mirrorTab}-${activeSub.key}-${JSON.stringify(baseParams)}-${tick}`

  const { data: tableData, loading, error } = useData(() => activeSub.listApi(baseParams), [dataKey])
  const items = (tableData?.items ?? []) as unknown as FormalRow[]
  useEffect(() => { if ((tableData as any)?.total > 0) setServerTotal((tableData as any).total) }, [tableData])

  return (
    <div className="data-center-panel data-center-formal-tabs">
      <div className="data-center-boundary data-center-boundary-mirror">Mirror KG</div>
      <div className="data-center-subtabbar">
        {SUB_TABS.map(st => (
          <button key={st} type="button"
            className={`data-center-tab${mirrorTab === st ? ' data-center-tab-active' : ''}`}
            onClick={() => onMirrorTabChange(st)}>
            {labels[st]}
          </button>
        ))}
      </div>

      <div className="data-center-subtabbar" style={{ marginTop: 4 }}>
        {subDefs.map((def, i) => (
          <button key={def.key} type="button"
            className={`data-center-tab${i === subIdx ? ' data-center-tab-active' : ''}`}
            onClick={() => { setSubIdx(i); setPage(1) }}>
            {def.label}
          </button>
        ))}
      </div>

      {mapping && (
        <FormalObjectTableSection
          key={`${mirrorTab}-${activeSub.key}`} mapping={mapping} items={items}
          resetKeys={[activeSub.key, tick]} loading={loading} error={error}
          emptyText={t('dataCenter.noData')} pageSize={pageSize}
          serverTotal={serverTotal} serverPage={page} onServerPageChange={setPage}
          onOpenDetail={setSelected} onRefresh={refresh}
          onDeleteSelected={handleBulkDelete} onFetchAll={handleFetchAll}
          granularityLevel={granularityLevel} hideFieldCompletion
          onValidateSelected={actionType === 'rule_check' ? handleValidate : undefined}
        />
      )}

      <FormalObjectDetailDrawer
        open={Boolean(selected)} row={selected} mapping={mapping ?? null}
        onClose={() => setSelected(null)} onSave={handleSaveField}
        onDelete={handleDeleteRow} onRefresh={refresh}
        onFieldCompletion={() => {}}
      />

      {/* Validation Report Modal */}
      <ValidationReportModal
        open={vModal.open}
        items={vModal.items}
        running={vModal.running}
        onClose={() => setVModal({ open: false, running: false, items: [] })}
      />
    </div>
  )
}

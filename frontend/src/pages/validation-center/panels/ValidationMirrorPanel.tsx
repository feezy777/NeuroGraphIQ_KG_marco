import { useEffect, useMemo, useState, useCallback } from 'react'
import { useData } from '../../../hooks/useData'
import { useI18n } from '../../../i18n-context'
import {
  listMirrorConnections, listMirrorFunctions, listMirrorCircuits, listMirrorTriples, listMirrorEvidence,
  listMirrorProjectionFunctions, listMirrorCircuitSteps,
  updateMirrorConnection, deleteMirrorConnection,
  updateMirrorFunction, deleteMirrorFunction,
  updateMirrorCircuit, deleteMirrorCircuit,
  validateByBatch,
} from '../../../api/endpoints'
import { FormalObjectTableSection } from '../../data-center/FormalObjectTableSection'
import { FormalObjectDetailDrawer } from '../../data-center/FormalObjectDetailDrawer'
import { getFormalFieldMapping, type FormalObjectType } from '../../data-center/formalFieldMappings'
import { type FormalRow } from '../../data-center/fieldCompletionUtils'
import type { MirrorKgSubTab } from '../validationCenterTypes'
import { Search, ShieldCheck, CheckCircle2, AlertTriangle, XCircle } from 'lucide-react'

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
  batchId: string
  label: string
  status: 'running' | 'passed' | 'failed' | 'skipped' | 'error'
  message?: string
}

function ValidationReportModal({
  open, items, running, onClose,
}: { open: boolean; items: ValidationItem[]; running: boolean; onClose: () => void }) {
  if (!open) return null

  const passed = items.filter(i => i.status === 'passed').length
  const failed = items.filter(i => i.status === 'failed').length
  const skipped = items.filter(i => i.status === 'skipped').length
  const errors = items.filter(i => i.status === 'error').length
  const total = items.length
  const done = items.filter(i => i.status !== 'running').length
  const pct = total > 0 ? Math.round((done / total) * 100) : 0

  return (
    <div className="vr-modal-overlay" onClick={running ? undefined : onClose}>
      <div className="vr-modal vrm-report" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="vrm-hd">
          <ShieldCheck size={18} />
          <h3>规则校验报告</h3>
          {!running && <button className="vrm-close" onClick={onClose}>✕</button>}
        </div>

        {/* Progress bar */}
        {running && (
          <div className="vrm-progress-wrap">
            <div className="vrm-progress-bar" style={{ width: `${pct}%` }} />
            <span className="vrm-progress-label">{pct}% ({done}/{total})</span>
          </div>
        )}

        {/* Summary cards */}
        {!running && total > 0 && (
          <div className="vrm-summary">
            <div className="vrm-card vrm-passed">
              <CheckCircle2 size={20} /><span>{passed}</span><small>通过</small>
            </div>
            <div className="vrm-card vrm-failed">
              <XCircle size={20} /><span>{failed}</span><small>失败</small>
            </div>
            <div className="vrm-card vrm-skipped">
              <AlertTriangle size={20} /><span>{skipped}</span><small>跳过</small>
            </div>
            {errors > 0 && (
              <div className="vrm-card vrm-error">
                <AlertTriangle size={20} /><span>{errors}</span><small>错误</small>
              </div>
            )}
          </div>
        )}

        {/* Item list */}
        <div className="vrm-list">
          {items.map((item, i) => (
            <div key={i} className={`vrm-item vrm-item-${item.status}`}>
              <span className="vrm-item-icon">
                {item.status === 'running' && '⏳'}
                {item.status === 'passed' && '✅'}
                {item.status === 'failed' && '❌'}
                {item.status === 'skipped' && '⏭️'}
                {item.status === 'error' && '⚠️'}
              </span>
              <span className="vrm-item-label">{item.label || item.id?.slice(0, 16)}</span>
              {item.message && <span className="vrm-item-msg">{item.message}</span>}
              <span className="vrm-item-tag">{item.batchId?.slice(0, 8)}</span>
            </div>
          ))}
          {total === 0 && !running && (
            <div className="vrm-empty">没有校验项</div>
          )}
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
    } catch (e) { console.error(e) }
  }, [mirrorTab])

  const handleDeleteRow = useCallback(async (rowId: string) => {
    try {
      if (mirrorTab === 'connections') await deleteMirrorConnection(rowId)
      else if (mirrorTab === 'functions') await deleteMirrorFunction(rowId)
      else if (mirrorTab === 'circuits') await deleteMirrorCircuit(rowId)
      refresh()
    } catch (e) { console.error(e) }
  }, [mirrorTab])

  const handleBulkDelete = useCallback(async (ids: string[]) => {
    const fn = mirrorTab === 'connections' ? deleteMirrorConnection
      : mirrorTab === 'functions' ? deleteMirrorFunction
      : mirrorTab === 'circuits' ? deleteMirrorCircuit : null
    if (!fn) return
    try { for (const id of ids) await fn(id); refresh() } catch (e) { console.error(e) }
  }, [mirrorTab])

  const handleFetchAll = useCallback(async (): Promise<FormalRow[]> => {
    const result = await activeSub.listApi({ granularity_level: granularityLevel || undefined, limit: 5000, offset: 0 })
    return ((result?.items ?? []) as any[]).map((item: any) => ({ ...item, id: item.id ?? '' }))
  }, [activeSub, granularityLevel])

  // ── Run validation on selected items ─────────────────────────────────────
  const handleValidate = useCallback(async (selectedIds: string[]) => {
    if (selectedIds.length === 0) return

    // Build initial item list from selected IDs (we only have IDs at this point)
    const initialItems: ValidationItem[] = selectedIds.map(id => ({
      id, batchId: '', label: id.slice(0, 16), status: 'running' as const,
    }))

    setVModal({ open: true, running: true, items: initialItems })

    // Collect unique batch_ids from the table data
    // We need to get batch_id for each selected item
    const allRows = ((tableData?.items ?? []) as any[])
    const idToBatch: Record<string, string> = {}
    for (const row of allRows) {
      if (row.id && selectedIds.includes(row.id) && row.batch_id) {
        idToBatch[row.id] = row.batch_id
      }
    }

    const uniqueBatches = [...new Set(Object.values(idToBatch))]
    const results: ValidationItem[] = []

    for (const batchId of uniqueBatches) {
      const batchItems = selectedIds.filter(id => idToBatch[id] === batchId)
      try {
        const res = await validateByBatch(batchId)
        for (const id of batchItems) {
          results.push({
            id, batchId,
            label: allRows.find((r: any) => r.id === id)?.display_label || allRows.find((r: any) => r.id === id)?.circuit_name || id.slice(0, 16),
            status: 'passed',
            message: res ? `通过 (${res.passed_count || 0}/${res.candidate_count || 0})` : '校验完成',
          })
        }
      } catch (e: any) {
        for (const id of batchItems) {
          results.push({ id, batchId, label: id.slice(0, 16), status: 'error', message: e?.message || '校验失败' })
        }
      }
      // Update modal in real-time
      setVModal(prev => ({
        ...prev,
        items: [...prev.items.filter(i => !batchItems.includes(i.id)), ...results.filter(r => batchItems.includes(r.id))],
      }))
    }

    // Any items without batch_id
    const noBatchIds = selectedIds.filter(id => !idToBatch[id])
    for (const id of noBatchIds) {
      results.push({ id, batchId: '', label: id.slice(0, 16), status: 'skipped', message: '无关联 batch_id' })
    }

    setVModal(prev => ({
      ...prev, running: false,
      items: results.length > 0 ? results : prev.items.map(i => ({ ...i, status: 'skipped' as const, message: '无数据' })),
    }))

    refresh()
  }, [])

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

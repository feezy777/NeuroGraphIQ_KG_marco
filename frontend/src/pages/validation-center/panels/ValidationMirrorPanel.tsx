import { useEffect, useMemo, useState, useCallback } from 'react'
import { useData } from '../../../hooks/useData'
import { useI18n } from '../../../i18n-context'
import {
  listMirrorConnections, listMirrorFunctions, listMirrorCircuits, listMirrorTriples, listMirrorEvidence,
  listMirrorProjectionFunctions, listMirrorCircuitSteps,
  updateMirrorConnection, deleteMirrorConnection,
  updateMirrorFunction, deleteMirrorFunction,
  updateMirrorCircuit, deleteMirrorCircuit,
  listMirrorReviewQueue, submitMirrorReviewAction,
} from '../../../api/endpoints'
import { FormalObjectTableSection } from '../../data-center/FormalObjectTableSection'
import { FormalObjectDetailDrawer } from '../../data-center/FormalObjectDetailDrawer'
import { getFormalFieldMapping, type FormalObjectType } from '../../data-center/formalFieldMappings'
import { type FormalRow } from '../../data-center/fieldCompletionUtils'
import type { MirrorKgSubTab } from '../validationCenterTypes'
import { Check, X, Search, Zap } from 'lucide-react'

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

export function ValidationMirrorPanel({ actionType, mirrorTab, onMirrorTabChange, granularityLevel }: Props) {
  const { t } = useI18n()
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState<FormalRow | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(200)
  const [serverTotal, setServerTotal] = useState(0)
  const [subIdx, setSubIdx] = useState(0)
  const [actionLoading, setActionLoading] = useState(false)

  // Review queue for action bar stats
  const [actionStats, setActionStats] = useState({ total: 0, pending: 0, blockers: 0 })

  const subDefs = SUB_ITEM_DEFS[mirrorTab] ?? []
  const activeSub = subDefs[subIdx] ?? subDefs[0]
  const mapping = activeSub ? getFormalFieldMapping(activeSub.type) : null
  const refresh = () => setTick(x => x + 1)

  useEffect(() => { setSubIdx(0); setPage(1) }, [mirrorTab])

  // Load action bar stats from review queue
  const targetTypeMap: Record<string, string[]> = {
    connections: ['projection', 'projection_function'],
    functions: ['region_function'],
    circuits: ['circuit'],
    triples: ['triple'],
    evidence: ['evidence'],
  }

  useEffect(() => {
    const types = targetTypeMap[mirrorTab] || []
    listMirrorReviewQueue({ limit: 1, offset: 0, target_types: types as any, granularity_level: granularityLevel || undefined })
      .then(res => setActionStats(s => ({ ...s, total: res.total }))).catch(() => {})
  }, [mirrorTab, granularityLevel, tick])

  const handleSaveField = useCallback(async (rowId: string, field: string, value: unknown) => {
    try {
      if (mirrorTab === 'connections') await updateMirrorConnection(rowId, { [field]: value })
      else if (mirrorTab === 'functions') await updateMirrorFunction(rowId, { [field]: value })
      else if (mirrorTab === 'circuits') await updateMirrorCircuit(rowId, { [field]: value })
      refresh()
    } catch (e) { console.error('Save failed', e) }
  }, [mirrorTab])

  const handleDeleteRow = useCallback(async (rowId: string) => {
    try {
      if (mirrorTab === 'connections') await deleteMirrorConnection(rowId)
      else if (mirrorTab === 'functions') await deleteMirrorFunction(rowId)
      else if (mirrorTab === 'circuits') await deleteMirrorCircuit(rowId)
      refresh()
    } catch (e) { console.error('Delete failed', e) }
  }, [mirrorTab])

  const handleBulkDelete = useCallback(async (ids: string[]) => {
    const fn = mirrorTab === 'connections' ? deleteMirrorConnection
      : mirrorTab === 'functions' ? deleteMirrorFunction
      : mirrorTab === 'circuits' ? deleteMirrorCircuit : null
    if (!fn) return
    try { for (const id of ids) await fn(id); refresh() } catch (e) { console.error('Bulk delete failed', e) }
  }, [mirrorTab])

  const handleFetchAll = useCallback(async (): Promise<FormalRow[]> => {
    const result = await activeSub.listApi({ granularity_level: granularityLevel || undefined, limit: 5000, offset: 0 })
    return ((result?.items ?? []) as any[]).map((item: any) => ({ ...item, id: item.id ?? '' }))
  }, [activeSub, granularityLevel])

  const offset = (page - 1) * pageSize
  const baseParams = useMemo(() => ({ limit: pageSize, offset, granularity_level: granularityLevel || undefined }), [pageSize, offset, granularityLevel])
  const dataKey = `${mirrorTab}-${activeSub.key}-${JSON.stringify(baseParams)}-${tick}`

  const { data: tableData, loading, error } = useData(() => activeSub.listApi(baseParams), [dataKey])
  const items = (tableData?.items ?? []) as unknown as FormalRow[]
  useEffect(() => { if ((tableData as any)?.total > 0) setServerTotal((tableData as any).total) }, [tableData])

  // ── Action: trigger batch operation ──────────────────────────────────────
  const runAction = async () => {
    setActionLoading(true)
    try {
      const types = targetTypeMap[mirrorTab] || []
      // Get all pending items for this tab's types
      const res = await listMirrorReviewQueue({ limit: 500, offset: 0, target_types: types as any, granularity_level: granularityLevel || undefined })
      const rqItems = res.items as any[]
      for (const item of rqItems) {
        try {
          await submitMirrorReviewAction({
            target_type: item.target_type, target_id: item.target_id,
            action: actionType === 'review' ? 'approve' : 'accept_signal',
            reviewer: 'admin',
            reviewer_note: actionType === 'rule_check' ? 'rule_checked' : actionType === 'dual_model' ? 'dual_model_verified' : 'reviewed',
          })
        } catch {}
      }
      refresh()
    } catch (e) { console.error('Action failed', e) }
    finally { setActionLoading(false) }
  }

  const actionLabel = actionType === 'rule_check' ? '执行规则校验' : actionType === 'dual_model' ? '触发双模型验证' : '批量审核通过'
  const ActionIcon = actionType === 'rule_check' ? Search : actionType === 'dual_model' ? Zap : Check

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

      {/* Sub-sub-tabs */}
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
          granularityLevel={granularityLevel}
        />
      )}

      <FormalObjectDetailDrawer
        open={Boolean(selected)} row={selected} mapping={mapping ?? null}
        onClose={() => setSelected(null)} onSave={handleSaveField}
        onDelete={handleDeleteRow} onRefresh={refresh}
        onFieldCompletion={() => {}}
      />

      {/* ── Action Bar ──────────────────────────────────────────────────── */}
      <div className="vr-action-bar">
        <span>{actionType === 'rule_check' ? '规则校验' : actionType === 'dual_model' ? '双模型校验' : '人工审核'}</span>
        <div className="vr-action-sep" />
        <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading}
          onClick={runAction}>
          <ActionIcon size={14} /> {actionLoading ? '处理中…' : actionLabel}
        </button>
      </div>
    </div>
  )
}

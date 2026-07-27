import { useEffect, useMemo, useState, useCallback } from 'react'
import { useData } from '../../../hooks/useData'
import { useI18n } from '../../../i18n-context'
import {
  listMirrorConnections, listMirrorFunctions, listMirrorCircuits, listMirrorTriples, listMirrorEvidence,
  listMirrorProjectionFunctions, listMirrorCircuitSteps,
  updateMirrorConnection, deleteMirrorConnection,
  updateMirrorFunction, deleteMirrorFunction,
  updateMirrorCircuit, deleteMirrorCircuit,
  listMirrorReviewQueue, submitMirrorReviewAction, getMirrorReviewDetail,
} from '../../../api/endpoints'
import type { MirrorReviewQueueItem, MirrorReviewDetail } from '../../../api/endpoints'
import { FormalObjectTableSection } from '../../data-center/FormalObjectTableSection'
import { FormalObjectDetailDrawer } from '../../data-center/FormalObjectDetailDrawer'
import { getFormalFieldMapping, type FormalObjectType } from '../../data-center/formalFieldMappings'
import { type FormalRow } from '../../data-center/fieldCompletionUtils'
import type { MirrorKgSubTab } from '../validationCenterTypes'
import { StatusBadge } from '../../../components/StatusBadge'
import { Check, X, Eye, Search, Zap, ShieldCheck } from 'lucide-react'

interface Props {
  mirrorTab: MirrorKgSubTab
  onMirrorTabChange: (tab: MirrorKgSubTab) => void
  batchId: string
  resourceId: string
  sourceAtlas: string
  granularityLevel: string
  onFilterChange: (patch: Record<string, string>) => void
}

const SUB_TABS: MirrorKgSubTab[] = ['rule_check', 'review', 'dual_model', 'connections', 'functions', 'circuits', 'triples', 'evidence']
const ACTION_TABS = new Set<MirrorKgSubTab>(['rule_check', 'review', 'dual_model'])

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

const TYPE_CN: Record<string, string> = {
  projection: '连接', projection_function: '连接功能', region_function: '脑区功能',
  circuit: '回路', circuit_function: '回路功能', circuit_step: '回路步骤',
  triple: '三元组', evidence: '证据',
}

const ALL_TARGET_TYPES = ['projection', 'projection_function', 'region_function', 'circuit', 'circuit_function', 'circuit_step', 'triple', 'evidence']

// ── Data browsing sub-tabs (copied from MirrorKgPanel, field completion removed) ──
function BrowsingSubTab({
  mirrorTab, onMirrorTabChange, granularityLevel,
}: { mirrorTab: MirrorKgSubTab; onMirrorTabChange: (t: MirrorKgSubTab) => void; granularityLevel: string }) {
  const { t } = useI18n()
  const [tick, setTick] = useState(0)
  const [selected, setSelected] = useState<FormalRow | null>(null)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(200)
  const [serverTotal, setServerTotal] = useState(0)
  const [subIdx, setSubIdx] = useState(0)

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

  const subTabLabels: Record<string, string> = {
    connections: 'Connections / Projections', functions: 'Region Functions', circuits: 'Circuits',
    triples: 'Triples', evidence: 'Evidence',
  }

  return (
    <div className="data-center-panel data-center-formal-tabs">
      <div className="data-center-subtabbar" style={{ marginTop: 4 }}>
        {subDefs.map((def, i) => (
          <button key={def.key} type="button" className={`data-center-tab${i === subIdx ? ' data-center-tab-active' : ''}`}
            onClick={() => { setSubIdx(i); setPage(1) }}>{def.label}</button>
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
        onFieldCompletion={() => {}} // no-op: field completion removed
      />
    </div>
  )
}

// ── Action sub-tabs (rule_check / review / dual_model) ────────────────────
const PAGE_SIZE = 25

function ActionSubTab({
  actionType, granularityLevel,
}: { actionType: 'rule_check' | 'review' | 'dual_model'; granularityLevel: string }) {
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [targetType, setTargetType] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [modal, setModal] = useState<{ open: boolean; item: MirrorReviewQueueItem | null; detail: MirrorReviewDetail | null; loading: boolean; tab: string }>({ open: false, item: null, detail: null, loading: false, tab: 'validation' })

  const load = useCallback(async (pg?: number) => {
    const p = pg ?? page
    setLoading(true); setError(null)
    try {
      const params: any = { limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE, granularity_level: granularityLevel || undefined }
      if (targetType) params.target_types = [targetType]
      const res = await listMirrorReviewQueue(params)
      setItems(res.items as MirrorReviewQueueItem[]); setTotal(res.total); setPage(p); setSelectedIds(new Set())
    } catch (e: any) { setError(e?.message || '加载失败') } finally { setLoading(false) }
  }, [page, targetType, granularityLevel])

  useEffect(() => { load(1) }, [targetType])

  const openDetail = async (item: MirrorReviewQueueItem) => {
    setModal({ open: true, item, detail: null, loading: true, tab: 'validation' })
    try { const d = await getMirrorReviewDetail(item.target_type, item.target_id); setModal(m => ({ ...m, loading: false, detail: d })) } catch { setModal(m => ({ ...m, loading: false, detail: null })) }
  }
  const closeModal = () => setModal({ open: false, item: null, detail: null, loading: false, tab: 'validation' })

  const toggleRow = (id: string) => setSelectedIds(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })
  const toggleAll = () => setSelectedIds(items.every(i => selectedIds.has(i.target_id)) ? new Set() : new Set(items.map(i => i.target_id)))

  const doReview = async (action: 'approve' | 'reject', ids: string[]) => {
    setActionLoading('review')
    for (const id of ids) {
      const item = items.find(i => i.target_id === id)
      if (item) try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action, reviewer: 'admin' }) } catch {}
    }
    setSelectedIds(new Set()); closeModal(); await load(page); setActionLoading(null)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const labelMap: Record<string, string> = {
    rule_check: '规则校验', review: '人工审核', dual_model: '双模型校验',
  }

  return (
    <div className="vr-panel">
      <div className="vr-header">
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <select className="input" value={targetType} onChange={e => { setTargetType(e.target.value); setPage(1) }} style={{ width: 'auto', minWidth: 110 }}>
            <option value="">全部类型</option>
            {ALL_TARGET_TYPES.map(t => <option key={t} value={t}>{TYPE_CN[t] || t}</option>)}
          </select>
          <span className="vr-total">共 {total} 条</span>
        </div>
      </div>
      {error && <div className="vr-error">{error}</div>}
      <div className="vr-table-wrap">
        <table className="vr-table">
          <thead>
            <tr>
              <th className="vr-th-check"><input type="checkbox" checked={items.length > 0 && items.every(i => selectedIds.has(i.target_id))} onChange={toggleAll} /></th>
              <th className="vr-th-type">类型</th>
              <th className="vr-th-label">名称</th>
              {actionType === 'rule_check' && <><th className="vr-th-status">Mirror状态</th><th className="vr-th-conf">置信度</th><th className="vr-th-issues">校验问题</th></>}
              {actionType === 'review' && <><th className="vr-th-status">审核状态</th><th className="vr-th-conf">置信度</th><th className="vr-th-issues">问题</th></>}
              {actionType === 'dual_model' && <><th className="vw-th-stage">共识状态</th><th className="vr-th-conf">DeepSeek</th><th className="vr-th-conf">Kimi</th></>}
              <th className="vr-th-act"></th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && <tr><td colSpan={7} className="vr-empty">加载中…</td></tr>}
            {!loading && items.length === 0 && !error && <tr><td colSpan={7} className="vr-empty">暂无数据</td></tr>}
            {items.map((item, idx) => {
              const sel = selectedIds.has(item.target_id)
              const b = item.blocker_count ?? 0; const e = item.error_count ?? 0; const w = item.warning_count ?? 0
              const conflict = item.consensus_status === 'model_conflict'
              return (
                <tr key={item.target_type + item.target_id} className={`vr-row${sel ? ' selected' : ''}${idx % 2 === 0 ? ' even' : ''}`}
                  onClick={() => toggleRow(item.target_id)}>
                  <td className="vr-td-check" onClick={e => e.stopPropagation()}><input type="checkbox" checked={sel} onChange={() => toggleRow(item.target_id)} /></td>
                  <td className="vr-td-type"><span className="vr-badge">{TYPE_CN[item.target_type] || item.target_type}</span></td>
                  <td className="vr-td-label" title={item.display_label || item.target_id}>{item.display_label || item.target_label || item.target_id.slice(0, 16)}</td>
                  {actionType === 'rule_check' && <>
                    <td className="vr-td-status"><StatusBadge status={item.mirror_status} /></td>
                    <td className="vr-td-conf">{item.confidence?.toFixed(2) ?? '—'}</td>
                    <td className="vr-td-issues">
                      {b > 0 ? <span className="vr-issue b">B:{b}</span> : null}
                      {e > 0 ? <span className="vr-issue e">E:{e}</span> : null}
                      {w > 0 ? <span className="vr-issue w">W:{w}</span> : null}
                      {!b && !e && !w && <span className="vr-clean">✓</span>}
                    </td>
                  </>}
                  {actionType === 'review' && <>
                    <td className="vr-td-status"><StatusBadge status={item.review_status} /></td>
                    <td className="vr-td-conf">{item.confidence?.toFixed(2) ?? '—'}</td>
                    <td className="vr-td-issues">
                      {b > 0 ? <span className="vr-issue b">B:{b}</span> : null}
                      {w > 0 ? <span className="vr-issue w">W:{w}</span> : null}
                      {!b && !w && <span className="vr-clean">✓</span>}
                    </td>
                  </>}
                  {actionType === 'dual_model' && <>
                    <td className="vw-td-stage">
                      {conflict ? <span className="vw-stage-badge vw-bad">⚡冲突</span>
                       : item.consensus_status === 'consensus_supported' ? <span className="vw-stage-badge vw-ok">🤝一致</span>
                       : <span className="vw-stage-badge vw-muted">—</span>}
                    </td>
                    <td className="vr-td-conf">{item.confidence?.toFixed(2) ?? '—'}</td>
                    <td className="vr-td-conf">—</td>
                  </>}
                  <td className="vr-td-act"><button type="button" className="btn btn-xs btn-ghost" onClick={e => { e.stopPropagation(); openDetail(item) }}><Eye size={14} /></button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="vr-pagination">
        <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
        <span>第 {page}/{totalPages} 页</span>
        <button disabled={page >= totalPages} onClick={() => load(page + 1)}>下一页</button>
      </div>
      {selectedIds.size > 0 && (
        <div className="vr-action-bar">
          <span>已选 <strong>{selectedIds.size}</strong> 项</span>
          <button type="button" className="btn btn-xs btn-ghost" onClick={() => setSelectedIds(new Set())}>清空</button>
          <div className="vr-action-sep" />
          {actionType === 'rule_check' && (
            <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading !== null}
              onClick={async () => { setActionLoading('validate'); for (const id of [...selectedIds]) { const it = items.find(i => i.target_id === id); if (it) try { await submitMirrorReviewAction({ target_type: it.target_type, target_id: id, action: 'accept_signal', reviewer: 'admin', reviewer_note: 'rule_checked' }) } catch {} } setSelectedIds(new Set()); await load(page); setActionLoading(null) }}>
              <Search size={14} /> 执行规则校验</button>
          )}
          {actionType === 'review' && (<>
            <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading !== null} onClick={() => doReview('approve', [...selectedIds])}><Check size={14} /> 批准</button>
            <button type="button" className="btn btn-sm btn-danger" disabled={actionLoading !== null} onClick={() => doReview('reject', [...selectedIds])}><X size={14} /> 拒绝</button>
          </>)}
          {actionType === 'dual_model' && (
            <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading !== null}
              onClick={async () => { setActionLoading('dual'); for (const id of [...selectedIds]) { const it = items.find(i => i.target_id === id); if (it) try { await submitMirrorReviewAction({ target_type: it.target_type, target_id: id, action: 'accept_signal', reviewer: 'admin', reviewer_note: 'dual_model_requested' }) } catch {} } setSelectedIds(new Set()); await load(page); setActionLoading(null) }}>
              <Zap size={14} /> 触发双模型验证</button>
          )}
        </div>
      )}
      {/* Detail modal */}
      {modal.open && modal.item && (
        <div className="vr-modal-overlay" onClick={closeModal}>
          <div className="vr-modal" onClick={e => e.stopPropagation()}>
            <div className="vr-modal-hd"><h3>{modal.item.display_label || '对象详情'}</h3><span className="vr-modal-meta">{TYPE_CN[modal.item.target_type] || modal.item.target_type} · {modal.item.target_id.slice(0, 8)}…</span><button className="vr-modal-close" onClick={closeModal}>✕</button></div>
            <div className="vr-modal-body">
              {modal.loading ? <div className="vr-modal-loading">加载中…</div> : modal.detail ? <>
                <section className="vr-section"><h4>对象数据</h4><pre className="vr-json">{JSON.stringify(modal.detail.object_json, null, 2)}</pre></section>
                {modal.detail.validation_results?.length > 0 && <section className="vr-section"><h4>校验结果</h4>{modal.detail.validation_results.map((r: any, i: number) => <div key={i} className="vr-result-row"><span className={`vr-result-badge vr-result-${r.severity || r.status || 'info'}`}>{(r.severity || r.status || '—').toUpperCase()}</span><span>{r.message || ''}</span></div>)}</section>}
                {modal.detail.evidence_records?.length > 0 && <section className="vr-section"><h4>证据记录</h4><div className="vr-evidence-list">{modal.detail.evidence_records.map((ev: any, i: number) => <div key={i} className="vr-evidence-item"><span className="vr-evidence-type">{ev.evidence_type || ev.type || '—'}</span><span className="vr-evidence-text">{(ev.evidence_text || ev.text || '').slice(0, 200)}</span></div>)}</div></section>}
                {modal.detail.review_records?.length > 0 && <section className="vr-section"><h4>审核历史</h4>{modal.detail.review_records.map((r: any, i: number) => <div key={i} className="vr-history-row"><span className={`vr-history-action vr-action-${r.action || 'unknown'}`}>{r.action || '—'}</span><span className="vr-history-reviewer">{r.reviewer || '—'}</span><span className="vr-history-note">{(r.reviewer_note || '').slice(0, 100)}</span></div>)}</section>}
              </> : <div className="vr-modal-loading">无法加载详情</div>}
            </div>
            {modal.detail && (
              <div className="vr-modal-ft">
                {modal.detail.allowed_actions?.includes('approve') && <button type="button" className="btn btn-primary" onClick={() => doReview('approve', [modal.item!.target_id])}><Check size={14} /> 批准</button>}
                {modal.detail.allowed_actions?.includes('reject') && <button type="button" className="btn btn-danger" onClick={() => doReview('reject', [modal.item!.target_id])}><X size={14} /> 拒绝</button>}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────
export function ValidationMirrorPanel(props: Props) {
  const { mirrorTab, onMirrorTabChange, granularityLevel } = props
  const isAction = ACTION_TABS.has(mirrorTab)

  const labels: Record<string, string> = {
    rule_check: '规则校验', review: '人工审核', dual_model: '双模型校验',
    connections: '连接', functions: '功能', circuits: '回路',
    triples: '三元组', evidence: '证据',
  }

  return (
    <div className="data-center-panel data-center-formal-tabs">
      <div className="data-center-boundary data-center-boundary-mirror">Mirror KG — 验证中心</div>
      <div className="data-center-subtabbar">
        {SUB_TABS.map(st => (
          <button key={st} type="button"
            className={`data-center-tab${mirrorTab === st ? ' data-center-tab-active' : ''}`}
            onClick={() => onMirrorTabChange(st)}>
            {labels[st] || st}
          </button>
        ))}
      </div>
      {isAction
        ? <ActionSubTab actionType={mirrorTab as 'rule_check' | 'review' | 'dual_model'} granularityLevel={granularityLevel} />
        : <BrowsingSubTab mirrorTab={mirrorTab} onMirrorTabChange={onMirrorTabChange} granularityLevel={granularityLevel} />
      }
    </div>
  )
}

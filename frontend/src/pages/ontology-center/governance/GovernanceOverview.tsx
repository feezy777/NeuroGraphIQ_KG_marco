import { useCallback, useEffect, useState } from 'react'
import {
  getGovernanceDashboard,
  runDeterministicGrounding,
  runOntologyAudit,
  type GovernanceDashboard,
} from '../../../api/endpoints'

export type GovernanceSubTab = 'functions' | 'regions' | 'relations'

export function GovernanceOverview({
  granularity,
  onNavigate,
}: {
  granularity: string
  onNavigate: (tab: GovernanceSubTab) => void
}) {
  const [data, setData] = useState<GovernanceDashboard | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [runResults, setRunResults] = useState<string[]>([])

  const load = useCallback(async () => {
    setLoading(true)
    try {
      setData(await getGovernanceDashboard({ granularity_level: granularity }))
    } catch {
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [granularity])

  useEffect(() => {
    load()
  }, [load])

  const runDeterministic = useCallback(async () => {
    setBusy('deterministic')
    setRunResults([])
    const results: string[] = []
    for (const targetType of ['circuit_function', 'projection_function', 'region_function']) {
      try {
        const r = await runDeterministicGrounding({ target_type: targetType, limit: 2000 })
        results.push(`${targetType}: 扫描 ${r.processed} · 成功 ${r.grounded} · 未命中 ${r.ungrounded}`)
      } catch (err) {
        results.push(`${targetType}: 失败 ${err instanceof Error ? err.message : String(err)}`)
      }
    }
    setRunResults(results)
    setBusy(null)
    await load()
  }, [load])

  const runAudit = useCallback(async () => {
    setBusy('audit')
    setRunResults([])
    try {
      const r = await runOntologyAudit({ granularity_level: granularity })
      setRunResults([`本体审计完成（${r.status}）：未锚定 ${r.summary.term_ungrounded} · 脑区待对齐 ${r.summary.region_unaligned} · 枚举异常 ${r.summary.enum_invalid}`])
    } catch (err) {
      setRunResults([`本体审计失败：${err instanceof Error ? err.message : String(err)}`])
    }
    setBusy(null)
    await load()
  }, [granularity, load])

  const cards = [
    { key: 'rate', label: '功能术语锚定率', value: data ? `${Math.round(data.function_anchor_rate * 100)}%` : '—', sub: data ? `${data.function_grounded}/${data.function_total}` : '', tab: 'functions' as GovernanceSubTab },
    { key: 'proposed', label: '待审核术语', value: data?.proposed_terms ?? '—', sub: 'proposed', tab: 'functions' as GovernanceSubTab },
    { key: 'ungrounded', label: '未锚定记录', value: data?.ungrounded_records ?? '—', sub: '需处理', tab: 'functions' as GovernanceSubTab },
    { key: 'region', label: '脑区待对齐', value: data?.region_unaligned ?? '—', sub: '候选审核', tab: 'regions' as GovernanceSubTab },
    { key: 'enum', label: '枚举/关系异常', value: data?.enum_anomalies ?? '—', sub: '异常值', tab: 'relations' as GovernanceSubTab },
    { key: 'audit', label: '最近审计', value: data?.last_audit_at ? new Date(data.last_audit_at).toLocaleString() : '未运行', sub: '本体审计', tab: 'relations' as GovernanceSubTab },
  ]

  return (
    <div className="card ontology-overview">
      <div className="ontology-overview-header">
        <span className="ontology-card-title">本体治理总览</span>
        <div className="ontology-overview-actions">
          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={runDeterministic}>
            {busy === 'deterministic' ? '运行中…' : '运行确定性锚定'}
          </button>
          <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={runAudit}>
            {busy === 'audit' ? '审计中…' : '运行本体审计'}
          </button>
          <button type="button" className="btn btn-sm" onClick={load}>刷新数据</button>
        </div>
      </div>
      {loading && <div className="ontology-empty">加载中…</div>}
      {!loading && (
        <div className="ontology-overview-grid">
          {cards.map(card => (
            <button key={card.key} type="button" className="ontology-stat-card" onClick={() => onNavigate(card.tab)}>
              <span className="ontology-stat-label">{card.label}</span>
              <span className="ontology-stat-value">{card.value}</span>
              <span className="ontology-stat-sub">{card.sub}</span>
            </button>
          ))}
        </div>
      )}
      {runResults.length > 0 && (
        <div className="ontology-run-results">
          {runResults.map((line, i) => (
            <div key={i} className="ontology-run-line">{line}</div>
          ))}
        </div>
      )}
    </div>
  )
}

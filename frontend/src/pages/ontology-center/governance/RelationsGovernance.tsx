import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  getVocabularyUsage,
  listChangeLogs,
  listEnumAnomalies,
  replaceEnumValues,
  type ChangeLogItem,
  type VocabularyUsageItem,
} from '../../../api/endpoints'

type RelationsSubView = 'registry' | 'anomalies' | 'constraints' | 'logs'

export function RelationsGovernance({ granularity, role }: { granularity: string; role: string }) {
  const [subView, setSubView] = useState<RelationsSubView>('registry')
  const [usage, setUsage] = useState<VocabularyUsageItem[]>([])
  const [field, setField] = useState('category')
  const [anomalies, setAnomalies] = useState<Array<{ target_type: string; target_id: string; field: string; value: string; granularity_level: string | null }>>([])
  const [anomalyTotal, setAnomalyTotal] = useState(0)
  const [message, setMessage] = useState<string | null>(null)
  const [logs, setLogs] = useState<ChangeLogItem[]>([])
  const [replaceForm, setReplaceForm] = useState({ old_value: '', new_code: '' })

  const loadUsage = useCallback(async () => {
    const resp = await getVocabularyUsage()
    setUsage(resp.items)
  }, [])
  const loadAnomalies = useCallback(async () => {
    const resp = await listEnumAnomalies({ field, granularity_level: granularity, limit: 50 })
    setAnomalies(resp.items)
    setAnomalyTotal(resp.total)
  }, [field, granularity])

  const loadLogs = useCallback(async () => {
    const resp = await listChangeLogs({ limit: 50 })
    setLogs(resp.items)
  }, [])

  useEffect(() => {
    if (subView === 'registry') loadUsage()
    if (subView === 'anomalies') loadAnomalies()
    if (subView === 'logs') loadLogs()
  }, [subView, loadUsage, loadAnomalies, loadLogs])

  const grouped = useMemo(() => {
    const map = new Map<string, VocabularyUsageItem[]>()
    for (const item of usage) {
      const list = map.get(item.vocab_type) ?? []
      list.push(item)
      map.set(item.vocab_type, list)
    }
    return [...map.entries()]
  }, [usage])

  const domainLabels: Record<string, string> = {
    connection_type: '连接类型与方向',
    directionality: '连接方向',
    circuit_type: '回路类型',
    circuit_region_role: '回路角色',
    step_type: '步骤类型',
    step_role: '步骤角色',
    projection_role: '投影角色',
    triple_subject_type: '三元组 subject 类型',
    triple_object_type: '三元组 object 类型',
    triple_scope: '三元组范围',
    category: '功能分类',
    relation_type: '功能关系',
    predicate: '谓词',
  }

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">关系与枚举</span>
        <span className="ontology-card-sub">共 {usage.length} 条词汇</span>
      </div>
      <div className="ontology-subview-tabs">
        {(
          [
            ['registry', '注册表'],
            ['anomalies', '异常值'],
            ['constraints', '约束说明'],
            ['logs', '审计日志'],
          ] as Array<[RelationsSubView, string]>
        ).map(([key, label]) => (
          <button key={key} type="button" className={`ontology-subview-tab ${subView === key ? 'ontology-subview-tab-active' : ''}`} onClick={() => setSubView(key)}>{label}</button>
        ))}
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      {subView === 'registry' && grouped.map(([type, items]) => (
        <details key={type} className="ontology-vocab-group" open>
          <summary>{domainLabels[type] ?? type}（{items.length}）</summary>
          <table className="data-table ontology-term-table">
            <thead><tr><th>code</th><th>中文</th><th>英文</th><th>状态</th><th>使用量</th><th>排序</th></tr></thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id}>
                  <td className="ontology-term-code">{item.code}</td>
                  <td>{item.label_cn ?? '—'}</td>
                  <td>{item.label_en ?? '—'}</td>
                  <td>{item.status}</td>
                  <td>{item.usage_count}</td>
                  <td>{item.seq}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
      {subView === 'anomalies' && (
        <div>
          <div className="ontology-form-row">
            <select className="filter-select" value={field} onChange={e => setField(e.target.value)}>
              {Object.keys(domainLabels).map(f => <option key={f} value={f}>{domainLabels[f]}</option>)}
            </select>
            <button type="button" className="btn btn-sm" onClick={loadAnomalies}>查询（{anomalyTotal}）</button>
          </div>
          {role === 'ontology_admin' && (
            <div className="ontology-form-row">
              <input className="filter-input" placeholder="旧值（异常值）" value={replaceForm.old_value} onChange={e => setReplaceForm(f => ({ ...f, old_value: e.target.value }))} />
              <select className="filter-select" value={replaceForm.new_code} onChange={e => setReplaceForm(f => ({ ...f, new_code: e.target.value }))}>
                <option value="">选择合法 code</option>
                {usage.filter(u => u.vocab_type === field).map(u => <option key={u.id} value={u.code}>{u.code}</option>)}
              </select>
              <button
                type="button"
                className="btn btn-sm"
                disabled={!replaceForm.old_value || !replaceForm.new_code}
                onClick={async () => {
                  setMessage(null)
                  try {
                    const r = await replaceEnumValues({ field, old_value: replaceForm.old_value, new_code: replaceForm.new_code })
                    setMessage(`已替换 ${r.updated} 条`)
                    await loadAnomalies()
                  } catch (err) {
                    setMessage(`替换失败：${err instanceof Error ? err.message : String(err)}`)
                  }
                }}
              >
                批量替换
              </button>
            </div>
          )}
          <table className="data-table ontology-term-table">
            <thead><tr><th>类型</th><th>ID</th><th>字段</th><th>异常值</th><th>颗粒度</th></tr></thead>
            <tbody>
              {anomalies.map(a => (
                <tr key={`${a.target_type}-${a.target_id}`}>
                  <td>{a.target_type}</td><td>{a.target_id}</td><td>{a.field}</td><td className="ontology-anomaly-value">{a.value}</td><td>{a.granularity_level ?? '—'}</td>
                </tr>
              ))}
              {anomalies.length === 0 && <tr><td colSpan={5} className="ontology-empty">没有异常值</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {subView === 'constraints' && (
        <div className="ontology-constraints">
          {Object.entries(domainLabels).map(([type, label]) => (
            <div key={type} className="ontology-constraint-item">
              <strong>{label}</strong>
              <span>允许值见注册表；非法值由校验规则 ONT_ENUM_INVALID / ONT_PREDICATE_UNKNOWN 拦截（blocker），可在“异常值”视图批量替换为合法 code。</span>
            </div>
          ))}
        </div>
      )}
      {subView === 'logs' && (
        <table className="data-table ontology-term-table">
          <thead><tr><th>时间</th><th>操作</th><th>实体</th><th>操作者</th><th>原因</th></tr></thead>
          <tbody>
            {logs.map(log => (
              <tr key={log.id}>
                <td>{new Date(log.created_at).toLocaleString()}</td>
                <td>{log.action_type}</td>
                <td>{log.entity_type}:{log.entity_id.slice(0, 8)}</td>
                <td>{log.operator_id ?? 'system'}</td>
                <td>{log.reason ?? '—'}</td>
              </tr>
            ))}
            {logs.length === 0 && <tr><td colSpan={5} className="ontology-empty">暂无审计日志</td></tr>}
          </tbody>
        </table>
      )}
    </div>
  )
}

import { useEffect, useState } from 'react'
import { listDuplicateTerms } from '../../../api/endpoints'

export function DuplicatesView() {
  const [groups, setGroups] = useState<Array<{ basis: string; term_ids: string[] }>>([])
  const [total, setTotal] = useState(0)
  useEffect(() => {
    listDuplicateTerms({ limit: 50 }).then(r => { setGroups(r.items); setTotal(r.total) }).catch(() => undefined)
  }, [])
  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">合并建议（疑似重复）</span>
        <span className="ontology-card-sub">共 {total} 组</span>
      </div>
      <table className="data-table ontology-term-table">
        <thead><tr><th>依据</th><th>术语 ID</th></tr></thead>
        <tbody>
          {groups.map((g, i) => (
            <tr key={i}><td>{g.basis}</td><td>{g.term_ids.join(', ')}</td></tr>
          ))}
          {groups.length === 0 && <tr><td colSpan={2} className="ontology-empty">暂无疑似重复</td></tr>}
        </tbody>
      </table>
    </div>
  )
}

import { useEffect, useState } from 'react'
import {
  getOntologyCoverage,
  listOntologyTerms,
  type OntologyCoverage,
  type OntologyTerm,
} from '../../api/endpoints'

export function OntologyCoverageCard() {
  const [coverage, setCoverage] = useState<OntologyCoverage | null>(null)
  const [proposed, setProposed] = useState<OntologyTerm[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    Promise.all([getOntologyCoverage(), listOntologyTerms({ status: 'proposed', limit: 20 })])
      .then(([c, t]) => {
        if (!alive) return
        setCoverage(c)
        setProposed(t.items)
      })
      .catch(() => {
        if (alive) setError('加载失败')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  if (loading) {
    return <div className="card ontology-card">本体锚定覆盖率加载中…</div>
  }
  if (error || !coverage) {
    return <div className="card ontology-card">本体锚定覆盖率：{error ?? '暂无数据'}</div>
  }

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">本体锚定覆盖率</span>
        <span className="ontology-card-sub">
          active {coverage.active_terms} · proposed {coverage.proposed_terms}
        </span>
      </div>
      <div className="ontology-card-grid">
        {coverage.items.map(item => {
          const pct = item.total ? Math.round((item.grounded / item.total) * 100) : 0
          return (
            <div key={item.key} className="ontology-card-item">
              <span className="ontology-card-label">{item.label}</span>
              <span className="ontology-card-value">
                {item.grounded}/{item.total}
              </span>
              <span className={`ontology-card-pct ${pct >= 95 ? 'ontology-card-pct-ok' : ''}`}>{pct}%</span>
            </div>
          )
        })}
      </div>
      <details className="ontology-proposed-list">
        <summary>待审核新词（{coverage.proposed_terms}）</summary>
        <ul>
          {proposed.slice(0, 10).map(term => (
            <li key={term.id}>
              {term.canonical_term_en}
              <span className="ontology-term-meta">（{term.created_by}）</span>
            </li>
          ))}
          {proposed.length === 0 && <li>暂无待审核新词</li>}
        </ul>
      </details>
    </div>
  )
}

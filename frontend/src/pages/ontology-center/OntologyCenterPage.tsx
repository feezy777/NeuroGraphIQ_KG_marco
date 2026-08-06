import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import {
  activateOntologyTerm,
  addOntologySynonym,
  deprecateOntologyTerm,
  getOntologyCoverage,
  getRegionAlignment,
  listOntologyTerms,
  listOntologyVocabularies,
  mergeOntologyTerm,
  type OntologyCoverage,
  type OntologyTerm,
  type OntologyVocabulary,
  type RegionAlignmentSummary,
} from '../../api/endpoints'

type TabId = 'functions' | 'regions' | 'relations'
type TermStatusFilter = 'proposed' | 'active' | 'all'

const PAGE_SIZE = 50

export function OntologyCenterPage() {
  const { granularity } = useGlobalGranularity()
  const [tab, setTab] = useState<TabId>('functions')

  return (
    <div className="data-center-page">
      <div className="data-center-header-static">
        <PageHeader title="本体中心" description="功能/脑区/关系本体，跟随顶部颗粒度切换" readonly />
      </div>
      <div className="ontology-page">
        <div className="ontology-page-tabs">
          {(
            [
              ['functions', '功能'],
              ['regions', '脑区'],
              ['relations', '关系'],
            ] as Array<[TabId, string]>
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`ontology-page-tab ${tab === key ? 'ontology-page-tab-active' : ''}`}
              onClick={() => setTab(key)}
            >
              {label}
            </button>
          ))}
          <span className="ontology-page-granularity">当前颗粒度：{granularity}</span>
        </div>
        {tab === 'functions' && <FunctionsTab granularity={granularity} />}
        {tab === 'regions' && <RegionsTab granularity={granularity} />}
        {tab === 'relations' && <RelationsTab />}
      </div>
    </div>
  )
}

function FunctionsTab({ granularity }: { granularity: string }) {
  const [coverage, setCoverage] = useState<OntologyCoverage | null>(null)
  const [terms, setTerms] = useState<OntologyTerm[]>([])
  const [total, setTotal] = useState(0)
  const [status, setStatus] = useState<TermStatusFilter>('proposed')
  const [q, setQ] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)

  const loadCoverage = useCallback(async () => {
    try {
      setCoverage(await getOntologyCoverage({ granularity_level: granularity }))
    } catch {
      setCoverage(null)
    }
  }, [granularity])

  const loadTerms = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await listOntologyTerms({
        status: status === 'all' ? undefined : status,
        q: q || undefined,
        limit: PAGE_SIZE,
        offset,
      })
      setTerms(resp.items)
      setTotal(resp.total)
    } catch {
      setTerms([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [status, q, offset])

  useEffect(() => {
    loadCoverage()
  }, [loadCoverage])

  useEffect(() => {
    loadTerms()
  }, [loadTerms])

  const refresh = useCallback(async () => {
    await Promise.all([loadCoverage(), loadTerms()])
  }, [loadCoverage, loadTerms])

  const runAction = useCallback(
    async (action: () => Promise<unknown>, okText: string) => {
      setMessage(null)
      try {
        await action()
        setMessage(okText)
        await refresh()
      } catch (err) {
        setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
      }
    },
    [refresh],
  )

  const handleMerge = useCallback(
    async (term: OntologyTerm) => {
      const targetText = window.prompt(`将「${term.canonical_term_en}」合并到哪个词？（输入 canonical 词）`)
      if (!targetText?.trim()) return
      const resp = await listOntologyTerms({ q: targetText.trim(), status: 'active', limit: 5 })
      const target = resp.items.find(t => t.canonical_term_en.toLowerCase() === targetText.trim().toLowerCase())
      if (!target) {
        setMessage('未找到目标 active 词，请检查名称')
        return
      }
      await runAction(() => mergeOntologyTerm(term.id, target.id), `已合并到 ${target.canonical_term_en}`)
    },
    [runAction],
  )

  const handleSynonym = useCallback(
    async (term: OntologyTerm) => {
      const text = window.prompt(`为「${term.canonical_term_en}」添加同义词：`)
      if (!text?.trim()) return
      await runAction(() => addOntologySynonym(term.id, { synonym_text: text.trim() }), `已添加同义词 ${text.trim()}`)
    },
    [runAction],
  )

  return (
    <div>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="card ontology-card">
        <div className="ontology-card-header">
          <span className="ontology-card-title">功能术语锚定覆盖率</span>
          <span className="ontology-card-sub">
            active {coverage?.active_terms ?? '-'} · proposed {coverage?.proposed_terms ?? '-'}
          </span>
        </div>
        <div className="ontology-card-grid">
          {(coverage?.items ?? []).map(item => {
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
          {coverage && coverage.items.every(i => i.total === 0) && (
            <div className="ontology-empty">当前颗粒度暂无功能数据，请用顶部切换器切换颗粒度</div>
          )}
        </div>
      </div>

      <div className="card ontology-card">
        <div className="ontology-card-header">
          <span className="ontology-card-title">术语列表</span>
          <div className="ontology-page-filters">
            <input
              className="filter-input"
              placeholder="搜索术语"
              value={q}
              onChange={e => {
                setQ(e.target.value)
                setOffset(0)
              }}
            />
            <select
              className="filter-select"
              value={status}
              onChange={e => {
                setStatus(e.target.value as TermStatusFilter)
                setOffset(0)
              }}
            >
              <option value="proposed">待审核</option>
              <option value="active">已激活</option>
              <option value="all">全部</option>
            </select>
            <button type="button" className="btn btn-sm" onClick={refresh}>刷新</button>
          </div>
        </div>
        <table className="data-table ontology-term-table">
          <thead>
            <tr>
              <th>词条</th>
              <th>代码</th>
              <th>状态</th>
              <th>来源</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={5} className="ontology-empty">加载中…</td></tr>
            )}
            {!loading && terms.length === 0 && (
              <tr><td colSpan={5} className="ontology-empty">暂无术语</td></tr>
            )}
            {terms.map(term => (
              <tr key={term.id}>
                <td>
                  {term.canonical_term_en}
                  {term.canonical_term_cn ? <span className="ontology-term-meta">（{term.canonical_term_cn}）</span> : null}
                </td>
                <td className="ontology-term-code">{term.term_code}</td>
                <td><span className={`ontology-status ontology-status-${term.status}`}>{term.status}</span></td>
                <td>{term.created_by}</td>
                <td className="ontology-term-actions">
                  {term.status === 'proposed' && (
                    <button type="button" className="btn btn-xs" onClick={() => runAction(() => activateOntologyTerm(term.id), '已激活')}>激活</button>
                  )}
                  {term.status === 'active' && (
                    <button type="button" className="btn btn-xs" onClick={() => runAction(() => deprecateOntologyTerm(term.id), '已弃用')}>弃用</button>
                  )}
                  <button type="button" className="btn btn-xs" onClick={() => handleMerge(term)}>合并</button>
                  <button type="button" className="btn btn-xs" onClick={() => handleSynonym(term)}>同义词</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="ontology-page-pager">
          <button
            type="button"
            className="btn btn-xs"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            上一页
          </button>
          <span>{offset + 1}-{Math.min(offset + PAGE_SIZE, total)} / {total}</span>
          <button
            type="button"
            className="btn btn-xs"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}

function RegionsTab({ granularity }: { granularity: string }) {
  const [data, setData] = useState<RegionAlignmentSummary | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    setLoading(true)
    getRegionAlignment({ granularity_level: granularity })
      .then(d => {
        if (alive) setData(d)
      })
      .catch(() => {
        if (alive) setData(null)
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [granularity])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">脑区外部标识对齐</span>
        <span className="ontology-card-sub">
          {data ? `已对齐 ${data.aligned} / ${data.total}` : ''}
        </span>
      </div>
      {loading && <div className="ontology-empty">加载中…</div>}
      {!loading && data && data.total === 0 && (
        <div className="ontology-empty">当前颗粒度暂无脑区数据，请用顶部切换器切换颗粒度</div>
      )}
      {!loading && data && data.total > 0 && (
        <table className="data-table ontology-term-table">
          <thead>
            <tr>
              <th>脑区</th>
              <th>图谱</th>
              <th>UBERON</th>
              <th>NIFSTD</th>
              <th>状态</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map(item => (
              <tr key={item.id}>
                <td>{item.en_name}{item.cn_name ? <span className="ontology-term-meta">（{item.cn_name}）</span> : null}</td>
                <td>{item.source_atlas}</td>
                <td>{item.uberon_iri ? <a href={item.uberon_iri} target="_blank" rel="noreferrer">{item.uberon_iri}</a> : '—'}</td>
                <td>{item.nifstd_iri ? <a href={item.nifstd_iri} target="_blank" rel="noreferrer">{item.nifstd_iri}</a> : '—'}</td>
                <td><span className={`ontology-status ontology-status-${item.alignment_status}`}>{item.alignment_status}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function RelationsTab() {
  const [vocab, setVocab] = useState<OntologyVocabulary[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    listOntologyVocabularies()
      .then(resp => {
        if (alive) setVocab(resp.items)
      })
      .catch(() => {
        if (alive) setVocab([])
      })
      .finally(() => {
        if (alive) setLoading(false)
      })
    return () => {
      alive = false
    }
  }, [])

  const grouped = useMemo(() => {
    const map = new Map<string, OntologyVocabulary[]>()
    for (const item of vocab) {
      const list = map.get(item.vocab_type) ?? []
      list.push(item)
      map.set(item.vocab_type, list)
    }
    return [...map.entries()]
  }, [vocab])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">关系与枚举词汇表</span>
        <span className="ontology-card-sub">共 {vocab.length} 条（只读）</span>
      </div>
      {loading && <div className="ontology-empty">加载中…</div>}
      {!loading && grouped.map(([type, items]) => (
        <details key={type} className="ontology-vocab-group" open>
          <summary>{type}（{items.length}）</summary>
          <table className="data-table ontology-term-table">
            <thead>
              <tr><th>code</th><th>label_en</th><th>label_cn</th><th>status</th><th>seq</th></tr>
            </thead>
            <tbody>
              {items.map(item => (
                <tr key={item.id}>
                  <td className="ontology-term-code">{item.code}</td>
                  <td>{item.label_en ?? '—'}</td>
                  <td>{item.label_cn ?? '—'}</td>
                  <td>{item.status}</td>
                  <td>{item.seq}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      ))}
    </div>
  )
}

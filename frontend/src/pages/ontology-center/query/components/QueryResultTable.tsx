import { useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronRight } from 'lucide-react'
import type {
  OntologyQueryResultItem,
  OntologyQueryCategory,
} from '../../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../../browser/tree/OntologyTreeNode'
import { CATEGORY_TO_ENTITY_TYPE } from '../queryTypes'
import {
  categoryLabel,
  confidencePercent,
  directionLabel,
  displayName,
  provenanceLabel,
  relationLabel,
} from '../queryFormat'
import { ConfidenceMeter } from './ConfidenceMeter'

type TabKey = 'all' | 'provenance' | 'circuit'

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'all', label: '结构结果' },
  { key: 'provenance', label: '证据链' },
  { key: 'circuit', label: '相关回路' },
]

interface ConnectionDetail {
  direction?: string
  endpoint_region?: {
    id?: string
    canonical_name_cn?: string | null
    canonical_name_en?: string | null
  }
}

/** 行点击跳转目标：连接项优先跳对端脑区，其余按分类映射本体类型 */
function targetOf(item: OntologyQueryResultItem): { type: OntologyEntityType; id: string } | null {
  if (item.category === 'connection') {
    const endpoint = (item.detail as ConnectionDetail).endpoint_region
    if (endpoint?.id) return { type: 'region', id: endpoint.id }
  }
  const type = CATEGORY_TO_ENTITY_TYPE[item.category]
  return type ? { type, id: item.id } : null
}

/** 结果表：结构结果 / 证据链 / 相关回路 三个 Tab；置信度列可排序（默认降序） */
export function QueryResultTable({
  items,
  onOpenDetail,
}: {
  items: OntologyQueryResultItem[]
  onOpenDetail: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const [tab, setTab] = useState<TabKey>('all')
  const [sortDesc, setSortDesc] = useState(true)

  const sorted = useMemo(() => {
    const list = [...items]
    list.sort((a, b) => {
      const ca = a.confidence ?? -1
      const cb = b.confidence ?? -1
      return sortDesc ? cb - ca : ca - cb
    })
    return list
  }, [items, sortDesc])

  /** 证据链 Tab：按来源分组（数量降序） */
  const provenanceGroups = useMemo(() => {
    const byLabel = new Map<string, OntologyQueryResultItem[]>()
    for (const item of sorted) {
      const label = provenanceLabel(item.provenance)
      const group = byLabel.get(label) ?? []
      group.push(item)
      byLabel.set(label, group)
    }
    return [...byLabel.entries()]
      .map(([label, group]) => ({ label, group }))
      .sort((a, b) => b.group.length - a.group.length)
  }, [sorted])

  const circuitItems = useMemo(
    () => sorted.filter(item => item.category === 'circuit'),
    [sorted],
  )

  const headerCell = (
    key: string,
    content: React.ReactNode,
    sortable = false,
  ) => {
    if (!sortable) return <th key={key} scope="col">{content}</th>
    return (
      <th key={key} scope="col" aria-sort={sortDesc ? 'descending' : 'ascending'}>
        <button
          type="button"
          className="oqd-th-sort"
          onClick={() => setSortDesc(prev => !prev)}
          title="切换置信度排序"
        >
          {content}
          {sortDesc ? <ArrowDown size={12} aria-hidden="true" /> : <ArrowUp size={12} aria-hidden="true" />}
        </button>
      </th>
    )
  }

  const renderRow = (item: OntologyQueryResultItem) => {
    const target = targetOf(item)
    return (
      <tr
        key={item.id}
        className={target ? 'oqd-row-clickable' : undefined}
        onClick={target ? () => onOpenDetail(target.type, target.id) : undefined}
      >
        <td className="oqd-td-entity">
          {displayName(item)}
          {item.code && <span className="oqd-td-code">{item.code}</span>}
        </td>
        <td>{categoryLabel(item)}</td>
        <td>{relationLabel(item)}</td>
        <td>{directionLabel((item.detail as ConnectionDetail).direction)}</td>
        <td className="oqd-td-confidence">
          <ConfidenceMeter value={item.confidence} />
        </td>
        <td className="oqd-td-source">{provenanceLabel(item.provenance)}</td>
      </tr>
    )
  }

  const renderAll = () => (
    <table className="oqd-table">
      <thead>
        <tr>
          {headerCell('entity', '实体')}
          {headerCell('category', '类型')}
          {headerCell('relation', '关系')}
          {headerCell('direction', '方向')}
          {headerCell('confidence', '置信度', true)}
          {headerCell('source', '来源')}
        </tr>
      </thead>
      <tbody>{sorted.map(renderRow)}</tbody>
    </table>
  )

  const renderProvenance = () => (
    <div className="oqd-provenance-list">
      {provenanceGroups.map(group => (
        <div key={group.label} className="oqd-provenance-group">
          <div className="oqd-provenance-head">
            <span className="oqd-provenance-label">{group.label}</span>
            <span className="oqd-provenance-count">{group.group.length} 条</span>
          </div>
          <table className="oqd-table oqd-table-nested">
            <tbody>{group.group.map(renderRow)}</tbody>
          </table>
        </div>
      ))}
    </div>
  )

  const renderCircuit = () =>
    circuitItems.length === 0 ? (
      <p className="oqd-tab-empty">该实体暂无相关回路结果</p>
    ) : (
      <table className="oqd-table">
        <thead>
          <tr>
            {headerCell('entity', '实体')}
            {headerCell('category', '类型')}
            {headerCell('relation', '关系')}
            {headerCell('direction', '方向')}
            {headerCell('confidence', '置信度', true)}
            {headerCell('source', '来源')}
          </tr>
        </thead>
        <tbody>{circuitItems.map(renderRow)}</tbody>
      </table>
    )

  return (
    <section className="oqd-results" aria-label="Query Results">
      <div className="oqd-tabs" role="tablist" aria-label="结果视图">
        {TABS.map(t => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`oqd-tab${tab === t.key ? ' oqd-tab-active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {t.key === 'circuit' && circuitItems.length > 0 && (
              <span className="oqd-tab-count">{circuitItems.length}</span>
            )}
          </button>
        ))}
      </div>
      {tab === 'all' && renderAll()}
      {tab === 'provenance' && renderProvenance()}
      {tab === 'circuit' && renderCircuit()}
      {items.length > 0 && (
        <div className="oqd-results-hint">
          <ChevronRight size={12} aria-hidden="true" />
          点击行查看本体详情
        </div>
      )}
    </section>
  )
}

export type { OntologyQueryCategory }

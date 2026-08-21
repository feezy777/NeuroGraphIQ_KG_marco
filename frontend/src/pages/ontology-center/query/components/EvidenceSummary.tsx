import type { OntologyQueryResultItem } from '../../../../api/ontologyQueryApi'
import { CONNECTION_KIND_LABELS, connectionKind, type ConnectionKind } from '../queryFormat'

const KINDS: Array<ConnectionKind | 'other'> = ['structural', 'functional', 'uncertain', 'other']

const KIND_LABELS: Record<string, string> = { ...CONNECTION_KIND_LABELS, other: '其他' }

/** Evidence Summary：按连接类型统计（结构蓝 / 功能绿 / 不确定橙 / 其他灰） */
export function EvidenceSummary({ items }: { items: OntologyQueryResultItem[] }) {
  if (items.length === 0) return null

  const counts: Record<ConnectionKind | 'other', number> = {
    structural: 0,
    functional: 0,
    uncertain: 0,
    other: 0,
  }
  for (const item of items) {
    if (item.category === 'connection') counts[connectionKind(item)] += 1
    else counts.other += 1
  }
  const visible = KINDS.filter(kind => counts[kind] > 0)
  if (visible.length === 0) return null

  return (
    <section className="oqd-evidence-summary" aria-label="Evidence Summary">
      <div className="oqd-card-header">
        <h3>Evidence Summary</h3>
      </div>
      <div className="oqd-evidence-grid">
        {visible.map(kind => (
          <div key={kind} className={`oqd-evs oqd-evs-${kind}`}>
            <span className="oqd-evs-count">{counts[kind]}</span>
            <span className="oqd-evs-label">{KIND_LABELS[kind]}</span>
            <span className="oqd-evs-bar" aria-hidden="true">
              <span
                className="oqd-evs-bar-fill"
                style={{ width: `${Math.round((counts[kind] / items.length) * 100)}%` }}
              />
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}

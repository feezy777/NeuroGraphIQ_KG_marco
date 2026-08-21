import type { OntologyQueryResultItem } from '../../../../api/ontologyQueryApi'
import { groupProvenances } from '../queryFormat'
import { SectionCard } from '../../ui/SectionCard'

/** Evidence Source 卡片（右侧栏）：结果按来源分组，数量 + 占比条 */
export function SourceListCard({ items }: { items: OntologyQueryResultItem[] }) {
  const groups = groupProvenances(items)
  if (groups.length === 0) return null

  return (
    <SectionCard title="Evidence Source" count={items.length}>
      <ul className="oqd-source-list">
        {groups.map(group => (
          <li key={group.label} className="oqd-source-row">
            <div className="oqd-source-head">
              <span className="oqd-source-label">{group.label}</span>
              <span className="oqd-source-count">
                {group.count} 条 · {Math.round((group.count / items.length) * 100)}%
              </span>
            </div>
            <div className="oqd-source-bar" aria-hidden="true">
              <span
                className="oqd-source-bar-fill"
                style={{ width: `${Math.round((group.count / items.length) * 100)}%` }}
              />
            </div>
            {group.examples.length > 0 && (
              <span className="oqd-source-examples" title={group.examples.join(' / ')}>
                {group.examples.slice(0, 2).join(' / ')}
              </span>
            )}
          </li>
        ))}
      </ul>
    </SectionCard>
  )
}

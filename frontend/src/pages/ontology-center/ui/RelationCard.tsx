import { ArrowDown, ArrowUp } from 'lucide-react'
import { EntityIcon } from './EntityIcon'
import { StatusChip } from './StatusChip'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'
import type { RelationItem } from '../detail/types'

/**
 * 单条关系的 Card（右栏关系浏览器 / Inspector 拓扑共用）：
 * 信息优先级分行展示——
 *   1. 名称（第一优先，最多两行不截断）
 *   2. code（mono 单行省略，hover tooltip 完整）
 *   3. 状态（ACTIVE 等）
 *   4. meta 逐行 key/value
 * 名称与 code 不在同一行；card padding 12px、宽度固定填满列。
 */
export function RelationCard({
  item,
  navigable = true,
  arrow,
  onNavigate,
}: {
  item: RelationItem
  navigable?: boolean
  /** 关系方向箭头：up = 父节点，down = 子节点 */
  arrow?: 'up' | 'down'
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const ref = item.ref
  const body = (
    <span className="oc-relation-card-body">
      <span className="oc-relation-card-head">
        <EntityIcon entityType={ref.entityType} size={16} className="oc-entity-chip-icon" />
        <span className="oc-relation-card-name">{ref.name}</span>
        {arrow && (
          <span className={`oc-relation-arrow oc-relation-arrow-${arrow}`} aria-hidden="true">
            {arrow === 'up' ? <ArrowUp size={14} /> : <ArrowDown size={14} />}
          </span>
        )}
      </span>
      {ref.code && (
        <span className="oc-relation-card-code" title={ref.code}>
          {ref.code}
        </span>
      )}
      {ref.status && (
        <span className="oc-relation-card-status">
          <StatusChip status={ref.status} />
        </span>
      )}
      {item.meta.length > 0 && (
        <span className="oc-relation-card-meta">
          {item.meta.map(meta => (
            <span className="oc-relation-card-meta-row" key={meta.label}>
              <em>{meta.label}</em>
              <span>{meta.value}</span>
            </span>
          ))}
        </span>
      )}
    </span>
  )

  if (!navigable) {
    return <div className="oc-relation-card oc-relation-card-static">{body}</div>
  }
  return (
    <button
      type="button"
      className="oc-relation-card"
      onClick={() => onNavigate?.(ref.entityType, ref.id)}
      disabled={!onNavigate}
    >
      {body}
    </button>
  )
}

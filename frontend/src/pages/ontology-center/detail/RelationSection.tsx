import { EmptyState } from '../ui/EmptyState'
import { RelationCard } from '../ui/RelationCard'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'
import type { RelationGroup, RelationItem } from './types'

type RelationSectionProps = {
  group: RelationGroup
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}

/**
 * 关系方向箭头：parent=上，children=下。
 * 连接卡片的方向已编码在名称 "Source → Target" 中，不再叠加图标；
 * 出向/入向仍保留在 meta 行。
 */
function arrowFor(group: RelationGroup): 'up' | 'down' | undefined {
  if (group.key === 'parent') return 'up'
  if (group.key === 'children') return 'down'
  return undefined
}

/**
 * 统一关系分组（Phase 3）：组头 + RelationCard 列表。
 * - unavailable = 后端暂无该关系 API → 空状态 + 原因（不写假数据）
 * - navigable=false → 静态卡（如对齐候选等非实体记录）
 */
export function RelationSection({ group, onNavigate }: RelationSectionProps) {
  return (
    <section className="oc-relation-group">
      <header className="oc-relation-group-header">
        <span className="oc-relation-group-label">{group.label}</span>
        {!group.unavailable && (
          <span className="oc-relation-group-count">{group.items.length}</span>
        )}
      </header>
      {group.unavailable ? (
        <EmptyState
          title="No canonical relation available"
          reason="后端 API 待接入（不展示假数据）"
        />
      ) : group.items.length === 0 ? (
        <EmptyState title="No canonical relation available" reason="该实体暂无此关系记录" />
      ) : (
        group.items.map(item => (
          <RelationCard
            key={item.ref.id}
            item={item}
            navigable={group.navigable !== false}
            arrow={arrowFor(group)}
            onNavigate={onNavigate}
          />
        ))
      )}
    </section>
  )
}

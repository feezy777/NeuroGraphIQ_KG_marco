import { EntityIcon } from './EntityIcon'
import { OntologyBadge } from './OntologyBadge'
import { StatusChip } from './StatusChip'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'

/** 实体图标 + 名称 + code + 状态 的内联组合（关系卡片头 / 详情头共用） */
export function EntityChip({
  entityType,
  name,
  code,
  status,
  size = 14,
  hideCode = false,
}: {
  entityType: OntologyEntityType
  name: string
  code?: string | null
  status?: string | null
  size?: number
  /** code 单独成行展示的容器（如 RelationCard）隐藏内联 badge */
  hideCode?: boolean
}) {
  return (
    <span className="oc-entity-chip">
      <EntityIcon entityType={entityType} size={size} className="oc-entity-chip-icon" />
      <span className="oc-entity-chip-name">{name}</span>
      {!hideCode && code && (
        <OntologyBadge variant="code" title={code}>
          {code}
        </OntologyBadge>
      )}
      <StatusChip status={status} />
    </span>
  )
}

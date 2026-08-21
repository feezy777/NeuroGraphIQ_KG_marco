import { Brain } from 'lucide-react'
import type { OntologyQueryEntity } from '../../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../../browser/tree/OntologyTreeNode'
import { ENTITY_TYPE_LABELS, GRANULARITY_LEVEL_NAMES } from '../../browser/tree/OntologyTreeNode'
import { MATCHED_BY_LABELS } from '../queryTypes'
import { SectionCard } from '../../ui/SectionCard'

/**
 * Recognized Entity 卡片（右侧栏第一模块）。
 * 名称 + code + 类型/匹配层级/置信度 dl；粒度/状态/别名由 props 传入，
 * API 未提供时优雅隐藏（不渲染空行）。
 */
export function EntityContextCard({
  entity,
  confidence,
  granularity,
  status,
  aliases,
  onOpenDetail,
}: {
  entity: OntologyQueryEntity | null
  /** 语义置信度（response.confidence） */
  confidence: number
  granularity?: string | null
  status?: string | null
  aliases?: string[]
  onOpenDetail?: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const typeLabel = entity ? ENTITY_TYPE_LABELS[entity.type as OntologyEntityType] ?? entity.type : null
  const matchedByLabel = entity?.matched_by
    ? MATCHED_BY_LABELS[entity.matched_by] ?? entity.matched_by
    : null

  return (
    <SectionCard title="Recognized Entity">
      {entity ? (
        <div className="oqd-entity-context">
          <div className="oqd-entity-head">
            <span className="oqd-entity-icon" aria-hidden="true">
              <Brain size={18} />
            </span>
            <div className="oqd-entity-title">
              <span className="oqd-entity-name">{entity.name}</span>
              {entity.code && <span className="oqd-entity-code">{entity.code}</span>}
            </div>
          </div>
          <dl className="oqd-dl">
            {typeLabel && (
              <div className="oqd-dl-row">
                <dt>类型</dt>
                <dd>{typeLabel}</dd>
              </div>
            )}
            {matchedByLabel && (
              <div className="oqd-dl-row">
                <dt>匹配方式</dt>
                <dd>{matchedByLabel}</dd>
              </div>
            )}
            <div className="oqd-dl-row">
              <dt>语义置信度</dt>
              <dd>{Math.round(confidence * 100)}%</dd>
            </div>
            {granularity && (
              <div className="oqd-dl-row">
                <dt>粒度</dt>
                <dd>{GRANULARITY_LEVEL_NAMES[granularity] ?? granularity}</dd>
              </div>
            )}
            {status && (
              <div className="oqd-dl-row">
                <dt>状态</dt>
                <dd>{status}</dd>
              </div>
            )}
            {aliases && aliases.length > 0 && (
              <div className="oqd-dl-row">
                <dt>别名</dt>
                <dd className="oqd-dl-aliases">
                  {aliases.map(alias => (
                    <span key={alias} className="oqd-alias-chip">{alias}</span>
                  ))}
                </dd>
              </div>
            )}
          </dl>
          {onOpenDetail && (
            <button
              type="button"
              className="oqd-entity-open"
              onClick={() => onOpenDetail(entity.type as OntologyEntityType, entity.id)}
            >
              在本体浏览器中查看
            </button>
          )}
        </div>
      ) : (
        <p className="oqd-entity-empty">未识别实体 — 请尝试输入更明确的脑区名称</p>
      )}
    </SectionCard>
  )
}

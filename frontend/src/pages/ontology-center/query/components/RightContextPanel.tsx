import { Eye, GitBranch, Network } from 'lucide-react'
import type { OntologyQueryResponse } from '../../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../../browser/tree/OntologyTreeNode'
import { EntityContextCard } from './EntityContextCard'
import { SourceListCard } from './SourceListCard'

/**
 * 右侧 Evidence / Entity Context 栏。
 * Recognized Entity + supplemental（Evidence Source + Quick Actions）；
 * 1280–1600px 下 supplemental 由 CSS 隐藏。
 */
export function RightContextPanel({
  response,
  onOpenDetail,
  onOpenBrowser,
}: {
  response: OntologyQueryResponse
  onOpenDetail: (entityType: OntologyEntityType, entityId: string) => void
  onOpenBrowser: () => void
}) {
  const entity = response.entity

  /** 相关回路跳转：优先首个回路结果，否则回到实体详情（浏览器内含回路面板） */
  const handleOpenCircuit = () => {
    const circuit = response.results.find(item => item.category === 'circuit')
    if (circuit) {
      onOpenDetail('circuit', circuit.id)
      return
    }
    if (entity) onOpenDetail(entity.type as OntologyEntityType, entity.id)
  }

  const actions = [
    { key: 'ontology', label: '查看本体', icon: <Eye size={14} aria-hidden="true" />, onClick: entity ? () => onOpenDetail(entity.type as OntologyEntityType, entity.id) : undefined },
    { key: 'graph', label: '查看图谱', icon: <Network size={14} aria-hidden="true" />, onClick: onOpenBrowser },
    { key: 'circuit', label: '查看相关回路', icon: <GitBranch size={14} aria-hidden="true" />, onClick: entity || response.results.length > 0 ? handleOpenCircuit : undefined },
  ]

  return (
    <aside className="oqd-context" aria-label="Evidence and Entity Context">
      <EntityContextCard
        entity={entity}
        confidence={response.confidence}
        onOpenDetail={onOpenDetail}
      />
      <div className="oqd-context-supplemental">
        <SourceListCard items={response.results} />
        <section className="oqd-quick-actions" aria-label="Quick Actions">
          <div className="oqd-card-header">
            <h3>Quick Actions</h3>
          </div>
          {actions.map(action => (
            <button
              key={action.key}
              type="button"
              className="oqd-quick-action"
              disabled={!action.onClick}
              onClick={action.onClick}
            >
              {action.icon}
              <span>{action.label}</span>
            </button>
          ))}
        </section>
      </div>
    </aside>
  )
}

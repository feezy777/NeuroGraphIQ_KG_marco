import { Activity, Brain, ListTree, Search } from 'lucide-react'
import type { OntologyQueryResponse } from '../../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../../browser/tree/OntologyTreeNode'
import { MATCHED_BY_LABELS, QUERY_INTENT_LABELS } from '../queryTypes'
import { QueryMetricCard } from './QueryMetricCard'

/** Query Summary：问题 + 四个紧凑指标卡（Entity / Intent / Results / Confidence） */
export function QuerySummaryCard({
  response,
  question,
  onOpenDetail,
}: {
  response: OntologyQueryResponse
  question: string
  onOpenDetail: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const entity = response.entity
  const matchedBy = entity?.matched_by
    ? MATCHED_BY_LABELS[entity.matched_by] ?? entity.matched_by
    : null

  return (
    <section className="oqd-summary" aria-label="Query Summary">
      <div className="oqd-card-header">
        <h3>Query Summary</h3>
        <span className="oqd-card-question" title={question}>
          {question}
        </span>
      </div>
      <div className="oqd-summary-grid">
        <QueryMetricCard
          label="Entity"
          value={entity?.name ?? '—'}
          sub={entity?.code ?? undefined}
          icon={<Brain size={14} aria-hidden="true" />}
          mono={!matchedBy}
          onClick={
            entity ? () => onOpenDetail(entity.type as OntologyEntityType, entity.id) : undefined
          }
        />
        <QueryMetricCard
          label="Intent"
          value={QUERY_INTENT_LABELS[response.intent] ?? response.intent}
          sub={matchedBy ?? undefined}
          icon={<Search size={14} aria-hidden="true" />}
        />
        <QueryMetricCard
          label="Results"
          value={String(response.results.length)}
          sub="条结果"
          icon={<ListTree size={14} aria-hidden="true" />}
        />
        <QueryMetricCard
          label="Confidence"
          value={`${Math.round(response.confidence * 100)}%`}
          sub="语义置信度"
          icon={<Activity size={14} aria-hidden="true" />}
          tone="green"
        />
      </div>
    </section>
  )
}

/**
 * Phase P0-4C — Candidate Knowledge tab.
 *
 * The candidate POOL of one BrainRegion: every LLM candidate proposed around it,
 * across all its discovery runs, loaded from the region-scoped read API. It does
 * NOT walk the run history and merge client-side — the backend answers "what
 * belongs to this region" and that is the only answer used.
 *
 * READ-ONLY. There is no accept / reject / defer here, and no review request of
 * any kind: this phase navigates and inspects, it does not decide. Selecting a
 * CIRCUIT opens its own detail page; the other three kinds have no detail page
 * yet and say so instead of pretending otherwise.
 */
import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import { DataTable, type Column } from '../../components/DataTable'
import { fetchBrainRegionLlmCandidates } from './kpApi'
import {
  CANDIDATE_STATUS_LABEL_KEYS,
  CANDIDATE_STATUS_TONES,
  CANDIDATE_TYPE_LABEL_KEYS,
  CANDIDATE_TYPE_ORDER,
  CANDIDATE_TYPE_TONES,
  type DiscoveryCandidateType,
  type LlmDiscoveryCandidate,
} from './candidateTypes'
import { formatTimestamp, orDash } from './kpFormat'

type Filter = 'all' | DiscoveryCandidateType

type Props = {
  /** The Workspace's BrainRegion — the route is the selection authority. */
  entityId: string
  /** Open the circuit detail page. The caller owns navigation. */
  onOpenCircuit: (candidateId: string) => void
}

export function CandidateKnowledgeTab({ entityId, onOpenCircuit }: Props) {
  const { t } = useI18n()
  const [candidates, setCandidates] = useState<LlmDiscoveryCandidate[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  // A kind with no detail page yet: named, never silently inert.
  const [noDetailType, setNoDetailType] = useState<DiscoveryCandidateType | null>(null)

  useEffect(() => {
    let cancelled = false
    setCandidates(null)
    setError(null)
    setFilter('all')
    setNoDetailType(null)
    fetchBrainRegionLlmCandidates(entityId)
      .then(res => {
        if (!cancelled) setCandidates(res.items)
      })
      .catch((e: unknown) => {
        // An unreadable pool is UNKNOWN, never empty: "this region has no
        // candidates" would be a claim we cannot make.
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [entityId])

  if (error) {
    return (
      <div data-testid="kp-candidates-tab">
        <div className="state-box state-err" data-testid="kp-candidate-pool-error">
          <p>{error}</p>
        </div>
      </div>
    )
  }
  if (candidates === null) {
    return (
      <div data-testid="kp-candidates-tab">
        <p className="kp-muted" data-testid="kp-candidate-pool-loading">
          {t('knowledgeProduction.loading')}
        </p>
      </div>
    )
  }

  // Counts are over the WHOLE pool, not the filtered view: they are the pool's
  // composition, and re-counting what is filtered would make them a moving target.
  const countOf = (type: DiscoveryCandidateType) =>
    candidates.filter(c => c.candidate_type === type).length
  const shown = filter === 'all' ? candidates : candidates.filter(c => c.candidate_type === filter)

  const columns: Column<LlmDiscoveryCandidate>[] = [
    { key: 'candidate_id', header: t('knowledgeProduction.llmCandidates.col.candidateId') },
    {
      key: 'candidate_type',
      header: t('knowledgeProduction.llmCandidates.col.type'),
      render: c => (
        <span className={`badge ${CANDIDATE_TYPE_TONES[c.candidate_type]}`}>
          {t(CANDIDATE_TYPE_LABEL_KEYS[c.candidate_type])}
        </span>
      ),
    },
    { key: 'local_id', header: t('knowledgeProduction.llmCandidates.col.localId') },
    { key: 'name', header: t('knowledgeProduction.llmCandidates.col.name') },
    {
      key: 'confidence',
      header: t('knowledgeProduction.llmCandidates.col.confidence'),
      render: c => orDash(c.confidence),
    },
    {
      key: 'status',
      header: t('knowledgeProduction.llmCandidates.col.status'),
      render: c => (
        <span className={`badge ${CANDIDATE_STATUS_TONES[c.status]}`}>
          {t(CANDIDATE_STATUS_LABEL_KEYS[c.status])}
        </span>
      ),
    },
    {
      key: 'run_id',
      header: t('knowledgeProduction.candidateKnowledge.col.run'),
      render: c => <span className="kp-mono-sm">{c.run_id}</span>,
    },
    {
      key: 'created_at',
      header: t('knowledgeProduction.candidateKnowledge.col.created'),
      render: c => formatTimestamp(c.created_at),
    },
  ]

  const filterDefs: { id: Filter; label: string }[] = [
    { id: 'all', label: t('knowledgeProduction.candidateKnowledge.filter.all') },
    ...CANDIDATE_TYPE_ORDER.map(type => ({
      id: type as Filter,
      label: t(CANDIDATE_TYPE_LABEL_KEYS[type]),
    })),
  ]

  return (
    <div data-testid="kp-candidates-tab">
      <div className="kp-stat-row" data-testid="kp-candidate-pool-stats">
        <span className="kp-stat" data-testid="kp-candidate-count-total">
          <span className="kp-stat-label">
            {t('knowledgeProduction.candidateKnowledge.stat.total')}
          </span>
          <span className="kp-stat-value">{candidates.length}</span>
        </span>
        {CANDIDATE_TYPE_ORDER.map(type => (
          <span className="kp-stat" key={type} data-testid={`kp-candidate-count-${type}`}>
            <span className="kp-stat-label">{t(CANDIDATE_TYPE_LABEL_KEYS[type])}</span>
            <span className="kp-stat-value">{countOf(type)}</span>
          </span>
        ))}
      </div>

      <div className="kp-filter-row" data-testid="kp-candidate-filters">
        {filterDefs.map(f => (
          <button
            key={f.id}
            type="button"
            className={`tab-btn${filter === f.id ? ' active' : ''}`}
            data-testid={`kp-candidate-filter-${f.id}`}
            aria-pressed={filter === f.id}
            onClick={() => setFilter(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {noDetailType && (
        <p className="kp-muted" data-testid="kp-candidate-no-detail">
          {t('knowledgeProduction.candidateKnowledge.noDetailYet', {
            type: t(CANDIDATE_TYPE_LABEL_KEYS[noDetailType]),
          })}
        </p>
      )}

      {shown.length === 0 ? (
        <p className="kp-muted" data-testid="kp-candidate-pool-empty">
          {candidates.length === 0
            ? t('knowledgeProduction.candidateKnowledge.emptyPool')
            : t('knowledgeProduction.candidateKnowledge.emptyFilter')}
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={shown}
          getKey={c => c.candidate_id}
          onRowClick={c =>
            c.candidate_type === 'circuit'
              ? onOpenCircuit(c.candidate_id)
              : setNoDetailType(c.candidate_type)
          }
          getRowClassName={c => (c.candidate_type === 'circuit' ? 'kp-row-openable' : undefined)}
        />
      )}
    </div>
  )
}

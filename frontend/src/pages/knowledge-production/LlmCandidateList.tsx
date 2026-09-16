/**
 * Phase P0-4A — LLM Discovery candidate list (read-only).
 *
 *     selected LLM_DISCOVERY run
 *       -> the candidates that run proposed
 *          -> one candidate's persisted fields, verbatim
 *
 * Architecture: mirrors LiteratureInspector. It does NOT list runs — the
 * Discovery tab's RunHistory is the run authority on screen, and this component
 * is handed the run the user selected there. It reaches exactly ONE Knowledge
 * Production read endpoint and knows nothing about how a discovery is executed.
 *
 * READ-ONLY, and this phase's hard boundary: there is no ACCEPT / REJECT / DEFER
 * control, no review request of any kind, and no review history here. A candidate
 * row shows what was persisted and nothing more. Review is a separate phase with
 * its own contract.
 *
 * Scientific boundary: a candidate is a PROPOSAL. Nothing here canonicalizes it,
 * resolves its local references, or claims it is validated or evidence-backed.
 * `status` is displayed as the API reports it; no label implies more than the
 * stored value says.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n-context'
import { DataTable, type Column } from '../../components/DataTable'
import { fetchRunLlmCandidates } from './kpApi'
import {
  CANDIDATE_STATUS_LABEL_KEYS,
  CANDIDATE_STATUS_TONES,
  CANDIDATE_TYPE_LABEL_KEYS,
  CANDIDATE_TYPE_TONES,
  type DiscoveryCandidateStatus,
  type DiscoveryCandidateType,
  type LlmCandidateListResponse,
  type LlmDiscoveryCandidate,
} from './candidateTypes'
import type { DiscoveryRun } from './types'

type Props = {
  /**
   * This seed's LLM-route runs. `null` means NOT YET KNOWN — in flight, or
   * unreadable. That is a third state, distinct from `[]`: an unreadable list
   * must never be rendered as "there are none", which would state as fact
   * something we do not know.
   */
  llmRuns: DiscoveryRun[] | null
  /** Which run the user selected in the Discovery tab's history. */
  selectedRunId: string | null
}

/** `—` for a value the API legitimately reports as absent. */
function orDash(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

/** One labelled read-only value. `testId` is only for values a test asserts. */
function Field({
  label,
  value,
  testId,
}: {
  label: string
  value: string | number | null | undefined
  testId?: string
}) {
  return (
    <div className="kp-field">
      <span className="kp-field-label">{label}</span>
      <span className="kp-field-value" data-testid={testId}>
        {orDash(value)}
      </span>
    </div>
  )
}

function TypeBadge({ type }: { type: DiscoveryCandidateType }) {
  const { t } = useI18n()
  // The tone keys off the RAW enum; only the caption is localized.
  return (
    <span className={`badge ${CANDIDATE_TYPE_TONES[type]}`} data-testid="kp-candidate-type-badge">
      {t(CANDIDATE_TYPE_LABEL_KEYS[type])}
    </span>
  )
}

function CandidateStatusBadge({ status }: { status: DiscoveryCandidateStatus }) {
  const { t } = useI18n()
  return (
    <span
      className={`badge ${CANDIDATE_STATUS_TONES[status]}`}
      data-testid="kp-candidate-status-badge"
    >
      {t(CANDIDATE_STATUS_LABEL_KEYS[status])}
    </span>
  )
}

function columns(t: (key: string) => string): Column<LlmDiscoveryCandidate>[] {
  return [
    // Identifiers and enums are shown VERBATIM and never translated: a reader
    // matches them against the database, and logic compares them.
    { key: 'candidate_id', header: t('knowledgeProduction.llmCandidates.col.candidateId') },
    { key: 'candidate_type', header: t('knowledgeProduction.llmCandidates.col.type'),
      render: c => <TypeBadge type={c.candidate_type} /> },
    { key: 'local_id', header: t('knowledgeProduction.llmCandidates.col.localId') },
    // `name` is the backend's own projection of the typed candidate — for a
    // connection, "source -> target [type]". It is shown as stored, never
    // rebuilt here from the payload.
    { key: 'name', header: t('knowledgeProduction.llmCandidates.col.name') },
    { key: 'confidence', header: t('knowledgeProduction.llmCandidates.col.confidence'),
      // The raw 0..1 value as persisted, not a percentage: rescaling it would be
      // a second representation the backend never produced.
      render: c => orDash(c.confidence) },
    { key: 'status', header: t('knowledgeProduction.llmCandidates.col.status'),
      render: c => <CandidateStatusBadge status={c.status} /> },
  ]
}

/**
 * One candidate's persisted fields, verbatim. No review control of any kind.
 *
 * The payload is the candidate's actual content — `name` is only a projection of
 * it — so it is shown as stored rather than summarized away.
 */
function CandidateDetail({ candidate }: { candidate: LlmDiscoveryCandidate }) {
  const { t } = useI18n()
  const f = (name: string) => t(`knowledgeProduction.llmCandidates.field.${name}`)
  // Label key suffix paired with the RAW API value. Listed rather than spelled
  // out as nine near-identical elements: the point of the grid is that every
  // contract field is present, and a list makes a missing one obvious.
  const rows: [string, string | number | null][] = [
    ['candidateId', candidate.candidate_id],
    ['runId', candidate.run_id],
    ['seedEntityId', candidate.seed_entity_id],
    ['localId', candidate.local_id],
    ['type', candidate.candidate_type],
    ['status', candidate.status],
    ['confidence', candidate.confidence],
    ['createdAt', candidate.created_at],
    ['updatedAt', candidate.updated_at],
  ]
  return (
    <div className="kp-field-grid" data-testid="kp-candidate-detail">
      {rows.map(([key, value]) => (
        <Field key={key} label={f(key)} value={value} />
      ))}
      <div className="kp-field kp-field-wide">
        <span className="kp-field-label">{f('payload')}</span>
        <pre className="kp-json" data-testid="kp-candidate-payload">
          {JSON.stringify(candidate.payload, null, 2)}
        </pre>
      </div>
    </div>
  )
}

export function LlmCandidateList({ llmRuns, selectedRunId }: Props) {
  const { t } = useI18n()
  const [candidates, setCandidates] = useState<LlmCandidateListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null)

  const selectedRun = llmRuns?.find(r => r.run_id === selectedRunId) ?? null
  const runId = selectedRun?.run_id ?? null

  // Reload whenever the selection changes. `cancelled` guards against a slower
  // response for the PREVIOUS run overwriting the current one — the same
  // convention the workspace page and the literature inspector use. Resetting
  // both states up front also means the previous run's candidates can never be
  // shown even for one frame under the new run's heading, and the row selection
  // is cleared so it cannot survive into a run that never contained it.
  useEffect(() => {
    setSelectedCandidateId(null)
    if (!runId) {
      setCandidates(null)
      setError(null)
      return
    }
    let cancelled = false
    setCandidates(null)
    setError(null)
    fetchRunLlmCandidates(runId)
      .then(res => {
        if (!cancelled) setCandidates(res)
      })
      .catch((e: unknown) => {
        // An unreadable result set is UNKNOWN, not empty — same rule the run
        // history and the literature inspector follow. Never rendered as "no
        // candidates were proposed".
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  // The heading is the same whichever answer the data gives, so the four states
  // differ only in this body.
  let body: ReactNode

  if (llmRuns === null) {
    // Unknown: the run list is in flight or unreadable. We do NOT know whether
    // this seed has LLM runs, so we must not claim it has none.
    body = (
      <p className="kp-muted" data-testid="kp-llm-candidates-runs-loading">
        {t('knowledgeProduction.loading')}
      </p>
    )
  } else if (llmRuns.length === 0) {
    // A: this seed has never run an LLM discovery. A clean empty state, never an
    // error — and never a claim that some run produced nothing.
    body = (
      <div className="kp-empty" data-testid="kp-llm-candidates-noruns">
        <h3 className="kp-empty-title">{t('knowledgeProduction.llmCandidates.noRunsTitle')}</h3>
        <p className="kp-empty-text">{t('knowledgeProduction.llmCandidates.noRunsText')}</p>
      </div>
    )
  } else if (!selectedRun) {
    // B: LLM runs exist, none selected yet.
    body = (
      <p className="kp-muted" data-testid="kp-llm-candidates-select-prompt">
        {t('knowledgeProduction.llmCandidates.selectPrompt')}
      </p>
    )
  } else {
    const rows = candidates?.items ?? []
    const selectedCandidate = rows.find(c => c.candidate_id === selectedCandidateId) ?? null
    body = (
      <>
        {/* Which run these candidates belong to. Stated explicitly so a reader
            can never mistake one run's results for another's. */}
        <div className="kp-field-grid" data-testid="kp-llm-candidates-run">
          <Field
            label={t('knowledgeProduction.llmCandidates.field.runId')}
            value={selectedRun.run_id}
          />
          <Field
            label={t('knowledgeProduction.llmCandidates.field.runStatus')}
            value={selectedRun.status}
          />
          <Field
            label={t('knowledgeProduction.llmCandidates.field.total')}
            value={candidates?.total}
            testId="kp-llm-candidates-total"
          />
        </div>

        {error && (
          <div className="state-box state-err" data-testid="kp-llm-candidates-error">
            <p>{error}</p>
          </div>
        )}

        {!error && candidates === null && (
          <p className="kp-muted" data-testid="kp-llm-candidates-loading">
            {t('knowledgeProduction.loading')}
          </p>
        )}

        {/* A genuine zero-candidate run. Only reachable once an answer arrived,
            so an outage or an unreadable list can never say this. */}
        {!error && candidates !== null && rows.length === 0 && (
          <p className="kp-muted" data-testid="kp-llm-candidates-empty">
            {t('knowledgeProduction.llmCandidates.emptyText')}
          </p>
        )}

        {!error && rows.length > 0 && (
          <>
            <div className="kp-candidate-table">
              <DataTable
                columns={columns(t)}
                rows={rows}
                getKey={c => c.candidate_id}
                onRowClick={c =>
                  setSelectedCandidateId(prev => (prev === c.candidate_id ? null : c.candidate_id))
                }
                getRowClassName={c =>
                  c.candidate_id === selectedCandidateId ? 'kp-candidate-selected' : undefined
                }
              />
            </div>
            {selectedCandidate && <CandidateDetail candidate={selectedCandidate} />}
          </>
        )}
      </>
    )
  }

  return (
    <section className="kp-section" data-testid="kp-llm-candidates">
      <h3 className="kp-section-title">{t('knowledgeProduction.llmCandidates.title')}</h3>
      {body}
    </section>
  )
}

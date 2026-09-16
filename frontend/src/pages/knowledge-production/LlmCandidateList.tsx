/**
 * Phase P0-4C — LLM Discovery run RESULT SUMMARY (read-only).
 *
 * Phase P0-4A rendered the run's candidates as a table here. That table now lives
 * on the Candidate Knowledge tab, where the whole POOL of a BrainRegion belongs;
 * what remains on the Discovery tab is what §3 of this phase assigns to it — the
 * execution outcome: how many candidates the run proposed, by kind, and the way
 * through to the pool.
 *
 * Keeping the file (rather than a rename) is deliberate: its fetching, its four
 * render states and its stale-run protection are unchanged and still tested, and
 * a rename would have churned a committed module for no behavioural gain.
 *
 * READ-ONLY: no review action of any kind, and no candidate is written here.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n-context'
import { fetchRunLlmCandidates } from './kpApi'
import {
  CANDIDATE_TYPE_LABEL_KEYS,
  CANDIDATE_TYPE_ORDER,
  type LlmCandidateListResponse,
} from './candidateTypes'
import { orDash } from './kpFormat'
import type { DiscoveryRun } from './types'

/** One labelled read-only value. */
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

type Props = {
  /**
   * This seed's LLM-route runs. `null` means NOT YET KNOWN — in flight, or
   * unreadable. Distinct from `[]`: an unreadable list must never be rendered as
   * "there are none", which would state as fact something we do not know.
   */
  llmRuns: DiscoveryRun[] | null
  /** Which run the user selected in the Discovery tab's history. */
  selectedRunId: string | null
  /** Open the Candidate Knowledge tab. The page owns the tab state. */
  onOpenCandidates: () => void
}

export function LlmCandidateList({ llmRuns, selectedRunId, onOpenCandidates }: Props) {
  const { t } = useI18n()
  const [candidates, setCandidates] = useState<LlmCandidateListResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  const selectedRun = llmRuns?.find(r => r.run_id === selectedRunId) ?? null
  const runId = selectedRun?.run_id ?? null

  // Reload whenever the selection changes. `cancelled` guards against a slower
  // response for the PREVIOUS run overwriting the current one — the same
  // convention the workspace page and the literature inspector use. Resetting
  // both states up front also means the previous run's counts can never be shown
  // even for one frame under the new run's heading.
  useEffect(() => {
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
        // history and the literature inspector follow. It is never rendered as
        // "no candidates were proposed".
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  // The heading is the same whichever answer the data gives, so the states differ
  // only in this body.
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
    // This seed has never run an LLM discovery. A clean empty state, never an
    // error — and never a claim that some run produced nothing.
    body = (
      <div className="kp-empty" data-testid="kp-llm-candidates-noruns">
        <h3 className="kp-empty-title">{t('knowledgeProduction.llmCandidates.noRunsTitle')}</h3>
        <p className="kp-empty-text">{t('knowledgeProduction.llmCandidates.noRunsText')}</p>
      </div>
    )
  } else if (!selectedRun) {
    body = (
      <p className="kp-muted" data-testid="kp-llm-candidates-select-prompt">
        {t('knowledgeProduction.llmCandidates.selectPrompt')}
      </p>
    )
  } else {
    const rows = candidates?.items ?? []
    const countOf = (type: string) => rows.filter(c => c.candidate_type === type).length
    body = (
      <>
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
            label={t('knowledgeProduction.execution.outcome')}
            value={selectedRun.outcome}
            testId="kp-llm-run-outcome"
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
            <p className="kp-muted" data-testid="kp-llm-run-found">
              {t('knowledgeProduction.execution.found')}
            </p>
            <div className="kp-stat-row" data-testid="kp-llm-run-summary">
              <span className="kp-stat" data-testid="kp-llm-run-total">
                <span className="kp-stat-label">
                  {t('knowledgeProduction.candidateKnowledge.stat.total')}
                </span>
                <span className="kp-stat-value">{rows.length}</span>
              </span>
              {CANDIDATE_TYPE_ORDER.map(type => (
                <span className="kp-stat" key={type} data-testid={`kp-llm-run-count-${type}`}>
                  <span className="kp-stat-label">{t(CANDIDATE_TYPE_LABEL_KEYS[type])}</span>
                  <span className="kp-stat-value">{countOf(type)}</span>
                </span>
              ))}
            </div>
            {/* The rows themselves live on the Candidate Knowledge tab: this tab
                reports the run, that tab owns the pool. */}
            <button
              type="button"
              className="btn btn-sm"
              data-testid="kp-open-candidates"
              onClick={onOpenCandidates}
            >
              {t('knowledgeProduction.candidateKnowledge.openTab')}
            </button>
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

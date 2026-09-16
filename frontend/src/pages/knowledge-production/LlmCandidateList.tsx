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
  isCandidateStorageUnavailable,
  type LlmCandidateListResponse,
} from './candidateTypes'
import { formatTimestamp, orDash } from './kpFormat'
import type { DiscoveryRun } from './types'

/**
 * How long a run took, from the two stamps the API reports — or `null`.
 *
 * `null` unless BOTH stamps parse: a duration computed from one stamp and a
 * guess would be a fabricated measurement. Negative or absurd values are also
 * refused rather than displayed.
 */
function runDuration(startedAt: string | null, finishedAt: string | null): string | null {
  if (!startedAt || !finishedAt) return null
  const start = new Date(startedAt).getTime()
  const end = new Date(finishedAt).getTime()
  if (Number.isNaN(start) || Number.isNaN(end) || end < start) return null
  const totalSeconds = Math.round((end - start) / 1000)
  if (totalSeconds < 60) return `${totalSeconds}s`
  const minutes = Math.floor(totalSeconds / 60)
  return `${minutes}m ${totalSeconds % 60}s`
}

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
  // This database has no candidate storage at all. A DEPLOYMENT state, not a
  // failed read: the run's result is not unavailable BY ERROR, it does not
  // exist to be read. Kept apart from `error` so it is answered quietly, and
  // apart from an empty list so it never reports "the run proposed nothing".
  const [storageNotEnabled, setStorageNotEnabled] = useState(false)

  const selectedRun = llmRuns?.find(r => r.run_id === selectedRunId) ?? null
  const runId = selectedRun?.run_id ?? null

  // Reload whenever the selection changes. `cancelled` guards against a slower
  // response for the PREVIOUS run overwriting the current one — the same
  // convention the workspace page and the literature inspector use. Resetting
  // all three states up front also means the previous run's counts can never be
  // shown even for one frame under the new run's heading.
  useEffect(() => {
    if (!runId) {
      setCandidates(null)
      setError(null)
      setStorageNotEnabled(false)
      return
    }
    let cancelled = false
    setCandidates(null)
    setError(null)
    setStorageNotEnabled(false)
    fetchRunLlmCandidates(runId)
      .then(res => {
        if (!cancelled) setCandidates(res)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        // Only this ONE condition is a state. A 500, a 502, a 503, a network
        // error or an unknown code stays an ERROR below.
        if (isCandidateStorageUnavailable(e)) {
          setStorageNotEnabled(true)
          return
        }
        // An unreadable result set is UNKNOWN, not empty — same rule the run
        // history and the literature inspector follow. It is never rendered as
        // "no candidates were proposed".
        setError(e instanceof Error ? e.message : String(e))
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
          {/* The rest of the run's provenance. All of it is real API data, and
              all of it is needed to audit a candidate: which model, which prompt,
              how long it ran. */}
          <Field
            label={t('knowledgeProduction.circuitDetail.field.provider')}
            value={selectedRun.provider ?? null}
            testId="kp-llm-run-provider"
          />
          <Field
            label={t('knowledgeProduction.circuitDetail.field.model')}
            value={selectedRun.model_name ?? null}
            testId="kp-llm-run-model"
          />
          <Field
            label={t('knowledgeProduction.circuitDetail.field.promptKey')}
            value={selectedRun.prompt_key ?? null}
            testId="kp-llm-run-prompt-key"
          />
          <Field
            label={t('knowledgeProduction.circuitDetail.field.promptVersion')}
            value={selectedRun.prompt_version ?? null}
            testId="kp-llm-run-prompt-version"
          />
          <Field
            label={t('knowledgeProduction.discovery.field.started')}
            value={formatTimestamp(selectedRun.started_at)}
            testId="kp-llm-run-started"
          />
          <Field
            label={t('knowledgeProduction.discovery.field.finished')}
            value={formatTimestamp(selectedRun.finished_at)}
            testId="kp-llm-run-finished"
          />
          {/* Derived from the two stamps above — arithmetic on reported times,
              not a new fact: a run with no finish stamp shows —. */}
          <Field
            label={t('knowledgeProduction.discovery.field.duration')}
            value={runDuration(selectedRun.started_at, selectedRun.finished_at)}
            testId="kp-llm-run-duration"
          />
        </div>

        {/* ONE gate for the whole result area. When the database has no
            candidate storage there is no result to report: not an errored one,
            not an empty one, and no counts — a count would be a number nobody
            measured. The run's provenance above stays, because that record IS
            readable and is what tells the reader the run happened. */}
        {storageNotEnabled ? (
          <p className="kp-muted" data-testid="kp-llm-candidates-storage-not-enabled">
            {t('knowledgeProduction.candidateStorage.notEnabled')}
          </p>
        ) : (
          <>
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

            {/* A genuine zero-candidate run. Only reachable once an answer
                arrived, so an outage or an unreadable list can never say this. */}
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
                {/* The rows themselves live on the Candidate Knowledge tab: this
                    tab reports the run, that tab owns the pool. */}
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

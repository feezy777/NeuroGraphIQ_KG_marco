/**
 * Phase 3E.2C — Literature Inspector (read-only).
 *
 * Shows what one literature run actually RETRIEVED:
 *
 *     selected literature run
 *       -> run fields + bounded diagnostics
 *       -> publications reached by that run
 *          -> the retrieval hits that reached each publication
 *
 * Scientific boundary, frozen: a hit means "this query found this publication".
 * It is retrieval provenance. It is NOT evidence, and nothing here renders or
 * implies supports / contradicts / evidence_strength.
 *
 * Architecture: this is a self-contained view. It does NOT list runs — the
 * Discovery tab's RunHistory is the run authority on screen, and this component
 * is handed the run the user selected there. It reaches only the Knowledge
 * Production read APIs and knows nothing about how a search is performed.
 *
 * UI placement is intentionally NOT a permanent freeze: the layout is expected
 * to be redesigned once real pilot data exists. Keeping this component free of
 * page-level routing and run-list ownership is what makes that cheap.
 */
import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import { DataTable, type Column } from '../../components/DataTable'
import { fetchRunPublications } from './kpApi'
import type { LiteratureRun, Publication, PublicationHit, PublicationListResponse } from './types'

type Props = {
  /**
   * The seed's literature runs. `null` means NOT YET KNOWN — either still in
   * flight or unreadable. That is a third state, distinct from `[]`: an
   * unreadable list must never be rendered as "there are none", which would
   * state as fact something we do not know.
   */
  literatureRuns: LiteratureRun[] | null
  /** Why the literature-run list could not be read, if it could not. */
  error: string | null
  /** Which run the user selected in the Discovery tab's history. */
  selectedRunId: string | null
}

/** `YYYY-MM-DD HH:mm` in local time, or `—`. Mirrors the workspace convention. */
function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
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

const HIT_COLUMNS = (
  t: (key: string) => string,
): Column<PublicationHit>[] => [
  // Provenance values are shown verbatim and are never translated: a query
  // string and a provider's name are data, not UI copy.
  { key: 'query_text', header: t('knowledgeProduction.literature.hit.queryText') },
  { key: 'query_family', header: t('knowledgeProduction.literature.hit.queryFamily'),
    render: h => orDash(h.query_family) },
  { key: 'query_level', header: t('knowledgeProduction.literature.hit.queryLevel'),
    render: h => orDash(h.query_level) },
  { key: 'source', header: t('knowledgeProduction.literature.hit.source'),
    render: h => orDash(h.source) },
  { key: 'result_rank', header: t('knowledgeProduction.literature.hit.rank'),
    render: h => orDash(h.result_rank) },
  { key: 'retrieved_at', header: t('knowledgeProduction.literature.hit.retrievedAt'),
    render: h => formatTimestamp(h.retrieved_at) },
  { key: 'run_id', header: t('knowledgeProduction.literature.hit.runId'),
    render: h => orDash(h.run_id) },
]

function PublicationCard({
  publication,
  defaultOpen,
}: {
  publication: Publication
  defaultOpen: boolean
}) {
  const { t } = useI18n()
  const [open, setOpen] = useState(defaultOpen)
  const hits = publication.hits

  return (
    <div className="kp-card kp-literature-publication" data-testid="kp-literature-publication">
      <div className="kp-literature-publication-head">
        <h4 className="kp-card-title">
          {publication.original_title || publication.entity_id}
        </h4>
        <span className="kp-chip">{orDash(publication.publication_year)}</span>
      </div>

      <div className="kp-field-grid">
        {/* Bibliographic identifiers keep their literal names in both languages:
            they are field names a reader matches against a paper, not UI copy. */}
        <Field label="PMID" value={publication.pmid} />
        <Field label="PMCID" value={publication.pmcid} />
        <Field label="DOI" value={publication.doi} />
        <Field
          label={t('knowledgeProduction.literature.field.sourceDatabase')}
          value={publication.source_database}
        />
      </div>

      <button
        type="button"
        className="btn btn-sm"
        onClick={() => setOpen(o => !o)}
        data-testid="kp-literature-hits-toggle"
      >
        {open
          ? t('knowledgeProduction.literature.hideHits')
          : t('knowledgeProduction.literature.showHits')}
        {' '}
        ({hits.length})
      </button>

      {open && (
        <div data-testid="kp-literature-hits">
          <DataTable
            columns={HIT_COLUMNS(t)}
            rows={hits}
            getKey={h => `${h.run_id ?? 'no-run'}-${h.query_text}-${h.result_rank ?? 'x'}-${h.retrieved_at}`}
            emptyText={t('knowledgeProduction.literature.noHits')}
          />
        </div>
      )}
    </div>
  )
}

export function LiteratureInspector({ literatureRuns, error, selectedRunId }: Props) {
  const { t } = useI18n()
  const [publications, setPublications] = useState<PublicationListResponse | null>(null)
  const [publicationsError, setPublicationsError] = useState<string | null>(null)

  const selectedRun = literatureRuns?.find(r => r.run_id === selectedRunId) ?? null
  const runId = selectedRun?.run_id ?? null

  // Reload whenever the selection changes. `cancelled` guards against a slower
  // response for the PREVIOUS run overwriting the current one's data — the same
  // convention the workspace page uses. Resetting both states up front also
  // means a stale result can never be shown even for one frame.
  useEffect(() => {
    if (!runId) {
      setPublications(null)
      setPublicationsError(null)
      return
    }
    let cancelled = false
    setPublications(null)
    setPublicationsError(null)
    fetchRunPublications(runId)
      .then(res => {
        if (!cancelled) setPublications(res)
      })
      .catch((e: unknown) => {
        // An unreadable result set is UNKNOWN, not empty — same rule the
        // Discovery run history follows.
        if (!cancelled) setPublicationsError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [runId])

  // Unknown: the literature-run list is unreadable. We do NOT know whether this
  // seed has literature runs, so we must not claim it has none.
  if (error) {
    return (
      <section className="kp-section" data-testid="kp-literature-inspector">
        <h3 className="kp-section-title">{t('knowledgeProduction.literature.title')}</h3>
        <div className="state-box state-err" data-testid="kp-literature-runs-error">
          <p>{error}</p>
        </div>
      </section>
    )
  }

  // Still loading, or not yet told.
  if (literatureRuns === null) {
    return (
      <section className="kp-section" data-testid="kp-literature-inspector">
        <h3 className="kp-section-title">{t('knowledgeProduction.literature.title')}</h3>
        <p className="kp-muted" data-testid="kp-literature-runs-loading">
          {t('knowledgeProduction.loading')}
        </p>
      </section>
    )
  }

  // A: no literature run for this seed. A clean empty state, never an error.
  if (literatureRuns.length === 0) {
    return (
      <section className="kp-section" data-testid="kp-literature-inspector">
        <h3 className="kp-section-title">{t('knowledgeProduction.literature.title')}</h3>
        <div className="kp-empty" data-testid="kp-literature-noruns">
          <h3 className="kp-empty-title">{t('knowledgeProduction.literature.emptyTitle')}</h3>
          <p className="kp-empty-text">{t('knowledgeProduction.literature.emptyText')}</p>
        </div>
      </section>
    )
  }

  // B: literature runs exist, none selected yet.
  if (!selectedRun) {
    return (
      <section className="kp-section" data-testid="kp-literature-inspector">
        <h3 className="kp-section-title">{t('knowledgeProduction.literature.title')}</h3>
        <p className="kp-muted" data-testid="kp-literature-select-prompt">
          {t('knowledgeProduction.literature.selectPrompt')}
        </p>
      </section>
    )
  }

  const d = selectedRun.diagnostics
  const failed = selectedRun.status === 'FAILED'

  return (
    <section className="kp-section kp-literature" data-testid="kp-literature-inspector">
      <h3 className="kp-section-title">{t('knowledgeProduction.literature.title')}</h3>

      {/* ---- RUN ---- */}
      <div className="kp-field-grid" data-testid="kp-literature-run">
        {/* Raw enums stay untranslated: logic compares them, readers quote them. */}
        <Field label={t('knowledgeProduction.literature.field.type')} value={selectedRun.discovery_type} />
        <Field label={t('knowledgeProduction.literature.field.status')} value={selectedRun.status} />
        <Field label={t('knowledgeProduction.literature.field.outcome')} value={selectedRun.outcome} />
        <Field label={t('knowledgeProduction.literature.field.provider')} value={selectedRun.provider} />
        <Field
          label={t('knowledgeProduction.literature.field.startedAt')}
          value={formatTimestamp(selectedRun.started_at)}
        />
        <Field
          label={t('knowledgeProduction.literature.field.finishedAt')}
          value={formatTimestamp(selectedRun.finished_at)}
        />
      </div>

      {/* Failure is NEVER rendered as an empty result. */}
      {failed && (
        <div className="state-box state-err" data-testid="kp-literature-run-failed">
          <p>{selectedRun.error_code ? `${selectedRun.error_code}: ` : ''}{orDash(selectedRun.error_message)}</p>
        </div>
      )}

      {/* ---- DIAGNOSTICS ---- */}
      <div data-testid="kp-literature-diagnostics">
        <div className="kp-field-grid">
          <Field
            label={t('knowledgeProduction.literature.field.papersFound')}
            value={d.papers_found}
            testId="kp-literature-papers-found"
          />
          <Field
            label={t('knowledgeProduction.literature.field.partial')}
            value={d.partial ? t('knowledgeProduction.literature.yes') : t('knowledgeProduction.literature.no')}
          />
          {/* The VALUE of the diagnostic, stated as a field. The failure box
              below explains what the value MEANS — the two are not duplicates:
              one is the reading, the other is its consequence. */}
          <Field
            label={t('knowledgeProduction.literature.field.allProvidersFailed')}
            value={
              d.all_providers_failed
                ? t('knowledgeProduction.literature.yes')
                : t('knowledgeProduction.literature.no')
            }
            testId="kp-literature-all-providers-failed-value"
          />
        </div>

        {/* A provider outage is a DIFFERENT fact from a zero-result search. */}
        {d.all_providers_failed && (
          <div className="state-box state-err" data-testid="kp-literature-all-providers-failed">
            <p>{t('knowledgeProduction.literature.allProvidersFailedText')}</p>
          </div>
        )}

        {/* Results are real but incomplete — say so without hiding them. */}
        {d.partial && !d.all_providers_failed && (
          <div className="state-box" data-testid="kp-literature-partial">
            <p>{t('knowledgeProduction.literature.partialText')}</p>
          </div>
        )}

        {d.provider_failures.length > 0 && (
          <div data-testid="kp-literature-provider-failures">
            <h4 className="kp-section-title">
              {t('knowledgeProduction.literature.providerFailures')}
            </h4>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>{t('knowledgeProduction.literature.failure.provider')}</th>
                    <th>{t('knowledgeProduction.literature.failure.statusCode')}</th>
                    <th>{t('knowledgeProduction.literature.failure.retryable')}</th>
                    <th>{t('knowledgeProduction.literature.failure.message')}</th>
                    <th>{t('knowledgeProduction.literature.failure.queryStrategy')}</th>
                  </tr>
                </thead>
                <tbody>
                  {d.provider_failures.map((f, i) => (
                    <tr key={`${f.provider}-${i}`}>
                      <td>{orDash(f.provider)}</td>
                      <td>{orDash(f.status_code)}</td>
                      <td>
                        {f.retryable === null
                          ? '—'
                          : f.retryable
                            ? t('knowledgeProduction.literature.yes')
                            : t('knowledgeProduction.literature.no')}
                      </td>
                      <td>{orDash(f.message)}</td>
                      <td>{orDash(f.query_strategy)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      {/* ---- PUBLICATIONS ---- */}
      <div data-testid="kp-literature-publications">
        {publicationsError && (
          <div className="state-box state-err" data-testid="kp-literature-publications-error">
            <p>{publicationsError}</p>
          </div>
        )}
        {!publicationsError && publications === null && (
          <p className="kp-muted" data-testid="kp-literature-publications-loading">
            {t('knowledgeProduction.loading')}
          </p>
        )}

        {!publicationsError && publications !== null && (
          <>
            {/* Both counts stay visible and visibly distinct: one publication
                reached by three queries is 1 publication and 3 retrieval facts. */}
            <div className="kp-field-grid" data-testid="kp-literature-summary">
              <Field
                label={t('knowledgeProduction.literature.field.distinctPublications')}
                value={publications.distinct_publications}
                testId="kp-literature-distinct"
              />
              <Field
                label={t('knowledgeProduction.literature.field.hitsTotal')}
                value={publications.hits_total}
                testId="kp-literature-hits-total"
              />
            </div>

            {/* Order matters: an outage is reported as an outage, and a genuine
                zero-result run is the ONLY case that says "found nothing". */}
            {publications.distinct_publications === 0 && !d.all_providers_failed && !failed && (
              <p className="kp-muted" data-testid="kp-literature-no-publications">
                {t('knowledgeProduction.literature.noPublications')}
              </p>
            )}

            {publications.items.map(p => (
              <PublicationCard
                key={p.entity_id}
                publication={p}
                // A single publication opens its hits by default; with several,
                // the reader chooses. Information density is unknown until real
                // pilot data exists.
                defaultOpen={publications.items.length === 1}
              />
            ))}
          </>
        )}
      </div>
    </section>
  )
}

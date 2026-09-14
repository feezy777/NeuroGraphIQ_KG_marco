/**
 * Knowledge Production — Production Index (Phase 1B).
 *
 * The index is for BROWSING and ENTERING a BrainRegion. It deliberately does
 * NOT host the production workflow: clicking a row navigates to that region's
 * workspace, where Discovery / Candidates / Evidence / Validation live.
 *
 * (See docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8.1.)
 */
import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import { BrainRegionSeedList } from './BrainRegionSeedList'
import { fetchBrainRegionSummary } from './kpApi'
import { KP_GRANULARITY_OPTIONS, type BrainRegionSeed, type BrainRegionSummary } from './types'
import { kpWorkspacePath, navigate } from './routes'

/** The authority database the counts come from — technical, never translated. */
const AUTHORITY_DATABASE = 'neurographiq_human_brain_v1'

function SummaryCards({ summary }: { summary: BrainRegionSummary | null }) {
  const { t } = useI18n()
  const cells: { key: string; labelKey: string; value: string; hint: string }[] = [
    {
      key: 'total',
      labelKey: 'knowledgeProduction.summary.total',
      value: summary ? String(summary.total) : '—',
      hint: AUTHORITY_DATABASE,
    },
    ...KP_GRANULARITY_OPTIONS.map(opt => ({
      key: opt.value,
      labelKey: opt.labelKey,
      value: summary ? String(summary.by_granularity[opt.value] ?? 0) : '—',
      // The raw Gate7B enum stays the tooltip: it is the authoritative value.
      hint: opt.value,
    })),
  ]
  return (
    <section
      className="kp-summary-row"
      data-testid="kp-summary-row"
      aria-label={t('knowledgeProduction.summary.total')}
    >
      {cells.map(c => (
        <div
          className={`kp-summary-card${c.key === 'total' ? ' kp-summary-card--total' : ''}`}
          key={c.key}
          data-testid={`kp-summary-${c.key}`}
          title={c.hint}
        >
          <span className="kp-summary-label">{t(c.labelKey)}</span>
          <span
            className={`kp-summary-value${c.value === '—' ? ' kp-summary-value--muted' : ''}`}
          >
            {c.value}
          </span>
        </div>
      ))}
    </section>
  )
}

export function KnowledgeProductionPage() {
  const { t } = useI18n()
  const [summary, setSummary] = useState<BrainRegionSummary | null>(null)

  useEffect(() => {
    let cancelled = false
    fetchBrainRegionSummary()
      .then(s => {
        if (!cancelled) setSummary(s)
      })
      .catch(() => {
        // counts are decorative on the index; a failure must not break browsing
        if (!cancelled) setSummary(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const openWorkspace = (seed: BrainRegionSeed) => navigate(kpWorkspacePath(seed.entity_id))

  return (
    <div className="page kp-page" data-testid="knowledge-production-page">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t('knowledgeProduction.title')}</h1>
          <p className="page-desc">
            {t('knowledgeProduction.subtitle', { database: AUTHORITY_DATABASE })}
          </p>
        </div>
      </header>

      <SummaryCards summary={summary} />

      <BrainRegionSeedList onOpen={openWorkspace} />
    </div>
  )
}

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
import { BrainRegionSeedList } from './BrainRegionSeedList'
import { fetchBrainRegionSummary } from './kpApi'
import { KP_GRANULARITY_OPTIONS, type BrainRegionSeed, type BrainRegionSummary } from './types'
import { kpWorkspacePath, navigate } from './routes'

function SummaryCards({ summary }: { summary: BrainRegionSummary | null }) {
  const cells: { key: string; label: string; value: string; hint: string }[] = [
    { key: 'total', label: 'Total', value: summary ? String(summary.total) : '—', hint: '全部脑区' },
    ...KP_GRANULARITY_OPTIONS.map(opt => ({
      key: opt.value,
      label: opt.label,
      value: summary ? String(summary.by_granularity[opt.value] ?? 0) : '—',
      hint: opt.value,
    })),
  ]
  return (
    <section className="kp-summary-row" data-testid="kp-summary-row" aria-label="脑区汇总">
      {cells.map(c => (
        <div
          className={`kp-summary-card${c.key === 'total' ? ' kp-summary-card--total' : ''}`}
          key={c.key}
          data-testid={`kp-summary-${c.key}`}
          title={c.hint}
        >
          <span className="kp-summary-label">{c.label}</span>
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
          <h1 className="page-title">知识生产</h1>
          <p className="page-desc">以脑区为中心的知识生产 · 权威库 neurographiq_human_brain_v1</p>
        </div>
      </header>

      <SummaryCards summary={summary} />

      <BrainRegionSeedList onOpen={openWorkspace} />
    </div>
  )
}

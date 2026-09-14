/**
 * Left pane — live BrainRegion seed list from the Gate7B authority.
 *
 * Server-side pagination only: the component never fetches all rows and slices
 * in the browser. Filter changes reset to page 1.
 */
import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import { DataTable, type Column } from '../../components/DataTable'
import { DataCenterPagination } from '../data-center/DataCenterPagination'
import { fetchBrainRegionSeeds } from './kpApi'
import {
  KP_GRANULARITY_OPTIONS,
  brainRegionNames,
  type BrainRegionSeed,
  type KpGranularity,
} from './types'

const PAGE_SIZE = 50

export interface BrainRegionSeedListProps {
  /** Called when a row is activated (click or Enter) — opens the workspace. */
  onOpen: (seed: BrainRegionSeed) => void
}

export function BrainRegionSeedList({ onOpen }: BrainRegionSeedListProps) {
  const { language, t } = useI18n()
  const [granularity, setGranularity] = useState<KpGranularity | null>(null)
  const [atlas, setAtlas] = useState('')
  const [atlasApplied, setAtlasApplied] = useState('')
  const [search, setSearch] = useState('')
  const [searchApplied, setSearchApplied] = useState('')
  const [page, setPage] = useState(1)
  const [refreshToken, setRefreshToken] = useState(0)

  const [rows, setRows] = useState<BrainRegionSeed[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchBrainRegionSeeds({
      granularityLevel: granularity,
      sourceAtlas: atlasApplied,
      search: searchApplied,
      limit: PAGE_SIZE,
      offset: (page - 1) * PAGE_SIZE,
    })
      .then(res => {
        if (cancelled) return
        setRows(res.items)
        setTotal(res.total)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setRows([])
        setTotal(0)
        setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [granularity, atlasApplied, searchApplied, page, refreshToken])

  const applyFilters = useCallback(() => {
    setPage(1)
    setAtlasApplied(atlas)
    setSearchApplied(search)
  }, [atlas, search])

  const resetFilters = useCallback(() => {
    setAtlas('')
    setSearch('')
    setAtlasApplied('')
    setSearchApplied('')
    setGranularity(null)
    setPage(1)
  }, [])

  const columns: Column<BrainRegionSeed>[] = [
    {
      key: 'name',
      header: t('knowledgeProduction.table.name'),
      // Locale-aware (§11): zh leads with name_zh, en leads with name_en; the
      // other name stays visible as a subtle secondary line.
      render: r => {
        const { primary, secondary } = brainRegionNames(r, language)
        return (
          <div className="kp-name-cell">
            <span className="kp-name-primary">{primary}</span>
            {secondary && <span className="kp-name-secondary">{secondary}</span>}
          </div>
        )
      },
    },
    {
      key: 'entity_id',
      header: t('knowledgeProduction.table.entityId'),
      render: r => <span className="kp-mono">{r.entity_id}</span>,
    },
    {
      key: 'granularity_level',
      header: t('knowledgeProduction.table.granularity'),
      // The chip shows the raw Gate7B value (language-neutral authority); the
      // localized reading is available on hover.
      render: r =>
        r.granularity_level ? (
          <span
            className="kp-chip kp-chip--accent"
            title={t(`knowledgeProduction.granularity.${r.granularity_level}`)}
          >
            {r.granularity_level}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'atlas_names',
      header: t('knowledgeProduction.table.atlas'),
      // Canonical atlas names are official English names — never translated.
      render: r => (r.atlas_names.length ? r.atlas_names.join(', ') : '—'),
    },
    {
      key: 'hemisphere',
      header: t('knowledgeProduction.table.hemisphere'),
      render: r => (r.hemisphere ? <span className="kp-hemi">{r.hemisphere}</span> : '—'),
    },
    {
      key: 'production',
      header: t('knowledgeProduction.table.production'),
      // A neutral resting state — deliberately not coloured as warning/error.
      render: () => (
        <span className="kp-prod">{t('knowledgeProduction.production.notInitialized')}</span>
      ),
    },
    {
      key: 'open',
      header: '',
      // Row affordance: reveals on hover, signalling the row opens a workspace.
      render: () => (
        <span className="kp-chevron" aria-hidden="true">
          ›
        </span>
      ),
    },
  ]

  return (
    <section className="kp-seed-pane" data-testid="kp-seed-pane">
      <div className="kp-toolbar" data-testid="kp-filter-bar">
        <span className="kp-toolbar-label">{t('knowledgeProduction.filters.granularity')}</span>
        <div
          className="kp-gran-group"
          role="group"
          aria-label={t('knowledgeProduction.filters.granularity')}
        >
          {KP_GRANULARITY_OPTIONS.map(opt => (
            <button
              key={opt.value}
              type="button"
              className="kp-gran-btn"
              aria-pressed={granularity === opt.value}
              // Tooltip keeps the raw enum; the caption is localized (§13).
              title={opt.value}
              data-testid={`kp-gran-${opt.key}`}
              onClick={() => {
                setGranularity(prev => (prev === opt.value ? null : opt.value))
                setPage(1)
              }}
            >
              {t(opt.labelKey)}
            </button>
          ))}
        </div>

        <input
          className="filter-input"
          placeholder={t('knowledgeProduction.filters.atlas')}
          aria-label={t('knowledgeProduction.filters.atlas')}
          data-testid="kp-atlas-input"
          value={atlas}
          onChange={e => setAtlas(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
        />
        <input
          className="filter-input"
          placeholder={t('knowledgeProduction.filters.search')}
          aria-label={t('knowledgeProduction.filters.search')}
          data-testid="kp-search-input"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
        />
        <button type="button" className="btn btn-sm btn-primary" data-testid="kp-apply" onClick={applyFilters}>
          {t('knowledgeProduction.filters.apply')}
        </button>
        <button type="button" className="btn btn-sm" data-testid="kp-reset" onClick={resetFilters}>
          {t('knowledgeProduction.filters.reset')}
        </button>
        <span className="kp-toolbar-spacer" />
        <button
          type="button"
          className="btn btn-sm"
          data-testid="kp-refresh"
          onClick={() => setRefreshToken(n => n + 1)}
        >
          {t('knowledgeProduction.filters.refresh')}
        </button>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        total={total}
        emptyText={t('knowledgeProduction.empty.noMatch')}
        getKey={r => r.entity_id}
        onRowClick={onOpen}
      />

      <DataCenterPagination
        page={page}
        pageSize={PAGE_SIZE}
        total={total}
        onPageChange={setPage}
        disabled={loading}
      />
    </section>
  )
}

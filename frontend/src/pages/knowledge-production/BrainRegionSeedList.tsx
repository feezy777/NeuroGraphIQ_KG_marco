/**
 * Left pane — live BrainRegion seed list from the Gate7B authority.
 *
 * Server-side pagination only: the component never fetches all rows and slices
 * in the browser. Filter changes reset to page 1.
 */
import { useCallback, useEffect, useState } from 'react'
import { DataTable, type Column } from '../../components/DataTable'
import { DataCenterPagination } from '../data-center/DataCenterPagination'
import { fetchBrainRegionSeeds } from './kpApi'
import { KP_GRANULARITY_OPTIONS, type BrainRegionSeed, type KpGranularity } from './types'

const PAGE_SIZE = 50

export interface BrainRegionSeedListProps {
  selectedId: string | null
  onSelect: (seed: BrainRegionSeed) => void
}

export function BrainRegionSeedList({ selectedId, onSelect }: BrainRegionSeedListProps) {
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
    { key: 'name_en', header: '名称 (EN)', render: r => r.name_en ?? '—' },
    { key: 'entity_id', header: 'entity_id', render: r => r.entity_id },
    {
      key: 'granularity_level',
      header: '粒度',
      render: r => r.granularity_level ?? '—',
    },
    {
      key: 'atlas_names',
      header: '来源 Atlas',
      render: r => (r.atlas_names.length ? r.atlas_names.join(', ') : '—'),
    },
    { key: 'hemisphere', header: '半球', render: r => r.hemisphere ?? '—' },
  ]

  return (
    <section className="kp-seed-pane" data-testid="kp-seed-pane">
      <div className="kp-filter-bar" data-testid="kp-filter-bar">
        <div className="kp-granularity-group" role="group" aria-label="G1-G4 粒度筛选">
          {KP_GRANULARITY_OPTIONS.map(opt => (
            <button
              key={opt.value}
              type="button"
              className={`btn btn-sm${granularity === opt.value ? ' active' : ''}`}
              aria-pressed={granularity === opt.value}
              data-testid={`kp-gran-${opt.label}`}
              onClick={() => {
                setGranularity(prev => (prev === opt.value ? null : opt.value))
                setPage(1)
              }}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <input
          className="kp-input"
          placeholder="Atlas 名称"
          aria-label="Atlas 筛选"
          data-testid="kp-atlas-input"
          value={atlas}
          onChange={e => setAtlas(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
        />
        <input
          className="kp-input"
          placeholder="搜索脑区"
          aria-label="脑区搜索"
          data-testid="kp-search-input"
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && applyFilters()}
        />
        <button type="button" className="btn btn-sm" data-testid="kp-apply" onClick={applyFilters}>
          筛选
        </button>
        <button type="button" className="btn btn-sm" data-testid="kp-reset" onClick={resetFilters}>
          重置
        </button>
        <button
          type="button"
          className="btn btn-sm"
          data-testid="kp-refresh"
          onClick={() => setRefreshToken(t => t + 1)}
        >
          刷新
        </button>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        loading={loading}
        error={error}
        total={total}
        emptyText="没有匹配的脑区"
        getKey={r => r.entity_id}
        onRowClick={onSelect}
        getRowClassName={r => (r.entity_id === selectedId ? 'kp-row-selected' : undefined)}
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

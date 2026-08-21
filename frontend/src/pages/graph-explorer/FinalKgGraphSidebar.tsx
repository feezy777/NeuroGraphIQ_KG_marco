import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchCandidates, fetchFinalRegions } from '../../api/endpoints'
import { GRANULARITY_LEVELS } from '../../hooks/useGlobalGranularity'
import {
  CANONICAL_NODE_TYPE_LABELS,
  GRAPH_CENTER_TYPES,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import { NODE_TYPE_COLORS } from './graphTheme'
import type { GraphDataSource } from './useGraphData'

// ── Types ───────────────────────────────────────────────────────────────────────

export interface GraphFilters {
  /** 后端 source_atlas 过滤（请求参数，可选） */
  atlas: string
  /** 后端 granularity_level 过滤（请求参数，可选） */
  granularity: string
  includeFunctions: boolean
  includeEvidence: boolean
}

interface FinalKgGraphSidebarProps {
  /** 数据源：mirror（当前有数据）/ final（晋升后使用） */
  dataSource: GraphDataSource
  onDataSourceChange: (source: GraphDataSource) => void
  filters: GraphFilters
  onFiltersChange: (filters: GraphFilters) => void
  /** 以 center 加载图（filters 由页面合并进请求） */
  onLoadCenter: (centerType: string, centerId: string) => void
  loading: boolean
  nodeCount: number
  edgeCount: number
  warnings: string[]
}

interface RegionOption {
  id: string
  label: string
  sub: string
}

const EDGE_GROUP_LEGEND = [
  { label: 'Structural', color: '#64748b' },
  { label: 'Has Function', color: '#f59e0b' },
  { label: 'Participates In', color: '#8b5cf6' },
  { label: 'Evidence', color: '#9ca3af' },
]

const SOURCE_OPTIONS: { value: GraphDataSource; label: string }[] = [
  { value: 'mirror', label: 'Mirror KG' },
  { value: 'final', label: 'Final KG' },
]

/** mirror 模式手动中心仅支持候选脑区（candidate_id） */
const MIRROR_CENTER_TYPES = [{ value: 'region', label: 'Region（candidate_id）' }]

// ── 左侧控制面板（240px，8pt 网格）─────────────────────────────────────────────

export function FinalKgGraphSidebar({
  dataSource,
  onDataSourceChange,
  filters,
  onFiltersChange,
  onLoadCenter,
  loading,
  nodeCount,
  edgeCount,
  warnings,
}: FinalKgGraphSidebarProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [regionOptions, setRegionOptions] = useState<RegionOption[]>([])
  const [showDropDown, setShowDropDown] = useState(false)
  const [searching, setSearching] = useState(false)
  const [centerType, setCenterType] = useState('region')
  const [centerIdInput, setCenterIdInput] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const dropDownRef = useRef<HTMLDivElement>(null)
  const isMirror = dataSource === 'mirror'
  const sourceRef = useRef<GraphDataSource>(dataSource)
  sourceRef.current = dataSource
  const searchTermRef = useRef(searchTerm)
  searchTermRef.current = searchTerm

  // 切换数据源：清空搜索/手动输入残留（两个源的 id 空间与搜索域不同）
  useEffect(() => {
    setSearchTerm('')
    setRegionOptions([])
    setShowDropDown(false)
    setCenterIdInput('')
    setCenterType('region')
  }, [dataSource])

  // 脑区名称自动补全：mirror → 候选库搜索；final → final_brain_regions 搜索
  const handleSearchChange = useCallback(
    (value: string) => {
      setSearchTerm(value)
      if (debounceRef.current) clearTimeout(debounceRef.current)
      if (value.trim().length < 2) {
        setRegionOptions([])
        setShowDropDown(false)
        return
      }
      debounceRef.current = setTimeout(async () => {
        setSearching(true)
        try {
          let items: RegionOption[] = []
          if (isMirror) {
            const res = await fetchCandidates({ search: value.trim(), limit: 10 })
            items = (res.items ?? []).map(c => ({
              id: c.id,
              label: c.en_name || c.std_name || c.cn_name || c.raw_name,
              sub: [c.source_atlas, c.granularity_level].filter(Boolean).join(' · '),
            }))
          } else {
            const res = await fetchFinalRegions({ keyword: value.trim(), limit: 10 })
            items = (res.items ?? []).map(r => ({
              id: r.candidate_id,
              label: r.en_name || r.std_name || r.cn_name || r.raw_name,
              sub: [r.source_atlas, r.granularity_level].filter(Boolean).join(' · '),
            }))
          }
          // 数据源已切换或搜索词已更新 → 丢弃过期结果
          if (sourceRef.current === dataSource && searchTermRef.current === value) {
            setRegionOptions(items)
            setShowDropDown(true)
          }
        } catch {
          setRegionOptions([])
        } finally {
          setSearching(false)
        }
      }, 300)
    },
    [isMirror, dataSource],
  )

  const selectRegion = useCallback(
    (option: RegionOption) => {
      setShowDropDown(false)
      setSearchTerm(option.label)
      onLoadCenter('region', option.id)
    },
    [onLoadCenter],
  )

  // 点击下拉框外关闭
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (dropDownRef.current && !dropDownRef.current.contains(e.target as Node)) {
        setShowDropDown(false)
      }
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const handleManualLoad = () => {
    const id = centerIdInput.trim()
    if (!id) return
    onLoadCenter(isMirror ? 'region' : centerType, id)
  }

  const centerTypeOptions = isMirror ? MIRROR_CENTER_TYPES : GRAPH_CENTER_TYPES

  return (
    <aside className="cg-sidebar">
      <div className="cg-sidebar-head">
        <h3 className="cg-sidebar-title">Canonical KG Explorer</h3>
        <p className="cg-sidebar-desc">
          {isMirror
            ? '镜像库数据（晋升完成后可切换 Final 数据）'
            : '基于 final_macro_clinical browser API 的本体知识图谱（确定性布局）'}
        </p>
      </div>

      {/* ── 数据源切换 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">数据源</label>
        <div className="cg-source-switch" role="group" aria-label="图数据源">
          {SOURCE_OPTIONS.map(opt => (
            <button
              key={opt.value}
              type="button"
              className={`cg-source-switch-btn${dataSource === opt.value ? ' is-active' : ''}`}
              onClick={() => onDataSourceChange(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* ── 中心实体搜索 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">中心脑区搜索</label>
        <div className="cg-autocomplete" ref={dropDownRef}>
          <input
            className="cg-input"
            type="text"
            placeholder={isMirror ? '输入候选脑区名称（≥2 字符）…' : '输入脑区名称（≥2 字符）…'}
            value={searchTerm}
            onChange={e => handleSearchChange(e.target.value)}
            onFocus={() => {
              if (regionOptions.length > 0) setShowDropDown(true)
            }}
          />
          {showDropDown && (
            <div className="cg-autocomplete-dropdown">
              {searching ? (
                <div className="cg-autocomplete-hint">搜索中…</div>
              ) : regionOptions.length === 0 ? (
                <div className="cg-autocomplete-hint">无匹配脑区</div>
              ) : (
                regionOptions.map(option => (
                  <button
                    key={option.id}
                    type="button"
                    className="cg-autocomplete-item"
                    onClick={() => selectRegion(option)}
                  >
                    <span className="cg-autocomplete-item-label">{option.label}</span>
                    {option.sub && <span className="cg-autocomplete-item-sub">{option.sub}</span>}
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </section>

      {/* ── 手动中心加载 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">手动指定中心</label>
        <select className="cg-select" value={centerType} onChange={e => setCenterType(e.target.value)}>
          {centerTypeOptions.map(ct => (
            <option key={ct.value} value={ct.value}>
              {ct.label}
            </option>
          ))}
        </select>
        <div className="cg-inline-row">
          <input
            className="cg-input"
            type="text"
            placeholder={isMirror ? 'candidate_id（uuid）' : '实体 id（uuid）'}
            value={centerIdInput}
            onChange={e => setCenterIdInput(e.target.value)}
          />
          <button
            type="button"
            className="btn btn-sm btn-primary"
            onClick={handleManualLoad}
            disabled={loading || !centerIdInput.trim()}
          >
            {loading ? '加载中…' : '加载'}
          </button>
        </div>
      </section>

      {/* ── 请求过滤（后端参数） ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">Atlas（可选）</label>
        <input
          className="cg-input"
          type="text"
          placeholder="如 AAL3 / Macro96"
          value={filters.atlas}
          onChange={e => onFiltersChange({ ...filters, atlas: e.target.value })}
        />
        <label className="cg-sidebar-label">粒度（可选）</label>
        <select
          className="cg-select"
          value={filters.granularity}
          onChange={e => onFiltersChange({ ...filters, granularity: e.target.value })}
        >
          <option value="">全部粒度</option>
          {GRANULARITY_LEVELS.map(g => (
            <option key={g.key} value={g.key}>
              {g.label}
            </option>
          ))}
        </select>
        <div className="cg-check-row">
          <label className="cg-check">
            <input
              type="checkbox"
              checked={filters.includeFunctions}
              onChange={e => onFiltersChange({ ...filters, includeFunctions: e.target.checked })}
            />
            <span>包含功能节点</span>
          </label>
          <label className={`cg-check${isMirror ? ' is-disabled' : ''}`} title={isMirror ? '镜像数据暂无独立证据节点' : undefined}>
            <input
              type="checkbox"
              checked={filters.includeEvidence}
              disabled={isMirror}
              onChange={e => onFiltersChange({ ...filters, includeEvidence: e.target.checked })}
            />
            <span>包含证据节点</span>
          </label>
        </div>
      </section>

      {/* ── 图统计 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">当前图</label>
        <div className="cg-stats-row">
          <span className="cg-stat">
            <strong>{nodeCount}</strong> 节点
          </span>
          <span className="cg-stat">
            <strong>{edgeCount}</strong> 边
          </span>
        </div>
        {warnings.length > 0 && (
          <ul className="cg-warnings">
            {warnings.map((w, i) => (
              <li key={i}>⚠ {w}</li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 图例 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">节点图例</label>
        {(Object.keys(CANONICAL_NODE_TYPE_LABELS) as CanonicalNodeType[]).map(t => (
          <div key={t} className="cg-legend-row">
            <span className="cg-legend-swatch" style={{ background: NODE_TYPE_COLORS[t] }} />
            <span className="cg-legend-text">{CANONICAL_NODE_TYPE_LABELS[t]}</span>
          </div>
        ))}
        <label className="cg-sidebar-label">边图例</label>
        {EDGE_GROUP_LEGEND.map(item => (
          <div key={item.label} className="cg-legend-row">
            <span className="cg-legend-line" style={{ borderTopColor: item.color }} />
            <span className="cg-legend-text">{item.label}</span>
          </div>
        ))}
      </section>
    </aside>
  )
}

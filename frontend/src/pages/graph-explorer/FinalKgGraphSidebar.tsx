import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import {
  Brain,
  CircuitBoard,
  FileText,
  Link2,
  ListOrdered,
  Search,
  Sigma,
  TimerReset,
  X,
} from 'lucide-react'
import { fetchCandidates } from '../../api/endpoints'
import { GRANULARITY_LEVELS } from '../../hooks/useGlobalGranularity'
import { getCanonicalRegionDirectory, searchCanonicalRegions } from './adapters/finalEgoGraph'
import {
  CANONICAL_NODE_TYPE_LABELS,
  GRAPH_CENTER_TYPES,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import { NODE_TYPE_COLORS } from './graphTheme'
import { toggleSetValue, type DisplayFilters } from './graphFilter'
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
  /** 图内证据节点数（final 源才有独立证据节点） */
  evidenceCount: number
  warnings: string[]
  /** 展示过滤（实体可见性 / 关系分组），由页面持有 → hash 同步 */
  displayFilters: DisplayFilters
  onDisplayFiltersChange: (filters: DisplayFilters) => void
  /** 当前图内按实体类型计数（诚实统计，非 mock） */
  entityCounts: Record<CanonicalNodeType, number>
}

interface RegionOption {
  id: string
  label: string
  sub: string
}

interface RecentCenter {
  label: string
  centerType: string
  centerId: string
}

const SOURCE_OPTIONS: { value: GraphDataSource; label: string }[] = [
  { value: 'mirror', label: 'Mirror KG' },
  { value: 'final', label: 'Final KG' },
]

/** 实体类型卡（含图标）：按 spec 仅列 5 类（circuit_step 保留在图上但不在面板） */
const ENTITY_CARD_TYPES: CanonicalNodeType[] = [
  'brain_region',
  'connection',
  'circuit',
  'function',
  'evidence',
]

const ENTITY_TYPE_ICONS: Record<CanonicalNodeType, typeof Search> = {
  brain_region: Brain,
  connection: Link2,
  circuit: CircuitBoard,
  circuit_step: ListOrdered,
  function: Sigma,
  evidence: FileText,
}

/** 关系过滤展示标签（spec 四类语义命名；值仍用 RELATION_GROUPS.value） */
const RELATION_FILTERS: { value: string; label: string }[] = [
  { value: 'structural', label: 'Structural Connection' },
  { value: 'has_function', label: 'Functional Association' },
  { value: 'participates_in', label: 'Circuit Participation' },
  { value: 'evidence', label: 'Evidence Support' },
]

/** mirror 模式手动中心仅支持候选脑区（candidate_id） */
const MIRROR_CENTER_TYPES = [{ value: 'region', label: 'Region（candidate_id）' }]

// ── 最近搜索（localStorage 真实历史，非 mock） ──────────────────────────────────

const RECENT_KEY = 'kg.explorer.recentCenters'
const RECENT_MAX = 5

function readRecentCenters(): RecentCenter[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as RecentCenter[]
    if (!Array.isArray(parsed)) return []
    return parsed.filter(r => r && typeof r.label === 'string' && r.centerId).slice(0, RECENT_MAX)
  } catch {
    return []
  }
}

function pushRecentCenter(center: RecentCenter): RecentCenter[] {
  const next = [center, ...readRecentCenters().filter(r => r.centerId !== center.centerId)].slice(0, RECENT_MAX)
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next))
  } catch {
    // ignore
  }
  return next
}

// ── 左侧探索控制面板 ────────────────────────────────────────────────────────────

export function FinalKgGraphSidebar({
  dataSource,
  onDataSourceChange,
  filters,
  onFiltersChange,
  onLoadCenter,
  loading,
  nodeCount,
  edgeCount,
  evidenceCount,
  warnings,
  displayFilters,
  onDisplayFiltersChange,
  entityCounts,
}: FinalKgGraphSidebarProps) {
  const [searchTerm, setSearchTerm] = useState('')
  const [regionOptions, setRegionOptions] = useState<RegionOption[]>([])
  const [showDropDown, setShowDropDown] = useState(false)
  const [searching, setSearching] = useState(false)
  const [recentCenters, setRecentCenters] = useState<RecentCenter[]>(readRecentCenters)
  const [centerType, setCenterType] = useState('region')
  const [centerIdInput, setCenterIdInput] = useState('')
  const [showRequestOptions, setShowRequestOptions] = useState(false)
  const [showManualLoad, setShowManualLoad] = useState(false)
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

  /** 记录真实最近搜索并触发加载 */
  const loadCenter = useCallback(
    (label: string, centerTypeVal: string, centerId: string) => {
      setRecentCenters(pushRecentCenter({ label, centerType: centerTypeVal, centerId }))
      onLoadCenter(centerTypeVal, centerId)
    },
    [onLoadCenter],
  )

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
            // Data Adapter V1：Final/Canonical 源搜索 = canonical 脑区目录本地过滤（686 区全量一次）
            const directory = await getCanonicalRegionDirectory()
            items = searchCanonicalRegions(directory, value, 10).map(r => ({
              id: r.id,
              label: r.canonical_name_en,
              sub: [r.granularity_level, r.species].filter(Boolean).join(' · '),
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
      loadCenter(option.label, 'region', option.id)
    },
    [loadCenter],
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
    loadCenter(id.slice(0, 32) || 'manual', isMirror ? 'region' : centerType, id)
  }

  const centerTypeOptions = isMirror ? MIRROR_CENTER_TYPES : GRAPH_CENTER_TYPES

  const toggleEntityType = useCallback(
    (type: CanonicalNodeType) => {
      onDisplayFiltersChange({
        ...displayFilters,
        entityTypes: toggleSetValue(displayFilters.entityTypes, type),
      })
    },
    [displayFilters, onDisplayFiltersChange],
  )

  const toggleRelationGroup = useCallback(
    (group: string) => {
      onDisplayFiltersChange({
        ...displayFilters,
        relationGroups: toggleSetValue(displayFilters.relationGroups, group),
      })
    },
    [displayFilters, onDisplayFiltersChange],
  )

  return (
    <aside className="cg-sidebar">
      <div className="cg-sidebar-head">
        <h3 className="cg-sidebar-title">探索控制面板</h3>
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
        <label className="cg-sidebar-label">搜索图谱中心</label>
        <div className="cg-autocomplete" ref={dropDownRef}>
          <Search size={13} className="cg-autocomplete-icon" />
          <input
            className="cg-input cg-input-search"
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

        {/* ── 快速搜索卡片（最近搜索，localStorage 真实历史） ── */}
        <div className="cg-recent-block">
          <span className="cg-recent-title">快速搜索</span>
          {recentCenters.length === 0 ? (
            <span className="cg-recent-empty">暂无最近搜索（加载一个中心后自动记录）</span>
          ) : (
            <div className="cg-recent-chips">
              {recentCenters.map(rc => (
                <span key={rc.centerId} className="cg-recent-chip">
                  <span
                    className="cg-recent-chip-label"
                    role="button"
                    tabIndex={0}
                    onClick={() => loadCenter(rc.label, rc.centerType, rc.centerId)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') loadCenter(rc.label, rc.centerType, rc.centerId)
                    }}
                  >
                    {rc.label}
                  </span>
                  <button
                    type="button"
                    className="cg-recent-chip-x"
                    aria-label={`移除 ${rc.label}`}
                    onClick={() =>
                      setRecentCenters(
                        readRecentCenters().filter(c => c.centerId !== rc.centerId).slice(0, RECENT_MAX),
                      )
                    }
                  >
                    <X size={10} />
                  </button>
                </span>
              ))}
            </div>
          )}
          {recentCenters.length > 0 && (
            <button
              type="button"
              className="cg-recent-clear"
              onClick={() => {
                try {
                  localStorage.removeItem(RECENT_KEY)
                } catch {
                  // ignore
                }
                setRecentCenters([])
              }}
            >
              清除记录
            </button>
          )}
        </div>
      </section>

      {/* ── 实体类型（带图标卡片 + 图内计数；点击切换可见性） ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">实体类型</label>
        <div className="cg-entity-type-grid">
          {ENTITY_CARD_TYPES.map(type => {
            const Icon = ENTITY_TYPE_ICONS[type]
            const count = entityCounts[type] ?? 0
            const active = displayFilters.entityTypes.size === 0 || displayFilters.entityTypes.has(type)
            return (
              <button
                key={type}
                type="button"
                className={`cg-entity-type-card${active ? '' : ' is-hidden'}`}
                style={{ '--cg-type-color': NODE_TYPE_COLORS[type] } as CSSProperties}
                aria-pressed={active}
                onClick={() => toggleEntityType(type)}
              >
                <span className="cg-entity-type-icon">
                  <Icon size={14} />
                </span>
                <span className="cg-entity-type-text">
                  <span className="cg-entity-type-name">{CANONICAL_NODE_TYPE_LABELS[type]}</span>
                  <span className="cg-entity-type-count">{count}</span>
                </span>
              </button>
            )
          })}
        </div>
      </section>

      {/* ── 图谱统计 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">图谱统计</label>
        <div className="cg-stats-grid">
          <div className="cg-stat-card">
            <span className="cg-stat-num">{nodeCount}</span>
            <span className="cg-stat-name">Nodes</span>
          </div>
          <div className="cg-stat-card">
            <span className="cg-stat-num">{edgeCount}</span>
            <span className="cg-stat-name">Edges</span>
          </div>
          <div className="cg-stat-card">
            <span className="cg-stat-num">{evidenceCount}</span>
            <span className="cg-stat-name">Evidence</span>
          </div>
        </div>
        {warnings.length > 0 && (
          <ul className="cg-warnings">
            {warnings.map((w, i) => (
              <li key={i}>⚠ {w}</li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 关系过滤 ── */}
      <section className="cg-sidebar-section">
        <label className="cg-sidebar-label">关系过滤</label>
        <div className="cg-relation-filter">
          {RELATION_FILTERS.map(({ value, label }) => {
            const active = displayFilters.relationGroups.size === 0 || displayFilters.relationGroups.has(value)
            return (
              <button
                key={value}
                type="button"
                className={`cg-relation-filter-btn${active ? '' : ' is-hidden'}`}
                aria-pressed={active}
                onClick={() => toggleRelationGroup(value)}
              >
                <span
                  className="cg-relation-filter-line"
                  style={{
                    borderTopColor: NODE_TYPE_COLORS.brain_region,
                    borderTopStyle: value === 'has_function' || value === 'evidence' ? 'dashed' : 'solid',
                  }}
                />
                <span className="cg-relation-filter-label">{label}</span>
              </button>
            )
          })}
        </div>
      </section>

      {/* ── 请求选项（折叠；后端请求参数） ── */}
      <section className="cg-sidebar-section">
        <button
          type="button"
          className="cg-sidebar-collapse"
          onClick={() => setShowRequestOptions(v => !v)}
          aria-expanded={showRequestOptions}
        >
          <TimerReset size={12} />
          请求选项（Atlas / 粒度）
          <span className="cg-sidebar-collapse-arrow">{showRequestOptions ? '▾' : '▸'}</span>
        </button>
        {showRequestOptions && (
          <div className="cg-sidebar-collapse-body">
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
          </div>
        )}
      </section>

      {/* ── 手动中心加载（折叠） ── */}
      <section className="cg-sidebar-section">
        <button
          type="button"
          className="cg-sidebar-collapse"
          onClick={() => setShowManualLoad(v => !v)}
          aria-expanded={showManualLoad}
        >
          <Search size={12} />
          手动指定中心（uuid）
          <span className="cg-sidebar-collapse-arrow">{showManualLoad ? '▾' : '▸'}</span>
        </button>
        {showManualLoad && (
          <div className="cg-sidebar-collapse-body">
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
          </div>
        )}
      </section>
    </aside>
  )
}

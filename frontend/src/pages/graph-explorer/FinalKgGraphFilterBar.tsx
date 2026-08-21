/**
 * 顶部过滤条（Phase 7）：
 * 实体类型 / 粒度 / 关系分组 三组 chip 开关 + 重置。
 * 只过滤前端展示（filterCanonicalGraph），不修改数据库、不发请求。
 */
import { useCallback } from 'react'
import { GRANULARITY_LEVELS } from '../../hooks/useGlobalGranularity'
import {
  CANONICAL_NODE_TYPE_LABELS,
  RELATION_GROUPS,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import {
  emptyDisplayFilters,
  toggleSetValue,
  type DisplayFilters,
} from './graphFilter'

interface FinalKgGraphFilterBarProps {
  filters: DisplayFilters
  onFiltersChange: (filters: DisplayFilters) => void
}

export function FinalKgGraphFilterBar({ filters, onFiltersChange }: FinalKgGraphFilterBarProps) {
  const toggleEntity = useCallback(
    (type: CanonicalNodeType) => {
      onFiltersChange({ ...filters, entityTypes: toggleSetValue(filters.entityTypes, type) })
    },
    [filters, onFiltersChange],
  )

  const toggleGroup = useCallback(
    (group: string) => {
      onFiltersChange({ ...filters, relationGroups: toggleSetValue(filters.relationGroups, group) })
    },
    [filters, onFiltersChange],
  )

  const selectGranularity = useCallback(
    (value: string) => {
      onFiltersChange({ ...filters, granularity: value })
    },
    [filters, onFiltersChange],
  )

  const reset = useCallback(() => {
    onFiltersChange(emptyDisplayFilters())
  }, [onFiltersChange])

  return (
    <div className="cg-filterbar" role="toolbar" aria-label="图谱展示过滤">
      <div className="cg-filterbar-group">
        <span className="cg-filterbar-label">实体</span>
        {(Object.keys(CANONICAL_NODE_TYPE_LABELS) as CanonicalNodeType[]).map(type => (
          <button
            key={type}
            type="button"
            className={`cg-filter-chip${filters.entityTypes.has(type) ? ' cg-filter-chip-active' : ''}`}
            aria-pressed={filters.entityTypes.has(type)}
            onClick={() => toggleEntity(type)}
          >
            {CANONICAL_NODE_TYPE_LABELS[type]}
          </button>
        ))}
      </div>

      <div className="cg-filterbar-group">
        <span className="cg-filterbar-label">粒度</span>
        <button
          type="button"
          className={`cg-filter-chip${filters.granularity === '' ? ' cg-filter-chip-active' : ''}`}
          aria-pressed={filters.granularity === ''}
          onClick={() => selectGranularity('')}
        >
          全部
        </button>
        {GRANULARITY_LEVELS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`cg-filter-chip${filters.granularity === g.key ? ' cg-filter-chip-active' : ''}`}
            aria-pressed={filters.granularity === g.key}
            onClick={() => selectGranularity(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>

      <div className="cg-filterbar-group">
        <span className="cg-filterbar-label">关系</span>
        {RELATION_GROUPS.map(group => (
          <button
            key={group.value}
            type="button"
            className={`cg-filter-chip${filters.relationGroups.has(group.value) ? ' cg-filter-chip-active' : ''}`}
            aria-pressed={filters.relationGroups.has(group.value)}
            onClick={() => toggleGroup(group.value)}
          >
            {group.label}
          </button>
        ))}
      </div>

      <button type="button" className="cg-filterbar-reset" onClick={reset}>
        重置
      </button>
    </div>
  )
}

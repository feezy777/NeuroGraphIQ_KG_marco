/**
 * 顶部知识图谱导航栏（Phase 7；V2 改造）：
 * 标题 + 模式徽章 + 数据源状态 + 粒度 pills + 保存/分享视图。
 * 实体类型 / 关系分组过滤已移至左侧探索面板（V2）；
 * 粒度仍在顶部作为一级导航（spec：粒度是首层切换）。
 * 只过滤前端展示（filterCanonicalGraph），不修改数据库、不发请求。
 */
import { useCallback, useState } from 'react'
import { BookOpen, Link as LinkIcon, Save } from 'lucide-react'
import { GRANULARITY_LEVELS } from '../../hooks/useGlobalGranularity'
import type { DisplayFilters } from './graphFilter'
import type { GraphDataSource } from './useGraphData'

interface FinalKgGraphFilterBarProps {
  filters: DisplayFilters
  onFiltersChange: (filters: DisplayFilters) => void
  dataSource: GraphDataSource
  /** 保存视图：把当前过滤写入 URL hash（页面实现，防循环） */
  onSaveView: () => void
}

export function FinalKgGraphFilterBar({
  filters,
  onFiltersChange,
  dataSource,
  onSaveView,
}: FinalKgGraphFilterBarProps) {
  const [copied, setCopied] = useState(false)

  const selectGranularity = useCallback(
    (value: string) => {
      onFiltersChange({ ...filters, granularity: value })
    },
    [filters, onFiltersChange],
  )

  const reset = useCallback(() => {
    onFiltersChange({ entityTypes: new Set(), granularity: '', relationGroups: new Set() })
  }, [onFiltersChange])

  const handleShare = useCallback(async () => {
    try {
      onSaveView()
      await navigator.clipboard.writeText(window.location.href)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // clipboard 不可用（http 或权限）→ 忽略
    }
  }, [onSaveView])

  const granularity = filters.granularity

  return (
    <div className="kg-header" role="toolbar" aria-label="知识图谱导航栏">
      <div className="kg-header-left">
        <span className="kg-header-icon">
          <BookOpen size={15} />
        </span>
        <div className="kg-header-titles">
          <span className="kg-header-title">Canonical Knowledge Graph</span>
          <span className="kg-header-badge kg-header-badge-mode">Canonical</span>
          <span className={`kg-header-badge kg-header-badge-source${dataSource === 'mirror' ? ' is-mirror' : ' is-final'}`}>
            {dataSource === 'mirror' ? 'Mirror KG' : 'Final KG'}
          </span>
        </div>
      </div>

      <div className="kg-header-group">
        <span className="kg-header-label">粒度</span>
        <button
          type="button"
          className={`kg-header-chip${granularity === '' ? ' is-active' : ''}`}
          aria-pressed={granularity === ''}
          onClick={() => selectGranularity('')}
        >
          全部
        </button>
        {GRANULARITY_LEVELS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`kg-header-chip${granularity === g.key ? ' is-active' : ''}`}
            aria-pressed={granularity === g.key}
            onClick={() => selectGranularity(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>

      <div className="kg-header-right">
        <button type="button" className="kg-header-action" onClick={onSaveView}>
          <Save size={13} />
          保存视图
        </button>
        <button type="button" className="kg-header-action" onClick={handleShare}>
          <LinkIcon size={13} />
          {copied ? '已复制链接' : '分享视图'}
        </button>
        <button type="button" className="kg-header-action" onClick={reset}>
          重置
        </button>
      </div>
    </div>
  )
}

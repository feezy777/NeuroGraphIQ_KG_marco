import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { ontologyApi } from '../../../api/ontologyApi'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { SkeletonRows } from '../ui/Skeleton'
import { SEARCH_GROUP_DEFS } from './tree/entityRoots'
import { TreeNodeRow } from './tree/TreeNodeRow'
import type { OntologyTreeNode } from './tree/OntologyTreeNode'

/** 触发搜索的最小输入长度（Browser 据此在树 / 搜索结果间切换） */
export const ONTOLOGY_SEARCH_MIN_LENGTH = 2
const DEBOUNCE_MS = 300

type OntologySearchInputProps = {
  value: string
  onChange: (value: string) => void
}

/** 顶部搜索框：name / chinese name / code / alias（数据层过滤逻辑在 ontologyApi.searchEntities） */
export function OntologySearchInput({ value, onChange }: OntologySearchInputProps) {
  return (
    <div className="oc-tree-search">
      <Search size={14} className="oc-tree-search-icon" aria-hidden="true" />
      <input
        type="search"
        className="oc-tree-search-input"
        placeholder="Search ontology..."
        aria-label="Search ontology"
        value={value}
        onChange={e => onChange(e.target.value)}
      />
    </div>
  )
}

type OntologySearchResultsProps = {
  query: string
  onSelect: (node: OntologyTreeNode) => void
}

/**
 * 搜索结果（替代树显示）：4 个全量列表端点并行查询，按实体类型分组，
 * 复用 TreeNodeRow 展示（depth=0、无 chevron）。防抖 + AbortController 取消竞态。
 */
export function OntologySearchResults({ query, onSelect }: OntologySearchResultsProps) {
  const [results, setResults] = useState<OntologyTreeNode[] | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [hasError, setHasError] = useState(false)
  const [retryKey, setRetryKey] = useState(0)

  useEffect(() => {
    const trimmed = query.trim()
    if (trimmed.length < ONTOLOGY_SEARCH_MIN_LENGTH) {
      setResults(null)
      setIsLoading(false)
      setHasError(false)
      return
    }
    const controller = new AbortController()
    let active = true
    setIsLoading(true)
    setHasError(false)
    const timer = setTimeout(() => {
      ontologyApi
        .searchEntities(trimmed, controller.signal)
        .then(nodes => {
          if (active) {
            setResults(nodes)
            setIsLoading(false)
          }
        })
        .catch(() => {
          if (active) {
            setHasError(true)
            setIsLoading(false)
          }
        })
    }, DEBOUNCE_MS)
    return () => {
      active = false
      controller.abort()
      clearTimeout(timer)
    }
  }, [query, retryKey])

  const grouped = useMemo(() => {
    if (!results) return []
    return SEARCH_GROUP_DEFS.map(def => ({
      label: def.name,
      nodes: results.filter(node => node.entityType === def.entityType),
    })).filter(group => group.nodes.length > 0)
  }, [results])

  if (hasError) {
    return (
      <ErrorState message="Search failed" onRetry={() => setRetryKey(k => k + 1)} />
    )
  }

  if (isLoading) {
    return (
      <div className="oc-skeleton-block" aria-label="加载中">
        <SkeletonRows rows={4} />
      </div>
    )
  }

  if (query.trim().length < ONTOLOGY_SEARCH_MIN_LENGTH) return null

  if (!results || results.length === 0) {
    return (
      <EmptyState title="No matching entities" reason={`“${query.trim()}” 无匹配的本体实体`} />
    )
  }

  return (
    <div className="oc-tree-root" role="list">
      {grouped.map(group => (
        <div key={group.label}>
          <div className="oc-tree-results-group">{group.label}</div>
          {group.nodes.map(node => (
            <TreeNodeRow
              key={node.id}
              node={node}
              depth={0}
              isExpanded={false}
              isSelected={false}
              isLoading={false}
              hasError={false}
              showChevron={false}
              onToggle={() => undefined}
              onSelect={onSelect}
            />
          ))}
        </div>
      ))}
    </div>
  )
}

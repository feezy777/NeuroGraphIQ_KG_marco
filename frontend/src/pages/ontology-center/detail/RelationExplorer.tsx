import { useState } from 'react'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { SkeletonRows } from '../ui/Skeleton'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'
import { RelationSection } from './RelationSection'
import type { RelationGroup } from './types'

type RelationExplorerProps = {
  /** 关系数据由 Browser 单次拉取后共享（null = 加载中） */
  groups: RelationGroup[] | null
  hasError: boolean
  onRetry?: () => void
  /** 关系行导航（点击跳转到相关实体详情）→ 宿主在树中重新选中 */
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}

type RelationTab = { key: string; label: string; groupKeys: string[] | null }

const TAB_DEFS: RelationTab[] = [
  { key: 'all', label: 'All', groupKeys: null },
  { key: 'connections', label: 'Connections', groupKeys: ['connections'] },
  { key: 'circuits', label: 'Circuits', groupKeys: ['circuits'] },
  { key: 'functions', label: 'Functions', groupKeys: ['functions'] },
]

/**
 * Relation Explorer（右栏）：Tabs [All/Connections/Circuits/Functions] + 数量 badge，
 * 关系以 RelationCard 展示。纯展示组件——数据由 Browser 拉取后注入。
 */
export function RelationExplorer({ groups, hasError, onRetry, onNavigate }: RelationExplorerProps) {
  const [activeTab, setActiveTab] = useState('all')

  if (hasError) {
    return <ErrorState message="Relations failed to load" onRetry={onRetry} />
  }

  if (!groups) {
    return (
      <div className="oc-skeleton-block" aria-label="加载中">
        <SkeletonRows rows={5} />
      </div>
    )
  }

  const availableTabs = TAB_DEFS.filter(
    tab => tab.groupKeys === null || groups.some(group => tab.groupKeys?.includes(group.key)),
  )
  const currentTab = availableTabs.some(tab => tab.key === activeTab) ? activeTab : 'all'
  const currentDef = TAB_DEFS.find(tab => tab.key === currentTab)
  const visibleGroups =
    currentTab === 'all' || !currentDef?.groupKeys
      ? groups
      : groups.filter(group => currentDef.groupKeys?.includes(group.key))

  const countFor = (tab: RelationTab): number => {
    const scoped = tab.groupKeys === null ? groups : groups.filter(g => tab.groupKeys?.includes(g.key))
    return scoped.reduce((sum, group) => sum + (group.unavailable ? 0 : group.items.length), 0)
  }

  return (
    <div className="oc-relation-explorer">
      <div className="oc-relation-tabs" role="tablist" aria-label="Relation filters">
        {availableTabs.map(tab => (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={currentTab === tab.key}
            className={`oc-relation-tab ${currentTab === tab.key ? 'oc-relation-tab-active' : ''}`}
            onClick={() => setActiveTab(tab.key)}
          >
            {tab.label}
            <span className="oc-relation-tab-count">{countFor(tab)}</span>
          </button>
        ))}
      </div>
      <div className="oc-relation-groups">
        {visibleGroups.length === 0 ? (
          <EmptyState title="No canonical relation available" reason="该实体暂无此关系记录" />
        ) : (
          visibleGroups.map(group => (
            <RelationSection key={group.key} group={group} onNavigate={onNavigate} />
          ))
        )}
      </div>
    </div>
  )
}

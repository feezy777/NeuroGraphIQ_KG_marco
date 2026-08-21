import { ChevronDown, ChevronRight, Folder, Loader2 } from 'lucide-react'
import { EntityIcon } from '../../ui/EntityIcon'
import { OntologyBadge } from '../../ui/OntologyBadge'
import { StatusChip } from '../../ui/StatusChip'
import {
  GRANULARITY_LEVEL_NAMES,
  type OntologyTreeNode,
} from './OntologyTreeNode'

type TreeNodeRowProps = {
  node: OntologyTreeNode
  depth: number
  isExpanded: boolean
  isSelected: boolean
  isLoading: boolean
  hasError: boolean
  showChevron: boolean
  /** 已知子计数（已加载 → 缓存长度；折叠 → childCountById）；>0 时显示 (n) 徽章 */
  childCount?: number
  onToggle: (node: OntologyTreeNode) => void
  onSelect: (node: OntologyTreeNode) => void
}

/**
 * 纯展示行：实体图标 + 名称 + [Macro] 粒度徽章 + (n) 子计数 + 状态 chip；
 * code 隐藏到行 tooltip（不占行宽），长名称行内省略 + 名称自身 tooltip。
 * isGroup（connection_type / circuit_type 虚拟分组）：文件夹图标 + 计数徽章，
 * 无 level/状态 chip，点击仅展开/收起。
 */
export function TreeNodeRow({
  node,
  depth,
  isExpanded,
  isSelected,
  isLoading,
  hasError,
  showChevron,
  childCount,
  onToggle,
  onSelect,
}: TreeNodeRowProps) {
  const levelName = node.granularityLevel
    ? GRANULARITY_LEVEL_NAMES[node.granularityLevel]
    : undefined

  return (
    <div
      className={`oc-tree-row ${isSelected ? 'oc-tree-row-selected' : ''} ${
        node.isGroup ? 'oc-tree-row-group' : ''
      }`}
      style={{ paddingLeft: 8 + depth * 16 }}
      title={node.code ?? undefined}
      onClick={() => onSelect(node)}
    >
      {showChevron ? (
        <button
          type="button"
          className="oc-tree-chevron"
          aria-label={isExpanded ? '收起' : '展开'}
          onClick={e => {
            e.stopPropagation()
            onToggle(node)
          }}
        >
          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
      ) : (
        <span className="oc-tree-chevron oc-tree-chevron-spacer" aria-hidden="true" />
      )}
      {isLoading && <Loader2 size={12} className="spin oc-tree-spinner" aria-label="加载中" />}
      {node.isGroup ? (
        <Folder size={14} className="oc-tree-icon oc-tree-group-icon" />
      ) : (
        <EntityIcon entityType={node.entityType} size={14} className="oc-tree-icon" />
      )}
      <span
        className={`oc-tree-label ${node.isEntityRoot ? 'oc-tree-entity-root' : ''} ${
          node.isGroup ? 'oc-tree-group-label' : ''
        }`}
        title={node.name}
      >
        {node.name}
      </span>
      {node.isGroup && (
        <span className="oc-tree-group-count">{node.children?.length ?? 0}</span>
      )}
      {!node.isGroup && levelName && (
        <OntologyBadge variant="level" title={levelName}>
          {`[${levelName}]`}
        </OntologyBadge>
      )}
      {!node.isGroup && childCount != null && childCount > 0 && (
        <span className="oc-tree-child-count" title={`${childCount} 个子节点`}>
          ({childCount})
        </span>
      )}
      {hasError && <span className="oc-tree-error">加载失败</span>}
      {!node.isGroup && <StatusChip status={node.status} />}
    </div>
  )
}

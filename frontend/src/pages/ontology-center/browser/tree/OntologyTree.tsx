import { useEffect, useMemo, useRef, useState } from 'react'
import type { OntologyTreeNode } from './OntologyTreeNode'
import { TreeNodeRow } from './TreeNodeRow'

type OntologyTreeProps = {
  roots: OntologyTreeNode[]
  /** 子节点数据源（由 ontologyApi.getTreeChildren 注入，树框架不直接调 API） */
  getChildren: (node: OntologyTreeNode, signal?: AbortSignal) => Promise<OntologyTreeNode[]>
  /** 非分类根节点的选中回调；entity root 点击 = 切换展开，不触发 onSelect */
  onSelect: (node: OntologyTreeNode) => void
  /** 选中态受控（父组件持有，关系栏导航可反向驱动树高亮） */
  selectedId: string | null
  /** 默认展开（缺省 = 全部根节点） */
  initialExpandedIds?: string[]
  /**
   * 级联自动展开的粒度层级（如 whole_brain/macro/clinical）：
   * 子节点加载完成后，落在集合内的节点自动展开并继续级联加载；
   * 集合外（如 meso）保持折叠，由用户手动展开。
   */
  autoExpandLevels?: readonly string[]
  /**
   * meso 小分支自动展开集合（children 1..10 且全部 subregion/fine）：
   * 与 autoExpandLevels 并列的自动展开条件（研究地图，见 ontologyApi.getRegionResearchView）。
   */
  mesoAutoExpandIds?: ReadonlySet<string>
  /** 预加载子节点（自动展开的 meso 免发 /children 请求）；键 = 节点 id */
  preloadedChildren?: Readonly<Record<string, OntologyTreeNode[]>>
  /** 折叠节点的已知子计数（行徽章 (n)）；已加载节点用缓存长度 */
  childCountById?: Readonly<Record<string, number>>
  /** 「展开到研究层级」按钮目标（含 subregion/fine 子节点的 meso 节点）；空 → 隐藏按钮 */
  researchExpandIds?: readonly string[]
  /** 研究目标的祖先 id 并集（按钮穿越折叠祖先链用，如临床级祖先不在级联中） */
  researchAncestorIds?: readonly string[]
}

type FlatRow = { node: OntologyTreeNode; depth: number }

/** 研究地图异步到达后的父链展开轮询间隔/超时 */
const CHAIN_POLL_INTERVAL_MS = 30
const CHAIN_WAIT_TIMEOUT_MS = 5000

/**
 * 通用本体树容器：扁平行渲染（DFS 派生 visibleRows，行组件只拿 depth）。
 * 状态：expandedIds / childrenCache / loadingIds / errorIds；
 * 懒加载：首次展开时拉取并缓存，收起再展开不发第二次请求；
 * hasChildren=false → 无 chevron（叶子）；undefined → 展开时探测；
 * 缓存为空数组 → chevron 消失；失败 → 行内「加载失败」，再次展开重试。
 *
 * 展开策略（2026-08-21 修订）：
 * - autoExpandLevels（whole_brain/macro/clinical）级联自动展开；
 * - mesoAutoExpandIds（小规模 subregion/fine 分支，如 Hippocampal formation）自动展开，
 *   大规模分支（children > 10，如 BNA/HCP）保持折叠，由按钮或手动展开；
 * - fine 节点按叶子展示（无 chevron）；
 * - 行徽章显示已知子计数（已加载 → 缓存长度；折叠 → childCountById）。
 */
export function OntologyTree({
  roots,
  getChildren,
  onSelect,
  selectedId,
  initialExpandedIds,
  autoExpandLevels,
  mesoAutoExpandIds,
  preloadedChildren,
  childCountById,
  researchExpandIds,
  researchAncestorIds,
}: OntologyTreeProps) {
  const [expandedIds, setExpandedIds] = useState<Set<string>>(
    () => new Set(initialExpandedIds ?? roots.map(r => r.id)),
  )
  const [childrenCache, setChildrenCache] = useState<Map<string, OntologyTreeNode[]>>(new Map())
  const [loadingIds, setLoadingIds] = useState<Set<string>>(new Set())
  const [errorIds, setErrorIds] = useState<Set<string>>(new Set())

  // ref 镜像：事件处理器/异步级联内同步读写，防止快速连点时的重复拉取/竞态
  const cacheRef = useRef(childrenCache)
  const loadingRef = useRef(loadingIds)
  const expandedRef = useRef(expandedIds)
  // 节点索引（id → 节点）：研究地图补触发与「展开到研究层级」扫描用
  const nodeIndexRef = useRef<Map<string, OntologyTreeNode>>(new Map())

  /** 子节点自动展开判定：级联层级 ∪ meso 小分支集合 */
  const shouldAutoExpand = (child: OntologyTreeNode) =>
    (child.granularityLevel != null && (autoExpandLevels?.includes(child.granularityLevel) ?? false)) ||
    (mesoAutoExpandIds?.has(child.id) ?? false)

  /** 子节点入缓存（记录节点索引），随后级联自动展开 */
  const seedCache = (nodeId: string, children: OntologyTreeNode[]) => {
    cacheRef.current = new Map(cacheRef.current).set(nodeId, children)
    setChildrenCache(cacheRef.current)
    for (const child of children) {
      nodeIndexRef.current.set(child.id, child)
    }
    for (const child of children) {
      if (shouldAutoExpand(child)) expandAndLoad(child)
    }
  }

  /** 展开 + 懒加载（级联与 toggle 共用；不重复展开已展开节点） */
  const expandAndLoad = (node: OntologyTreeNode) => {
    if (expandedRef.current.has(node.id)) return
    expandedRef.current = new Set(expandedRef.current).add(node.id)
    setExpandedIds(expandedRef.current)
    loadChildren(node)
  }

  const loadChildren = (node: OntologyTreeNode) => {
    if (node.hasChildren === false) return
    if (cacheRef.current.has(node.id) || loadingRef.current.has(node.id)) return
    // 内联子节点（虚拟分组等）：直接入缓存，不发请求
    if (node.children) {
      seedCache(node.id, node.children)
      return
    }
    // 预加载子节点（研究地图自动展开的 meso）：直接入缓存，免一次 /children 请求
    const preloaded = preloadedChildren?.[node.id]
    if (preloaded) {
      seedCache(node.id, preloaded)
      return
    }
    const nextLoading = new Set(loadingRef.current).add(node.id)
    loadingRef.current = nextLoading
    setLoadingIds(nextLoading)
    getChildren(node)
      .then(children => {
        seedCache(node.id, children)
      })
      .catch(() => {
        setErrorIds(prev => new Set(prev).add(node.id))
      })
      .finally(() => {
        const done = new Set(loadingRef.current)
        done.delete(node.id)
        loadingRef.current = done
        setLoadingIds(done)
      })
  }

  const toggle = (node: OntologyTreeNode) => {
    if (expandedRef.current.has(node.id)) {
      const next = new Set(expandedRef.current)
      next.delete(node.id)
      expandedRef.current = next
      setExpandedIds(next)
      return
    }
    if (errorIds.has(node.id)) {
      setErrorIds(prev => {
        const next = new Set(prev)
        next.delete(node.id)
        return next
      })
    }
    expandAndLoad(node)
  }

  const handleSelect = (node: OntologyTreeNode) => {
    if (node.isEntityRoot || node.isGroup) {
      toggle(node)
      return
    }
    onSelect(node)
  }

  // 默认展开的节点在 mount 时自动懒加载（缺省 = 全部根节点）
  useEffect(() => {
    for (const root of roots) nodeIndexRef.current.set(root.id, root)
    for (const root of roots) {
      if (expandedIds.has(root.id)) loadChildren(root)
    }
    // 仅挂载时执行一次，使用初始 roots/expandedIds 快照
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 研究地图到达或缓存增长后：补触发已缓存子节点中的 meso 自动展开（expandAndLoad 幂等）。
  // 两个到达顺序都覆盖：地图晚于级联（地图 deps 触发）；地图早于级联完成
  // （级联旧闭包错过 → 缓存更新时重扫，新闭包补上）。
  useEffect(() => {
    if (!mesoAutoExpandIds || mesoAutoExpandIds.size === 0) return
    for (const children of cacheRef.current.values()) {
      for (const child of children) {
        if (mesoAutoExpandIds.has(child.id)) expandAndLoad(child)
      }
    }
  }, [mesoAutoExpandIds, childrenCache])

  /** 轮询等待某节点子数据入缓存（失败/超时则放弃该链） */
  const waitForChildren = async (nodeId: string) => {
    const start = Date.now()
    while (Date.now() - start < CHAIN_WAIT_TIMEOUT_MS) {
      if (cacheRef.current.has(nodeId)) return
      await new Promise(resolve => setTimeout(resolve, CHAIN_POLL_INTERVAL_MS))
    }
  }

  /**
   * 「展开到研究层级」：迭代扫描展开——每轮展开「级联层级 ∪ 研究目标 ∪ 研究目标祖先链」
   * 中已索引的折叠节点（祖先链由研究地图一次性构建，如 clinical 级祖先不在级联中，
   * 也必须展开才能到达 meso 目标；展开暴露新节点后下一轮继续，最多 20 轮防死循环）。
   * 只展开 subregion/fine 分支：cyto/molecular 不在目标集合也不在级联层级，不受影响；
   * 祖先链上的折叠节点逐层展开各发 1 次懒加载请求，不探测无关分支。
   */
  const expandToResearch = async () => {
    if (!researchExpandIds || researchExpandIds.length === 0) return
    const researchSet = new Set(researchExpandIds)
    const ancestorSet = new Set(researchAncestorIds ?? [])
    for (let round = 0; round < 20; round++) {
      let progressed = false
      for (const node of nodeIndexRef.current.values()) {
        if (expandedRef.current.has(node.id)) continue
        const inCascade =
          node.granularityLevel != null && (autoExpandLevels?.includes(node.granularityLevel) ?? false)
        if (!inCascade && !researchSet.has(node.id) && !ancestorSet.has(node.id)) continue
        expandAndLoad(node)
        await waitForChildren(node.id)
        progressed = true
      }
      if (!progressed) break
    }
  }

  const visibleRows = useMemo<FlatRow[]>(() => {
    const rows: FlatRow[] = []
    const walk = (nodes: OntologyTreeNode[], depth: number) => {
      for (const node of nodes) {
        rows.push({ node, depth })
        if (expandedIds.has(node.id)) {
          const children = childrenCache.get(node.id) ?? node.children
          if (children && children.length > 0) walk(children, depth + 1)
        }
      }
    }
    walk(roots, 0)
    return rows
  }, [expandedIds, childrenCache, roots])

  return (
    <div className="oc-tree-root" role="tree">
      {researchExpandIds && researchExpandIds.length > 0 && (
        <div className="oc-tree-toolbar">
          <button type="button" className="oc-tree-expand-research" onClick={expandToResearch}>
            展开到研究层级
          </button>
        </div>
      )}
      {visibleRows.map(({ node, depth }) => {
        const cached = childrenCache.get(node.id)
        const discoveredLeaf = cached !== undefined && cached.length === 0
        // fine 节点按叶子展示（无 chevron、不探测子节点）
        const showChevron = node.granularityLevel !== 'fine' && node.hasChildren !== false && !discoveredLeaf
        const childCount = node.isGroup
          ? undefined
          : cached
            ? cached.length
            : childCountById?.[node.id]
        return (
          <TreeNodeRow
            key={node.id}
            node={node}
            depth={depth}
            isExpanded={expandedIds.has(node.id)}
            isSelected={selectedId === node.id}
            isLoading={loadingIds.has(node.id)}
            hasError={errorIds.has(node.id) && cached === undefined}
            showChevron={showChevron}
            childCount={childCount}
            onToggle={toggle}
            onSelect={handleSelect}
          />
        )
      })}
    </div>
  )
}

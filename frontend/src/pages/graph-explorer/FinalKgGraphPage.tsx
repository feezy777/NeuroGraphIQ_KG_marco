/**
 * Canonical KG Explorer 页面（Phase 3；V2 知识图谱改造）：
 * 顶部知识图谱导航栏 + 三栏布局 — 左侧探索控制面板 + 中间画布（自适应）+ 右侧实体详情面板。
 * 画布下方为 Path Explorer（Beta，后端无路径端点 → 诚实空态）。
 * 画布位置由 dagre 确定性布局计算（layout/dagreLayout），无随机布局。
 * 页面持有选中节点 id，组装 GraphLoadParams（filters → 后端查询参数）。
 *
 * URL hash 状态同步（V2）：
 * 数据源 / 粒度 / 实体类型 / 关系分组 编码为 `view=canonical&src=&gran=&types=&groups=`
 * （与 GraphExplorerPage 的 view 参数共存；replaceState 防 hashchange 循环）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { listRegionCandidates } from '../../api/endpoints'
import { buildHashUrl, readHashQueryParams } from '../../utils/pipelineNavigation'
import { FinalKgGraphCanvas } from './FinalKgGraphCanvas'
import { FinalKgGraphFilterBar } from './FinalKgGraphFilterBar'
import { FinalKgInspector } from './FinalKgInspector'
import { FinalKgGraphSidebar, type GraphFilters } from './FinalKgGraphSidebar'
import { expandRequestForNode } from './adapters/finalKgAdapter'
import { expandRequestForMirrorNode } from './adapters/mirrorKgAdapter'
import { emptyDisplayFilters, filterCanonicalGraph, type DisplayFilters } from './graphFilter'
import { useGraphData, type GraphLoadParams } from './useGraphData'
import { KgPathExplorer, type KgPathExploreOutcome, type KgPathStep } from './KgPathExplorer'
import type { CanonicalNodeType } from './adapters/finalKgAdapter'
import '@xyflow/react/dist/style.css'
import './FinalKgGraphPage.css'

// ── URL hash 状态序列化（graph-explorer 页面子状态，与 view 参数共存） ───────────

const EMPTY_ENTITY_TYPES: CanonicalNodeType[] = []

function hashTypes(value: string): CanonicalNodeType[] {
  if (!value) return EMPTY_ENTITY_TYPES
  const allowed: CanonicalNodeType[] = ['brain_region', 'connection', 'circuit', 'circuit_step', 'function', 'evidence']
  return value.split(',').filter((v): v is CanonicalNodeType => (allowed as string[]).includes(v))
}

/** 读取 hash 初始化展示过滤（空集合 = 全部可见语义） */
function displayFiltersFromHash(): DisplayFilters {
  const q = readHashQueryParams()
  const types = hashTypes(q.types ?? '')
  const groups = (q.groups ?? '').split(',').filter(Boolean)
  return {
    entityTypes: new Set(types),
    granularity: q.gran ?? '',
    relationGroups: new Set(groups),
  }
}

/** 只需记录非默认值的序列化（默认：无类型/分组过滤、粒度全部） */
function hashOfDisplayFilters(filters: DisplayFilters, dataSource: string): string {
  const q: Record<string, string> = { view: 'canonical', src: dataSource }
  if (filters.granularity) q.gran = filters.granularity
  if (filters.entityTypes.size > 0) q.types = [...filters.entityTypes].join(',')
  if (filters.relationGroups.size > 0) q.groups = [...filters.relationGroups].join(',')
  return buildHashUrl('/graph-explorer', q)
}

export function FinalKgGraphPage() {
  const [filters, setFilters] = useState<GraphFilters>({
    atlas: '',
    granularity: '',
    includeFunctions: true,
    includeEvidence: false,
  })
  const [displayFilters, setDisplayFilters] = useState<DisplayFilters>(displayFiltersFromHash)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null)
  const [initialEntityError, setInitialEntityError] = useState<string | null>(null)
  const { graph, loading, error, fitKey, dataSource, setDataSource, loadGraph, expandGraph } = useGraphData()
  const dataSourceRef = useRef(dataSource)
  dataSourceRef.current = dataSource

  // 顶部粒度/左侧过滤只滤画布展示（不修改数据、不发请求）
  const visibleGraph = useMemo(() => filterCanonicalGraph(graph, displayFilters), [graph, displayFilters])

  // 图内诚实统计（非 mock）：证据节点数 / 各类型计数
  const evidenceCount = useMemo(
    () => graph.nodes.filter(n => n.type === 'evidence').length,
    [graph],
  )
  const entityCounts = useMemo(() => {
    const counts = {
      brain_region: 0,
      connection: 0,
      circuit: 0,
      circuit_step: 0,
      function: 0,
      evidence: 0,
    } satisfies Record<CanonicalNodeType, number>
    for (const n of graph.nodes) {
      counts[n.type] += 1
    }
    return counts
  }, [graph])

  /** 组装图请求：filters → 后端查询参数 */
  const buildParams = useCallback(
    (centerType: string, centerId: string): GraphLoadParams => ({
      center_type: centerType,
      center_id: centerId,
      depth: 1,
      source_atlas: filters.atlas || undefined,
      granularity_level: filters.granularity || undefined,
      include_functions: filters.includeFunctions,
      include_evidence: filters.includeEvidence,
      include_triples: true,
      limit: 200,
    }),
    [filters],
  )

  const handleLoadCenter = useCallback(
    (centerType: string, centerId: string) => {
      loadGraph(buildParams(centerType, centerId))
    },
    [loadGraph, buildParams],
  )

  // ── hash 同步（debounce 300ms；replaceState 防 hashchange 循环） ─────────────
  const displayFiltersRef = useRef(displayFilters)
  displayFiltersRef.current = displayFilters

  const syncHash = useCallback((immediate = false) => {
    const url = hashOfDisplayFilters(displayFiltersRef.current, dataSourceRef.current)
    if (window.location.hash === url) return
    if (immediate) {
      history.replaceState(null, '', url)
      return
    }
    setTimeout(() => {
      if (window.location.hash !== url) history.replaceState(null, '', url)
    }, 300)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    syncHash()
  }, [syncHash, displayFilters, dataSource])

  const handleSaveView = useCallback(() => {
    syncHash(true)
  }, [syncHash])

  // Phase 8 方向 1：URL entity 参数（canonical 脑区 id，来自本体中心「Open in Graph」）
  // 挂载时消费一次：解析候选 → 以 region 为中心加载 → 从 URL 移除（避免覆盖后续手动加载）
  useEffect(() => {
    const entityId = readHashQueryParams().entity
    if (!entityId) return
    let cancelled = false
    ;(async () => {
      try {
        const candidates = await listRegionCandidates(entityId)
        if (cancelled) return
        const candidateId = candidates.find(c => c.candidate_id)?.candidate_id
        if (!candidateId) {
          setInitialEntityError('该本体脑区暂无对齐候选（candidate），无法在图谱中定位')
          return
        }
        await loadGraph(buildParams('region', candidateId))
      } catch {
        if (!cancelled) setInitialEntityError('本体脑区定位失败（候选解析接口不可用）')
      } finally {
        if (!cancelled) {
          window.location.hash = buildHashUrl('/graph-explorer', { view: 'canonical' })
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadGraph, buildParams])

  // 增量展开：以节点为中心拉取子图并合并进已有图（禁止清空；mergeCanonicalGraphs 按 id 去重）
  // mirror 模式仅 brain_region（candidate）可展开；final 模式沿用后端 center_type 映射
  const handleExpandNode = useCallback(
    (nodeId: string) => {
      const node = graph.nodes.find(n => n.id === nodeId)
      if (!node) return
      if (dataSource === 'mirror') {
        const request = expandRequestForMirrorNode(node)
        if (!request) return
        expandGraph(buildParams('region', request.candidate_id))
        return
      }
      const request = expandRequestForNode(node)
      if (!request) return
      expandGraph(buildParams(request.center_type, request.center_id))
    },
    [graph.nodes, dataSource, expandGraph, buildParams],
  )

  const selectedNode = selectedNodeId ? (graph.nodes.find(n => n.id === selectedNodeId) ?? null) : null
  const selectedEdge = selectedEdgeId ? (graph.edges.find(e => e.id === selectedEdgeId) ?? null) : null

  /** 节点/边互斥选择：选节点清边，选边清节点 */
  const handleNodeClick = useCallback((nodeId: string | null) => {
    setSelectedNodeId(nodeId)
    if (nodeId) setSelectedEdgeId(null)
  }, [])
  const handleEdgeSelect = useCallback((edgeId: string | null) => {
    setSelectedEdgeId(edgeId)
    if (edgeId) setSelectedNodeId(null)
  }, [])

  // Path Explorer：后端暂无路径查询端点 → 返回诚实空态（设计组件接口，不伪造数据）
  const centerNode = graph.centerNodeId ? graph.nodes.find(n => n.id === graph.centerNodeId) ?? null : null
  const handlePathExplore = useCallback(async (from: string, to: string): Promise<KgPathExploreOutcome> => {
    // TODO(backend): 接入图谱路径查询端点后映射为 KgPathStep[]
    void from
    void to
    return { path: null, reason: '后端暂无图谱路径查询端点（服务端发现最短知识路径后将按 KgPathStep 模型接入）' }
  }, [])

  return (
    <div className="graph-explorer-page">
      <ReactFlowProvider>
        <FinalKgGraphSidebar
          dataSource={dataSource}
          onDataSourceChange={setDataSource}
          filters={filters}
          onFiltersChange={setFilters}
          onLoadCenter={handleLoadCenter}
          loading={loading}
          nodeCount={graph.nodes.length}
          edgeCount={graph.edges.length}
          evidenceCount={evidenceCount}
          warnings={graph.warnings}
          displayFilters={displayFilters}
          onDisplayFiltersChange={setDisplayFilters}
          entityCounts={entityCounts}
        />
        <div className="cg-center">
          <FinalKgGraphFilterBar
            filters={displayFilters}
            onFiltersChange={setDisplayFilters}
            dataSource={dataSource}
            onSaveView={handleSaveView}
          />
          <FinalKgGraphCanvas
            graph={visibleGraph}
            loading={loading}
            error={error ?? initialEntityError}
            fitKey={fitKey}
            selectedNodeId={selectedNodeId}
            dataSource={dataSource}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeSelect}
            onExpandNode={handleExpandNode}
          />
          <KgPathExplorer onExplore={handlePathExplore} currentCenterLabel={centerNode?.label ?? null} />
        </div>
        <FinalKgInspector
          node={selectedNode}
          edge={selectedEdge}
          graph={graph}
          dataSource={dataSource}
          onNavigateNode={handleNodeClick}
        />
      </ReactFlowProvider>
    </div>
  )
}

// 保留类型导出（组件接口消费方需要）
export type { KgPathStep }

/**
 * Canonical KG Explorer 页面（Phase 3）：
 * 三栏布局 — 左侧 240px 控制面板 + 中间画布（自适应）+ 右侧 360px Inspector。
 * 画布位置由 dagre 确定性布局计算（layout/dagreLayout），无随机布局。
 * 页面持有选中节点 id，组装 GraphLoadParams（filters → 后端查询参数）。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
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
import '@xyflow/react/dist/style.css'
import './FinalKgGraphPage.css'

export function FinalKgGraphPage() {
  const [filters, setFilters] = useState<GraphFilters>({
    atlas: '',
    granularity: '',
    includeFunctions: true,
    includeEvidence: false,
  })
  const [displayFilters, setDisplayFilters] = useState<DisplayFilters>(emptyDisplayFilters)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [initialEntityError, setInitialEntityError] = useState<string | null>(null)
  const { graph, loading, error, fitKey, dataSource, setDataSource, loadGraph, expandGraph } = useGraphData()

  // 顶部过滤条只过滤画布展示（不修改数据、不发请求）
  const visibleGraph = useMemo(() => filterCanonicalGraph(graph, displayFilters), [graph, displayFilters])

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
          warnings={graph.warnings}
        />
        <div className="cg-center">
          <FinalKgGraphFilterBar filters={displayFilters} onFiltersChange={setDisplayFilters} />
          <FinalKgGraphCanvas
            graph={visibleGraph}
            loading={loading}
            error={error ?? initialEntityError}
            fitKey={fitKey}
            selectedNodeId={selectedNodeId}
            dataSource={dataSource}
            onNodeClick={setSelectedNodeId}
            onExpandNode={handleExpandNode}
          />
        </div>
        <FinalKgInspector node={selectedNode} graph={graph} onNavigateNode={setSelectedNodeId} />
      </ReactFlowProvider>
    </div>
  )
}

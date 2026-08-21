/**
 * Canonical KG 图数据 hook（双数据源）：
 * - final  ：final_macro_clinical browser 图 API → finalKgAdapter
 * - mirror ：以 candidate 为中心的镜像对象（connections/functions/circuits）
 *            → mirrorKgAdapter（先用镜像库数据，晋升后再用 final 数据）
 * 布局位置由 layout/dagreLayout 确定（确定性，无随机）。
 *
 * Phase 6：
 * - loadGraph 以新中心替换加载（左侧手动加载 / 搜索入口）
 * - expandGraph 增量展开：拉取子图后合并进已有图（禁止清空）
 */
import { useCallback, useRef, useState } from 'react'
import {
  getCandidateRegion,
  getFinalGraph,
  listMirrorCircuits,
  listMirrorConnections,
  listMirrorFunctions,
} from '../../api/endpoints'
import {
  adaptFinalGraphResponse,
  mergeCanonicalGraphs,
  type CanonicalGraph,
} from './adapters/finalKgAdapter'
import { adaptMirrorGraphResponse } from './adapters/mirrorKgAdapter'

export interface GraphLoadParams {
  center_type: string
  center_id: string
  depth?: number
  source_atlas?: string
  granularity_level?: string
  include_functions?: boolean
  include_evidence?: boolean
  include_triples?: boolean
  limit?: number
}

/** 图数据源：mirror（当前有数据） / final（晋升后使用） */
export type GraphDataSource = 'mirror' | 'final'

const EMPTY_GRAPH: CanonicalGraph = { nodes: [], edges: [], centerNodeId: null, warnings: [] }

export interface GraphDataState {
  graph: CanonicalGraph
  loading: boolean
  error: string | null
  /** 每次成功加载/展开 +1，Canvas 据此 fitView */
  fitKey: number
  dataSource: GraphDataSource
  setDataSource: (source: GraphDataSource) => void
  loadGraph: (params: GraphLoadParams) => Promise<void>
  expandGraph: (params: GraphLoadParams) => Promise<void>
}

/** 组装 final 图请求并拉取 Canonical 图 */
async function fetchFinalGraph(params: GraphLoadParams): Promise<CanonicalGraph> {
  const res = await getFinalGraph({
    center_type: params.center_type,
    center_id: params.center_id,
    depth: params.depth ?? 1,
    source_atlas: params.source_atlas || undefined,
    granularity_level: params.granularity_level || undefined,
    include_functions: params.include_functions ?? true,
    include_evidence: params.include_evidence ?? false,
    include_triples: params.include_triples ?? true,
    limit: params.limit ?? 200,
  })
  return adaptFinalGraphResponse(res)
}

/**
 * 镜像单类对象单次拉取上限（防大图卡顿）：
 * hub 型候选可达数百连接 + 数百回路，全量拉取后布局/渲染会冻结主线程。
 * 超出部分由后端按 limit 截断，前端在 warnings 中提示截断数量。
 */
export const MIRROR_FETCH_LIMIT = 300

/**
 * 以 candidate 为中心拉取镜像图：
 * 连接（源/目标任一 = candidate）+ 功能 + 回路（成员关系）→ mirrorKgAdapter。
 * 每类对象最多拉取 MIRROR_FETCH_LIMIT 条（截断时附警告）。
 */
export async function fetchMirrorGraph(
  candidateId: string,
  params: GraphLoadParams,
): Promise<CanonicalGraph> {
  const [center, connRes, fnRes, circuitRes] = await Promise.all([
    getCandidateRegion(candidateId),
    listMirrorConnections({
      candidate_id: candidateId,
      source_atlas: params.source_atlas || undefined,
      granularity_level: params.granularity_level || undefined,
      limit: MIRROR_FETCH_LIMIT,
    }),
    params.include_functions === false
      ? Promise.resolve({ items: [], total: 0 })
      : listMirrorFunctions({
          candidate_id: candidateId,
          source_atlas: params.source_atlas || undefined,
          granularity_level: params.granularity_level || undefined,
          limit: MIRROR_FETCH_LIMIT,
        }),
    listMirrorCircuits({
      candidate_id: candidateId,
      source_atlas: params.source_atlas || undefined,
      granularity_level: params.granularity_level || undefined,
      limit: MIRROR_FETCH_LIMIT,
    }),
  ])
  const graph = adaptMirrorGraphResponse({
    center,
    connections: connRes.items ?? [],
    functions: fnRes.items ?? [],
    circuits: circuitRes.items ?? [],
  })

  // 截断警告：total > 实际返回条数 → 后端按 limit 截断（防大图卡顿的护栏）
  const truncationWarnings: string[] = []
  if ((connRes.total ?? 0) > (connRes.items ?? []).length) {
    truncationWarnings.push(`连接仅显示前 ${MIRROR_FETCH_LIMIT} 条（共 ${connRes.total} 条，防大图卡顿截断）`)
  }
  if ((fnRes.total ?? 0) > (fnRes.items ?? []).length) {
    truncationWarnings.push(`功能仅显示前 ${MIRROR_FETCH_LIMIT} 条（共 ${fnRes.total} 条，防大图卡顿截断）`)
  }
  if ((circuitRes.total ?? 0) > (circuitRes.items ?? []).length) {
    truncationWarnings.push(`回路仅显示前 ${MIRROR_FETCH_LIMIT} 条（共 ${circuitRes.total} 条，防大图卡顿截断）`)
  }

  return { ...graph, warnings: [...truncationWarnings, ...graph.warnings] }
}

export function useGraphData(): GraphDataState {
  const [graph, setGraph] = useState<CanonicalGraph>(EMPTY_GRAPH)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fitKey, setFitKey] = useState(0)
  const [dataSource, setDataSourceState] = useState<GraphDataSource>('mirror')
  const sourceRef = useRef<GraphDataSource>('mirror')

  /** 切换数据源：清空当前图（新旧源的 id 空间不同，禁止混用） */
  const setDataSource = useCallback((source: GraphDataSource) => {
    if (sourceRef.current === source) return
    sourceRef.current = source
    setDataSourceState(source)
    setGraph(EMPTY_GRAPH)
    setError(null)
  }, [])

  const fetchGraph = useCallback(
    (params: GraphLoadParams): Promise<CanonicalGraph> => {
      if (sourceRef.current === 'mirror') return fetchMirrorGraph(params.center_id, params)
      return fetchFinalGraph(params)
    },
    [],
  )

  /** 以新中心替换加载（清空旧图） */
  const loadGraph = useCallback(
    async (params: GraphLoadParams) => {
      setLoading(true)
      setError(null)
      try {
        setGraph(await fetchGraph(params))
        setFitKey(k => k + 1)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to load graph')
      } finally {
        setLoading(false)
      }
    },
    [fetchGraph],
  )

  /** 增量展开：合并进已有图（禁止清空；已存在节点保留原数据，中心锚点不变） */
  const expandGraph = useCallback(
    async (params: GraphLoadParams) => {
      setLoading(true)
      setError(null)
      try {
        const incoming = await fetchGraph(params)
        setGraph(prev => mergeCanonicalGraphs(prev, incoming))
        setFitKey(k => k + 1)
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : 'Failed to expand graph')
      } finally {
        setLoading(false)
      }
    },
    [fetchGraph],
  )

  return { graph, loading, error, fitKey, dataSource, setDataSource, loadGraph, expandGraph }
}

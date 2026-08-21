import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api/endpoints', () => ({
  getCandidateRegion: vi.fn(),
  getFinalGraph: vi.fn(),
  listMirrorCircuits: vi.fn(),
  listMirrorConnections: vi.fn(),
  listMirrorFunctions: vi.fn(),
}))

import {
  getCandidateRegion,
  listMirrorCircuits,
  listMirrorConnections,
  listMirrorFunctions,
} from '../../api/endpoints'
import { fetchMirrorGraph, MIRROR_FETCH_LIMIT } from './useGraphData'

const CENTER = {
  id: 'cand-1',
  en_name: 'Hippocampus',
  std_name: null,
  cn_name: null,
  raw_name: null,
  candidate_status: 'valid',
  granularity_level: 'macro',
}

/** 最小可用镜像连接（两端点候选齐全，适配器不产生悬空警告） */
function mockConnection() {
  return {
    id: 'conn-1',
    canonical_id: null,
    source_region_candidate_id: 'cand-1',
    target_region_candidate_id: 'cand-2',
    source_region_name_en: 'Hippocampus',
    source_region_name_cn: null,
    target_region_name_en: 'Entorhinal',
    target_region_name_cn: null,
    connection_type: 'structural_connection',
    granularity_level: 'macro',
    confidence: 0.7,
    source_atlas: 'AAL3',
    granularity_family: 'macro_clinical',
    mirror_status: 'llm_suggested',
    review_status: 'pending',
  }
}

const LOAD_PARAMS = { center_type: 'region', center_id: 'cand-1' }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(getCandidateRegion).mockResolvedValue(CENTER as never)
  vi.mocked(listMirrorConnections).mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(listMirrorFunctions).mockResolvedValue({ items: [], total: 0 } as never)
  vi.mocked(listMirrorCircuits).mockResolvedValue({ items: [], total: 0 } as never)
})

describe('fetchMirrorGraph（镜像拉取限量 + 截断警告）', () => {
  it('每类镜像对象按 MIRROR_FETCH_LIMIT 限量拉取', async () => {
    await fetchMirrorGraph('cand-1', LOAD_PARAMS)
    expect(listMirrorConnections).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: 'cand-1', limit: MIRROR_FETCH_LIMIT }),
    )
    expect(listMirrorFunctions).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: 'cand-1', limit: MIRROR_FETCH_LIMIT }),
    )
    expect(listMirrorCircuits).toHaveBeenCalledWith(
      expect.objectContaining({ candidate_id: 'cand-1', limit: MIRROR_FETCH_LIMIT }),
    )
  })

  it('total 超过返回条数时按类型附截断警告', async () => {
    vi.mocked(listMirrorConnections).mockResolvedValue({
      items: [mockConnection()],
      total: MIRROR_FETCH_LIMIT + 20,
    } as never)
    vi.mocked(listMirrorCircuits).mockResolvedValue({ items: [], total: MIRROR_FETCH_LIMIT + 5 } as never)

    const graph = await fetchMirrorGraph('cand-1', LOAD_PARAMS)
    expect(graph.warnings).toContain(
      `连接仅显示前 ${MIRROR_FETCH_LIMIT} 条（共 ${MIRROR_FETCH_LIMIT + 20} 条，防大图卡顿截断）`,
    )
    expect(graph.warnings).toContain(
      `回路仅显示前 ${MIRROR_FETCH_LIMIT} 条（共 ${MIRROR_FETCH_LIMIT + 5} 条，防大图卡顿截断）`,
    )
  })

  it('未超出限量时不产生截断警告', async () => {
    vi.mocked(listMirrorConnections).mockResolvedValue({ items: [mockConnection()], total: 1 } as never)

    const graph = await fetchMirrorGraph('cand-1', LOAD_PARAMS)
    expect(graph.warnings).toEqual([])
  })

  it('include_functions=false 时跳过功能查询', async () => {
    await fetchMirrorGraph('cand-1', { ...LOAD_PARAMS, include_functions: false })
    expect(listMirrorFunctions).not.toHaveBeenCalled()
  })
})

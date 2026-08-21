import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ontologyApi } from './ontologyApi'
import type { CanonicalConnection, CanonicalRegion } from './endpoints'

vi.mock('./endpoints', () => ({
  listCanonicalRegions: vi.fn(),
  listCanonicalRegionRoots: vi.fn(),
  listAtlasRegions: vi.fn(),
  listAtlasRegionMappings: vi.fn(),
  getCanonicalRegion: vi.fn(),
  getCanonicalRegionMultiscale: vi.fn(),
  getCanonicalRegionParent: vi.fn(),
  listCanonicalRegionAncestors: vi.fn(),
  listCanonicalRegionChildren: vi.fn(),
  listRegionCandidates: vi.fn(),
  listRegionConnections: vi.fn(),
  listRegionCircuits: vi.fn(),
  listRegionFunctions: vi.fn(),
  listCanonicalConnections: vi.fn(),
  getCanonicalConnection: vi.fn(),
  listCanonicalCircuits: vi.fn(),
  getCanonicalCircuit: vi.fn(),
  listCanonicalCircuitRegions: vi.fn(),
  listCanonicalCircuitConnections: vi.fn(),
  listCanonicalCircuitFunctions: vi.fn(),
  listOntologyTerms: vi.fn(),
  getOntologyTermDetail: vi.fn(),
  listTermHierarchyParents: vi.fn(),
  listTermHierarchyChildren: vi.fn(),
  listCellTypes: vi.fn(),
  listMolecularEntities: vi.fn(),
  listRegionCellAlignments: vi.fn(),
  listRegionMolecularAlignments: vi.fn(),
}))

import * as endpoints from './endpoints'
const ep = vi.mocked(endpoints)

// ─── fixtures ──────────────────────────────────────────────────────────

function makeRegion(id: string, name: string, granularityLevel = 'clinical'): CanonicalRegion {
  return {
    id,
    region_code: `ng:br:${id}`,
    canonical_name_en: name,
    canonical_name_cn: null,
    species: 'human',
    granularity_domain: 'macro_clinical',
    granularity_level: granularityLevel,
    hemisphere_policy: 'unilateral',
    status: 'active',
    description: null,
    confidence: 0.9,
    source_summary: {},
    external_mappings: {},
    created_by: 'seed',
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  }
}

const PT = makeRegion('pars_triangularis', 'Pars triangularis')
const PC = makeRegion('posterior_cingulate', 'Posterior cingulate')
const HIPPO = makeRegion('hippocampus', 'Hippocampus')

function makeConnection(overrides: Partial<CanonicalConnection> = {}): CanonicalConnection {
  return {
    id: 'c-1',
    connection_code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate',
    source_region_id: 'pars_triangularis',
    target_region_id: 'posterior_cingulate',
    connection_type: 'association',
    directionality_policy: 'bidirectional',
    species: 'human',
    granularity_level: 'clinical',
    status: 'proposed',
    confidence: 0.4,
    source_summary: {},
    evidence_summary: {},
    provenance_json: { mapping_method: 'macro96_canonical_connection_v1' },
    replaced_by_connection_id: null,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  ep.listCanonicalRegions.mockResolvedValue([PT, PC, HIPPO])
})

describe('ontologyApi 信息优先级适配（名称 > 关系结构 > code > provenance）', () => {
  describe('getTreeChildren：Connection 按 connection_type 分组', () => {
    it('groups by type in stable order, children use human-readable display names', async () => {
      ep.listCanonicalConnections.mockResolvedValue([
        makeConnection({ id: 'a', connection_type: 'association' }),
        makeConnection({ id: 'b', connection_type: 'structural', connection_code: 'ng:cn:structural_hippocampus_to_amygdala' }),
        makeConnection({ id: 'c', connection_type: 'uncertain', connection_code: 'ng:cn:uncertain_x_to_y' }),
      ])

      const nodes = await ontologyApi.getTreeChildren(
        { id: 'root:connection', code: null, name: 'Connection', entityType: 'connection', isEntityRoot: true },
      )

      // 稳定顺序：structural → association → uncertain；无空组
      expect(nodes.map(n => n.id)).toEqual([
        'group:connection:structural',
        'group:connection:association',
        'group:connection:uncertain',
      ])
      expect(nodes.every(n => n.isGroup)).toBe(true)
      expect(nodes.every(n => n.code === null)).toBe(true) // 分组行无 code

      // 子节点：显示名不再携带 ng:cn: 前缀与类型前缀
      const association = nodes.find(n => n.id === 'group:connection:association')
      expect(association?.children?.[0]).toMatchObject({
        code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate', // code 保留在 tooltip
        name: 'pars triangularis → posterior cingulate',
      })
      const structural = nodes.find(n => n.id === 'group:connection:structural')
      expect(structural?.children?.[0].name).toBe('hippocampus → amygdala')
    })
  })

  describe('getTreeChildren：Circuit 按 circuit_type 分组', () => {
    it('groups circuits with title-cased group names', async () => {
      ep.listCanonicalCircuits.mockResolvedValue([
        {
          id: 'ci-1', circuit_code: 'ng:ci:auditory', canonical_name_en: 'auditory_pathway',
          canonical_name_cn: null, species: 'human', granularity_level: 'clinical',
          circuit_type: 'network', status: 'proposed', description: null, confidence: 0.5,
          source_summary: {}, provenance_json: {}, replaced_by_circuit_id: null,
          created_by: null, created_at: '2026-08-01', updated_at: '2026-08-01',
        },
        {
          id: 'ci-2', circuit_code: 'ng:ci:loop', canonical_name_en: 'reward_loop',
          canonical_name_cn: null, species: 'human', granularity_level: 'clinical',
          circuit_type: 'functional_loop', status: 'proposed', description: null, confidence: 0.5,
          source_summary: {}, provenance_json: {}, replaced_by_circuit_id: null,
          created_by: null, created_at: '2026-08-01', updated_at: '2026-08-01',
        },
      ])

      const nodes = await ontologyApi.getTreeChildren(
        { id: 'root:circuit', code: null, name: 'Circuit', entityType: 'circuit', isEntityRoot: true },
      )

      expect(nodes.map(n => n.id)).toEqual(['group:circuit:network', 'group:circuit:functional_loop'])
      expect(nodes[0].name).toBe('Network') // functional_loop → "Functional loop"
      expect(nodes[1].name).toBe('Functional loop')
    })
  })

  describe('getTreeChildren：Region 树结构来自 canonical_region_hierarchy', () => {
    it('entity-root 子节点 = hierarchy 无父边根，不再按粒度拍平', async () => {
      ep.listCanonicalRegionRoots.mockResolvedValue([makeRegion('brain', 'Brain', 'whole_brain')])

      const nodes = await ontologyApi.getTreeChildren(
        { id: 'root:region', code: null, name: 'Brain Region', entityType: 'region', isEntityRoot: true },
        'meso',
      )

      expect(ep.listCanonicalRegionRoots).toHaveBeenCalled()
      expect(ep.listCanonicalRegions).not.toHaveBeenCalled() // 全量列表不再充当树顶层
      expect(nodes.map(n => n.name)).toEqual(['Brain'])
      expect(nodes[0].granularityLevel).toBe('whole_brain')
    })

    it('meso 透镜隐藏 fine 子节点 —— Meso 与 Fine 不显示在同一级', async () => {
      ep.listCanonicalRegionChildren.mockResolvedValue([
        makeRegion('hippocampal_formation', 'Hippocampal formation', 'meso'),
        makeRegion('ca1', 'CA1', 'fine'),
      ])
      const hippocampus = {
        id: 'r-hippocampus',
        code: 'ng:br:hippocampus',
        name: 'Hippocampus',
        entityType: 'region' as const,
        granularityLevel: 'clinical',
      }

      const underMeso = await ontologyApi.getTreeChildren(hippocampus, 'meso')
      expect(underMeso.map(n => n.name)).toEqual(['Hippocampal formation']) // fine 被透镜隐藏

      const underFine = await ontologyApi.getTreeChildren(hippocampus, 'fine')
      expect(underFine.map(n => n.name)).toEqual(['Hippocampal formation', 'CA1']) // 切到 fine 透镜后同现于其父节点下
    })
  })

  describe('getEntityDetail：Connection 类型化展示', () => {
    it('resolves type title and Source/Target names via bulk region map', async () => {
      ep.getCanonicalConnection.mockResolvedValue(makeConnection())

      const detail = await ontologyApi.getEntityDetail('connection', 'c-1')

      expect(detail.typeTitle).toBe('Association connection') // 主标题 = 类型标题
      expect(detail.name).toBe('ng:cn:association_pars_triangularis_to_posterior_cingulate') // code 保留在数据层
      expect(detail.source).toMatchObject({ id: 'pars_triangularis', name: 'Pars triangularis' })
      expect(detail.target).toMatchObject({ id: 'posterior_cingulate', name: 'Posterior cingulate' })
      // 批量解析：只发一次列表请求，不对 source/target 逐个 GET
      expect(ep.getCanonicalRegion).not.toHaveBeenCalled()
      expect(ep.listCanonicalRegions).toHaveBeenCalledTimes(1)
    })

    it('falls back to region id when the region map is unavailable', async () => {
      ep.getCanonicalConnection.mockResolvedValue(makeConnection())
      ep.listCanonicalRegions.mockRejectedValue(new Error('offline'))

      const detail = await ontologyApi.getEntityDetail('connection', 'c-1')

      expect(detail.source).toEqual({ id: 'pars_triangularis', code: null, name: 'pars_triangularis', entityType: 'region' })
      expect(detail.target).toEqual({ id: 'posterior_cingulate', code: null, name: 'posterior_cingulate', entityType: 'region' })
    })
  })

  describe('getEntityDetail：Function hierarchy 映射', () => {
    it('maps hierarchy edges to parent/children refs and degrades on failure', async () => {
      ep.getOntologyTermDetail.mockResolvedValue({
        term: {
          id: 't-1', term_code: 'ng:fn:somatosensory', canonical_term_en: 'Somatosensory processing',
          canonical_term_cn: null, term_type: 'function', category: null, domain: null,
          role: null, effect_type: null, description: null, status: 'proposed',
          created_by: 'seed', created_at: '2026-08-01', updated_at: '2026-08-01',
        },
        synonyms: [], external_mappings: [], references: { items: [], total: 0 }, change_logs: [],
      })
      ep.listTermHierarchyParents.mockResolvedValue({
        items: [{
          id: 'e-1',
          predicate: 'is_a',
          status: 'active',
          child: { term_id: 't-1', term_code: 'ng:fn:somatosensory', canonical_term_en: 'Somatosensory processing', canonical_term_cn: null, term_status: 'proposed' },
          parent: { term_id: 't-0', term_code: 'ng:fn:perception', canonical_term_en: 'Perception', canonical_term_cn: null, term_status: 'proposed' },
        }],
        total: 1,
      })
      ep.listTermHierarchyChildren.mockRejectedValue(new Error('offline'))

      const detail = await ontologyApi.getEntityDetail('function', 't-1')

      expect(detail.parent).toMatchObject({ id: 't-0', name: 'Perception', entityType: 'function' })
      expect(detail.children).toEqual([]) // 层级拉取失败 → 降级为空，不 blank 面板
    })
  })

  describe('getRelations：Region 连接卡片 "Source → Target"', () => {
    it('names outgoing connections Self → Endpoint and incoming Endpoint → Self', async () => {
      ep.getCanonicalRegionParent.mockResolvedValue(null)
      ep.listCanonicalRegionChildren.mockResolvedValue([])
      ep.listRegionCircuits.mockResolvedValue([])
      ep.listRegionFunctions.mockResolvedValue([])
      ep.listRegionCandidates.mockResolvedValue([])
      ep.listRegionConnections.mockResolvedValue([
        {
          connection_id: 'c-out', connection_code: 'ng:cn:hippo_to_pt', connection_type: 'structural',
          directionality_policy: 'unidirectional', status: 'proposed', confidence: 0.8,
          direction: 'outgoing', endpoint_region: { id: 'pars_triangularis', region_code: 'ng:br:pars_triangularis', canonical_name_en: 'Pars triangularis', canonical_name_cn: null, granularity_level: 'clinical' },
        },
        {
          connection_id: 'c-in', connection_code: 'ng:cn:pc_to_hippo', connection_type: 'functional',
          directionality_policy: 'unidirectional', status: 'proposed', confidence: 0.5,
          direction: 'incoming', endpoint_region: { id: 'posterior_cingulate', region_code: 'ng:br:posterior_cingulate', canonical_name_en: 'Posterior cingulate', canonical_name_cn: null, granularity_level: 'clinical' },
        },
      ])

      const groups = await ontologyApi.getRelations('region', 'hippocampus')
      const connections = groups.find(g => g.key === 'connections')

      expect(connections?.items[0].ref.name).toBe('Hippocampus → Pars triangularis')
      expect(connections?.items[0].meta).toContainEqual({ label: '方向', value: '出向' })
      expect(connections?.items[1].ref.name).toBe('Posterior cingulate → Hippocampus')
      expect(connections?.items[1].meta).toContainEqual({ label: '方向', value: '入向' })
    })
  })

  describe('getRelations：Region Atlas Mappings 组', () => {
    const ATLAS_MAPPING = {
      id: 'm-1',
      atlas_region_id: 'ar-1',
      canonical_region_id: 'hippocampus',
      mapping_type: 'exact_match',
      confidence: 0.9,
      species_relation: 'same_species',
      match_details: {},
      provenance: {},
      status: 'active',
      created_by: 'seed',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    }
    const ATLAS_REGION = {
      id: 'ar-1',
      atlas_resource_id: 'res-1',
      atlas_name: 'AAL3',
      atlas_version: 'v3',
      atlas_region_id: '4010',
      region_name: 'Hippocampus_L',
      region_acronym: 'HIP.L',
      parent_region_id: null,
      species: 'human',
      hemisphere: 'L',
      source_file: 'aal3.nii',
      status: 'active',
      created_at: '2026-08-01T00:00:00Z',
      updated_at: '2026-08-01T00:00:00Z',
    }
    const mockRegionBasics = () => {
      ep.getCanonicalRegionParent.mockResolvedValue(null)
      ep.listCanonicalRegionChildren.mockResolvedValue([])
      ep.listRegionCircuits.mockResolvedValue([])
      ep.listRegionFunctions.mockResolvedValue([])
      ep.listRegionCandidates.mockResolvedValue([])
      ep.listRegionConnections.mockResolvedValue([])
      ep.getCanonicalRegionMultiscale.mockResolvedValue({
        region: makeRegion('hippocampus', 'Hippocampus'),
        parents: [],
        children: [],
        meso_regions: [],
        subregions: [],
        fine_regions: [],
        cell_types: [],
        molecules: [],
      })
    }

    it('adds an Atlas Mappings group with 图谱 meta when mappings exist', async () => {
      mockRegionBasics()
      ep.listAtlasRegionMappings.mockResolvedValue([ATLAS_MAPPING])
      ep.listAtlasRegions.mockResolvedValue([ATLAS_REGION])

      const groups = await ontologyApi.getRelations('region', 'hippocampus')
      const atlas = groups.find(g => g.key === 'atlas')

      expect(atlas).toBeTruthy()
      expect(atlas?.items[0].ref.name).toBe('Hippocampus_L') // atlas 区域名，非映射 id
      expect(atlas?.items[0].meta).toContainEqual({ label: '图谱', value: 'AAL3' })
      expect(atlas?.items[0].meta).toContainEqual({ label: '映射类型', value: 'exact_match' })
      expect(ep.listAtlasRegions).toHaveBeenCalledTimes(1)
    })

    it('skips the atlas region table fetch when a region has no atlas mappings', async () => {
      mockRegionBasics()
      ep.listAtlasRegionMappings.mockResolvedValue([])

      const groups = await ontologyApi.getRelations('region', 'hippocampus')

      expect(groups.some(g => g.key === 'atlas')).toBe(false)
      expect(ep.listAtlasRegions).not.toHaveBeenCalled() // Allen mouse 1327 行：无映射不发大请求
    })
  })

  describe('getRelations：Connection → Source/Target 卡片', () => {
    it('exposes endpoint regions as navigable groups, circuits group honest-unavailable', async () => {
      ep.getCanonicalConnection.mockResolvedValue(makeConnection())

      const groups = await ontologyApi.getRelations('connection', 'c-1')

      expect(groups.map(g => g.key)).toEqual(['source', 'target', 'circuits'])
      expect(groups[0].items[0].ref).toMatchObject({ id: 'pars_triangularis', name: 'Pars triangularis', entityType: 'region' })
      expect(groups[1].items[0].ref).toMatchObject({ id: 'posterior_cingulate', name: 'Posterior cingulate', entityType: 'region' })
      expect(groups[2].unavailable).toBe(true) // 后端暂无反向 API → 不展示假数据
    })
  })

  describe('getRelations：Circuit 连接卡片 "Source → Target"', () => {
    it('resolves connection endpoints through the region map', async () => {
      ep.listCanonicalCircuitRegions.mockResolvedValue([])
      ep.listCanonicalCircuitFunctions.mockResolvedValue([])
      ep.listCanonicalCircuitConnections.mockResolvedValue([
        { id: 'l-1', circuit_id: 'ci-1', connection_id: 'c-1', role: 'primary', confidence: 0.7, provenance_json: {}, created_at: '2026-08-01' },
      ])
      ep.getCanonicalConnection.mockResolvedValue(makeConnection())

      const groups = await ontologyApi.getRelations('circuit', 'ci-1')
      const connections = groups.find(g => g.key === 'connections')

      expect(connections?.items[0].ref).toMatchObject({
        id: 'c-1',
        code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate',
        name: 'Pars triangularis → Posterior cingulate',
        entityType: 'connection',
      })
    })
  })

  describe('getRelations：Function 诚实空状态', () => {
    it('returns unavailable groups without fabricating data', async () => {
      const groups = await ontologyApi.getRelations('function', 't-1')

      expect(groups.map(g => g.key)).toEqual(['circuits', 'regions'])
      expect(groups.every(g => g.unavailable === true && g.items.length === 0)).toBe(true)
      expect(ep.listCanonicalCircuits).not.toHaveBeenCalled()
    })
  })

  describe('searchEntities：搜索结果同样使用人类可读名称', () => {
    it('connection hits render display name, not the raw code', async () => {
      ep.listCanonicalRegions.mockResolvedValue([])
      ep.listCanonicalCircuits.mockResolvedValue([])
      ep.listOntologyTerms.mockResolvedValue({ items: [], total: 0 })
      ep.listCanonicalConnections.mockResolvedValue([makeConnection()])

      const nodes = await ontologyApi.searchEntities('pars')

      expect(nodes).toHaveLength(1)
      expect(nodes[0]).toMatchObject({
        entityType: 'connection',
        name: 'pars triangularis → posterior cingulate',
        code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate',
      })
    })
  })
})

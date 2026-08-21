import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { EntityDetailPanel } from './EntityDetailPanel'
import * as ontologyApiModule from '../../../api/ontologyApi'
import type { EntityDetailData, RelationGroup } from './types'

vi.mock('../../../api/ontologyApi', () => ({
  ontologyApi: {
    getTreeChildren: vi.fn(),
    getEntityDetail: vi.fn(),
    getRelations: vi.fn(),
  },
}))

const mocked = vi.mocked(ontologyApiModule.ontologyApi)

const REGION_DETAIL: EntityDetailData = {
  entityType: 'region',
  id: 'r-cerebrum',
  name: 'Cerebrum',
  code: 'ng:br:cerebrum',
  status: 'active',
  granularityLevel: 'macro',
  confidence: 0.9,
  description: 'largest part of the brain',
  basic: [{ label: '名称 (CN)', value: '大脑' }],
  path: [
    { id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' },
    { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
  ],
  parent: { id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' },
  children: [
    {
      id: 'r-hippo',
      code: 'ng:br:hippo',
      name: 'Hippocampus',
      entityType: 'region',
      granularityLevel: 'clinical',
    },
  ],
  provenance: [{ label: 'atlas', value: 'AAL3' }],
}

/**
 * Hippocampus（clinical）多尺度详情 —— 与真实 API 夹具一致：
 * 直接子节点 2×meso（由 multiscale 桶 Meso children 展示）+ 5×subregion
 * （Field CA1/CA2/CA3、Dentate gyrus、Subiculum）+ 1×cell type + 1×molecule
 */
const HIPPOCAMPUS_DETAIL: EntityDetailData = {
  entityType: 'region',
  id: 'r-hippocampus',
  name: 'Hippocampus',
  code: 'ng:br:hippocampus',
  status: 'active',
  granularityLevel: 'clinical',
  confidence: 0.92,
  description: null,
  basic: [
    { label: '名称 (CN)', value: '海马体' },
    { label: '物种', value: 'human' },
    { label: '来源', value: 'AAL3' },
  ],
  path: [
    { id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' },
    { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
    { id: 'r-hippocampus', code: 'ng:br:hippocampus', name: 'Hippocampus', entityType: 'region' },
  ],
  parent: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
  children: [
    {
      id: 'r-formation',
      code: 'ng:br:hippocampal_formation',
      name: 'Hippocampal formation',
      entityType: 'region',
      granularityLevel: 'meso',
    },
    {
      id: 'r-entorhinal',
      code: 'ng:br:entorhinal_cortex',
      name: 'Entorhinal cortex',
      entityType: 'region',
      granularityLevel: 'meso',
    },
  ],
  multiscale: {
    mesoRegions: [
      {
        id: 'r-formation',
        code: 'ng:br:hippocampal_formation',
        name: 'Hippocampal formation',
        entityType: 'region',
        granularityLevel: 'meso',
      },
      {
        id: 'r-entorhinal',
        code: 'ng:br:entorhinal_cortex',
        name: 'Entorhinal cortex',
        entityType: 'region',
        granularityLevel: 'meso',
      },
    ],
    subregions: [
      { id: 'r-ca1', code: 'ng:br:ca1', name: 'Field CA1', entityType: 'region', granularityLevel: 'subregion' },
      { id: 'r-ca2', code: 'ng:br:ca2', name: 'Field CA2', entityType: 'region', granularityLevel: 'subregion' },
      { id: 'r-ca3', code: 'ng:br:ca3', name: 'Field CA3', entityType: 'region', granularityLevel: 'subregion' },
      {
        id: 'r-dg',
        code: 'ng:br:dentate_gyrus',
        name: 'Dentate gyrus',
        entityType: 'region',
        granularityLevel: 'subregion',
      },
      {
        id: 'r-subiculum',
        code: 'ng:br:subiculum',
        name: 'Subiculum',
        entityType: 'region',
        granularityLevel: 'subregion',
      },
    ],
    fineRegions: [],
    cellTypes: [
      {
        ref: {
          id: 'ct-pyramidal',
          code: 'ng:ct:pyramidal_neuron',
          name: 'Pyramidal neuron',
          entityType: 'cell_type',
          granularityLevel: 'cyto',
        },
        relation: 'contains',
        confidence: 0.85,
        detail: 'Allen Human Brain Atlas',
      },
    ],
    molecules: [
      {
        ref: {
          id: 'm-bdnf',
          code: 'ng:mo:bdnf',
          name: 'BDNF',
          entityType: 'molecule',
          granularityLevel: 'molecular',
        },
        relation: 'expression',
        confidence: 0.9,
        detail: 'GTEx v10 brain tissue median TPM',
      },
    ],
  },
  provenance: [{ label: 'source', value: 'AAL3' }],
}

/** 普通脑区：无下级分区、无 atlas 映射、无 cell/molecule 对齐 */
const PARAHIPPOCAMPAL_DETAIL: EntityDetailData = {
  entityType: 'region',
  id: 'r-parahippocampal',
  name: 'Parahippocampal gyrus',
  code: 'ng:br:parahippocampal_gyrus',
  status: 'active',
  granularityLevel: 'clinical',
  confidence: 0.9,
  description: null,
  basic: [{ label: '物种', value: 'human' }],
  path: [
    { id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' },
    { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
    {
      id: 'r-parahippocampal',
      code: 'ng:br:parahippocampal_gyrus',
      name: 'Parahippocampal gyrus',
      entityType: 'region',
    },
  ],
  parent: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
  children: [],
  multiscale: { mesoRegions: [], subregions: [], fineRegions: [], cellTypes: [], molecules: [] },
  provenance: [],
}

const CONNECTION_DETAIL: EntityDetailData = {
  entityType: 'connection',
  id: 'c-1',
  name: 'ng:cn:association_pars_triangularis_to_posterior_cingulate',
  code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate',
  status: 'proposed',
  granularityLevel: 'clinical',
  confidence: 0.4,
  description: null,
  typeTitle: 'Association connection',
  source: { id: 'r-pt', code: 'ng:br:pars_triangularis', name: 'Pars triangularis', entityType: 'region' },
  target: { id: 'r-pc', code: 'ng:br:posterior_cingulate', name: 'Posterior cingulate', entityType: 'region' },
  basic: [
    { label: '连接类型', value: 'association' },
    { label: '方向策略', value: 'bidirectional' },
    { label: '物种', value: 'human' },
  ],
  path: [{ id: 'c-1', code: 'ng:cn:association_pars_triangularis_to_posterior_cingulate', name: 'ng:cn:association_pars_triangularis_to_posterior_cingulate', entityType: 'connection' }],
  parent: null,
  children: [],
  provenance: [{ label: 'mapping_method', value: 'macro96_canonical_connection_v1' }],
}

const CIRCUIT_DETAIL: EntityDetailData = {
  entityType: 'circuit',
  id: 'ci-1',
  name: 'auditory_brainstem_thalamocortical_pathway',
  code: 'ng:ci:auditory_brainstem_thalamocortical_pathway',
  status: 'proposed',
  granularityLevel: 'clinical',
  confidence: 0.55,
  description: '听觉脑干-丘脑-皮层通路',
  basic: [{ label: '回路类型', value: 'network' }],
  path: [{ id: 'ci-1', code: 'ng:ci:auditory_brainstem_thalamocortical_pathway', name: 'auditory_brainstem_thalamocortical_pathway', entityType: 'circuit' }],
  parent: null,
  children: [],
  provenance: [],
}

const CIRCUIT_RELATIONS: RelationGroup[] = [
  {
    key: 'regions',
    label: 'Regions',
    items: [
      {
        ref: { id: 'r-th', code: 'ng:br:thalamus', name: 'Thalamus', entityType: 'region' },
        meta: [{ label: '角色', value: '核心区域' }],
      },
    ],
  },
  {
    key: 'connections',
    label: 'Connections',
    items: [
      {
        ref: { id: 'c-2', code: 'ng:cn:a_to_b', name: 'Brainstem → Thalamus', entityType: 'connection' },
        meta: [{ label: '置信度', value: '60%' }],
      },
    ],
  },
  { key: 'functions', label: 'Functions', items: [] },
]

const FUNCTION_DETAIL: EntityDetailData = {
  entityType: 'function',
  id: 'f-1',
  name: 'Somatosensory processing',
  code: 'ng:fn:somatosensory',
  status: 'proposed',
  granularityLevel: null,
  confidence: null,
  description: null,
  basic: [{ label: '术语类型', value: 'function' }],
  path: [{ id: 'f-1', code: 'ng:fn:somatosensory', name: 'Somatosensory processing', entityType: 'function' }],
  parent: null,
  children: [],
  provenance: [],
}

const FUNCTION_RELATIONS: RelationGroup[] = [
  { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] },
  { key: 'regions', label: 'Related Regions', unavailable: true, items: [] },
]

beforeEach(() => {
  vi.clearAllMocks()
  mocked.getEntityDetail.mockResolvedValue(REGION_DETAIL)
})

describe('EntityDetailPanel', () => {
  it('shows skeleton while fetching', () => {
    mocked.getEntityDetail.mockReturnValue(new Promise(() => {}))
    render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)
    expect(screen.getByLabelText('加载中')).toBeTruthy()
  })

  describe('region inspector（医学本体浏览器详情）', () => {
    it('renders header, breadcrumb and the seven detail modules', async () => {
      render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)

      expect(await screen.findByText('Basic Information')).toBeTruthy()
      expect(screen.getByText('Children')).toBeTruthy()
      expect(screen.getByText('External Atlas')).toBeTruthy()
      expect(screen.getByText('Cell Types')).toBeTruthy()
      expect(screen.getByText('Molecules')).toBeTruthy()
      expect(screen.getByText('Provenance')).toBeTruthy()

      // Entity Header：人类可读名称 + code 次要 + 类型行
      expect(screen.getAllByText('ng:br:cerebrum').length).toBeGreaterThan(0) // header + Basic Information Code 行
      expect(screen.getByText('Macro Brain Region')).toBeTruthy()
      expect(screen.getByText('大脑')).toBeTruthy()
      expect(screen.getByText('largest part of the brain')).toBeTruthy()
      expect(screen.getByText('Hippocampus')).toBeTruthy()
      expect(screen.getByText('AAL3')).toBeTruthy()

      // 可点击面包屑（root-first）= Hierarchy Path
      const breadcrumb = screen.getByRole('navigation', { name: '层级路径' })
      expect(within(breadcrumb).getByText('Brain')).toBeTruthy()
      expect(within(breadcrumb).getByText('Cerebrum')).toBeTruthy()

      // 无 multiscale 数据 → 生物层两个折叠 section 显示 EmptyState（不显示空白）
      expect(screen.getByText('No cell type alignment on record')).toBeTruthy()
      expect(screen.getByText('No molecular entity on record')).toBeTruthy()

      expect(mocked.getEntityDetail).toHaveBeenCalledWith('region', 'r-cerebrum', expect.anything())
    })

    it('renders Hippocampus multiscale detail: CA fields, Dentate gyrus, BDNF, Pyramidal neuron', async () => {
      mocked.getEntityDetail.mockResolvedValue(HIPPOCAMPUS_DETAIL)
      render(<EntityDetailPanel entityType="region" entityId="r-hippocampus" />)

      // Basic Information：name + 中文名 + granularity + species + source
      expect(await screen.findByRole('heading', { name: 'Hippocampus' })).toBeTruthy()
      expect(screen.getByText('海马体')).toBeTruthy()
      expect(screen.getByText('Clinical Brain Region')).toBeTruthy()
      expect(screen.getByText('human')).toBeTruthy()
      expect(screen.getAllByText('AAL3').length).toBeGreaterThan(0) // 基本信息来源 + provenance source

      // Hierarchy Path 面包屑：Brain > Cerebrum > Hippocampus
      const breadcrumb = screen.getByRole('navigation', { name: '层级路径' })
      expect(
        within(breadcrumb)
          .getAllByRole('button')
          .map(button => button.textContent),
      ).toEqual(['Brain', 'Cerebrum', 'Hippocampus'])

      // Children 粒度分组：Meso children（2）+ Subregion children（5，含 CA1/CA2/CA3/DG）
      expect(screen.getByText('Meso children')).toBeTruthy()
      expect(screen.getByText('Subregion children')).toBeTruthy()
      expect(screen.getByText('Hippocampal formation')).toBeTruthy()
      expect(screen.getByText('Field CA1')).toBeTruthy()
      expect(screen.getByText('Field CA2')).toBeTruthy()
      expect(screen.getByText('Field CA3')).toBeTruthy()
      expect(screen.getByText('Dentate gyrus')).toBeTruthy()
      expect(screen.getByText('Subiculum')).toBeTruthy()

      // Biological Layer：Cell Types（关系/分类学/置信度）+ Molecules（证据/来源/置信度）
      expect(screen.getByText('Pyramidal neuron')).toBeTruthy()
      expect(screen.getByText('contains')).toBeTruthy()
      expect(screen.getByText('Allen Human Brain Atlas')).toBeTruthy()
      expect(screen.getByText('85%')).toBeTruthy()
      expect(screen.getByText('BDNF')).toBeTruthy()
      expect(screen.getByText('expression')).toBeTruthy()
      expect(screen.getByText('GTEx v10 brain tissue median TPM')).toBeTruthy()
      expect(screen.getByText('90%')).toBeTruthy()
    })

    it('renders an ordinary region without cell/molecule data with EmptyState instead of blank space', async () => {
      mocked.getEntityDetail.mockResolvedValue(PARAHIPPOCAMPAL_DETAIL)
      render(<EntityDetailPanel entityType="region" entityId="r-parahippocampal" relations={[]} />)

      expect(await screen.findByRole('heading', { name: 'Parahippocampal gyrus' })).toBeTruthy()

      // 无下级分区 / 无 atlas / 无 cell / 无 molecule → 全部 EmptyState（不显示空白）
      expect(screen.getByText('No subregions on record')).toBeTruthy()
      expect(screen.getByText('No atlas mappings on record')).toBeTruthy()
      expect(screen.getByText('No cell type alignment on record')).toBeTruthy()
      expect(screen.getByText('No molecular entity on record')).toBeTruthy()
    })

    it('collapses large Meso children groups by default and expands on click', async () => {
      const manyMeso = Array.from({ length: 30 }, (_, index) => ({
        id: `r-meso-${index}`,
        code: `ng:br:meso_${index}`,
        name: `Meso region ${index}`,
        entityType: 'region' as const,
        granularityLevel: 'meso',
      }))
      mocked.getEntityDetail.mockResolvedValue({
        ...REGION_DETAIL,
        children: [],
        multiscale: { mesoRegions: manyMeso, subregions: [], fineRegions: [], cellTypes: [], molecules: [] },
      })
      render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)

      await screen.findByText('Basic Information')
      // 默认折叠：组头（含计数 30）可见，行不渲染
      const group = screen.getByText('Meso children').closest('.oc-children-group') as HTMLElement
      expect(within(group).getByText('30')).toBeTruthy()
      expect(screen.queryByText('Meso region 0')).toBeNull()

      fireEvent.click(screen.getByRole('button', { name: /Meso children/ }))
      expect(screen.getByText('Meso region 0')).toBeTruthy()
    })

    it('navigates via breadcrumb and Children group links', async () => {
      const onNavigate = vi.fn()
      render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" onNavigate={onNavigate} />)
      await screen.findByText('Basic Information')

      fireEvent.click(screen.getAllByText('Brain')[0]) // 面包屑
      expect(onNavigate).toHaveBeenCalledWith('region', 'r-brain')

      fireEvent.click(screen.getByText('Hippocampus'))
      expect(onNavigate).toHaveBeenCalledWith('region', 'r-hippo')
    })
  })

  describe('connection inspector（类型化展示）', () => {
    it('uses type title as header with Source → Target subtitle, code moved to Properties', async () => {
      mocked.getEntityDetail.mockResolvedValue(CONNECTION_DETAIL)
      const { container } = render(<EntityDetailPanel entityType="connection" entityId="c-1" />)

      // 主标题 = 类型标题（不再是 canonical code）
      expect(await screen.findByText('Association connection')).toBeTruthy()
      expect(container.querySelector('.oc-entity-code')).toBeNull() // code 不进入 header 视觉层
      // 端点名出现两次：header 副标题（Source → Target）+ 对应卡片
      expect(screen.getAllByText('Pars triangularis')).toHaveLength(2)
      expect(screen.getAllByText('Posterior cingulate')).toHaveLength(2)
      expect(screen.getByLabelText('指向')).toBeTruthy() // → 箭头

      // 类型化卡片
      expect(screen.getByText('Source Region')).toBeTruthy()
      expect(screen.getByText('Target Region')).toBeTruthy()
      expect(screen.getByText('Properties')).toBeTruthy()
      // code 下沉到 Properties 行（仅此一处）
      expect(screen.getAllByText('ng:cn:association_pars_triangularis_to_posterior_cingulate').length).toBe(1)
      expect(screen.getByText('bidirectional')).toBeTruthy()
      expect(screen.getByText('macro96_canonical_connection_v1')).toBeTruthy()

      // 不渲染 Region 专属结构
      expect(screen.queryByText('Hierarchy')).toBeNull()
      expect(screen.queryByRole('navigation', { name: '层级路径' })).toBeNull()
    })

    it('navigates from Source/Target cards to the endpoint regions', async () => {
      mocked.getEntityDetail.mockResolvedValue(CONNECTION_DETAIL)
      const onNavigate = vi.fn()
      render(<EntityDetailPanel entityType="connection" entityId="c-1" onNavigate={onNavigate} />)
      await screen.findByText('Association connection')

      // 端点名两处出现：副标题 + 卡片；点击卡片（后者）
      fireEvent.click(screen.getAllByText('Pars triangularis')[1])
      expect(onNavigate).toHaveBeenCalledWith('region', 'r-pt')

      fireEvent.click(screen.getAllByText('Posterior cingulate')[1])
      expect(onNavigate).toHaveBeenCalledWith('region', 'r-pc')
    })
  })

  describe('circuit inspector（类型化展示）', () => {
    it('shows name header plus region topology / connections / functions cards', async () => {
      mocked.getEntityDetail.mockResolvedValue(CIRCUIT_DETAIL)
      render(
        <EntityDetailPanel
          entityType="circuit"
          entityId="ci-1"
          relations={CIRCUIT_RELATIONS}
        />,
      )

      expect(await screen.findByText('auditory_brainstem_thalamocortical_pathway')).toBeTruthy()
      expect(screen.getByText('Region topology')).toBeTruthy()
      expect(screen.getByText('Connections')).toBeTruthy()
      expect(screen.getByText('Functions')).toBeTruthy()

      // 拓扑：角色 meta + 连接卡 "Source → Target" 名称
      expect(screen.getByText('Thalamus')).toBeTruthy()
      expect(screen.getByText('核心区域')).toBeTruthy()
      expect(screen.getByText('Brainstem → Thalamus')).toBeTruthy()
      expect(screen.getByText('60%')).toBeTruthy()

      // 空拓扑组 → 空状态（不造数据）
      expect(screen.getByText('该实体暂无此关系记录')).toBeTruthy()
    })
  })

  describe('function inspector（类型化展示）', () => {
    it('shows name header plus hierarchy and associated cards', async () => {
      mocked.getEntityDetail.mockResolvedValue(FUNCTION_DETAIL)
      render(
        <EntityDetailPanel
          entityType="function"
          entityId="f-1"
          relations={FUNCTION_RELATIONS}
        />,
      )

      expect(await screen.findByText('Somatosensory processing')).toBeTruthy()
      expect(screen.getByText('Hierarchy')).toBeTruthy()
      expect(screen.getByText('No parent on record')).toBeTruthy()
      expect(screen.getByText('Associated regions')).toBeTruthy()
      expect(screen.getByText('Associated circuits')).toBeTruthy()

      // 后端暂无 function 反向关系 API → 诚实空状态（两处卡片）
      expect(screen.getAllByText('后端 API 待接入（不展示假数据）').length).toBe(2)
    })
  })

  describe('provenance 专业化展示', () => {
    it('renders array provenance as item count + Expand JSON inside the card', async () => {
      mocked.getEntityDetail.mockResolvedValue({
        ...REGION_DETAIL,
        provenance: [
          {
            label: 'original_connection_ids',
            value: JSON.stringify(['e20a1be7-3b2c-4d5e-8f90-1234567890ab', 'b06e96e8-1a2b-3c4d-9e0f-abcdef012345']),
          },
        ],
      })
      render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)

      expect(await screen.findByText('2 items')).toBeTruthy()
      expect(screen.getByText('[ e20a1be7-3b2c-4d... ]')).toBeTruthy()

      fireEvent.click(screen.getByRole('button', { name: /Expand JSON/ }))
      const section = screen.getByText('2 items').closest('section') as HTMLElement | null
      const pre = section?.querySelector('.oc-provenance-json')
      expect(pre).toBeTruthy()
      expect(pre?.textContent).toContain('e20a1be7-3b2c-4d5e-8f90-1234567890ab')
      expect(pre?.textContent).toContain('b06e96e8-1a2b-3c4d-9e0f-abcdef012345')
    })
  })

  it('shows error state and retries on failure', async () => {
    mocked.getEntityDetail
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(REGION_DETAIL)
    render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)

    expect(await screen.findByText('Entity detail failed to load')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Basic Information')).toBeTruthy()
  })

  it('collapses and expands a section', async () => {
    render(<EntityDetailPanel entityType="region" entityId="r-cerebrum" />)
    await screen.findByText('Basic Information')

    fireEvent.click(screen.getByRole('button', { name: /Basic Information/ }))
    expect(screen.queryByText('大脑')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Basic Information/ }))
    expect(screen.getByText('大脑')).toBeTruthy()
  })
})

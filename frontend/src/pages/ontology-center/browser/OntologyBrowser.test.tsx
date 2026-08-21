import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { OntologyBrowser } from './OntologyBrowser'
import * as ontologyApiModule from '../../../api/ontologyApi'
import type { OntologyTreeNode } from './tree/OntologyTreeNode'
import type { EntityDetailData, RelationGroup } from '../detail/types'

vi.mock('../../../api/ontologyApi', () => ({
  ontologyApi: {
    getTreeChildren: vi.fn(),
    getEntityDetail: vi.fn(),
    getRelations: vi.fn(),
    getRegionResearchView: vi.fn(),
  },
}))

const mocked = vi.mocked(ontologyApiModule.ontologyApi)

const BRAIN_NODE: OntologyTreeNode = {
  id: 'r-brain',
  code: 'ng:br:brain',
  name: 'Brain',
  entityType: 'region',
  granularityLevel: 'whole_brain',
  status: 'active',
}

const CEREBRUM_NODE: OntologyTreeNode = {
  id: 'r-cerebrum',
  code: 'ng:br:cerebrum',
  name: 'Cerebrum',
  entityType: 'region',
  granularityLevel: 'macro',
  status: 'active',
}

const HIPPOCAMPUS_NODE: OntologyTreeNode = {
  id: 'r-hippocampus',
  code: 'ng:br:hippocampus',
  name: 'Hippocampus',
  entityType: 'region',
  granularityLevel: 'clinical',
  status: 'active',
}

const FORMATION_NODE: OntologyTreeNode = {
  id: 'r-hippocampal-formation',
  code: 'ng:br:hippocampal_formation',
  name: 'Hippocampal formation',
  entityType: 'region',
  granularityLevel: 'meso',
  status: 'active',
}

const CA1_NODE: OntologyTreeNode = {
  id: 'r-ca1',
  code: 'ng:br:ca1',
  name: 'CA1',
  entityType: 'region',
  granularityLevel: 'fine',
  status: 'active',
}

/** 层级链（canonical_region_hierarchy part_of 递归）：
 *  Brain → Cerebrum → Hippocampus → Hippocampal formation → CA1 */
const CHILDREN_BY_ID: Record<string, OntologyTreeNode[]> = {
  'root:region': [BRAIN_NODE],
  'r-brain': [CEREBRUM_NODE],
  'r-cerebrum': [HIPPOCAMPUS_NODE],
  'r-hippocampus': [FORMATION_NODE],
  'r-hippocampal-formation': [CA1_NODE],
}

const BRAIN_DETAIL: EntityDetailData = {
  entityType: 'region',
  id: 'r-brain',
  name: 'Brain',
  code: 'ng:br:brain',
  status: 'active',
  granularityLevel: 'whole_brain',
  confidence: 0.95,
  description: null,
  basic: [{ label: '名称 (CN)', value: '脑' }],
  path: [{ id: 'r-brain', code: 'ng:br:brain', name: 'Brain', entityType: 'region' }],
  parent: null,
  children: [
    {
      id: 'r-cerebrum',
      code: 'ng:br:cerebrum',
      name: 'Cerebrum',
      entityType: 'region',
      granularityLevel: 'macro',
    },
  ],
  provenance: [{ label: 'atlas', value: 'AAL3' }],
}

const BRAIN_RELATIONS: RelationGroup[] = [
  { key: 'parent', label: '父节点', items: [] },
  {
    key: 'children',
    label: '子节点',
    items: [
      {
        ref: { id: 'r-cerebrum', code: 'ng:br:cerebrum', name: 'Cerebrum', entityType: 'region' },
        meta: [],
      },
    ],
  },
  { key: 'connections', label: 'Related Connections', items: [] },
  { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] },
  { key: 'functions', label: 'Functions（经回路）', items: [] },
]

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom 不在测试间重置 location —— 尺度切换会写 oc_scale 到 hash，
  // 污染后续测试的挂载初始尺度（导致树只剩 Cell Type 根、'Brain' 永不出现）
  window.location.hash = ''
  mocked.getTreeChildren.mockImplementation(async node => CHILDREN_BY_ID[node.id] ?? [])
  mocked.getEntityDetail.mockResolvedValue(BRAIN_DETAIL)
  mocked.getRelations.mockResolvedValue(BRAIN_RELATIONS)
  // 默认无研究地图（挂载 effect 需要 resolved promise，否则 .then 抛错）
  mocked.getRegionResearchView.mockResolvedValue(null)
})

describe('OntologyBrowser', () => {
  it('renders 4 entity roots and lazy-loads children via ontologyApi', async () => {
    render(<OntologyBrowser />)

    // 树顶层四根（「Brain Region」同时出现在尺度选择器组名，故限定在树容器内查询）
    const treeRoot = document.querySelector('.oc-tree-root') as HTMLElement
    expect(treeRoot).toBeTruthy()
    expect(within(treeRoot).getByText('Brain Region')).toBeTruthy()
    expect(within(treeRoot).getByText('Connection')).toBeTruthy()
    expect(within(treeRoot).getByText('Circuit')).toBeTruthy()
    expect(within(treeRoot).getByText('Function')).toBeTruthy()

    expect(await screen.findByText('Brain', { selector: '.oc-tree-label' })).toBeTruthy()
    // mount 自动展开 4 个根 + 级联展开 whole_brain/macro/clinical（meso 可见但折叠，不再级联加载）
    expect(await screen.findByText('Hippocampal formation', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(mocked.getTreeChildren).toHaveBeenCalledTimes(7)
  })

  it('expands Brain → Cerebrum → Hippocampal formation → CA1 level by level, Meso collapsed by default', async () => {
    render(<OntologyBrowser />)

    // 默认级联：Whole-brain / Macro / Clinical 自动展开
    expect(await screen.findByText('Brain', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(await screen.findByText('Cerebrum', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(await screen.findByText('Hippocampus', { selector: '.oc-tree-label' })).toBeTruthy()

    // Meso 可见但折叠：Hippocampal formation 行在，Fine（CA1）未渲染
    expect(await screen.findByText('Hippocampal formation', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(screen.queryByText('CA1')).toBeNull()

    // 默认 fine 透镜包含全层级 → 展开 Meso 即可逐级到达 Fine（CA1），无需切换透镜
    const formationRow = (await screen.findByText('Hippocampal formation', { selector: '.oc-tree-label' })).closest(
      '.oc-tree-row',
    ) as HTMLElement
    fireEvent.click(within(formationRow).getByRole('button', { name: '展开' }))
    expect(await screen.findByText('CA1', { selector: '.oc-tree-label' })).toBeTruthy()
  })

  it('switches tree roots to the biological layer when the scale changes', async () => {
    render(<OntologyBrowser />)
    await screen.findByText('Brain', { selector: '.oc-tree-label' })

    fireEvent.click(screen.getByRole('radio', { name: 'Cyto' }))

    // 树重挂：顶层只剩 Cell Type 根，且以 cyto 尺度加载
    expect(await screen.findByText('Cell Type')).toBeTruthy()
    expect(mocked.getTreeChildren).toHaveBeenCalledWith(
      expect.objectContaining({ entityType: 'cell_type', isEntityRoot: true }),
      'cyto',
      undefined,
    )
    // 尺度选择器自身仍在（两组 + 选中态）
    expect(screen.getByRole('radio', { name: 'Cyto' }).getAttribute('aria-checked')).toBe('true')

    // 切回脑区尺度 → 树恢复四根
    fireEvent.click(screen.getByRole('radio', { name: 'Meso' }))
    expect(await screen.findByText('Brain', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(mocked.getTreeChildren).toHaveBeenCalledWith(
      expect.objectContaining({ entityType: 'region', isEntityRoot: true }),
      'meso',
      undefined,
    )
  })

  it('shows three-column layout with hint placeholders before selection', async () => {
    render(<OntologyBrowser />)
    await screen.findByText('Brain', { selector: '.oc-tree-label' })

    expect(screen.getByText('Ontology Explorer')).toBeTruthy()
    expect(screen.getByText('Entity Detail')).toBeTruthy()
    expect(screen.getByText('Relations')).toBeTruthy()
    expect(screen.getAllByText(/点击左侧树节点/).length).toBeGreaterThan(0)
    expect(screen.getByText('选中实体后显示关系。')).toBeTruthy()
  })

  it('opens the detail panel with unified data when a node is clicked', async () => {
    render(<OntologyBrowser />)

    fireEvent.click(await screen.findByText('Brain', { selector: '.oc-tree-label' }))

    // 右栏：医学本体浏览器详情（Basic Information / Children 粒度分组 / External Atlas /
    // Cell Types / Molecules / Knowledge Relations）
    expect(await screen.findByText('Basic Information')).toBeTruthy()
    expect(screen.getByText('Children')).toBeTruthy()
    expect(screen.getByText('Macro children')).toBeTruthy()
    expect(screen.getByText('External Atlas')).toBeTruthy()
    expect(screen.getByText('Cell Types')).toBeTruthy()
    expect(screen.getByText('Molecules')).toBeTruthy()
    expect(screen.getByText('Provenance')).toBeTruthy()
    expect(screen.getAllByText('Whole-brain').length).toBeGreaterThan(0) // 粒度层级（医生视角名，无 L 编号）
    expect(mocked.getEntityDetail).toHaveBeenCalledWith('region', 'r-brain', expect.anything())

    // 无 cell/molecule 数据 → EmptyState（不显示空白）
    expect(screen.getByText('No cell type alignment on record')).toBeTruthy()
    expect(screen.getByText('No molecular entity on record')).toBeTruthy()

    // 关系组共享：Connections 空 / Circuits 无 API / Functions 空；子节点 Cerebrum 出现在 Children 分组。
    // 同一关系组标签同时渲染于详情模块与右栏 Relation Explorer Tabs → getAllByText 容许多个
    expect((await screen.findAllByText('Connections')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('Circuits').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Functions').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Cerebrum').length).toBeGreaterThan(0)
    expect(mocked.getRelations).toHaveBeenCalledWith('region', 'r-brain', expect.anything())
  })

  it('shows 暂无数据 for relation groups without backend API', async () => {
    render(<OntologyBrowser />)
    fireEvent.click(await screen.findByText('Brain', { selector: '.oc-tree-label' }))

    // Circuits 无 API → 详情模块与右栏关系组各渲染一次空状态
    expect((await screen.findAllByText('后端 API 待接入（不展示假数据）')).length).toBeGreaterThan(0)
  })

  it('navigates to a related entity from the detail Children group and the relations column', async () => {
    render(<OntologyBrowser />)
    fireEvent.click(await screen.findByText('Brain', { selector: '.oc-tree-label' }))
    await screen.findByText('Basic Information')

    // 详情面板 Children 分组导航
    const detailPanel = document.querySelector('.oc-browser-detail')
    expect(detailPanel).toBeTruthy()
    fireEvent.click(within(detailPanel as HTMLElement).getByText('Cerebrum'))

    expect(mocked.getEntityDetail).toHaveBeenCalledWith('region', 'r-cerebrum', expect.anything())

    // 右栏 Relation Explorer 子节点组同样可导航（先等关系栏重挂载后加载完成）
    const relationsPanel = document.querySelector('.oc-browser-relations')
    expect(relationsPanel).toBeTruthy()
    const cerebrumInRelations = await within(relationsPanel as HTMLElement).findByText('Cerebrum')
    fireEvent.click(cerebrumInRelations)

    expect(mocked.getEntityDetail).toHaveBeenCalledTimes(2)
    expect(mocked.getEntityDetail).toHaveBeenLastCalledWith('region', 'r-cerebrum', expect.anything())
  })

  it('shows error + retry in the detail panel on failure', async () => {
    mocked.getEntityDetail
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(BRAIN_DETAIL)
    render(<OntologyBrowser />)
    fireEvent.click(await screen.findByText('Brain', { selector: '.oc-tree-label' }))

    expect(await screen.findByText('Entity detail failed to load')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Basic Information')).toBeTruthy()
  })

  it('auto-expands the small meso branch from the research map without extra tree requests', async () => {
    // 研究地图：Hippocampal formation（children=1 的 subregion/fine 分支）自动展开 + 预加载
    mocked.getRegionResearchView.mockResolvedValue({
      autoExpandIds: ['r-hippocampal-formation'],
      researchExpandIds: ['r-hippocampal-formation'],
      researchAncestorIds: ['r-brain', 'r-cerebrum', 'r-hippocampus'],
      preloadedChildren: { 'r-hippocampal-formation': [CA1_NODE] },
      childCountById: { 'r-hippocampal-formation': 1 },
    })
    render(<OntologyBrowser />)

    // 默认视图直达 CA1（无任何手动点击）
    expect(await screen.findByText('CA1', { selector: '.oc-tree-label' })).toBeTruthy()
    // 预加载命中 → 不为 formation 发 /children 请求（7 = 4 根 + Brain/Cerebrum/Hippocampus）
    expect(mocked.getTreeChildren).toHaveBeenCalledTimes(7)
    expect(mocked.getTreeChildren).not.toHaveBeenCalledWith(
      FORMATION_NODE,
      expect.anything(),
      expect.anything(),
    )
    // 「展开到研究层级」按钮出现（研究地图含 subregion/fine 目标）
    expect(screen.getByRole('button', { name: '展开到研究层级' })).toBeTruthy()
  })

  it('shows the (n) child-count badge on a collapsed large meso branch', async () => {
    // 大分支（360）：不自动展开，徽章说明折叠原因
    mocked.getRegionResearchView.mockResolvedValue({
      autoExpandIds: [],
      researchExpandIds: ['r-hippocampal-formation'],
      researchAncestorIds: ['r-brain', 'r-cerebrum', 'r-hippocampus'],
      preloadedChildren: {},
      childCountById: { 'r-hippocampal-formation': 360 },
    })
    render(<OntologyBrowser />)

    const formationRow = (
      await screen.findByText('Hippocampal formation', { selector: '.oc-tree-label' })
    ).closest('.oc-tree-row') as HTMLElement
    expect(within(formationRow).getByText('(360)')).toBeTruthy()
    // 保持折叠：CA1 未渲染
    expect(screen.queryByText('CA1')).toBeNull()
  })

  it('expands down to research level when 展开到研究层级 is clicked', async () => {
    mocked.getRegionResearchView.mockResolvedValue({
      autoExpandIds: [],
      researchExpandIds: ['r-hippocampal-formation'],
      researchAncestorIds: ['r-brain', 'r-cerebrum', 'r-hippocampus'],
      preloadedChildren: {},
      childCountById: {},
    })
    render(<OntologyBrowser />)

    // 默认折叠：CA1 不可见
    expect(await screen.findByText('Hippocampal formation', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(screen.queryByText('CA1')).toBeNull()

    fireEvent.click(await screen.findByRole('button', { name: '展开到研究层级' }))

    // 按钮沿树链展开到 meso 目标 → 懒加载 formation → CA1 出现
        expect(await screen.findByText('CA1', { selector: '.oc-tree-label' })).toBeTruthy()
    expect(mocked.getTreeChildren).toHaveBeenCalledWith(
      FORMATION_NODE,
      expect.anything(),
      undefined,
    )
  })
})

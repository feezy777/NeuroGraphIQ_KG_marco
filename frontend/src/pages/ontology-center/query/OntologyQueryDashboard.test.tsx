import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import type {
  OntologyExplainResponse,
  OntologyQueryResultItem,
} from '../../../api/ontologyQueryApi'
import { postOntologyExplain } from '../../../api/ontologyQueryApi'
import { OntologyQueryPage } from './OntologyQueryPage'

vi.mock('../../../api/ontologyQueryApi', () => ({
  postOntologyExplain: vi.fn(),
}))

const mockExplain = vi.mocked(postOntologyExplain)

const ENTITY = {
  type: 'region',
  id: 'r-hippocampus',
  code: 'ng:br:hippocampus',
  name: '海马',
  matched_by: 'canonical_name_cn',
}

const CONNECTION_ITEM: OntologyQueryResultItem = {
  id: 'cn-hippo-entorhinal',
  code: 'structural_hippo_entorhinal',
  name: '海马→内嗅皮层',
  category: 'connection',
  detail: {
    direction: 'outgoing',
    connection_type: 'structural',
    endpoint_region: {
      id: 'r-entorhinal',
      canonical_name_cn: '内嗅皮层',
      canonical_name_en: 'Entorhinal cortex',
      region_code: 'ng:br:entorhinal',
    },
  },
  confidence: 0.92,
  provenance: 'canonical_connections',
}

const CIRCUIT_ITEM: OntologyQueryResultItem = {
  id: 'ci-hippocampal-memory',
  code: 'ng:ci:hippocampal_memory',
  name: '海马-前额叶记忆回路',
  category: 'circuit',
  detail: { circuit_type: '记忆回路' },
  confidence: 0.7,
  provenance: 'canonical_circuit',
}

function makeResponse(overrides: Partial<OntologyExplainResponse> = {}): OntologyExplainResponse {
  return {
    question: '海马有哪些功能？',
    query_result: {
      intent: 'region_functions',
      entity: ENTITY,
      results: [CONNECTION_ITEM, CIRCUIT_ITEM],
      confidence: 0.9,
      warnings: [],
      source_entities: [ENTITY],
    },
    explanation: {
      answer: '海马主要参与情景记忆的编码与巩固。',
      summary: '海马是记忆回路的核心节点。',
      key_points: ['情景记忆编码'],
      evidence_entities: ['海马', '内嗅皮层'],
      confidence: 0.9,
      hallucination_warning: [],
    },
    ...overrides,
  }
}

const typeQuestion = (question: string) =>
  fireEvent.change(screen.getByLabelText('自然语言问题'), { target: { value: question } })

const submit = () => fireEvent.click(screen.getByRole('button', { name: /查询/ }))

beforeEach(() => {
  localStorage.clear()
  mockExplain.mockReset()
  // 默认成功响应
  mockExplain.mockResolvedValue(makeResponse())
})

describe('OntologyQueryDashboard', () => {
  it('1. 页面正常加载（标题 + 示例问题 + 初始空状态）', () => {
    render(<OntologyQueryPage />)

    expect(screen.getByText('NeuroGraphIQ Query')).toBeTruthy()
    expect(screen.getByText('Ask neuroscience knowledge graph')).toBeTruthy()
    expect(screen.getByText('请输入问题')).toBeTruthy()
    expect(screen.getByText('海马有哪些亚区？')).toBeTruthy()
    expect(screen.getByText('连接海马的脑区有哪些？')).toBeTruthy()
    expect(screen.getByText('海马参与哪些回路？')).toBeTruthy()
    expect(screen.getByText('海马有哪些细胞和分子？')).toBeTruthy()
  })

  it('2. 输入问题后提交，调用 explain API', async () => {
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些连接？')
    fireEvent.click(screen.getByRole('button', { name: /查询/ }))

    expect(mockExplain).toHaveBeenCalledWith('海马有哪些连接？', expect.anything())
    expect(await screen.findByText('Query Summary')).toBeTruthy()
  })

  it('3. 结果显示实体卡片（Query Summary + Recognized Entity）', async () => {
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()

    // Query Summary 的 Entity 指标 + 右侧 Recognized Entity
    expect(await screen.findByText('Query Summary')).toBeTruthy()
    expect(screen.getAllByText('海马').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('ng:br:hippocampus').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Recognized Entity')).toBeTruthy()
    expect(screen.getAllByText('语义置信度').length).toBeGreaterThanOrEqual(2)
    expect(screen.getAllByText('90%').length).toBeGreaterThanOrEqual(2)
  })

  it('4. 结果显示表格（置信度降序 + Tab 切换）', async () => {
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()

    expect(await screen.findByText('Evidence Summary')).toBeTruthy()
    expect(screen.getByText('结构连接')).toBeTruthy()

    const table = () => screen.getByRole('table')
    expect(within(table()).getByText('内嗅皮层')).toBeTruthy()
    expect(within(table()).getByText('连接组学数据')).toBeTruthy()

    // 置信度降序：第一行是 92% 的连接项
    const rows = within(table()).getAllByRole('row')
    expect(rows[1].textContent).toContain('92%')
    expect(rows[1].textContent).toContain('内嗅皮层')

    // 相关回路 Tab：只看回路
    fireEvent.click(screen.getByRole('tab', { name: /相关回路/ }))
    expect(screen.getByText('海马-前额叶记忆回路')).toBeTruthy()
    expect(within(table()).queryByText('内嗅皮层')).toBeNull()
  })

  it('5. 未识别实体 → unresolved 空状态 + warnings', async () => {
    mockExplain.mockResolvedValue(
      makeResponse({
        query_result: {
          intent: 'unresolved',
          entity: null,
          results: [],
          confidence: 0,
          warnings: ['未找到标准脑区：颞叶内部区域'],
          source_entities: [],
        },
      }),
    )
    render(<OntologyQueryPage />)

    typeQuestion('颞叶内部区域')
    submit()

    expect(await screen.findByText('未找到匹配脑区')).toBeTruthy()
    expect(screen.getByText('未找到标准脑区：颞叶内部区域')).toBeTruthy()
    expect(screen.getByText('未识别实体 — 请尝试输入更明确的脑区名称')).toBeTruthy()
  })

  it('5b. 未识别实体但带 fuzzy 候选 → 候选 chips 展示，点击直接以候选名重新查询', async () => {
    mockExplain.mockResolvedValue(
      makeResponse({
        query_result: {
          intent: 'unresolved',
          entity: null,
          results: [],
          confidence: 0,
          warnings: ['「基底节」未与标准脑区完全匹配，找到 1 个候选（未自动选择，供消歧）：基底前脑。'],
          source_entities: [{ candidate: '基底前脑', confidence: 0.5 }],
        },
      }),
    )
    render(<OntologyQueryPage />)

    typeQuestion('基底节')
    submit()

    expect(await screen.findByText('候选脑区（未自动选择，点击直接查询）')).toBeTruthy()
    const chip = screen.getByRole('button', { name: /基底前脑/ })
    expect(chip.textContent).toContain('50%')

    fireEvent.click(chip)
    expect(mockExplain).toHaveBeenLastCalledWith('基底前脑', expect.anything())
    expect((screen.getByLabelText('自然语言问题') as HTMLTextAreaElement).value).toBe('基底前脑')
  })

  it('6. 快捷问题点击 → 直接执行查询', async () => {
    render(<OntologyQueryPage />)

    fireEvent.click(screen.getByRole('button', { name: '海马有哪些亚区？' }))

    expect(mockExplain).toHaveBeenCalledWith('海马有哪些亚区？', expect.anything())
    expect(await screen.findByText('Query Summary')).toBeTruthy()
    // 输入框同步填入
    expect((screen.getByLabelText('自然语言问题') as HTMLTextAreaElement).value).toBe('海马有哪些亚区？')
  })

  it('7. 点击结果行 → 跳转 Ontology Browser 详情', async () => {
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()
    await screen.findByText('Query Summary')

    // 连接行 → 跳转对端脑区（内嗅皮层 region）
    fireEvent.click(within(screen.getByRole('table')).getByText('内嗅皮层'))
    expect(window.location.hash).toContain('tab=browser')
    expect(window.location.hash).toContain('entity_type=region')
    expect(window.location.hash).toContain(encodeURIComponent('r-entorhinal'))
  })

  it('8. AI 幻觉警告在结果页展示', async () => {
    mockExplain.mockResolvedValue(
      makeResponse({
        explanation: {
          ...makeResponse().explanation,
          hallucination_warning: ['颞极'],
        },
      }),
    )
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()

    const alert = await screen.findByRole('alert')
    expect(within(alert).getByText('颞极')).toBeTruthy()
  })

  it('9. 查询失败 → Error + Retry 重新查询', async () => {
    mockExplain.mockRejectedValueOnce(new Error('LLM 服务不可用'))
    render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()

    expect((await screen.findByRole('alert')).textContent).toContain('LLM 服务不可用')
    fireEvent.click(screen.getByRole('button', { name: /Retry/ }))
    expect(await screen.findByText('Query Summary')).toBeTruthy()
  })

  it('10. 最近查询写入 localStorage 并展示', async () => {
    const { unmount } = render(<OntologyQueryPage />)

    typeQuestion('海马有哪些功能？')
    submit()
    await screen.findByText('Query Summary')

    const saved = JSON.parse(localStorage.getItem('ngiq.ontology-query.recent') ?? '[]')
    expect(saved).toEqual(['海马有哪些功能？'])

    unmount()
    render(<OntologyQueryPage />)
    expect(screen.getByText('最近查询')).toBeTruthy()
    expect(screen.getByRole('button', { name: /海马有哪些功能/ })).toBeTruthy()
  })

  it('11. 最近查询去重且最多 5 条', async () => {
    mockExplain.mockImplementation(question =>
      Promise.resolve(makeResponse({ question: String(question) })),
    )
    const { unmount } = render(<OntologyQueryPage />)

    const queries = ['问一', '问二', '问三', '问四', '问五', '问一']
    for (const q of queries) {
      typeQuestion(q)
      submit()
      await screen.findByText('Query Summary')
    }

    const saved = JSON.parse(localStorage.getItem('ngiq.ontology-query.recent') ?? '[]')
    expect(saved).toEqual(['问一', '问五', '问四', '问三', '问二'])

    unmount()
    render(<OntologyQueryPage />)
    expect(screen.getAllByRole('button', { name: /问/ })).toHaveLength(5)
  })
})

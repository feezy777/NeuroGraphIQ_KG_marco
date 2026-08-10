import { describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { PaperEvidenceView } from './PaperEvidenceView'
import type { ClaimComponent, WorkbenchPassage } from './types'

const COMPONENTS: ClaimComponent[] = [
  { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
  { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
]

const PASSAGES: WorkbenchPassage[] = [
  {
    hash: 'h1',
    paper_id: 'paper-1',
    paper_passage_id: 'pp1',
    source_scope: 'fulltext',
    section_title: 'Results',
    paragraph_index: 3,
    paragraph_id: 'par-3',
    passage: 'We observed that R1 projects to R2 in the macaque.',
    translation_zh: null,
    direction: 'supports',
    evidence_level: 'direct',
    reason: '直接描述了 R1 到 R2 的投射',
    confidence: 0.9,
    semantic_confidence: 0.87,
    source_locator: 'Results §3',
    source_verified: true,
    source_verification_method: 'exact',
    supported_components: ['relation'],
  },
  {
    hash: 'h2',
    paper_id: 'paper-1',
    paper_passage_id: 'pp2',
    source_scope: 'abstract',
    section_title: null,
    paragraph_index: null,
    paragraph_id: null,
    passage: 'A secondary passage without verification.',
    translation_zh: null,
    direction: 'supports',
    evidence_level: 'indirect',
    reason: '',
    confidence: 0.5,
    semantic_confidence: null,
    source_locator: null,
    source_verified: false,
    source_verification_method: null,
    supported_components: [],
  },
]

const PAPER = {
  paperId: 'paper-1',
  pmid: '12345678',
  doi: '10.1234/test',
  title: 'A Study of R1 to R2 Projection',
  journal: 'Brain Journal',
  year: '2024',
}

function renderView(overrides?: { onTogglePassage?: (hash: string, checked: boolean) => void; selectedHashes?: Set<string> }) {
  const onBack = vi.fn()
  const onTogglePassage = overrides?.onTogglePassage ?? vi.fn()
  render(
    <PaperEvidenceView
      paper={PAPER}
      components={COMPONENTS}
      passages={PASSAGES}
      selectedHashes={overrides?.selectedHashes ?? new Set()}
      onTogglePassage={onTogglePassage}
      onBack={onBack}
    />,
  )
  return { onBack, onTogglePassage }
}

describe('PaperEvidenceView', () => {
  afterEach(cleanup)

  it('顶部渲染 ← 返回论文列表,点击触发 onBack', () => {
    const { onBack } = renderView()
    const back = screen.getByTestId('evidence-paper-back')
    expect(back.textContent).toContain('返回论文列表')
    fireEvent.click(back)
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('Paper Summary 展示标题/期刊/PMID/DOI', () => {
    renderView()
    expect(screen.getByText('A Study of R1 to R2 Projection')).toBeTruthy()
    expect(screen.getByText(/Brain Journal · 2024/)).toBeTruthy()
    expect(screen.getByText(/PMID 12345678 · DOI 10\.1234\/test/)).toBeTruthy()
  })

  it('Claim Coverage 组件表:支持的 ✓ / 未覆盖的 ○,右下角 Coverage N/M', () => {
    renderView()
    const coverage = screen.getByTestId('evidence-paper-coverage')
    // relation 被已核验片段支持 → ✓;source_region 未覆盖 → ○
    expect(coverage.textContent).toContain('源脑区')
    expect(coverage.textContent).toContain('连接关系')
    const rows = screen.getAllByTestId('evidence-coverage-row')
    expect(rows).toHaveLength(2)
    expect(rows[0].textContent).toContain('○')
    expect(rows[1].textContent).toContain('✓')
    expect(coverage.textContent).toContain('Coverage 1/2')
  })

  it('候选佐证原文复用 PassageEvidenceCard(readOnly:无翻译/证据等级编辑控件)', () => {
    renderView()
    expect(screen.getByText('候选佐证原文')).toBeTruthy()
    expect(screen.getByText('We observed that R1 projects to R2 in the macaque.')).toBeTruthy()
    // readOnly:不渲染翻译 textarea / 证据等级 select / 组件勾选
    expect(screen.queryByPlaceholderText('中文翻译（可编辑）')).toBeNull()
    expect(screen.queryByText('证据等级')).toBeNull()
  })

  it('已核验片段可勾选(onTogglePassage),未核验片段复选框禁用', () => {
    const { onTogglePassage } = renderView()
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes).toHaveLength(2)
    expect((boxes[0] as HTMLInputElement).disabled).toBe(false)
    expect((boxes[1] as HTMLInputElement).disabled).toBe(true)
    fireEvent.click(boxes[0])
    expect(onTogglePassage).toHaveBeenCalledWith('h1', true)
  })

  it('DeepSeek reason / semantic confidence 为低层级信息,展示在片段尾部', () => {
    renderView()
    expect(screen.getByText(/模型理由：直接描述了 R1 到 R2 的投射/)).toBeTruthy()
    expect(screen.getByText(/DeepSeek semantic confidence：0.87/)).toBeTruthy()
  })

  it('段落详细信息来源「详细信息」折叠(paragraph_id / 校验方式)', () => {
    renderView()
    fireEvent.click(screen.getAllByText('详细信息')[0])
    expect(screen.getByText(/paragraph_id: par-3/)).toBeTruthy()
    expect(screen.getByText(/校验方式: exact/)).toBeTruthy()
  })
})

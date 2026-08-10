import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvidenceCenterPage } from './EvidenceCenterPage'

vi.mock('../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn().mockResolvedValue({ items: [] }),
  listEvidencePapers: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  listPaperEvidenceTaskItems: vi.fn().mockResolvedValue({ items: [] }),
  getEvidenceTarget: vi.fn().mockResolvedValue(null),
  searchPaperEvidence: vi.fn().mockResolvedValue({ target_info: {}, papers: [] }),
  extractSelectedPaperEvidence: vi.fn().mockResolvedValue({ results: [] }),
  listPaperEvidence: vi.fn().mockResolvedValue({ items: [] }),
  attachPaperEvidencePreview: vi.fn().mockResolvedValue({}),
  attachPaperEvidence: vi.fn().mockResolvedValue({}),
  rollbackPaperEvidence: vi.fn().mockResolvedValue({}),
  translateEvidenceText: vi.fn().mockResolvedValue({ translated: '' }),
  saveTaskItemDraft: vi.fn().mockResolvedValue({ server_revision: 0 }),
  validatePassageSelection: vi.fn().mockResolvedValue({ source_verified: true }),
}))

describe('EvidenceCenterPage', () => {
  beforeEach(() => {
    sessionStorage.clear()
  })

  afterEach(() => { cleanup(); window.location.hash = ''; sessionStorage.clear() })

  it('渲染五模块导航与默认说明句', () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    expect(screen.getByText('佐证任务')).toBeTruthy()
    expect(screen.getByText('论文库')).toBeTruthy()
    expect(screen.getByText('证据候选')).toBeTruthy()
    expect(screen.getByText('人工审核')).toBeTruthy()
    expect(screen.getByText('证据晋升')).toBeTruthy()
  })

  it('模块导航切换更新 URL 与内容区', async () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterPage />)
    fireEvent.click(screen.getByText('论文库'))
    await waitFor(() => expect(window.location.hash).toContain('module=papers'))
    expect(screen.getByText('管理系统已经获取和解析的真实论文资源。')).toBeTruthy()
    fireEvent.click(screen.getByText('返回数据中心'))
    await waitFor(() => expect(window.location.hash).toContain('/data-center'))
  })

  it.each([
    { module: 'papers', selector: '.paper-module', text: /暂无论文/ },
    { module: 'candidates', selector: '.evidence-candidates', text: /请先在「佐证任务」中打开一个任务/ },
    { module: 'review', selector: '.evidence-review', text: /请先从「佐证任务」或「证据候选」进入一个目标对象/ },
    { module: 'promotion', selector: '.evidence-promotion', text: /请先从「佐证任务」或「证据候选」进入一个目标对象/ },
  ])('五模块接线:module=$module 渲染对应模块', async ({ module, selector, text }) => {
    window.location.hash = `#/evidence-center?module=${module}`
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(container.querySelector(selector)).toBeTruthy())
    expect(screen.getByText(text)).toBeTruthy()
  })
})

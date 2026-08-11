import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import * as endpoints from '../../../api/endpoints'
import { EvidenceCenterProvider } from '../EvidenceCenterContext'
import { RightPanel } from '../components/RightPanel'
import { EvidenceTasksModule } from './EvidenceTasksModule'

vi.mock('../../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
}))

const TASK = {
  id: 't1', target_type: 'connection', name: '任务一', status: 'pending',
  total_items: 2, processed_items: 0, awaiting_review_items: 2, failed_items: 0,
  review_status: 'not_started', granularity_level: 'macro',
  estimated_target_count: 2, materialized_target_count: 2,
  scope: 'filter', mode: 'existence', max_papers_per_object: 3,
  created_at: '2026-08-10T00:00:00Z', created_by: null,
  started_at: null, finished_at: null, error_message: null, materialization_status: 'completed',
  materialization_cursor: null, materialization_error: null, confidence_lt: null,
  only_oa: false, stop_after_strong_support: false, summary: null,
  scope_type: 'filter', filter_snapshot: null, versions: null,
}

/** 匹配 "标签 <b>值</b>" 结构的统计文本(直接文本子节点不含 <b> 内数值) */
const stat = (label: string, value: number) =>
  screen.getByText((_content, el) => el?.textContent === `${label} ${value}`)

/** 在 Task Summary 内匹配 "标签 <b>值</b>" 结构(避免与任务行统计重复匹配) */
const summaryStat = (label: string, value: number) =>
  within(screen.getByTestId('evidence-task-summary'))
    .getByText((_content, el) => el?.textContent === `${label} ${value}`)

/** 模块 + 右栏 Task Summary 组合渲染(与页面级 EvidenceCenterPage 接线一致) */
const renderWithRightPanel = () =>
  render(
    <EvidenceCenterProvider>
      <EvidenceTasksModule />
      <RightPanel module="tasks" />
    </EvidenceCenterProvider>,
  )

describe('EvidenceTasksModule', () => {
  afterEach(() => { cleanup(); window.location.hash = '' })
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [TASK], total: 1 })
    vi.mocked(endpoints.previewEvidenceBatchScope).mockResolvedValue({ estimated_target_count: 2, over_limit: false, message: null })
    vi.mocked(endpoints.createPaperEvidenceBatch).mockResolvedValue({ task_id: 'new1', target_count: 2, skipped_active_targets: 0, auto_started: true })
  })

  it('渲染任务列表与状态分组', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    // 状态分组标题
    expect(screen.getByText('待处理')).toBeTruthy()
    // 任务行:对象类型 / 任务级数字(待审=2) / 佐证数(待审+已处理=2)
    expect(screen.getByText('connection')).toBeTruthy()
    expect(stat('待审', 2)).toBeTruthy()
    expect(stat('佐证数', 2)).toBeTruthy()
    expect(stat('已处理', 0)).toBeTruthy()
    expect(stat('失败数', 0)).toBeTruthy()
    // 预处理/审核状态
    expect(screen.getByText('预处理 · 待预处理')).toBeTruthy()
    expect(screen.getByText('审核 · 未开始审核')).toBeTruthy()
  })

  it('创建批量预处理打开对话框,可关闭', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('创建批量预处理')).toBeTruthy())
    fireEvent.click(screen.getByText('创建批量预处理'))
    expect(screen.getByTestId('create-batch-dialog')).toBeTruthy()
    fireEvent.click(screen.getByText('关闭'))
    expect(screen.queryByTestId('create-batch-dialog')).toBeNull()
  })

  it('多状态任务进入对应分组(待人工审核/已审核/失败)', async () => {
    const tAwaiting = { ...TASK, id: 't2', name: '任务二', status: 'completed', awaiting_review_items: 3, review_status: 'in_progress' }
    const tReviewed = { ...TASK, id: 't4', name: '任务四', status: 'completed', awaiting_review_items: 0, review_status: 'completed' }
    const tFailed = { ...TASK, id: 't3', name: '任务三', status: 'failed', failed_items: 2, awaiting_review_items: 0 }
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [TASK, tAwaiting, tReviewed, tFailed], total: 4 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务四')).toBeTruthy())
    expect(screen.getByText('待处理')).toBeTruthy()
    expect(screen.getByText('待人工审核')).toBeTruthy()
    expect(screen.getByText('已审核')).toBeTruthy()
    expect(screen.getByText('失败')).toBeTruthy()
    // 已完成组:无任务落组(任务四被"已审核"优先吸收)
    expect(screen.queryByText('已完成')).toBeNull()
  })

  it('打开任务跳转候选模块(URL 带 task_id)', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByText('打开任务'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
  })

  it('打开任务清除 URL 残留的陈旧 target(避免审核/晋升打开上一任务的对象)', async () => {
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1&target_type=connection&target_id=stale-target'
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByText('打开任务'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
    expect(window.location.hash).not.toContain('target_type=')
    expect(window.location.hash).not.toContain('target_id=stale-target')
  })

  it('开始人工处理跳转候选模块', async () => {
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByText('开始人工处理'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
  })

  it('加载失败显示错误并可重试', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockRejectedValueOnce(new Error('503 backend down'))
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/任务加载失败/)).toBeTruthy())
    fireEvent.click(screen.getByText('重试'))
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
  })

  it('空列表显示空态提示', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText(/暂无佐证任务/)).toBeTruthy())
  })

  // ─── V2-S5 右栏 Task Summary ───

  it('未选中任务时右栏 Task Summary 显示引导提示', async () => {
    renderWithRightPanel()
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    expect(screen.getByTestId('evidence-task-summary')).toBeTruthy()
    expect(screen.getByText(/选择一个任务/)).toBeTruthy()
  })

  it('选中任务后右栏 Task Summary 显示进度计数条/状态/任务信息,行高亮', async () => {
    renderWithRightPanel()
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-row-t1'))
    const summary = screen.getByTestId('evidence-task-summary')
    // 名称与类型
    expect(within(summary).getByText('任务一')).toBeTruthy()
    expect(within(summary).getByText('connection')).toBeTruthy()
    // 状态 chips(与任务行内文本重复,限定在摘要内断言)
    expect(within(summary).getByText('预处理 · 待预处理')).toBeTruthy()
    expect(within(summary).getByText('审核 · 未开始审核')).toBeTruthy()
    // 进度计数条:processed=0 / awaiting=2 / failed=0(总数为 2)
    expect(within(summary).getByTestId('evidence-progress-bar')).toBeTruthy()
    expect((within(summary).getByTestId('evidence-progress-ok') as HTMLSpanElement).style.width).toBe('0%')
    expect((within(summary).getByTestId('evidence-progress-warn') as HTMLSpanElement).style.width).toBe('100%')
    expect((within(summary).getByTestId('evidence-progress-bad') as HTMLSpanElement).style.width).toBe('0%')
    expect(summaryStat('已处理', 0)).toBeTruthy()
    expect(summaryStat('待审', 2)).toBeTruthy()
    expect(summaryStat('失败', 0)).toBeTruthy()
    expect(summaryStat('总数', 2)).toBeTruthy()
    // 任务信息:模式/粒度/创建时间
    expect(within(summary).getByText('模式')).toBeTruthy()
    expect(within(summary).getByText('存在性')).toBeTruthy()
    expect(within(summary).getByText('粒度')).toBeTruthy()
    expect(within(summary).getByText('macro')).toBeTruthy()
    expect(within(summary).getByText('创建时间')).toBeTruthy()
    expect(within(summary).getByText('2026-08-10 00:00')).toBeTruthy()
    // 任务行选中高亮
    expect(screen.getByTestId('evidence-task-row-t1').className).toContain('evidence-task-row-selected')
  })

  it('TaskSummary [开始人工处理] 跳转候选模块(URL task_id)', async () => {
    renderWithRightPanel()
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-row-t1'))
    fireEvent.click(within(screen.getByTestId('evidence-task-summary')).getByText('开始人工处理'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).toContain('task_id=t1')
  })

  it('TaskSummary [创建批量预处理] 打开模块对话框,[刷新] 重新加载任务列表', async () => {
    renderWithRightPanel()
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-row-t1'))
    const summary = screen.getByTestId('evidence-task-summary')
    // 创建批量预处理:右栏按钮触发模块内对话框
    fireEvent.click(within(summary).getByText('创建批量预处理'))
    expect(screen.getByTestId('create-batch-dialog')).toBeTruthy()
    fireEvent.click(within(screen.getByTestId('create-batch-dialog')).getByText('关闭'))
    expect(screen.queryByTestId('create-batch-dialog')).toBeNull()
    // 刷新:重新请求任务列表
    const callsBefore = vi.mocked(endpoints.listPaperEvidenceTasks).mock.calls.length
    fireEvent.click(within(summary).getByText('刷新'))
    await waitFor(() =>
      expect(vi.mocked(endpoints.listPaperEvidenceTasks).mock.calls.length).toBeGreaterThan(callsBefore),
    )
  })

  it('URL 携带 task_id 时自动选中任务并在右栏显示摘要', async () => {
    window.location.hash = '#/evidence-center?module=tasks&task_id=t1'
    renderWithRightPanel()
    const summary = await screen.findByTestId('evidence-task-summary')
    await waitFor(() => expect(within(summary).getByText('任务一')).toBeTruthy())
    expect(screen.getByTestId('evidence-task-row-t1').className).toContain('evidence-task-row-selected')
    expect(within(summary).getByText('存在性')).toBeTruthy()
    expect(summaryStat('总数', 2)).toBeTruthy()
  })

  // ─── U4:模块标题体系 + TaskSummary 视觉语言一致 ───

  it('模块标题体系:工具栏 h3「任务列表」+ 说明句 + 分组白卡', async () => {
    const { container } = render(<EvidenceCenterProvider><EvidenceTasksModule /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    // 与论文库/人工审核同语言的工具栏标题
    expect(container.querySelector('.evidence-task-toolbar-title h3')?.textContent).toBe('任务列表')
    expect(screen.getByText(/共 1 个任务/)).toBeTruthy()
    // 分组卡:白底 + 标题 + 数量徽标(与晋升模块同语言)
    const group = container.querySelector('.evidence-task-group') as HTMLElement
    expect(group).toBeTruthy()
    expect(group.querySelector('.evidence-task-group-title')?.textContent).toBe('待处理')
    expect(group.querySelector('.evidence-task-group-count')?.textContent).toBe('1')
    // 任务行卡
    expect(container.querySelector('.evidence-task-row')).toBeTruthy()
  })

  it('TaskSummary 视觉语言:标题/进度区/分隔线/统计卡 + Primary 仅「开始人工处理」', async () => {
    renderWithRightPanel()
    await waitFor(() => expect(screen.getByText('任务一')).toBeTruthy())
    fireEvent.click(screen.getByTestId('evidence-task-row-t1'))
    const summary = screen.getByTestId('evidence-task-summary')
    // 标题
    expect(within(summary).getByText('任务摘要')).toBeTruthy()
    // 进度区 + 分隔线 + 统计卡(与右栏其他面板同语言)
    expect(within(summary).getByTestId('evidence-progress-bar')).toBeTruthy()
    expect(summary.querySelector('.evidence-section-divider')).toBeTruthy()
    expect(summary.querySelector('.evidence-summary-stats')).toBeTruthy()
    // Primary 唯一:「开始人工处理」,创建批量预处理/刷新为次要
    const primaryBtns = summary.querySelectorAll('.btn-primary')
    expect(primaryBtns.length).toBe(1)
    expect((primaryBtns[0] as HTMLElement).textContent).toContain('开始人工处理')
    const createBtn = within(summary).getByText('创建批量预处理') as HTMLButtonElement
    expect(createBtn.className).not.toContain('btn-primary')
  })
})

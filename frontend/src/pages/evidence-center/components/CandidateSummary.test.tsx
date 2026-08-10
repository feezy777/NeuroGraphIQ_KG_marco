import { describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { CandidateSummary, type CandidateSummaryData } from './CandidateSummary'

const DATA: CandidateSummaryData = {
  claimText: 'R1 投射到 R2 且影响功能',
  foundPapers: 5,
  extractedPapers: 3,
  verifiedPassages: 2,
  selectedPassages: 2,
  coverageRatio: 0.5,
  direction: 'supports',
  modelAssessment: '支持连接存在',
}

describe('CandidateSummary', () => {
  afterEach(cleanup)

  it('渲染当前 Claim / 找到论文 N / AI 提取 N / 已核验 N / Coverage / 模型判断', () => {
    render(<CandidateSummary data={DATA} onEnterReview={() => {}} />)
    expect(screen.getByText('候选摘要')).toBeTruthy()
    expect(screen.getByText('R1 投射到 R2 且影响功能')).toBeTruthy()
    expect(screen.getByText('找到论文')).toBeTruthy()
    expect(screen.getByText('5')).toBeTruthy()
    expect(screen.getByText('AI 提取论文')).toBeTruthy()
    expect(screen.getByText('3')).toBeTruthy()
    expect(screen.getByText('已核验片段')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy()
    expect(screen.getByText('Coverage')).toBeTruthy()
    expect(screen.getByText('50%')).toBeTruthy()
    expect(screen.getByText('模型判断')).toBeTruthy()
    expect(screen.getByText('支持')).toBeTruthy()
    expect(screen.getByText(/模型评估: 支持连接存在/)).toBeTruthy()
  })

  it('无数据时显示占位文案', () => {
    render(<CandidateSummary data={null} onEnterReview={() => {}} />)
    expect(screen.getByText('候选摘要')).toBeTruthy()
    expect(screen.getByText(/暂无候选数据/)).toBeTruthy()
  })

  it('点击 [进入人工审核] 触发 onEnterReview', () => {
    const onEnterReview = vi.fn()
    render(<CandidateSummary data={DATA} onEnterReview={onEnterReview} />)
    fireEvent.click(screen.getByRole('button', { name: /进入人工审核/ }))
    expect(onEnterReview).toHaveBeenCalledTimes(1)
  })

  it('零选中片段时 [进入人工审核] 禁用并提示先勾选已核验片段', () => {
    render(<CandidateSummary data={{ ...DATA, selectedPassages: 0 }} onEnterReview={() => {}} />)
    const btn = screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toContain('请先勾选已核验的候选片段')
  })

  it('已勾选片段时 [进入人工审核] 可用且按钮显示选中数', () => {
    render(<CandidateSummary data={DATA} onEnterReview={() => {}} />)
    const btn = screen.getByRole('button', { name: /进入人工审核（2）/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
  })

  it('禁止项:无 Reviewer Confidence / Direction 输入与 attach 控件', () => {
    render(<CandidateSummary data={DATA} onEnterReview={() => {}} />)
    expect(screen.queryByText(/Reviewer Confidence/i)).toBeNull()
    expect(screen.queryByText(/Reviewer Direction/i)).toBeNull()
    expect(screen.queryByText(/确认入库|attach|确认论文证据/i)).toBeNull()
    expect(screen.queryByRole('slider')).toBeNull()
    expect(screen.queryAllByRole('textbox')).toHaveLength(0)
  })
})

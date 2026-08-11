import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { PaperStatusSummary, type CandidateStats } from './PaperStatusSummary'

const STATS: CandidateStats = {
  foundPapers: 5,
  extractedPapers: 3,
  verifiedPassages: 4,
  selectedPassages: 2,
  coverageRatio: 0.5,
  coverageSupported: 1,
  coverageRequired: 2,
  direction: 'supports',
  modelAssessment: '支持连接存在',
}

describe('PaperStatusSummary', () => {
  it('浅蓝状态条字段:找到论文 / AI提取 / 已核验 / Coverage N/M / 模型判断(方向+评估)', () => {
    render(<PaperStatusSummary stats={STATS} onEnterReview={vi.fn()} />)
    const bar = screen.getByTestId('evidence-stats-bar')
    expect(within(bar).getByTestId('evidence-stats-found').textContent).toBe('5')
    expect(within(bar).getByTestId('evidence-stats-extracted').textContent).toBe('3')
    expect(within(bar).getByTestId('evidence-stats-verified').textContent).toBe('4')
    expect(within(bar).getByTestId('evidence-stats-coverage').textContent).toBe('1/2')
    expect(within(bar).getByTestId('evidence-stats-direction').textContent).toBe('支持')
    expect(within(bar).getByText('支持连接存在')).toBeTruthy()
    expect(within(bar).getByText('模型判断')).toBeTruthy()
  })

  it('stats 为 null 时显示零值占位并禁用 [进入人工审核]', () => {
    render(<PaperStatusSummary stats={null} onEnterReview={vi.fn()} />)
    const bar = screen.getByTestId('evidence-stats-bar')
    expect(within(bar).getByTestId('evidence-stats-found').textContent).toBe('0')
    expect(within(bar).getByTestId('evidence-stats-coverage').textContent).toBe('—')
    expect((screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('Coverage 无必需组件时显示百分比', () => {
    render(
      <PaperStatusSummary
        stats={{ ...STATS, coverageRequired: 0, coverageRatio: 0.75 }}
        onEnterReview={vi.fn()}
      />,
    )
    expect(screen.getByTestId('evidence-stats-coverage').textContent).toBe('75%')
  })

  it('[进入人工审核] 勾选片段后可用并显示计数;点击触发 onEnterReview', () => {
    const onEnterReview = vi.fn()
    render(<PaperStatusSummary stats={STATS} onEnterReview={onEnterReview} />)
    const btn = screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    expect(btn.textContent).toContain('进入人工审核（2）')
    fireEvent.click(btn)
    expect(onEnterReview).toHaveBeenCalledTimes(1)
  })

  it('零选中时禁用并带提示 title', () => {
    render(<PaperStatusSummary stats={{ ...STATS, selectedPassages: 0 }} onEnterReview={vi.fn()} />)
    const btn = screen.getByRole('button', { name: /进入人工审核/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toContain('勾选已核验的候选片段')
  })
})

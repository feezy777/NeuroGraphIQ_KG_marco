import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ReviewerDecisionPanel, type ReviewerDecisionPanelProps } from './ReviewerDecisionPanel'

function baseProps(overrides: Partial<ReviewerDecisionPanelProps> = {}): ReviewerDecisionPanelProps {
  return {
    direction: 'supports',
    modelDirection: null,
    onDirectionChange: () => {},
    evidenceLevel: 'direct',
    onEvidenceLevelChange: () => {},
    confidence: '0.8',
    onConfidenceChange: () => {},
    note: '',
    onNoteChange: () => {},
    selectedCount: 0,
    preview: null,
    previewBusy: false,
    ...overrides,
  }
}

describe('ReviewerDecisionPanel 审核通过 guard', () => {
  it('零选中时禁用「审核通过」并提示先勾选片段', () => {
    render(<ReviewerDecisionPanel {...baseProps()} />)
    const btn = screen.getByTestId('ew-approve-btn') as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toBe('请先勾选已核验的候选片段')
  })

  it('零选中时点击不会触发 onApprove(避免写入 review_approved 产生 canPromote=false 卡死项)', () => {
    const onApprove = vi.fn()
    render(<ReviewerDecisionPanel {...baseProps({ onApprove })} />)
    fireEvent.click(screen.getByTestId('ew-approve-btn'))
    expect(onApprove).not.toHaveBeenCalled()
  })

  it('有选中片段时按钮启用、title 恢复「审核通过」并触发 onApprove', () => {
    const onApprove = vi.fn()
    render(<ReviewerDecisionPanel {...baseProps({ selectedCount: 2, onApprove })} />)
    const btn = screen.getByTestId('ew-approve-btn') as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    expect(btn.title).toBe('审核通过')
    fireEvent.click(btn)
    expect(onApprove).toHaveBeenCalledTimes(1)
  })

  it('驳回按钮不受零选中 guard 影响', () => {
    const onReject = vi.fn()
    render(<ReviewerDecisionPanel {...baseProps({ onReject })} />)
    const btn = screen.getByTestId('ew-reject-btn') as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    expect(onReject).toHaveBeenCalledTimes(1)
  })
})

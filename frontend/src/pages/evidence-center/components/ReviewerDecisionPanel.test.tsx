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

  it('置信度影响 5 格:Current/Reviewer/Rule/Maximum/Final(无 preview 本地计算)', () => {
    render(<ReviewerDecisionPanel {...baseProps({ currentConfidence: 0.7 })} />)
    expect(screen.getByText('置信度影响')).toBeTruthy()
    expect(screen.getByTestId('ew-impact-current').textContent).toBe('0.70')
    expect(screen.getByTestId('ew-impact-reviewer').textContent).toBe('0.80')
    expect(screen.getByTestId('ew-impact-rule').textContent).toBe('≤0.85')
    // Maximum = max(current, reviewer)(规则上限前中间值)
    expect(screen.getByTestId('ew-impact-maximum').textContent).toBe('0.80')
    expect(screen.getByTestId('ew-impact-final').textContent).toBe('0.80')
  })

  it('Maximum 格:reviewer 高于 current 时显示 reviewer;contradicts 时仍为 max 不随 final', () => {
    render(<ReviewerDecisionPanel {...baseProps({ direction: 'contradicts', currentConfidence: 0.7 })} />)
    // contradicts → final = current(0.70),但 Maximum = max(0.7, 0.8) = 0.80
    expect(screen.getByTestId('ew-impact-maximum').textContent).toBe('0.80')
    expect(screen.getByTestId('ew-impact-final').textContent).toBe('0.70')
  })

  it('preview 可用时 Maximum 取 max(preview.current, preview.reviewer)', () => {
    render(<ReviewerDecisionPanel {...baseProps({
      currentConfidence: 0.7,
      preview: {
        target_type: 'connection', target_id: 'r1-r2',
        current_confidence: 0.6, direction: 'supports', reviewer_confidence: 0.8,
        final_confidence: 0.85, cap: 0.85, selected_passage_count: 1,
        duplicate_passage_count: 0, evidence_text_preview: '...', allow: true, block_reasons: [],
      },
    })} />)
    expect(screen.getByTestId('ew-impact-maximum').textContent).toBe('0.80')
  })
})

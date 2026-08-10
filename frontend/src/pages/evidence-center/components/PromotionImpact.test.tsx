import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { AttachPreviewResponse } from '../../../api/endpoints'
import { PromotionImpact } from './PromotionImpact'

const PREVIEW: AttachPreviewResponse = {
  target_type: 'connection',
  target_id: 'r1-r2',
  current_confidence: 0.6,
  direction: 'supports',
  reviewer_confidence: 0.8,
  final_confidence: 0.85,
  cap: 0.85,
  selected_passage_count: 1,
  duplicate_passage_count: 0,
  evidence_text_preview: '...',
  allow: true,
  block_reasons: [],
}

describe('PromotionImpact', () => {
  it('preview 可用时以服务端结果为准(KG 当前/晋升后)', () => {
    render(
      <PromotionImpact
        direction="supports"
        currentConfidence={0.6}
        reviewerConfidence={0.8}
        preview={PREVIEW}
        evidenceNewCount={1}
        passagesNewCount={2}
      />,
    )
    expect(screen.getByTestId('pi-current').textContent).toBe('0.60')
    expect(screen.getByTestId('pi-final').textContent).toBe('0.85')
  })

  it('无 preview 时本地公式 + 钳制:supports 上限 0.85,reviewer >1 钳到 1', () => {
    render(
      <PromotionImpact direction="supports" currentConfidence={0.7} reviewerConfidence={1.5} evidenceNewCount={1} passagesNewCount={1} />,
    )
    expect(screen.getByTestId('pi-final').textContent).toBe('0.85')
  })

  it('弱证据不改变:reviewer < current → final = current(不降低)', () => {
    render(
      <PromotionImpact direction="supports" currentConfidence={0.7} reviewerConfidence={0.5} evidenceNewCount={1} passagesNewCount={1} />,
    )
    expect(screen.getByTestId('pi-final').textContent).toBe('0.70')
  })

  it('contradicts 不自动修改置信度:final = current', () => {
    render(
      <PromotionImpact direction="contradicts" currentConfidence={0.7} reviewerConfidence={0.9} evidenceNewCount={1} passagesNewCount={1} />,
    )
    expect(screen.getByTestId('pi-final').textContent).toBe('0.70')
  })

  it('字段:方向标签 / Evidence 新增 / Passages 新增 / 状态 human_verified', () => {
    render(
      <PromotionImpact direction="partial" currentConfidence={0.7} reviewerConfidence={0.7} evidenceNewCount={1} passagesNewCount={3} />,
    )
    expect(screen.getByText('部分支持')).toBeTruthy()
    expect(screen.getByTestId('pi-evidence-new').textContent).toBe('+1')
    expect(screen.getByTestId('pi-passages-new').textContent).toBe('+3')
    expect(screen.getByTestId('pi-status').textContent).toContain('human_verified')
  })

  it('sticky 操作:确认晋升/退回人工审核 触发回调;canPromote=false 时确认禁用', () => {
    const onReturn = vi.fn()
    const onPromote = vi.fn()
    const { rerender } = render(
      <PromotionImpact
        direction="supports"
        currentConfidence={0.7}
        reviewerConfidence={0.8}
        evidenceNewCount={1}
        passagesNewCount={1}
        canPromote
        onReturnToReview={onReturn}
        onPromote={onPromote}
      />,
    )
    const promote = screen.getByTestId('pi-promote-btn') as HTMLButtonElement
    expect(promote.disabled).toBe(false)
    expect(promote.textContent).toContain('确认晋升')
    fireEvent.click(promote)
    expect(onPromote).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByTestId('pi-return-btn'))
    expect(onReturn).toHaveBeenCalledTimes(1)
    // 无草稿/无已核验片段 → 确认晋升禁用
    rerender(
      <PromotionImpact
        direction="supports"
        currentConfidence={0.7}
        reviewerConfidence={0.8}
        evidenceNewCount={1}
        passagesNewCount={0}
        canPromote={false}
        onReturnToReview={onReturn}
        onPromote={onPromote}
      />,
    )
    expect((screen.getByTestId('pi-promote-btn') as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByTestId('pi-return-btn') as HTMLButtonElement).disabled).toBe(false)
  })

  it('previewBusy 时显示计算中提示', () => {
    render(
      <PromotionImpact
        direction="supports"
        currentConfidence={0.7}
        reviewerConfidence={0.8}
        previewBusy
        evidenceNewCount={1}
        passagesNewCount={1}
      />,
    )
    expect(screen.getByText(/置信度预览/)).toBeTruthy()
  })
})

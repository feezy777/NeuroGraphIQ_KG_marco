import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import type { PaperEvidenceExtractionRun } from '../../../api/endpoints'
import { PaperExtractionProgress } from './PaperExtractionProgress'

function makeRun(overrides: Partial<PaperEvidenceExtractionRun> = {}): PaperEvidenceExtractionRun {
  return {
    id: 'run-1',
    target_type: 'connection',
    target_id: 't1',
    mode: 'function',
    status: 'running',
    total_items: 20,
    completed_items: 8,
    evidence_hit_items: 3,
    no_evidence_items: 4,
    failed_items: 1,
    requested_concurrency: 4,
    active_concurrency: 4,
    cancel_requested: false,
    created_at: '2026-08-12T00:00:00Z',
    updated_at: '2026-08-12T00:00:00Z',
    progress_percent: 40,
    items: [
      {
        id: 'i0',
        run_id: 'run-1',
        item_index: 0,
        title: 'Paper A',
        paper_json: {},
        status: 'completed',
        progress_percent: 100,
        attempt_count: 1,
        result_json: { passages: [{}, {}, {}] },
        stage_timings_json: {},
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'i1',
        run_id: 'run-1',
        item_index: 1,
        title: 'Paper B',
        paper_json: {},
        status: 'locating',
        progress_percent: 55,
        attempt_count: 1,
        stage_timings_json: {},
        updated_at: '2026-08-12T00:00:00Z',
      },
      {
        id: 'i2',
        run_id: 'run-1',
        item_index: 2,
        title: 'Paper C',
        paper_json: {},
        status: 'failed',
        progress_percent: 100,
        attempt_count: 1,
        error_message: 'timeout',
        stage_timings_json: {},
        updated_at: '2026-08-12T00:00:00Z',
      },
    ],
    ...overrides,
  }
}

describe('PaperExtractionProgress', () => {
  it('renders progress width and counters', () => {
    render(<PaperExtractionProgress run={makeRun()} onCancel={vi.fn()} onRetryFailed={vi.fn()} />)
    const bar = screen.getByRole('progressbar')
    expect(bar.getAttribute('aria-valuenow')).toBe('40')
    expect(screen.getByTestId('evidence-extraction-progress-meta').textContent).toContain('已完成 8/20 · 40%')
    expect(screen.getByTestId('evidence-extraction-progress-meta').textContent).toContain('命中 3')
    expect(screen.getByTestId('evidence-extraction-progress-meta').textContent).toContain('无证据 4')
    expect(screen.getByTestId('evidence-extraction-progress-meta').textContent).toContain('失败 1')
  })

  it('shows Chinese stage labels and cancel while running', () => {
    const onCancel = vi.fn()
    render(<PaperExtractionProgress run={makeRun()} onCancel={onCancel} onRetryFailed={vi.fn()} />)
    expect(screen.getByTestId('evidence-extraction-item-0').textContent).toContain('已命中 3 个片段')
    expect(screen.getByTestId('evidence-extraction-item-1').textContent).toContain('定位候选')
    expect(screen.getByTestId('evidence-extraction-item-2').textContent).toContain('失败')
    fireEvent.click(screen.getByTestId('evidence-extraction-cancel'))
    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('evidence-extraction-retry-failed')).toBeNull()
  })

  it('shows retry-failed only for terminal runs with failures', () => {
    const onRetry = vi.fn()
    render(
      <PaperExtractionProgress
        run={makeRun({ status: 'partially_failed', progress_percent: 100 })}
        onCancel={vi.fn()}
        onRetryFailed={onRetry}
      />,
    )
    expect(screen.queryByTestId('evidence-extraction-cancel')).toBeNull()
    fireEvent.click(screen.getByTestId('evidence-extraction-retry-failed'))
    expect(onRetry).toHaveBeenCalledTimes(1)
  })
})

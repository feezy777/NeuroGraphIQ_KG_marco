import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render } from '@testing-library/react'
import { EvidenceReviewModal } from './EvidenceReviewModal'
import { INITIAL_QUEUE_KEY } from '../evidence-center/evidenceCenterUrl'

const ITEM_A = {
  target_type: 'connection',
  target_id: '11111111-1111-1111-1111-111111111111',
  label: '连接 A',
  confidence: 0.42,
}
const ITEM_B = {
  target_type: 'connection',
  target_id: '22222222-2222-2222-2222-222222222222',
  label: '连接 B',
  confidence: 0.55,
}

describe('EvidenceReviewModal 兼容壳(跳转 Evidence Center)', () => {
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    sessionStorage.clear()
  })

  beforeEach(() => {
    sessionStorage.clear()
    window.location.hash = ''
  })

  it('open 时跳转 hash 含 /evidence-center 且 module=candidates', () => {
    render(<EvidenceReviewModal open onClose={vi.fn()} initialItems={[ITEM_A]} />)
    expect(window.location.hash).toContain('/evidence-center')
    expect(window.location.hash).toContain('module=candidates')
  })

  it('带 initialItems 时写入 sessionStorage initial-queue({ items, taskId })', () => {
    render(
      <EvidenceReviewModal open onClose={vi.fn()} initialItems={[ITEM_A, ITEM_B]} initialTaskId="task-9" />,
    )
    const raw = sessionStorage.getItem(INITIAL_QUEUE_KEY)
    expect(raw).toBeTruthy()
    expect(JSON.parse(raw as string)).toEqual({
      items: [ITEM_A, ITEM_B],
      taskId: 'task-9',
    })
  })

  it('首个对象写入 target_type / target_id，taskId 透传 task_id', () => {
    render(
      <EvidenceReviewModal open onClose={vi.fn()} initialItems={[ITEM_A, ITEM_B]} initialTaskId="task-9" />,
    )
    expect(window.location.hash).toContain(`target_type=${ITEM_A.target_type}`)
    expect(window.location.hash).toContain(`target_id=${ITEM_A.target_id}`)
    expect(window.location.hash).toContain('task_id=task-9')
  })

  it('onClose 在跳转后被调用', () => {
    const onClose = vi.fn()
    render(<EvidenceReviewModal open onClose={onClose} initialItems={[ITEM_A]} />)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('无 initialItems 时不写 initial-queue，仅带 task_id 跳转', () => {
    render(<EvidenceReviewModal open onClose={vi.fn()} initialTaskId="task-1" />)
    expect(sessionStorage.getItem(INITIAL_QUEUE_KEY)).toBeNull()
    expect(window.location.hash).toContain('module=candidates')
    expect(window.location.hash).toContain('task_id=task-1')
  })

  it('open=false 时不跳转、不写 storage、不调用 onClose', () => {
    const onClose = vi.fn()
    render(<EvidenceReviewModal open={false} onClose={onClose} initialItems={[ITEM_A]} />)
    expect(window.location.hash).toBe('')
    expect(sessionStorage.getItem(INITIAL_QUEUE_KEY)).toBeNull()
    expect(onClose).not.toHaveBeenCalled()
  })

  it('渲染为空(壳无业务 UI)', () => {
    const { container } = render(<EvidenceReviewModal open onClose={vi.fn()} initialItems={[ITEM_A]} />)
    expect(container.innerHTML).toBe('')
  })
})

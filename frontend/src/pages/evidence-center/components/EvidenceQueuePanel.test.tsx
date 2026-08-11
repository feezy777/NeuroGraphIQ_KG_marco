import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { EvidenceQueuePanel } from './EvidenceQueuePanel'
import type { QueueEntry } from './types'

const ENTRIES: QueueEntry[] = [
  { target_type: 'connection', target_id: 'a', label: '连接A', confidence: 0.8, status: 'awaiting_review', evidenceCount: 2 },
  { target_type: 'region', target_id: 'b', label: '脑区B', confidence: null, status: 'completed', evidenceCount: 0 },
  { target_type: 'region', target_id: 'c', label: '脑区C', confidence: 0.5, status: 'failed', evidenceCount: 1 },
]

describe('EvidenceQueuePanel', () => {
  it('渲染标题、数量徽标与 Tabs 计数;默认待审核 Tab 只显示未处理项且当前项高亮', () => {
    render(<EvidenceQueuePanel queue={ENTRIES} currentIndex={0} onSelect={() => {}} />)
    expect(screen.getByText('待处理对象')).toBeTruthy()
    expect(screen.getByTestId('evidence-queue-count').textContent).toBe('3')
    expect(screen.getByRole('tab', { name: /待审核/ }).textContent).toContain('1')
    expect(screen.getByRole('tab', { name: /已完成/ }).textContent).toContain('1')
    expect(screen.getByRole('tab', { name: /失败/ }).textContent).toContain('1')
    const items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(1)
    expect(items[0].textContent).toContain('连接A')
    expect(items[0].textContent).toContain('connection · 置信度 80%')
    expect(items[0].textContent).toContain('待审核')
    expect(items[0].textContent).toContain('2 证据')
    expect(items[0].className).toContain('evidence-queue-item-active')
  })

  it('切换 Tab 过滤已完成;勾选「只看未处理」叠加过滤后出现空态', () => {
    render(<EvidenceQueuePanel queue={ENTRIES} currentIndex={-1} onSelect={() => {}} />)
    fireEvent.click(screen.getByRole('tab', { name: /已完成/ }))
    let items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(1)
    expect(items[0].textContent).toContain('脑区B')
    expect(items[0].textContent).toContain('已完成')
    fireEvent.click(screen.getByText('只看未处理'))
    expect(screen.queryAllByTestId('evidence-queue-item')).toHaveLength(0)
    expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy()
  })

  it('待审核无匹配时显示空态(托盘图标/队列为空/当前没有待处理的对象);点击 [查看全部对象] 恢复全部条目', () => {
    const doneOnly: QueueEntry[] = [
      { target_type: 'region', target_id: 'b', label: '脑区B', confidence: null, status: 'completed', evidenceCount: 0 },
      { target_type: 'region', target_id: 'c', label: '脑区C', confidence: 0.5, status: 'failed', evidenceCount: 1 },
    ]
    const { container } = render(<EvidenceQueuePanel queue={doneOnly} currentIndex={-1} onSelect={() => {}} />)
    expect(screen.getByTestId('evidence-queue-empty')).toBeTruthy()
    expect(container.querySelector('.evidence-empty-icon svg')).toBeTruthy()
    expect(screen.getByText('队列为空')).toBeTruthy()
    expect(screen.getByText('当前没有待处理的对象')).toBeTruthy()
    const viewAll = screen.getByTestId('evidence-queue-view-all')
    expect(viewAll.textContent).toContain('查看全部对象')
    fireEvent.click(viewAll)
    expect(screen.queryByTestId('evidence-queue-empty')).toBeNull()
    expect(screen.getAllByTestId('evidence-queue-item')).toHaveLength(2)
  })

  it('当前项按原始队列下标高亮(过滤后仍正确)', () => {
    render(<EvidenceQueuePanel queue={ENTRIES} currentIndex={1} onSelect={() => {}} />)
    // 待审核 Tab 可见条目为 连接A(原始下标 0)≠ 当前项 1 → 不高亮
    expect(screen.getAllByTestId('evidence-queue-item')[0].className).not.toContain('evidence-queue-item-active')
    fireEvent.click(screen.getByRole('tab', { name: /已完成/ }))
    // 已完成 Tab 条目为 脑区B(原始下标 1)= 当前项 → 高亮
    expect(screen.getAllByTestId('evidence-queue-item')[0].className).toContain('evidence-queue-item-active')
  })

  it('点击条目触发 onSelect', () => {
    const onSelect = vi.fn()
    render(<EvidenceQueuePanel queue={ENTRIES} currentIndex={0} onSelect={onSelect} />)
    fireEvent.click(screen.getAllByTestId('evidence-queue-item')[0])
    expect(onSelect).toHaveBeenCalledWith(ENTRIES[0])
  })
})

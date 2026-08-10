import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { ObjectQueue } from './ObjectQueue'
import type { QueueEntry } from './types'

const ENTRIES: QueueEntry[] = [
  { target_type: 'connection', target_id: 'a', label: '连接A', confidence: 0.8, status: 'awaiting_review', evidenceCount: 2 },
  { target_type: 'region', target_id: 'b', label: '脑区B', confidence: null, status: 'completed', evidenceCount: 0 },
  { target_type: 'region', target_id: 'c', label: '脑区C', confidence: 0.5, status: 'failed', evidenceCount: 1 },
]

describe('ObjectQueue', () => {
  it('渲染标题、统计与全部条目,当前条目高亮', () => {
    render(<ObjectQueue queue={ENTRIES} currentIndex={0} onSelect={() => {}} />)
    expect(screen.getByText('待处理对象')).toBeTruthy()
    expect(screen.getByText(/待审核 1/)).toBeTruthy()
    expect(screen.getByText(/已完成 1/)).toBeTruthy()
    expect(screen.getByText(/失败 1/)).toBeTruthy()
    const items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(3)
    expect(items[0].className).toContain('evidence-queue-item-active')
    expect(items[0].textContent).toContain('连接A')
    expect(items[0].textContent).toContain('connection · 置信度 80%')
    expect(items[0].textContent).toContain('待审核')
    expect(items[0].textContent).toContain('2 证据')
  })

  it('点击条目触发 onSelect', () => {
    const onSelect = vi.fn()
    render(<ObjectQueue queue={ENTRIES} currentIndex={-1} onSelect={onSelect} />)
    fireEvent.click(screen.getAllByTestId('evidence-queue-item')[1])
    expect(onSelect).toHaveBeenCalledWith(ENTRIES[1])
  })

  it('勾选「只看未处理」后过滤已完成与失败', () => {
    render(<ObjectQueue queue={ENTRIES} currentIndex={0} onSelect={() => {}} />)
    fireEvent.click(screen.getByText('只看未处理'))
    const items = screen.getAllByTestId('evidence-queue-item')
    expect(items).toHaveLength(1)
    expect(items[0].textContent).toContain('连接A')
  })

  it('空队列显示占位', () => {
    render(<ObjectQueue queue={[]} currentIndex={-1} onSelect={() => {}} />)
    expect(screen.getByText('队列为空')).toBeTruthy()
    expect(within(screen.getByTestId('evidence-queue')).queryByTestId('evidence-queue-item')).toBeNull()
  })
})

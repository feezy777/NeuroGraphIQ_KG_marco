import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ContextBar } from './ContextBar'

const base = {
  targetLabel: 'R1→R2',
  targetType: 'connection',
  granularity: 'macro_clinical',
  confidence: 0.85,
  evidenceCount: 3,
  taskName: '佐证任务 A',
  queueIndex: 0,
  queueTotal: 5,
  taskStatus: '待审核',
}

describe('ContextBar', () => {
  it('显示当前对象信息与进度', () => {
    render(<ContextBar {...base} onBackToDataCenter={() => {}} onRefresh={() => {}} />)
    expect(screen.getByText('R1→R2')).toBeTruthy()
    expect(screen.getByText('connection')).toBeTruthy()
    expect(screen.getByText(/macro_clinical/)).toBeTruthy()
    expect(screen.getByText(/置信度 85%/)).toBeTruthy()
    expect(screen.getByText(/3 条证据/)).toBeTruthy()
    expect(screen.getByText(/佐证任务 A/)).toBeTruthy()
    expect(screen.getByText(/1\/5/)).toBeTruthy()
    expect(screen.getByText('待审核')).toBeTruthy()
  })

  it('队列为空时显示占位,不显示进度', () => {
    render(
      <ContextBar
        {...base}
        targetLabel={null}
        targetType={null}
        confidence={null}
        evidenceCount={null}
        taskName={null}
        taskStatus={null}
        queueIndex={-1}
        queueTotal={0}
        onBackToDataCenter={() => {}}
        onRefresh={() => {}}
      />,
    )
    expect(screen.getByText('未选择对象')).toBeTruthy()
    expect(screen.getByText(/等待处理对象/)).toBeTruthy()
    expect(screen.queryByText(/1\/5/)).toBeNull()
  })

  it('返回数据中心与刷新按钮触发回调', () => {
    const onBack = vi.fn()
    const onRefresh = vi.fn()
    render(<ContextBar {...base} onBackToDataCenter={onBack} onRefresh={onRefresh} />)
    fireEvent.click(screen.getByText('返回数据中心'))
    fireEvent.click(screen.getByText('刷新'))
    expect(onBack).toHaveBeenCalledTimes(1)
    expect(onRefresh).toHaveBeenCalledTimes(1)
  })
})

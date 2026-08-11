import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { composeClaimSentence, ContextBar } from './ContextBar'

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

  it('渲染完整事实句与状态 Badge(claimSentence 合成句)', () => {
    render(
      <ContextBar
        {...base}
        claimSentence="需要验证:R1 到 R2 存在投射连接(方向性:directed)"
        onBackToDataCenter={() => {}}
        onRefresh={() => {}}
      />,
    )
    expect(screen.getByText('需要验证:R1 到 R2 存在投射连接(方向性:directed)')).toBeTruthy()
    // 状态 Badge 优先展示 taskStatus
    expect(screen.getByText('待审核')).toBeTruthy()
  })

  it('无任务状态时状态 Badge 显示「等待处理对象」', () => {
    render(
      <ContextBar
        {...base}
        taskStatus={null}
        onBackToDataCenter={() => {}}
        onRefresh={() => {}}
      />,
    )
    expect(screen.getByText('等待处理对象')).toBeTruthy()
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

describe('composeClaimSentence', () => {
  it('组件齐全时拼装完整句(含方向)', () => {
    expect(composeClaimSentence('R1 投射到 R2', [
      { component_type: 'source_region', statement: 'right thalamus proper', required: true, metadata: {} },
      { component_type: 'target_region', statement: 'right putamen', required: true, metadata: {} },
      { component_type: 'relation', statement: '存在投射连接', required: true, metadata: {} },
      { component_type: 'direction', statement: 'directed', required: false, metadata: {} },
    ], null)).toBe('需要验证:right thalamus proper 到 right putamen 存在投射连接(方向性:directed)')
  })

  it('组件齐全但无方向时省略方向后缀', () => {
    expect(composeClaimSentence('', [
      { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
      { component_type: 'target_region', statement: 'R2', required: true, metadata: {} },
      { component_type: 'relation', statement: '存在投射连接', required: true, metadata: {} },
    ], null)).toBe('需要验证:R1 到 R2 存在投射连接')
  })

  it('组件不齐时回退完整 claimText', () => {
    expect(composeClaimSentence('R1 投射到 R2', [
      { component_type: 'source_region', statement: 'R1', required: true, metadata: {} },
      { component_type: 'relation', statement: '存在投射关系', required: true, metadata: {} },
    ], null)).toBe('需要验证:R1 投射到 R2')
  })

  it('无候选事实时回退队列对象 label', () => {
    expect(composeClaimSentence('', [], 'R1→R2')).toBe('需要验证:R1→R2')
  })

  it('全部缺失返回 null', () => {
    expect(composeClaimSentence('', [], null)).toBeNull()
  })
})

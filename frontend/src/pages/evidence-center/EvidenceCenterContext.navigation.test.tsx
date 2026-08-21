import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { EvidenceCenterProvider, useEvidenceCenter } from './EvidenceCenterContext'

/** 探针组件:暴露 context 导航函数供测试点击 */
function Probe({ action }: { action: 'taskTarget' | 'task' | 'closeTarget' | 'closeTask' | 'targetOnly' }) {
  const { state, openTaskTarget, openTask, closeTarget, closeTask, openTarget } = useEvidenceCenter()
  return (
    <div>
      <span data-testid="probe-state">
        {JSON.stringify({ module: state.module, taskId: state.taskId, targetType: state.targetType, targetId: state.targetId })}
      </span>
      <button data-testid="probe-taskTarget" onClick={() => openTaskTarget('t1', 'connection', 'c1')}>TT</button>
      <button data-testid="probe-task" onClick={() => openTask('t2')}>T</button>
      <button data-testid="probe-closeTarget" onClick={() => closeTarget()}>CT</button>
      <button data-testid="probe-closeTask" onClick={() => closeTask()}>CK</button>
      <button data-testid="probe-targetOnly" onClick={() => openTarget('connection', 'c3', 'candidates')}>TO</button>
      <span data-testid="probe-action">{action}</span>
    </div>
  )
}

function hashSeen(): string[] {
  return (window as unknown as { __hashTrace?: string[] }).__hashTrace ?? []
}

describe('EvidenceCenterContext 导航(第四步)', () => {
  beforeEach(() => {
    window.location.hash = ''
    const trace: string[] = []
    ;(window as unknown as { __hashTrace: string[] }).__hashTrace = trace
    window.addEventListener('hashchange', () => trace.push(window.location.hash))
  })
  afterEach(() => {
    cleanup()
    window.location.hash = ''
    ;(window as unknown as { __hashTrace?: string[] }).__hashTrace = undefined
  })

  it('openTaskTarget 一次导航:URL 一次到位(task+target),无中间态', async () => {
    window.location.hash = '#/evidence-center'
    render(<EvidenceCenterProvider><Probe action="taskTarget" /></EvidenceCenterProvider>)
    fireEvent.click(screen.getByTestId('probe-taskTarget'))
    await waitFor(() => expect(screen.getByTestId('probe-state').textContent).toContain('"targetId":"c1"'))
    expect(window.location.hash).toBe('#/evidence-center?task_id=t1&target_type=connection&target_id=c1')
    // jsdom 的 hashchange 为异步且可能合并,不断言精确条数;关键断言 = 从未出现过中间态(仅 task_id 的 URL)
    const final = '#/evidence-center?task_id=t1&target_type=connection&target_id=c1'
    await new Promise(r => setTimeout(r, 50))
    expect(hashSeen().every(h => h === final)).toBe(true)
    expect(hashSeen().some(h => h === '#/evidence-center?task_id=t1')).toBe(false)
  })

  it('embedded: URL 写入 /validation-center 且 tab 保留', async () => {
    window.location.hash = '#/validation-center?tab=paper_evidence'
    render(<EvidenceCenterProvider embedded><Probe action="taskTarget" /></EvidenceCenterProvider>)
    fireEvent.click(screen.getByTestId('probe-taskTarget'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c1'))
    expect(window.location.hash).toBe('#/validation-center?tab=paper_evidence&task_id=t1&target_type=connection&target_id=c1')
  })

  it('embedded: 初始 URL 缺 tab 时以 replaceState 补齐(不 push 历史)', async () => {
    const spy = vi.spyOn(window.history, 'replaceState')
    window.location.hash = '#/validation-center'
    render(<EvidenceCenterProvider embedded><Probe action="taskTarget" /></EvidenceCenterProvider>)
    await waitFor(() => expect(window.location.hash).toBe('#/validation-center?tab=paper_evidence'))
    expect(spy).toHaveBeenCalled()
    // replaceState 不触发 hashchange;若 jsdom 合并事件,其值也必须是补齐后的 URL(无中间态)
    await new Promise(r => setTimeout(r, 50))
    expect(hashSeen().every(h => h === '#/validation-center?tab=paper_evidence')).toBe(true)
    spy.mockRestore()
  })

  it('打开任务清除旧 target;关闭对象只清 target 保留 task', async () => {
    window.location.hash = '#/evidence-center?task_id=t1&target_type=connection&target_id=c1'
    render(<EvidenceCenterProvider><Probe action="task" /></EvidenceCenterProvider>)
    fireEvent.click(screen.getByTestId('probe-task'))
    await waitFor(() => expect(window.location.hash).toContain('task_id=t2'))
    expect(window.location.hash).not.toContain('target_id=')
    fireEvent.click(screen.getByTestId('probe-targetOnly'))
    await waitFor(() => expect(window.location.hash).toContain('target_id=c3'))
    fireEvent.click(screen.getByTestId('probe-closeTarget'))
    await waitFor(() => expect(window.location.hash).not.toContain('target_id='))
    expect(window.location.hash).toContain('task_id=t2')
    fireEvent.click(screen.getByTestId('probe-closeTask'))
    await waitFor(() => expect(window.location.hash).not.toContain('task_id='))
  })

  it('相同状态不重复写 URL(第二次点击不产生新的 hashchange)', async () => {
    window.location.hash = '#/evidence-center?task_id=t1&target_type=connection&target_id=c1'
    render(<EvidenceCenterProvider><Probe action="taskTarget" /></EvidenceCenterProvider>)
    await new Promise(r => setTimeout(r, 50))
    const before = hashSeen().length
    fireEvent.click(screen.getByTestId('probe-taskTarget'))
    await new Promise(r => setTimeout(r, 50))
    expect(hashSeen().length).toBe(before)
  })

  it('刷新等价:重新挂载后从 URL 恢复 task+target', async () => {
    window.location.hash = '#/evidence-center?task_id=t1&target_type=connection&target_id=c1'
    const first = render(<EvidenceCenterProvider><Probe action="taskTarget" /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('probe-state').textContent).toContain('"targetId":"c1"'))
    first.unmount()
    render(<EvidenceCenterProvider><Probe action="taskTarget" /></EvidenceCenterProvider>)
    await waitFor(() => expect(screen.getByTestId('probe-state').textContent).toContain('"targetId":"c1"'))
    expect(screen.getByTestId('probe-state').textContent).toContain('"taskId":"t1"')
  })

  it('无任务对象导航 → module=candidates,URL 无 task_id', async () => {
    window.location.hash = '#/validation-center?tab=paper_evidence'
    render(<EvidenceCenterProvider embedded><Probe action="targetOnly" /></EvidenceCenterProvider>)
    fireEvent.click(screen.getByTestId('probe-targetOnly'))
    await waitFor(() => expect(window.location.hash).toContain('module=candidates'))
    expect(window.location.hash).not.toContain('task_id=')
  })
})

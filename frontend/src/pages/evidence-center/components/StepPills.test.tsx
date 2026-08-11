import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { deriveStep, StepPills } from './StepPills'
import type { ModuleKey, ObjectProgress } from '../EvidenceCenterContext'

const NO_PROGRESS: ObjectProgress = { searched: false, extracted: false, reviewed: false, promoted: false }

describe('deriveStep', () => {
  it('候选模块:未检索 = 步骤 1 确认对象', () => {
    expect(deriveStep('candidates', NO_PROGRESS)).toBe(1)
  })

  it('searched=true → 步骤 2 查找论文', () => {
    expect(deriveStep('candidates', { ...NO_PROGRESS, searched: true })).toBe(2)
  })

  it('extracted=true → 步骤 3 找到原文(即使 searched 为 false)', () => {
    expect(deriveStep('candidates', { ...NO_PROGRESS, extracted: true })).toBe(3)
  })

  it('reviewed=true → 步骤 4 人工审核', () => {
    expect(deriveStep('candidates', { ...NO_PROGRESS, reviewed: true })).toBe(4)
  })

  it('promoted=true → 步骤 5 确认晋升', () => {
    expect(deriveStep('candidates', { ...NO_PROGRESS, promoted: true })).toBe(5)
  })

  it('module 覆盖:review → 4 人工审核,promotion → 5 确认晋升(不论 progress)', () => {
    expect(deriveStep('review', NO_PROGRESS)).toBe(4)
    expect(deriveStep('promotion', NO_PROGRESS)).toBe(5)
    expect(deriveStep('review', { ...NO_PROGRESS, promoted: true })).toBe(4)
    expect(deriveStep('promotion', { ...NO_PROGRESS, reviewed: true })).toBe(5)
  })

  it('tasks/papers 模块不参与五步流程(0 = 不高亮)', () => {
    expect(deriveStep('tasks', NO_PROGRESS)).toBe(0)
    expect(deriveStep('papers', NO_PROGRESS)).toBe(0)
    expect(deriveStep('tasks', { ...NO_PROGRESS, promoted: true })).toBe(0)
  })
})

describe('StepPills', () => {
  it('渲染五步胶囊', () => {
    render(<StepPills module="candidates" progress={NO_PROGRESS} />)
    const pills = screen.getByTestId('evidence-step-pills')
    for (const label of ['确认对象', '查找论文', '找到原文', '人工审核', '确认晋升']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(pills.querySelectorAll('.evidence-step-pill')).toHaveLength(5)
  })

  it.each<{ module: ModuleKey; progress: ObjectProgress; active: string }>([
    { module: 'candidates', progress: NO_PROGRESS, active: '确认对象' },
    { module: 'candidates', progress: { ...NO_PROGRESS, searched: true }, active: '查找论文' },
    { module: 'candidates', progress: { ...NO_PROGRESS, extracted: true }, active: '找到原文' },
    { module: 'candidates', progress: { ...NO_PROGRESS, reviewed: true }, active: '人工审核' },
    { module: 'candidates', progress: { ...NO_PROGRESS, promoted: true }, active: '确认晋升' },
    { module: 'review', progress: NO_PROGRESS, active: '人工审核' },
    { module: 'promotion', progress: NO_PROGRESS, active: '确认晋升' },
  ])('module=$module progress=$progress 时高亮 $active', ({ module, progress, active }) => {
    render(<StepPills module={module} progress={progress} />)
    const activePill = screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')
    expect(activePill?.textContent).toContain(active)
  })

  it('tasks/papers 模块时无高亮', () => {
    render(<StepPills module="tasks" progress={NO_PROGRESS} />)
    expect(screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')).toBeNull()
  })
})

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StepPills } from './StepPills'

describe('StepPills', () => {
  it('渲染五步胶囊', () => {
    render(<StepPills currentStep={0} />)
    const pills = screen.getByTestId('evidence-step-pills')
    for (const label of ['确认对象', '查找论文', '找到原文', '人工审核', '确认晋升']) {
      expect(screen.getByText(label)).toBeTruthy()
    }
    expect(pills.querySelectorAll('.evidence-step-pill')).toHaveLength(5)
  })

  it.each([
    { step: 1, active: '确认对象' },
    { step: 3, active: '找到原文' },
    { step: 4, active: '人工审核' },
    { step: 5, active: '确认晋升' },
  ])('currentStep=$step 时高亮 $active', ({ step, active }) => {
    render(<StepPills currentStep={step} />)
    const activePill = screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')
    expect(activePill?.textContent).toContain(active)
  })

  it('currentStep=0 时无高亮', () => {
    render(<StepPills currentStep={0} />)
    expect(screen.getByTestId('evidence-step-pills').querySelector('.evidence-step-pill.active')).toBeNull()
  })
})

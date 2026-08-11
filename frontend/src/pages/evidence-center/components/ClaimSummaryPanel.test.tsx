import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ClaimSummaryPanel } from './ClaimSummaryPanel'
import type { ClaimComponent } from './types'

const CONNECTION_COMPONENTS: ClaimComponent[] = [
  { component_type: 'source_region', statement: 'right thalamus proper', required: true, metadata: {} },
  { component_type: 'target_region', statement: 'right putamen', required: true, metadata: {} },
  { component_type: 'relation', statement: 'right thalamus proper 到 right putamen 存在投射关系', required: true, metadata: {} },
  { component_type: 'direction', statement: 'directed', required: false, metadata: {} },
]

describe('ClaimSummaryPanel', () => {
  it('connection 类型渲染 5 个独立信息块(类型/源脑区/目标脑区/连接关系/方向),每块带左侧图标', () => {
    render(<ClaimSummaryPanel claimText="fallback" components={CONNECTION_COMPONENTS} targetType="projection" />)
    expect(screen.getByText('当前需要验证的事实')).toBeTruthy()
    const blocks = screen.getAllByTestId('evidence-claim-block')
    expect(blocks).toHaveLength(5)
    expect(blocks[0].textContent).toContain('类型')
    expect(blocks[0].textContent).toContain('projection')
    expect(blocks[1].textContent).toContain('源脑区')
    expect(blocks[1].textContent).toContain('right thalamus proper')
    expect(blocks[2].textContent).toContain('目标脑区')
    expect(blocks[2].textContent).toContain('right putamen')
    expect(blocks[3].textContent).toContain('连接关系')
    expect(blocks[3].textContent).toContain('存在投射关系')
    expect(blocks[4].textContent).toContain('方向')
    expect(blocks[4].textContent).toContain('directed')
    for (const b of blocks) {
      expect(b.querySelector('.evidence-claim-block-icon')?.textContent?.length ?? 0).toBeGreaterThan(0)
    }
  })

  it('其他 target_type(circuit_function)按 components 动态生成块;未知 component_type 用通用「信息」块', () => {
    const comps: ClaimComponent[] = [
      { component_type: 'function', statement: '调控运动控制', required: true, metadata: {} },
      { component_type: 'circuit_identity', statement: '皮质-纹状体回路', required: true, metadata: {} },
      { component_type: 'unknown_thing', statement: '自定义值', required: false, metadata: {} },
    ]
    render(<ClaimSummaryPanel claimText="x" components={comps} targetType="circuit_function" />)
    const blocks = screen.getAllByTestId('evidence-claim-block')
    expect(blocks).toHaveLength(4) // 类型 + 3 个组件块
    expect(blocks[0].textContent).toContain('类型')
    expect(blocks[0].textContent).toContain('circuit_function')
    expect(blocks[1].textContent).toContain('功能')
    expect(blocks[1].textContent).toContain('调控运动控制')
    expect(blocks[2].textContent).toContain('回路身份')
    expect(blocks[2].textContent).toContain('皮质-纹状体回路')
    expect(blocks[3].textContent).toContain('信息')
    expect(blocks[3].textContent).toContain('自定义值')
  })

  it('无 components 时回退为 claimText 单块', () => {
    render(<ClaimSummaryPanel claimText="R1 投射到 R2" components={[]} targetType="" />)
    const blocks = screen.getAllByTestId('evidence-claim-block')
    expect(blocks).toHaveLength(1)
    expect(blocks[0].textContent).toContain('事实')
    expect(blocks[0].textContent).toContain('R1 投射到 R2')
  })

  it('granularity 展示在标题旁徽章', () => {
    render(<ClaimSummaryPanel claimText="" components={[]} targetType="connection" granularity="macro_clinical" />)
    expect(screen.getByText('macro_clinical')).toBeTruthy()
  })
})

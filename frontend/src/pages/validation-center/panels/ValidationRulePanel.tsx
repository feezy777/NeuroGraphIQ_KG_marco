interface Props { granularityLevel?: string }
export function ValidationRulePanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>规则校验</h3>
      <p>选择回路对象执行确定性规则校验。规则包括区域身份、边存在性、方向正确性、步骤连续性、闭环真实性、溯源完整性、粒度一致性等 12 项检查。</p>
    </div>
  )
}

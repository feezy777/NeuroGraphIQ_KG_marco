interface Props { granularityLevel?: string }
export function ValidationRulePanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>规则校验</h3>
      <p style={{ color: '#86909c', marginTop: 8 }}>选择粒度并创建验证运行后，规则校验引擎将对所有候选回路执行 12 项确定性检查（7 项硬性规则 + 5 项软性规则）。</p>
      <p style={{ marginTop: 16 }}>当前状态: 等待验证运行创建。</p>
      <p style={{ fontSize: 13, color: '#86909c' }}>API: POST /api/validation/circuit/runs → POST /runs/{'{id}'}/start</p>
    </div>
  )
}

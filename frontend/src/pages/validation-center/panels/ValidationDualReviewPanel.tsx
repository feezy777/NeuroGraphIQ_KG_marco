interface Props { granularityLevel?: string }
export function ValidationDualReviewPanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>双模型盲审</h3>
      <p style={{ color: '#86909c', marginTop: 8 }}>规则校验通过后，Reviewer A (神经解剖学) 和 Reviewer B (功能/证据) 独立评估回路。两者不能看到对方输出。评估完成后自动裁决。</p>
      <p style={{ marginTop: 16 }}>当前状态: 等待规则校验完成。</p>
    </div>
  )
}

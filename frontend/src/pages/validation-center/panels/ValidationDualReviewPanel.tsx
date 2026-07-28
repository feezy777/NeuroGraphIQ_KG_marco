interface Props { granularityLevel?: string }
export function ValidationDualReviewPanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>双模型盲审</h3>
      <p>Reviewer A (神经解剖学) 和 Reviewer B (功能/证据) 独立评估回路对象。两者不能看到对方的输出。评估完成后自动裁决。</p>
    </div>
  )
}

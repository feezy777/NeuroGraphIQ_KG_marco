interface Props { granularityLevel?: string }
export function ValidationHumanReviewPanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>人工审核</h3>
      <p style={{ color: '#86909c', marginTop: 8 }}>自动裁决完成后，结果进入人工审核队列。审核员可批准、拒绝、要求修改或将候选回路标记为拓扑模体。</p>
      <p style={{ marginTop: 16 }}>当前状态: 等待裁决完成。</p>
    </div>
  )
}

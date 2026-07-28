interface Props { granularityLevel?: string }
export function ValidationHumanReviewPanel({ granularityLevel }: Props) {
  return (
    <div style={{ padding: 20 }}>
      <h3>人工审核</h3>
      <p>查看裁决结果，执行人工审核操作：批准、拒绝、要求修改、标记为拓扑模体。</p>
    </div>
  )
}

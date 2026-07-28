interface Props { granularityLevel?: string }
export function ValidationStatsBar({ granularityLevel }: Props) {
  return (
    <div className="vw-stats">
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">待校验</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">规则通过</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">双模型一致</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">待审核</span></div>
      <div className="vw-stat"><span className="vw-stat-num">-</span><span className="vw-stat-label">已晋升</span></div>
    </div>
  )
}

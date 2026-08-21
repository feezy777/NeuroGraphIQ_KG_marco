/** Skeleton 块（详情 / 关系面板加载态，不显示空白） */
export function Skeleton({ height = 16, width }: { height?: number; width?: number | string }) {
  return <span className="oc-skeleton" style={{ height, width }} aria-hidden="true" />
}

/** 多行 Skeleton（面板加载占位；末行短 = 模拟文本块） */
export function SkeletonRows({ rows = 4, gap = 8 }: { rows?: number; gap?: number }) {
  return (
    <span className="oc-skeleton-rows" style={{ gap }} aria-hidden="true">
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} height={14} width={index === rows - 1 ? '60%' : '100%'} />
      ))}
    </span>
  )
}

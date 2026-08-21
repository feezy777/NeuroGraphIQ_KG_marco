import { EvidenceCenterPage } from '../evidence-center/EvidenceCenterPage'

interface Props { granularityLevel?: string }

/**
 * 验证中心 — 精简后直接承载论文佐证工作台。
 * granularityLevel 保留兼容旧调用方,不再向下传递(EvidenceCenterPage 不依赖粒度上下文)。
 */
export function ValidationWorkbench({ granularityLevel: _granularityLevel }: Props) {
  return (
    <div className="vw-root">
      <EvidenceCenterPage embedded />
    </div>
  )
}

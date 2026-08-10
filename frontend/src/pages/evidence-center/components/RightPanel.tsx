import type { ModuleKey } from '../EvidenceCenterContext'

const RIGHT_TITLES: Record<ModuleKey, string> = {
  tasks: '任务与队列概览',
  papers: '论文详情',
  candidates: '检索与候选',
  review: '审核决策',
  promotion: '晋升确认',
}

/** 右栏插槽:S2-S5 各模块将在此填充具体内容,本轮仅渲染占位标题 */
export function RightPanel({ module }: { module: ModuleKey }) {
  const title = RIGHT_TITLES[module]
  return (
    <aside className="evidence-right-panel" data-testid="evidence-right-panel">
      <h4>{title}</h4>
      <p className="evidence-module-hint">该面板将在后续迭代提供「{title}」相关内容。</p>
    </aside>
  )
}

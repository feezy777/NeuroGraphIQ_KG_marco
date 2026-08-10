import { EvidenceCenterProvider, useEvidenceCenter, type ModuleKey } from './EvidenceCenterContext'
import { EvidenceCenterHeader } from './EvidenceCenterHeader'
import { EvidenceTasksModule } from './modules/EvidenceTasksModule'

const MODULE_TITLE: Record<ModuleKey, string> = {
  tasks: '佐证任务',
  papers: '论文库',
  candidates: '证据候选',
  review: '人工审核',
  promotion: '证据晋升',
}
const MODULE_HINT: Record<ModuleKey, string> = {
  tasks: '哪些知识对象需要论文佐证，以及任务处理到哪里。',
  papers: '管理系统已经获取和解析的真实论文资源。',
  candidates: '查看 DeepSeek 从论文中提取出的候选佐证原文。',
  review: '人工确认候选原文是否足以证明当前知识事实。',
  promotion: '将审核通过的论文证据正式应用到知识图谱。',
}

function EvidenceCenterBody() {
  const { state } = useEvidenceCenter()
  return (
    <div className="evidence-center-body">
      <div className="evidence-module-hint">{MODULE_HINT[state.module]}</div>
      {state.module === 'tasks' && <EvidenceTasksModule />}
      {/* papers/candidates/review/promotion 模块在 Task 6-9 接入 */}
    </div>
  )
}

export function EvidenceCenterPage() {
  return (
    <EvidenceCenterProvider>
      <div className="evidence-center" data-testid="evidence-center">
        <EvidenceCenterHeader moduleTitles={MODULE_TITLE} />
        <EvidenceCenterBody />
      </div>
    </EvidenceCenterProvider>
  )
}

export default EvidenceCenterPage

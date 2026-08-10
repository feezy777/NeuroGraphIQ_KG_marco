import type { ModuleKey } from '../EvidenceCenterContext'

export const EVIDENCE_STEPS = ['确认对象', '查找论文', '找到原文', '人工审核', '确认晋升'] as const

/** module → 步骤(0 表示未进入任何步骤,不高亮):候选=1 确认对象,审核=3 找到原文,晋升=4 人工审核 */
export const MODULE_TO_STEP: Record<ModuleKey, number> = {
  tasks: 0,
  papers: 0,
  candidates: 1,
  review: 3,
  promotion: 4,
}

/** 五步流程小胶囊,仅当前步高亮 */
export function StepPills({ currentStep }: { currentStep: number }) {
  return (
    <div className="evidence-step-pills" data-testid="evidence-step-pills">
      {EVIDENCE_STEPS.map((label, i) => {
        const step = i + 1
        return (
          <span key={label} className={`evidence-step-pill${currentStep === step ? ' active' : ''}`}>
            <span className="evidence-step-num">{step}</span>
            {label}
          </span>
        )
      })}
    </div>
  )
}

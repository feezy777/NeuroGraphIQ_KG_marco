import type { ModuleKey, ObjectProgress } from '../EvidenceCenterContext'

export const EVIDENCE_STEPS = ['确认对象', '查找论文', '找到原文', '人工审核', '确认晋升'] as const

/**
 * 当前步骤由 module + 对象实际进度推导(而非固定 module 映射):
 * - tasks/papers 模块不参与五步流程(0 = 不高亮)
 * - 先看 module(review → 4 人工审核,promotion → 5 确认晋升)
 * - 再看 progress:promoted → 5,reviewed → 4,extracted → 3,searched → 2,否则 1 确认对象
 */
export function deriveStep(module: ModuleKey, progress: ObjectProgress): number {
  if (module === 'tasks' || module === 'papers') return 0
  if (module === 'promotion') return 5
  if (module === 'review') return 4
  if (progress.promoted) return 5
  if (progress.reviewed) return 4
  if (progress.extracted) return 3
  if (progress.searched) return 2
  return 1
}

/** 五步流程小胶囊:当前步高亮(active),已完成步标记完成态(done),其余未到态 */
export function StepPills({ module, progress }: { module: ModuleKey; progress: ObjectProgress }) {
  const currentStep = deriveStep(module, progress)
  return (
    <div className="evidence-step-pills" data-testid="evidence-step-pills">
      {EVIDENCE_STEPS.map((label, i) => {
        const step = i + 1
        return (
          <span
            key={label}
            className={`evidence-step-pill${currentStep === step ? ' active' : currentStep > step ? ' done' : ''}`}
          >
            <span className="evidence-step-num">{step}</span>
            {label}
          </span>
        )
      })}
    </div>
  )
}

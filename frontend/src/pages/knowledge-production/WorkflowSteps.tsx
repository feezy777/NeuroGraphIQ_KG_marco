/**
 * Generic presentational workflow indicator — numbered circles joined by
 * connecting lines.
 *
 * Pure props in, markup out — no data fetching, no business logic, no
 * knowledge of any specific pipeline. Callers own the step list and the
 * current index.
 *
 * Four lifecycle states are supported (pending / active / done / failed).
 * Phase 1 renders `pending` only, because no Discovery Run exists yet.
 */
import { useI18n } from '../../i18n-context'
import type { WorkflowStepDef } from './types'

export interface WorkflowStepsProps {
  steps: WorkflowStepDef[]
  /**
   * id of the step currently RUNNING, or null when no step is running.
   * null is meaningful: it lets a caller show progress (some steps completed)
   * while asserting that nothing is executing.
   */
  currentStepId: string | null
  /** id of the last COMPLETED step; steps up to and including it render as done. */
  completedThroughId?: string | null
  /** id of a step that ENDED IN FAILURE; wins over active/done. */
  failedStepId?: string | null
  className?: string
}

export function WorkflowSteps({
  steps,
  currentStepId,
  completedThroughId,
  failedStepId,
  className,
}: WorkflowStepsProps) {
  const { t } = useI18n()
  const activeIndex = currentStepId ? steps.findIndex(s => s.id === currentStepId) : -1
  const doneThroughIndex = completedThroughId
    ? steps.findIndex(s => s.id === completedThroughId)
    : -1
  const failedIndex = failedStepId ? steps.findIndex(s => s.id === failedStepId) : -1

  return (
    <ol
      className={`kp-workflow-steps${className ? ` ${className}` : ''}`}
      data-testid="kp-workflow-steps"
    >
      {steps.map((step, index) => {
        const state =
          index === failedIndex
            ? 'failed'
            : index === activeIndex
              ? 'active'
              : index <= doneThroughIndex
                ? 'done'
                : 'pending'
        return (
          <li
            key={step.id}
            className="kp-step"
            aria-current={state === 'active' ? 'step' : undefined}
            data-testid={`kp-step-${step.id}`}
            data-state={state}
          >
            <span className="kp-step-index" aria-hidden="true">
              {index + 1}
            </span>
            <span className="kp-step-label">{t(step.labelKey)}</span>
          </li>
        )
      })}
    </ol>
  )
}

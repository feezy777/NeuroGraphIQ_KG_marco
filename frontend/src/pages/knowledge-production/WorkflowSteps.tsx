/**
 * Generic presentational workflow step indicator.
 *
 * Pure props in, markup out — no data fetching, no business logic, no
 * knowledge of any specific pipeline. Callers own the step list and the
 * current index.
 */
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
  className?: string
}

export function WorkflowSteps({
  steps,
  currentStepId,
  completedThroughId,
  className,
}: WorkflowStepsProps) {
  const activeIndex = currentStepId ? steps.findIndex(s => s.id === currentStepId) : -1
  const doneThroughIndex = completedThroughId
    ? steps.findIndex(s => s.id === completedThroughId)
    : -1

  return (
    <ol className={`kp-workflow-steps${className ? ` ${className}` : ''}`} data-testid="kp-workflow-steps">
      {steps.map((step, index) => {
        const state =
          index === activeIndex ? 'active' : index <= doneThroughIndex ? 'done' : 'pending'
        return (
          <li
            key={step.id}
            className={`kp-workflow-step kp-workflow-step--${state}`}
            aria-current={state === 'active' ? 'step' : undefined}
            data-testid={`kp-step-${step.id}`}
            data-state={state}
          >
            <span className="kp-workflow-step-index">{index + 1}</span>
            <span className="kp-workflow-step-label">{step.label}</span>
          </li>
        )
      })}
    </ol>
  )
}

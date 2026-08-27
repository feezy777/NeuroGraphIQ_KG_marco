/**
 * SelectedValidationTask —— 统一「当前验证任务」上下文。
 *
 * 任务中心（EvidenceTasksModule）点击任一来源卡片（佐证任务 / 论文发现 / …）
 * 时先设置本上下文,再切换 Tab —— 证据候选模块据此解析对象,不再各自维护
 * selected state,也不再假设输入一定是旧 paper_evidence_task。
 *
 * 身份约定（用户规格）：
 *   - 旧 Evidence Task : sourceId = task_id / target_id（taskKey=evidence_task:{id}）
 *   - Macro Paper Discovery : sourceId = ranking_id（taskKey=macro_candidate:{id}）
 *   —— 禁止 source_name + target_name 作为任务身份。
 *
 * URL 深链：hash query `stask` / `ssrc` / `smode`（被 buildEmbeddedUrl 保留,
 * 不与 EvidenceCenter 状态参数冲突）→ 刷新后可恢复 sourceType / sourceId / mode。
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { readHashQueryParams } from '../../utils/pipelineNavigation'

export type ValidationTaskSource = 'evidence_task' | 'paper_discovery' | 'llm_extraction' | 'inference' | 'manual'
export type ValidationObjectType = 'connection' | 'circuit' | 'function'
export type ValidationWorkflowMode = 'new_knowledge' | 'evidence_enhancement'

export interface SelectedValidationTask {
  taskKey: string
  sourceType: ValidationTaskSource
  sourceId: string
  objectType: ValidationObjectType
  workflowMode: ValidationWorkflowMode
  title?: string
}

interface SelectedValidationTaskContextValue {
  selectedTask: SelectedValidationTask | null
  setSelectedTask: (task: SelectedValidationTask | null) => void
}

const SelectedTaskContext = createContext<SelectedValidationTaskContextValue>({
  selectedTask: null,
  setSelectedTask: () => {},
})

/** 从 URL hash 恢复（stask/ssrc/smode;深链重载） */
function taskFromHash(): { task: SelectedValidationTask | null; url: string | null } {
  const q = readHashQueryParams()
  const sourceId = q.stask
  const sourceType = q.ssrc
  const mode = q.smode
  if (!sourceId || !sourceType) return { task: null, url: null }
  const validSource = ['evidence_task', 'paper_discovery', 'llm_extraction', 'inference', 'manual'].includes(sourceType)
  if (!validSource) return { task: null, url: null }
  return {
    task: {
      taskKey: sourceType === 'paper_discovery' ? `macro_candidate:${sourceId}` : `${sourceType}:${sourceId}`,
      sourceType: sourceType as ValidationTaskSource,
      sourceId,
      objectType: 'connection',
      workflowMode: mode === 'evidence_enhancement' ? 'evidence_enhancement' : 'new_knowledge',
    },
    url: `#${window.location.hash.slice(1)}`,
  }
}

export function SelectedValidationTaskProvider({ children }: { children: ReactNode }) {
  const [selectedTask, setSelectedTaskState] = useState<SelectedValidationTask | null>(() => taskFromHash().task)

  // hash 变化时同步（浏览器前进/后退/深链）
  useEffect(() => {
    const onHash = () => {
      const { task } = taskFromHash()
      if (task) setSelectedTaskState(task)
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  const setSelectedTask = useCallback((task: SelectedValidationTask | null) => {
    setSelectedTaskState(task)
  }, [])

  const value = useMemo(() => ({ selectedTask, setSelectedTask }), [selectedTask, setSelectedTask])

  return <SelectedTaskContext.Provider value={value}>{children}</SelectedTaskContext.Provider>
}

export function useSelectedValidationTask(): SelectedValidationTaskContextValue {
  return useContext(SelectedTaskContext)
}

/** 构造 Macro 任务的统一对象（连续点击两条时自动覆盖,不残留上一条） */
export function macroSelectedTask(
  rankingId: string,
  opts?: { workflowMode?: ValidationWorkflowMode; title?: string },
): SelectedValidationTask {
  return {
    taskKey: `macro_candidate:${rankingId}`,
    sourceType: 'paper_discovery',
    sourceId: rankingId,
    objectType: 'connection',
    workflowMode: opts?.workflowMode ?? 'new_knowledge',
    title: opts?.title,
  }
}

/** 证据任务统一对象（旧流程;sourceId=task_id;原 navigateToEvidenceCandidates 流程不变） */
export function evidenceSelectedTask(taskId: string): SelectedValidationTask {
  return {
    taskKey: `evidence_task:${taskId}`,
    sourceType: 'evidence_task',
    sourceId: taskId,
    objectType: 'connection',
    workflowMode: 'new_knowledge',
  }
}

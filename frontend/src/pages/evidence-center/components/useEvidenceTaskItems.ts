import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listPaperEvidenceTaskItems,
  listPaperEvidenceTasks,
  type PaperEvidenceTask,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'

/** 队列/中栏共用的任务对象条目(全局模式带来源任务 id) */
export interface EvidenceQueueItem extends PaperEvidenceTaskItem {
  __taskId?: string
}

export interface EvidenceTaskItemsState {
  items: EvidenceQueueItem[]
  /** 非取消且有对象的任务列表(中栏任务卡片用) */
  tasks: PaperEvidenceTask[]
  /** 全局模式下任务 id → 展示名 */
  taskNames: Record<string, string>
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * 佐证任务对象取数 hook(中栏与右栏队列共用,避免双份取数与刷新节奏漂移):
 * - 无 taskId = 全局模式:并行拉取所有非取消且有对象任务的 items(每任务 limit 100)合并,单任务失败静默跳过;
 * - 有 taskId = 任务模式:只拉该任务 items。
 * 任务列表始终拉取(中栏任务卡片用)。两种模式均带陈旧响应守卫(切任务时丢弃乱序返回的旧响应)。
 */
export function useEvidenceTaskItems(): EvidenceTaskItemsState {
  const { state } = useEvidenceCenter()
  const taskId = state.taskId
  const [items, setItems] = useState<EvidenceQueueItem[]>([])
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [taskNames, setTaskNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestTaskIdRef = useRef(taskId)
  useEffect(() => { latestTaskIdRef.current = taskId }, [taskId])

  const load = useCallback(async () => {
    const r = await listPaperEvidenceTasks({ limit: 200 }).catch(() => null)
    if (!r) {
      setError('任务列表加载失败')
      setLoading(false)
      return
    }
    const scoped = r.items.filter(t => t.status !== 'cancelled' && t.total_items > 0)
    setTasks(scoped)
    setTaskNames(Object.fromEntries(scoped.map(t => [t.id, t.name || t.target_type])))
    if (!taskId) {
      setLoading(true)
      setError(null)
      setItems([])
      try {
        const settled = await Promise.allSettled(
          scoped.map(t => listPaperEvidenceTaskItems(t.id, { limit: 100 })),
        )
        if (latestTaskIdRef.current !== null) return
        const merged = settled.flatMap((s, i) =>
          s.status === 'fulfilled'
            ? s.value.items.map(it => ({ ...it, __taskId: scoped[i].id }))
            : [],
        )
        setItems(merged)
      } catch (err) {
        if (latestTaskIdRef.current !== null) return
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (latestTaskIdRef.current === null) setLoading(false)
      }
      return
    }
    const requestedTaskId = taskId
    setLoading(true)
    setError(null)
    setItems([])
    try {
      const itemsResp = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(itemsResp.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void load() }, [load])

  return { items, tasks, taskNames, loading, error, reload: load }
}

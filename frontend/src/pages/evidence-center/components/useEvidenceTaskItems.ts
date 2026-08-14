import { useCallback, useEffect, useRef, useState } from 'react'
import {
  listPaperEvidenceTaskItems,
  listPaperEvidenceTasks,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'

/** 队列/中栏共用的任务对象条目(全局模式带来源任务 id) */
export interface EvidenceQueueItem extends PaperEvidenceTaskItem {
  __taskId?: string
}

export interface EvidenceTaskItemsState {
  items: EvidenceQueueItem[]
  /** 全局模式下任务 id → 展示名 */
  taskNames: Record<string, string>
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * 佐证任务对象取数 hook(中栏与右栏队列共用,避免双份取数与刷新节奏漂移):
 * - 无 taskId = 全局模式:并行拉取所有进行中任务的 items(每任务 limit 100)合并,单任务失败静默跳过;
 * - 有 taskId = 任务模式:只拉该任务 items。
 * 两种模式均带陈旧响应守卫(切任务时丢弃乱序返回的旧响应)。
 */
export function useEvidenceTaskItems(): EvidenceTaskItemsState {
  const { state } = useEvidenceCenter()
  const taskId = state.taskId
  const [items, setItems] = useState<EvidenceQueueItem[]>([])
  const [taskNames, setTaskNames] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const latestTaskIdRef = useRef(taskId)
  useEffect(() => { latestTaskIdRef.current = taskId }, [taskId])

  const load = useCallback(async () => {
    if (!taskId) {
      setLoading(true)
      setError(null)
      setItems([])
      setTaskNames({})
      try {
        const r = await listPaperEvidenceTasks({ limit: 200 })
        // 取所有非取消且有对象的任务(对象状态由各面板自行过滤;
        // 部分历史任务的任务级 status 与对象状态不一致,按任务状态过滤会漏数据)
        const scoped = r.items.filter(t => t.status !== 'cancelled' && t.total_items > 0)
        setTaskNames(Object.fromEntries(scoped.map(t => [t.id, t.name || t.target_type])))
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
    setTaskNames({})
    try {
      const r = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(r.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void load() }, [load])

  return { items, taskNames, loading, error, reload: load }
}

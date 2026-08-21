import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../../api/client'
import { resolvePaperEvidenceTaskItem } from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'

/**
 * S6:任务模式下「当前 target → 任务项」只读解析(审核前置校验)。
 * - standalone(无 taskId):直接放行,审核不携带任何任务 ID;
 * - 有 taskId:调用 resolve 端点校验 task_item_id / 按 task+target 唯一匹配;
 *   唯一匹配且 URL 缺 task_item_id 时以 replace 语义补齐(不产生浏览器历史,三.8/9);
 *   0 个匹配 → not_found,多个匹配 → ambiguous(禁止创建 review,三.8/四.4)。
 */
export type TaskItemResolution =
  | { kind: 'standalone' }
  | { kind: 'resolving' }
  | { kind: 'resolved'; taskItemId: string; rescoreRevisionNo: number | null }
  | { kind: 'error'; reason: 'not_found' | 'ambiguous' | 'mismatch' | 'fetch'; message: string }

const ERROR_LABEL: Record<'not_found' | 'ambiguous' | 'mismatch' | 'fetch', string> = {
  not_found: '当前任务中没有匹配该对象的任务项',
  ambiguous: '无法唯一确定任务项:当前任务中存在多个匹配对象,禁止创建审核',
  mismatch: '任务项与当前对象不一致,禁止创建审核',
  fetch: '任务项解析失败',
}

export function useTaskItemResolution(): TaskItemResolution {
  const { state, backfillTaskItem } = useEvidenceCenter()
  const taskId = state.taskId
  const taskItemId = state.taskItemId
  const targetType = state.targetType
  const targetId = state.targetId
  const [resolution, setResolution] = useState<TaskItemResolution>({ kind: 'resolving' })
  const seqRef = useRef(0)
  // 已解析结果的缓存:backfill 写 URL 后 effect 重跑时不发起第二次请求
  const resolvedRef = useRef<{ taskId: string; taskItemId: string; targetType: string; targetId: string; rescoreRevisionNo: number | null } | null>(null)

  useEffect(() => {
    if (!taskId) {
      resolvedRef.current = null
      setResolution({ kind: 'standalone' })
      return
    }
    if (!targetType || !targetId) {
      resolvedRef.current = null
      setResolution({ kind: 'resolving' })
      return
    }
    const cached = resolvedRef.current
    if (
      cached && cached.taskId === taskId && cached.targetType === targetType
      && cached.targetId === targetId && cached.taskItemId === taskItemId
    ) {
      setResolution({ kind: 'resolved', taskItemId: cached.taskItemId, rescoreRevisionNo: cached.rescoreRevisionNo })
      return
    }
    const seq = ++seqRef.current
    setResolution({ kind: 'resolving' })
    resolvePaperEvidenceTaskItem(taskId, targetType, targetId, taskItemId)
      .then(r => {
        if (seqRef.current !== seq) return
        resolvedRef.current = { taskId, taskItemId: r.task_item_id, targetType, targetId, rescoreRevisionNo: r.rescore_revision_no ?? null }
        // 旧 deep link 唯一匹配后 replace 补齐 task_item_id(不产生历史)
        if (!taskItemId) backfillTaskItem(r.task_item_id)
        setResolution({ kind: 'resolved', taskItemId: r.task_item_id, rescoreRevisionNo: r.rescore_revision_no ?? null })
      })
      .catch(err => {
        if (seqRef.current !== seq) return
        if (err instanceof ApiError) {
          const reason = err.status === 404 ? 'not_found' : err.status === 409 ? 'ambiguous' : 'mismatch'
          setResolution({
            kind: 'error',
            reason,
            message: err.status === 404 || err.status === 409 ? ERROR_LABEL[reason] : `${ERROR_LABEL[reason]}:${err.message}`,
          })
          return
        }
        setResolution({ kind: 'error', reason: 'fetch', message: `${ERROR_LABEL.fetch}:${err instanceof Error ? err.message : String(err)}` })
      })
  }, [taskId, taskItemId, targetType, targetId, backfillTaskItem])

  return resolution
}

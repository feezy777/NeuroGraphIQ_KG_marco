import { useEffect } from 'react'
import {
  navigateToEvidenceCandidates,
  type EvidenceQueueHandoffItem,
} from '../evidence-center/evidenceCenterUrl'

export interface EvidenceReviewModalProps {
  open: boolean
  onClose: () => void
  initialItems?: EvidenceQueueHandoffItem[]
  initialTaskId?: string
}

/**
 * 兼容壳:旧入口(数据中心「论文佐证」/后台任务工作台)不再渲染工作台 UI,
 * 统一跳转 Evidence Center 的候选模块;业务工作流已由
 * evidence-center 的 tasks/papers/candidates/review/promotion 模块承接。
 */
export function EvidenceReviewModal({ open, onClose, initialItems, initialTaskId }: EvidenceReviewModalProps) {
  useEffect(() => {
    if (!open) return
    navigateToEvidenceCandidates({ items: initialItems, taskId: initialTaskId })
    onClose()
  }, [open, initialItems, initialTaskId, onClose])
  return null
}

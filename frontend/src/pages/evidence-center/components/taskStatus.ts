/** 佐证任务状态标签与色调用色(任务列表 EvidenceTasksModule 与右栏 TaskSummary 共用) */

export const TASK_STATUS_LABELS: Record<string, string> = {
  pending: '待预处理',
  running: '运行中',
  paused: '已暂停',
  completed: '预处理完成',
  failed: '预处理失败',
}

export const TASK_REVIEW_LABELS: Record<string, string> = {
  not_started: '未开始审核',
  processing: '审核中',
  in_progress: '审核中',
  completed: '审核完成',
}

export function taskStatusTone(status: string): string {
  switch (status) {
    case 'completed': return 'ok'
    case 'failed': return 'bad'
    case 'paused': return 'warn'
    case 'running': return 'info'
    default: return 'muted'
  }
}

export function taskReviewTone(reviewStatus: string | null): string {
  if (reviewStatus === 'completed') return 'ok'
  if (reviewStatus === 'processing' || reviewStatus === 'in_progress') return 'info'
  return 'muted'
}

/** 进行中任务状态(任务列表置顶排序第一组) */
export const IN_PROGRESS_TASK_STATUSES = ['pending', 'running', 'paused']

/** 任务列表排序秩:0=进行中,1=有等待审核,2=其他;同组内按创建时间倒序 */
export function taskSortRank(t: { status: string; awaiting_review_items: number }): number {
  if (IN_PROGRESS_TASK_STATUSES.includes(t.status)) return 0
  if (t.awaiting_review_items > 0) return 1
  return 2
}

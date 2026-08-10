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

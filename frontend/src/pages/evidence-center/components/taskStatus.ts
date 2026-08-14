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

/** 目标类型中文标签(任务/对象展示名兜底,避免直接显示 connection 等原始类型串) */
export const TARGET_TYPE_LABELS: Record<string, string> = {
  connection: '连接',
  projection: '投射',
  circuit: '回路',
  circuit_step: '回路步骤',
  circuit_function: '回路功能',
  region_function: '脑区功能',
  projection_function: '投射功能',
}

/** 任务展示名:优先任务名,缺失时用「类型中文 + 短ID」 */
export function taskDisplayName(t: { name: string | null; target_type: string; id: string }): string {
  return t.name || `${TARGET_TYPE_LABELS[t.target_type] ?? t.target_type}任务 #${t.id.slice(0, 8)}`
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** 对象展示名:label 缺失或为裸 UUID(后端未解析出名称的存量数据)时,用「类型中文 #短ID」兜底 */
export function itemDisplayLabel(item: { label: string | null; target_id: string; target_type: string }): string {
  if (item.label && !UUID_RE.test(item.label)) return item.label
  return `${TARGET_TYPE_LABELS[item.target_type] ?? item.target_type} #${item.target_id.slice(0, 8)}`
}

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

/** 任务展示名:优先用户自定义名,缺失时用「类型中文 + 短ID」(短ID 仅作辅助) */
export function taskDisplayName(t: { name: string | null; target_type: string; id: string }): string {
  return t.name || `${TARGET_TYPE_LABELS[t.target_type] ?? t.target_type}任务 #${t.id.slice(0, 8)}`
}

/** 任务业务标题(§8):自定义名 → 单对象「类型验证 · 对象名」 → 多对象「类型验证任务 · N 个对象」 */
export function taskTitle(
  t: { name: string | null; target_type: string; total_items: number },
  singleObjectName: string | null,
): string {
  if (t.name) return t.name
  const typeLabel = TARGET_TYPE_LABELS[t.target_type] ?? t.target_type
  if (t.total_items === 1 && singleObjectName) {
    return `${typeLabel}验证 · ${singleObjectName}`
  }
  return `${typeLabel}验证任务 · ${t.total_items} 个对象`
}

/** 对象卡片标题:中文 (英文);中文缺失只用英文;中英相同不重复;皆空回退兜底名 */
export function objectCardTitle(
  cn: string | null | undefined,
  en: string | null | undefined,
  fallback: string,
): string {
  const c = cn?.trim() || ''
  const e = en?.trim() || ''
  if (!c && !e) return fallback
  if (!c) return e
  if (!e || e === c) return c
  return `${c} (${e})`
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

/** 对象展示名(display 优先级):display_name ?? live_display_name ?? 非 UUID 快照 ?? 「类型中文 #短ID」。
 *  全程 nullish 判断(0/空串不参与名称逻辑)。 */
export function displayNameOf(item: {
  display_name?: string | null
  live_display_name?: string | null
  label?: string | null
  target_id: string
  target_type: string
}): string {
  if (item.display_name != null && item.display_name !== '') return item.display_name
  if (item.live_display_name != null && item.live_display_name !== '') return item.live_display_name
  if (item.label != null && item.label !== '' && !UUID_RE.test(item.label)) return item.label
  return `${TARGET_TYPE_LABELS[item.target_type] ?? item.target_type} #${item.target_id.slice(0, 8)}`
}

/** 对象展示置信度(display 优先级):display_confidence ?? live_confidence ?? current_confidence ?? null。
 *  0.0 是合法值,必须用 nullish 判断保留。 */
export function displayConfidenceOf(item: {
  display_confidence?: number | null
  live_confidence?: number | null
  current_confidence?: number | null
}): number | null {
  if (item.display_confidence !== null && item.display_confidence !== undefined) return item.display_confidence
  if (item.live_confidence !== null && item.live_confidence !== undefined) return item.live_confidence
  if (item.current_confidence !== null && item.current_confidence !== undefined) return item.current_confidence
  return null
}

/** 置信度百分比统一格式:0 →「置信度 0%」;0.356 →「置信度 35.6%」;null →「未评分」。不重复乘 100。 */
export function formatConfidencePercent(v: number | null | undefined): string {
  if (v === null || v === undefined) return '未评分'
  const pct = Math.round(v * 1000) / 10
  return `置信度 ${pct}%`
}

/** 低置信度默认阈值:与后端 _resolve_scope_ids_low_confidence 缺省一致(任务未保存 confidence_lt 时复用) */
export const LOW_CONFIDENCE_DEFAULT_THRESHOLD = 0.5

/** 低置信度判定:未评分(null)不算低置信度;0.0 是低置信度 */
export function isLowConfidence(confidence: number | null | undefined, threshold: number): boolean {
  if (confidence === null || confidence === undefined) return false
  return confidence < threshold
}

// ── 任务统一工作状态(权威口径来自后端 work_status,不做前端推导) ──

export const WORK_STATUS_LABELS: Record<string, string> = {
  empty: '空任务',
  processing: '进行中',
  paused: '已暂停',
  awaiting_review: '待验证',
  partially_failed: '部分失败',
  failed: '失败',
  completed: '已完成',
  cancelled: '已取消',
}

export function workStatusTone(ws: string): string {
  switch (ws) {
    case 'processing': return 'info'
    case 'paused': case 'awaiting_review': return 'warn'
    case 'partially_failed': case 'failed': return 'bad'
    case 'completed': return 'ok'
    case 'cancelled': case 'empty': default: return 'muted'
  }
}

/** 预处理结果中文标签(对象卡/任务卡徽章) */
export const PREPROCESS_OUTCOME_LABELS: Record<string, string> = {
  non_neural_target: '结构性不存在:靶标为非神经结构',
  evidence_negated: '证据否定',
  no_evidence_found: '无证据',
}

/** 任务卡排序:处理中 → 待验证 → 已暂停 → 部分失败 → 失败 → 已完成 → 空 → 已取消 */
export function workStatusRank(ws: string): number {
  const order = ['processing', 'awaiting_review', 'paused', 'partially_failed', 'failed', 'completed', 'empty', 'cancelled']
  const i = order.indexOf(ws)
  return i === -1 ? 9 : i
}

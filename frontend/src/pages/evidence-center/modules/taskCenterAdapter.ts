/**
 * Task Center 统一任务适配器（前端 DTO,不写数据库、不改端点）。
 *
 * 目标：验证中心「佐证任务」下只存在一个统一任务列表 —— 不同对象来源通过
 * `sourceType` 字段区分（evidence_task / paper_discovery / llm_extraction /
 * inference / manual）,而不是页面下方再渲染一块独立 Macro 区块。
 *
 * 母集合（用户规格）：
 * - 原佐证任务 = paper_evidence_tasks（evidence_task）
 * - Macro Paper Discovery = **paper_connection_candidate_rankings（1129 唯一 pair）**
 *   1129 ranking ──LEFT JOIN── 200 llm reviews ──LEFT JOIN── rule validation ──
 *   ——而不是「200 reviews 生成 200 任务」。200 只是状态数据。
 *
 * 稳定任务身份：taskKey = evidence_task:{task_id} / macro_candidate:{ranking_id}
 * （禁止用 source_name + target_name 作身份）。
 */
import type { PaperEvidenceTask } from '../../../api/endpoints'
import type {
  MacroCandidateView,
} from '../../validation-center/macro-governance/useMacroCandidates'

// ── 统一 DTO ────────────────────────────────────────────────────────────────────

export type TaskSourceType = 'evidence_task' | 'paper_discovery' | 'llm_extraction' | 'inference' | 'manual'

export interface TaskCenterItem {
  /** 稳定身份（严禁 name 拼接） */
  taskKey: string
  /** 对象类型（connection / projection / circuit / function …） */
  objectType: string
  sourceType: TaskSourceType
  sourceId: string | null
  title: string
  sourceRegion: string | null
  targetRegion: string | null
  relationType: string | null

  /** 流程阶段标签（中文显示键,见 STAGE_LABELS） */
  workflowStage: string
  workflowStatus: string

  rankingScore: number | null
  paperCount: number | null
  evidenceCount: number | null

  ruleStatus: 'PASS' | 'BLOCKED' | 'PENDING' | null
  aiDecision: 'supported' | 'uncertain' | 'not_supported' | null
  aiConfidence: number | null
  humanStatus: string | null
  promotionStatus: string | null

  /** 来源徽章（卡片头） */
  sourceLabel: string

  createdAt: string | null
  updatedAt: string | null

  /** 下层原始引用（操作回调使用;module 内不得直接改动数据） */
  evidenceTask?: PaperEvidenceTask
  macroView?: MacroCandidateView
}

export const SOURCE_LABELS: Record<TaskSourceType, string> = {
  evidence_task: '佐证任务',
  paper_discovery: '论文发现',
  llm_extraction: 'LLM提取',
  inference: '推理候选',
  manual: '人工',
}

/** 流程阶段标签（用户规格 8 档;宏观状态再细分为可观察档位） */
export const STAGE_LABELS: Record<string, string> = {
  rule_pending: '待规则验证',
  rule_passed: '规则已验证',
  ai_pending: '待AI审核',
  ai_reviewed: 'AI已审核',
  human_review: '待人工审核',
  promotion: '待晋升',
  completed: '已完成',
  blocked: '已阻断',
}

/** 阶段筛选定义（全部 + 8 档） */
export const STAGE_FILTERS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'rule_pending', label: '待规则验证' },
  { key: 'rule_passed', label: '规则已验证' },
  { key: 'ai_pending', label: '待AI审核' },
  { key: 'ai_reviewed', label: 'AI已审核' },
  { key: 'human_review', label: '待人工审核' },
  { key: 'promotion', label: '待晋升' },
  { key: 'completed', label: '已完成' },
  { key: 'blocked', label: '已阻断' },
]

/** 来源筛选定义 */
export const SOURCE_FILTERS: { key: TaskSourceType | 'all'; label: string }[] = [
  { key: 'all', label: '全部来源' },
  { key: 'evidence_task', label: '佐证任务' },
  { key: 'paper_discovery', label: '论文发现' },
  { key: 'llm_extraction', label: 'LLM提取' },
  { key: 'inference', label: '推理候选' },
]

// ── Evidence Task → TaskCenterItem ─────────────────────────────────────────────

export function toEvidenceTaskItem(task: PaperEvidenceTask): TaskCenterItem {
  const titleCn = task.display_name_cn?.trim()
  const titleEn = task.display_name_en?.trim()
  return {
    taskKey: `evidence_task:${task.id}`,
    objectType: task.target_type ?? 'connection',
    sourceType: 'evidence_task',
    sourceId: task.id,
    title: titleCn || titleEn || `${task.target_type ?? 'task'} #${task.id.slice(0, 8)}`,
    sourceRegion: null,
    targetRegion: null,
    relationType: null,
    workflowStage: stageOfEvidenceStatus(task.work_status),
    workflowStatus: task.work_status,
    rankingScore: null,
    paperCount: null,
    evidenceCount: task.item_counts?.total ?? null,
    ruleStatus: null,
    aiDecision: null,
    aiConfidence: null,
    humanStatus: null,
    promotionStatus: null,
    sourceLabel: SOURCE_LABELS.evidence_task,
    createdAt: task.created_at ?? null,
    updatedAt: task.created_at ?? null,
    evidenceTask: task,
  }
}

/** Evidence 任务 work_status → 阶段（对齐阶段筛选） */
function stageOfEvidenceStatus(ws: string): string {
  if (ws === 'completed') return 'completed'
  if (ws === 'processing' || ws === 'paused' || ws === 'partially_failed') return 'ai_pending'
  if (ws === 'awaiting_review') return 'human_review'
  if (ws === 'failed') return 'rule_pending'
  return 'rule_pending'
}

// ── Macro Candidate（1129 母集合）→ TaskCenterItem ────────────────────────────────

/**
 * Macro 阶段（宏观工作流状态 → 统一阶段,供筛选/标签）：
 * - rule_pending/rule_failed/candidate → 待规则验证
 * - rule_pass → 规则已验证
 * - rule_blocked → 已阻断
 * - ai_review_pending → 待AI审核
 * - ai_supported/ai_uncertain → AI已审核（后续准入人工/证据）
 * - not_supported → AI已审核（标记未支持,不直接入人工）
 * - human_review/approved/rejected/rollback → 待人工审核（或已完成）
 * - promotion_ready/promoted → 待晋升/已完成
 */
export function macroStageOf(status: string): string {
  if (status === 'rule_pending' || status === 'rule_failed' || status === 'candidate') return 'rule_pending'
  if (status === 'rule_pass') return 'rule_passed'
  if (status === 'rule_blocked') return 'blocked'
  if (status === 'ai_review_pending') return 'ai_pending'
  if (status === 'ai_supported' || status === 'ai_uncertain' || status === 'not_supported') return 'ai_reviewed'
  if (status === 'human_review' || status === 'approved' || status === 'rejected' || status === 'rollback') return 'human_review'
  if (status === 'promotion_ready') return 'promotion'
  if (status === 'promoted') return 'completed'
  return 'rule_pending'
}

export function toMacroCandidateItem(view: MacroCandidateView): TaskCenterItem {
  const r = view.ranking
  if (!r) {
    // 防御：母集合由 rankings 构造（non-null）;异常时为占位,绝不丢任务身份
    return {
      taskKey: `macro_candidate:${view.sourceName}|${view.targetName}`,
      objectType: 'connection',
      sourceType: 'paper_discovery',
      sourceId: null,
      title: `${view.sourceName} → ${view.targetName}`,
      sourceRegion: view.sourceName,
      targetRegion: view.targetName,
      relationType: null,
      workflowStage: macroStageOf(view.status),
      workflowStatus: view.status,
      rankingScore: null,
      paperCount: null,
      evidenceCount: null,
      ruleStatus: 'PENDING',
      aiDecision: null,
      aiConfidence: null,
      humanStatus: null,
      promotionStatus: null,
      sourceLabel: SOURCE_LABELS.paper_discovery,
      createdAt: null,
      updatedAt: null,
      macroView: view,
    }
  }
  const review = view.review
  const rule = view.ruleResult
  const ruleStatus: TaskCenterItem['ruleStatus'] = rule
    ? rule.blocked ? 'BLOCKED' : rule.passed ? 'PASS' : 'PENDING'
    : 'PENDING'
  const aiDecision: TaskCenterItem['aiDecision'] = review?.decision
    ? (review.decision === 'supported' || review.decision === 'uncertain' || review.decision === 'not_supported'
        ? review.decision : null)
    : null
  return {
    taskKey: `macro_candidate:${r.id}`,
    objectType: 'connection',
    sourceType: 'paper_discovery',
    sourceId: r.id,
    title: `${view.sourceName} → ${view.targetName}`,
    sourceRegion: view.sourceName,
    targetRegion: view.targetName,
    relationType: review?.connection_type ?? null,
    workflowStage: macroStageOf(view.status),
    workflowStatus: view.status,
    rankingScore: view.rankScore,
    paperCount: view.paperCount,
    evidenceCount: r.evidence_count ?? null,
    ruleStatus,
    aiDecision,
    aiConfidence: review?.confidence ?? null,
    humanStatus: null,
    promotionStatus: null,
    sourceLabel: SOURCE_LABELS.paper_discovery,
    createdAt: r.created_at ?? null,
    updatedAt: r.created_at ?? null,
    macroView: view,
  }
}

// ── 合并 + 过滤 + 分页（纯函数） ──────────────────────────────────────────────────

export function mergeTaskCenterItems(
  evidenceTasks: PaperEvidenceTask[],
  macroViews: MacroCandidateView[],
): TaskCenterItem[] {
  const dedup = new Map<string, TaskCenterItem>()
  for (const it of [
    ...evidenceTasks.map(toEvidenceTaskItem),
    ...macroViews.map(toMacroCandidateItem),
  ]) {
    // 稳定身份去重：一个 ranking_id/task_id 只出现一次
    if (!dedup.has(it.taskKey)) dedup.set(it.taskKey, it)
  }
  // 稳定排序：来源 → 更新时间降序
  return [...dedup.values()].sort((a, b) => {
    if (a.sourceType !== b.sourceType) return a.sourceType === 'evidence_task' ? -1 : 1
    return String(b.updatedAt ?? '').localeCompare(String(a.updatedAt ?? ''))
  })
}

export function filterTaskCenterItems(
  items: TaskCenterItem[],
  opts: {
    sourceType: TaskSourceType | 'all'
    stage: string // 'all' 或 STAGE_FILTERS key
    group: string // all/connection/circuit/function（沿用原分组 chips）
    keyword: string
  },
): TaskCenterItem[] {
  const kw = opts.keyword.trim().toLowerCase()
  return items.filter(it => {
    if (opts.sourceType !== 'all' && it.sourceType !== opts.sourceType) return false
    if (opts.stage !== 'all' && it.workflowStage !== opts.stage) return false
    if (opts.group !== 'all') {
      const g = it.objectType.toLowerCase()
      if (!g.includes(opts.group.toLowerCase())) return false
    }
    if (kw) {
      const blob = `${it.title} ${it.sourceRegion ?? ''} ${it.targetRegion ?? ''} ${it.relationType ?? ''}`.toLowerCase()
      if (!blob.includes(kw)) return false
    }
    return true
  })
}

export interface TaskCenterStats {
  total: number
  /** macro 母集合总数（1129,与筛选无关——诚实展示） */
  macroTotal: number
  aiReviewed: number
  aiPending: number
  supported: number
  uncertain: number
  notSupported: number
  rulePass: number
  ruleBlocked: number
  rulePending: number
}

export function computeTaskCenterStats(items: TaskCenterItem[]): TaskCenterStats {
  const macroItems = items.filter(it => it.sourceType === 'paper_discovery')
  let aiReviewed = 0, supported = 0, uncertain = 0, notSupported = 0
  let rulePass = 0, ruleBlocked = 0, rulePending = 0
  for (const it of macroItems) {
    if (it.aiDecision) aiReviewed += 1
    if (it.aiDecision === 'supported') supported += 1
    if (it.aiDecision === 'uncertain') uncertain += 1
    if (it.aiDecision === 'not_supported') notSupported += 1
    if (it.ruleStatus === 'PASS') rulePass += 1
    else if (it.ruleStatus === 'BLOCKED') ruleBlocked += 1
    else rulePending += 1
  }
  return {
    total: items.length,
    macroTotal: macroItems.length,
    aiReviewed,
    aiPending: macroItems.length - aiReviewed,
    supported,
    uncertain,
    notSupported,
    rulePass,
    ruleBlocked,
    rulePending,
  }
}

export const TASK_CENTER_PAGE_SIZE = 30

export function paginateTaskCenterItems(items: TaskCenterItem[], page: number): TaskCenterItem[] {
  const start = (page - 1) * TASK_CENTER_PAGE_SIZE
  return items.slice(start, start + TASK_CENTER_PAGE_SIZE)
}

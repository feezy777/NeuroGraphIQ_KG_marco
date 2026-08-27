/**
 * Macro 候选连接治理状态模型(前端流程序状态)。
 *
 * 13 个 workflow 状态(用户定义):
 *   candidate / rule_pending / rule_pass / rule_failed /
 *   ai_review_pending / ai_supported / ai_uncertain /
 *   human_review / approved / rejected / promotion_ready / promoted / rollback
 *
 * 数据来源(全部已有产物,不重新调用 LLM):
 * - paper_connection_candidate_rankings(排名/评分/论文数)
 * - macro_candidate_connection_llm_reviews(AI 审核结果)
 * - ReviewStatusStore(sessionStorage,人工审核决策)
 * - rollback 记录(sessionStorage,本模块扩展)
 *
 * 纯函数:deriveWorkflowStatus / runRuleChecks 可测试、无副作用。
 */

import type {
  MacroCandidateRankingDetail,
  MacroCandidateRankingItem,
  MacroCandidateReviewItem,
} from '../../../api/endpoints'
import type { ReviewStatusRecord } from '../../evidence-center/components/ReviewStatusStore'

export type MacroWorkflowStatus =
  | 'candidate'
  | 'rule_pending'
  | 'rule_pass'
  | 'rule_failed'
  | 'rule_blocked'
  | 'ai_review_pending'
  | 'ai_supported'
  | 'ai_uncertain'
  | 'human_review'
  | 'approved'
  | 'rejected'
  | 'promotion_ready'
  | 'promoted'
  | 'rollback'

export const WORKFLOW_LABEL: Record<MacroWorkflowStatus, string> = {
  candidate: '候选',
  rule_pending: '规则待验证',
  rule_pass: '规则通过',
  rule_failed: '规则未通过',
  rule_blocked: '规则拦截',
  ai_review_pending: 'AI 待审核',
  ai_supported: 'AI 支持',
  ai_uncertain: 'AI 不确定',
  human_review: '待人工审核',
  approved: '已批准',
  rejected: '已驳回',
  promotion_ready: '待晋升',
  promoted: '已晋升',
  rollback: '已回退',
}

export const WORKFLOW_TONE: Record<MacroWorkflowStatus, string> = {
  candidate: 'neutral',
  rule_pending: 'warn',
  rule_pass: 'blue',
  rule_failed: 'bad',
  rule_blocked: 'bad',
  ai_review_pending: 'warn',
  ai_supported: 'ok',
  ai_uncertain: 'warn',
  human_review: 'warn',
  approved: 'ok',
  rejected: 'bad',
  promotion_ready: 'blue',
  promoted: 'blue',
  rollback: 'neutral',
}

/** 各状态的治理阶段(时间线/门禁显示) */
export type MacroStage =
  | 'candidate' | 'rule_validation' | 'ai_review' | 'human_review' | 'promotion' | 'final'

export const STAGE_OF: Record<MacroWorkflowStatus, MacroStage> = {
  candidate: 'candidate',
  rule_pending: 'rule_validation',
  rule_pass: 'rule_validation',
  rule_failed: 'rule_validation',
  rule_blocked: 'rule_validation',
  ai_review_pending: 'ai_review',
  ai_supported: 'ai_review',
  ai_uncertain: 'ai_review',
  human_review: 'human_review',
  approved: 'human_review',
  rejected: 'human_review',
  promotion_ready: 'promotion',
  promoted: 'promotion',
  rollback: 'candidate',
}

// ---- 规则检查(纯前端派生;依据真实表字段:region 存在性/source!=target/type/direction/duplicate/hierarchy) ----

export interface RuleCheck {
  code: string
  name: string
  passed: boolean
  detail: string
  /** 规则严重级:block 级失败 → BLOCKED */
  severity?: 'normal' | 'block'
}

const CONNECTION_TYPES = ['structural_connection', 'functional_connectivity', 'projection', 'association', 'unknown'] as const
const DIRECTIONS = ['A_to_B', 'B_to_A', 'bidirectional', 'unknown'] as const

/** 运行 6 项规则;priority/status 可空=数据不足时规则按已证事实判定 */
export function runRuleChecks(
  ranking: MacroCandidateRankingItem,
  review: MacroCandidateReviewItem | null,
  hierarchy: Pick<MacroCandidateRankingDetail, 'source_parent_name' | 'target_parent_name'> | null,
  reversePairExists: boolean,
): RuleCheck[] {
  const checks: RuleCheck[] = []
  // 1. region 存在性(名称由 JOIN canonical 表产生,非空即存在)
  checks.push({
    code: 'R1',
    name: 'region 存在性',
    passed: Boolean(ranking.source_name?.trim() && ranking.target_name?.trim()),
    detail: `${ranking.source_name ?? '—'} 与 ${ranking.target_name ?? '—'} 均为 canonical 脑区`,
  })
  // 2. source != target(表 CHECK 保证)
  checks.push({
    code: 'R2',
    name: 'source != target',
    passed: ranking.source_region_id !== ranking.target_region_id,
    detail: '无自连接对',
  })
  // 3. connection_type 合法性(review 已有结果时校验;未审核时视为合法占位)
  const typeOk = review
    ? CONNECTION_TYPES.includes(review.connection_type as typeof CONNECTION_TYPES[number])
    : true
  checks.push({
    code: 'R3',
    name: 'connection_type 合法性',
    passed: typeOk,
    detail: review ? `connection_type=${review.connection_type}` : 'AI 审核未给出类型前可继续',
  })
  // 4. direction 合法性
  const dirOk = review
    ? DIRECTIONS.includes(review.direction as typeof DIRECTIONS[number])
    : true
  checks.push({
    code: 'R4',
    name: 'direction 合法性',
    passed: dirOk,
    detail: review ? `direction=${review.direction}` : 'direction 由 AI 审核填充',
  })
  // 5. duplicate 检查:反向 pair 独立存在(应合并镜像对)
  checks.push({
    code: 'R5',
    name: 'duplicate 检查',
    passed: !reversePairExists,
    detail: reversePairExists ? '存在镜像反向对,需合并' : '无镜像重复',
  })
  // 6. hierarchy 检查:父/子区不应与子/父区直接建连接(hierarchy 下沉冲突)
  const parentNames = hierarchy
    ? [hierarchy.source_parent_name, hierarchy.target_parent_name]
    : [null, null]
  const hierarchyConflict = Boolean(
    parentNames[0] && parentNames[0] === ranking.target_name
    || parentNames[1] && parentNames[1] === ranking.source_name,
  )
  checks.push({
    code: 'R6',
    name: 'hierarchy 检查',
    passed: !hierarchyConflict,
    detail: hierarchyConflict
      ? '源/目标脑区间存在父子区层级,应由聚合连接表达'
      : '无层级冲突',
  })
  return checks
}

export interface RuleCheckResult {
  passed: boolean
  blocked: boolean
  rules: RuleCheck[]
  /** 后端 duplicate 检查明细(Final/Canonical/Mirror) */
  duplicate_existing?: Record<string, unknown> | null
}

export function summarizeRuleChecks(checks: RuleCheck[]): RuleCheckResult {
  const failed = checks.filter(c => !c.passed)
  return {
    passed: failed.length === 0,
    // BLOCK 级失败(R5 duplicate / R6 hierarchy)→ BLOCKED;正常失败 → FAIL
    blocked: failed.some(c => c.severity === 'block'),
    rules: checks,
  }
}

// ---- 状态派生 ----

/** 同轨道唯一键(region 对,与 ranking 表一致:按 id 排序的无向对) */
export function pairKey(sourceRegionId: string, targetRegionId: string): string {
  // 无向对排序必须与 SQL least/greatest(uuid 字节序)一致：
  // uuid hex 的字典序 == uuid 字节序（字符串比较会碰撞,导致 1129 → 1125）
  const norm = (x: string) =>
    x.length === 36 && /^[0-9a-fA-F-]+$/.test(x) ? x.replace(/-/g, '') : x
  return [norm(sourceRegionId), norm(targetRegionId)].sort().join('|')
}

export interface WorkflowDeriveInput {
  ranking: MacroCandidateRankingItem | null
  review: MacroCandidateReviewItem | null
  ruleResult: RuleCheckResult | null
  humanDecision: ReviewStatusRecord | null
  rollbackAt: string | null       // rollback 记录时间(ISO),无则 null
  promotedAt: string | null       // evidence review promoted_at,无则 null
}

/**
 * 状态派生(顺序优先级):
 *   1. rollback(最新回退记录且无更新的 approved)→ rollback
 *   2. promoted(promoted_at 存在)→ promoted
 *   3. approved(human review_approved 且晚于 rollback)→ promotion_ready(并入待晋升)
 *   4. rejected → rejected
 *   5. ai 结果存在 → ai_supported / ai_uncertain(not_supported 归类 uncertain)
 *   6. 规则失败 → rule_failed(无 AI 结果)
 *   7. 规则通过 → rule_pass
 *   8. 仅有候选 → candidate(无规则数据时 rule_pending)
 */
export function deriveWorkflowStatus(input: WorkflowDeriveInput): MacroWorkflowStatus {
  const { ranking, review, ruleResult, humanDecision, rollbackAt, promotedAt } = input
  if (!ranking) return 'candidate'

  const decisionAt = humanDecision?.meta.at ?? null
  // 回退按时间最新性判定:回退晚于人工决策 → 显示回退(支持 promotion/approved 后回退);
  // 人工重新决策(新 at 晚于回退)后回到晋升链路。
  if (rollbackAt && rollbackAt > (decisionAt ?? '0')) {
    return 'rollback'
  }
  // 重审(晚于旧晋升)→ 重新晋升流程
  if (decisionAt && promotedAt && decisionAt > promotedAt) return 'promotion_ready'
  if (promotedAt) return 'promoted'

  if (humanDecision?.status === 'review_approved') return 'promotion_ready'
  if (humanDecision?.status === 'rejected') return 'rejected'

  if (review) return review.decision === 'supported' ? 'ai_supported' : 'ai_uncertain'

  if (ruleResult) {
    if (ruleResult.blocked) return 'rule_blocked'
    if (!ruleResult.passed) return 'rule_failed'
    return 'rule_pass'
  }
  return 'rule_pending'
}

// ---- 回退记录存储(sessionStorage;基于现有审核记录结构扩展,不覆盖旧记录) ----

export interface WorkflowRollbackRecord {
  targetId: string
  reason: string
  actor: string
  at: string
  from: string
}

export const ROLLBACK_KEY_PREFIX = 'evidence-center.workflow-rollback.'

export function saveWorkflowRollback(record: WorkflowRollbackRecord): void {
  const key = `${ROLLBACK_KEY_PREFIX}${record.targetId}`
  const raw = sessionStorage.getItem(key)
  const prev: WorkflowRollbackRecord[] = raw ? JSON.parse(raw) : []
  const next = [...prev, record]
  sessionStorage.setItem(key, JSON.stringify(next))
}

export function loadWorkflowRollbacks(targetId: string): WorkflowRollbackRecord[] {
  try {
    const raw = sessionStorage.getItem(`${ROLLBACK_KEY_PREFIX}${targetId}`)
    if (!raw) return []
    const parsed = JSON.parse(raw) as WorkflowRollbackRecord[]
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function latestRollback(targetId: string): WorkflowRollbackRecord | null {
  const list = loadWorkflowRollbacks(targetId)
  if (list.length === 0) return null
  return list.slice().sort((a, b) => (a.at < b.at ? 1 : -1))[0]
}

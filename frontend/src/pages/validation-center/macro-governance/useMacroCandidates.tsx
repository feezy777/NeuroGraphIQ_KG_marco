import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  listEvidenceReviews,
  listMacroCandidateRankings,
  listMacroCandidateReviews,
  listMacroCandidateRuleValidations,
  type EvidenceReviewItem,
  type MacroCandidateRankingDetail,
  type MacroCandidateRankingItem,
  type MacroCandidateReviewItem,
  type MacroCandidateRuleValidationItem,
} from '../../../api/endpoints'
import { loadReviewStatus } from '../../evidence-center/components/ReviewStatusStore'
import {
  deriveWorkflowStatus,
  latestRollback,
  pairKey,
  runRuleChecks,
  summarizeRuleChecks,
  type MacroWorkflowStatus,
  type RuleCheckResult,
  type WorkflowDeriveInput,
} from './macroWorkflow'

/** 目标对象 ↔ Macro 候选的匹配键(region 名称级,无向) */
export function regionPairKeyForEvidence(
  source: string | null | undefined,
  target: string | null | undefined,
): string | null {
  if (!source || !target) return null
  return [source, target].sort().join('|')
}

/** 聚合后的候选连接视图(排名 + LLM 审核 + 规则 + 人工 + 状态) */
export interface MacroCandidateView {
  key: string
  ranking: MacroCandidateRankingItem | null
  detail: MacroCandidateRankingDetail | null
  review: MacroCandidateReviewItem | null
  ruleResult: RuleCheckResult | null
  status: MacroWorkflowStatus
  sourceName: string
  targetName: string
  paperCount: number | null
  rankScore: number | null
  reversePairExists: boolean
}

interface MacroCandidatesContextValue {
  candidates: MacroCandidateView[]
  byKey: Map<string, MacroCandidateView>
  loading: boolean
  error: string | null
  refresh: () => void
  /** target_id → promoted_at(证据晋升记录;人工/晋升派生绑定证据对象) */
  promotedAtByTargetId: Record<string, string>
}

const MacroCandidatesContext = createContext<MacroCandidatesContextValue | null>(null)

/** 无 Provider 时的静默空态(模块独立渲染/既有测试兼容;Macro 层不阻断任何现有功能) */
const EMPTY: MacroCandidatesContextValue = {
  candidates: [],
  byKey: new Map(),
  loading: false,
  error: null,
  refresh: () => {},
  promotedAtByTargetId: {},
}

/** 后端规则结果 → 前端 RuleCheckResult(包含 blocked/duplicate_existing;6 条规则明细) */
function backendRuleToResult(rv: MacroCandidateRuleValidationItem): RuleCheckResult {
  return {
    passed: rv.validation_status === 'PASS',
    blocked: rv.validation_status === 'BLOCKED',
    rules: (rv.rule_results ?? []).map(c => ({
      code: c.code,
      name: c.name,
      passed: c.passed,
      detail: c.detail,
      severity: c.severity ?? 'normal',
    })),
    duplicate_existing: rv.duplicate_existing ?? null,
  }
}

/** 安全执行外部查询:任何异常(含 API 未定义/网络失败)返回 null,绝不向调用方抛错 */
function safeFetch<T>(fn: () => Promise<T>): Promise<T | null> {
  return new Promise(resolve => {
    Promise.resolve()
      .then(() => fn())
      .then(
        v => resolve(v),
        () => resolve(null),
      )
  })
}

/**
 * Macro 候选数据 Provider:并行拉取 rankings + LLM reviews + 已晋升 reviews
 * (全部为已有产物的只读查询,不调用 LLM),join 出工作流视图。
 * 任一接口失败整体降级(现有验证中心功能不受影响)。
 *
 * 注意:人工审核/回退/晋升记录以「证据对象 id」为键(ReviewStatusStore / review.target_id),
 * 与 ranking 的 region id 无外键映射 → 对象级完整状态由 useMacroViewForEvidence(带
 * evidence targetId) 派生;Provider 层面的 candidates 只含排名+审核+规则信息。
 */
export function MacroCandidatesProvider({ children }: { children: ReactNode }) {
  const [rankings, setRankings] = useState<MacroCandidateRankingItem[]>([])
  const [details, setDetails] = useState<Map<string, MacroCandidateRankingDetail>>(new Map())
  const [reviews, setReviews] = useState<MacroCandidateReviewItem[]>([])
  const [promoted, setPromoted] = useState<EvidenceReviewItem[]>([])
  const [ruleValidations, setRuleValidations] = useState<MacroCandidateRuleValidationItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)

  const refresh = useCallback(() => setEpoch(n => n + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    /** rankings 后端 limit 上限 1000(1129 > 1000)→ 分页循环拉全母集合 */
    const fetchAllRankings = async () => {
      const all: MacroCandidateRankingItem[] = []
      let offset = 0
      for (;;) {
        const r = await listMacroCandidateRankings({ limit: 500, offset })
        all.push(...(r.items ?? []))
        if ((r.items ?? []).length === 0 || offset + (r.items ?? []).length >= (r.total ?? 0)) break
        offset += (r.items ?? []).length
        if (offset > 3000) break // 护栏
      }
      return { items: all }
    }
    const fetchAllReviews = async () => {
      const all: MacroCandidateReviewItem[] = []
      let offset = 0
      for (;;) {
        const r = await listMacroCandidateReviews({ limit: 500, offset })
        all.push(...(r.items ?? []))
        if ((r.items ?? []).length === 0 || offset + (r.items ?? []).length >= (r.total ?? 0)) break
        offset += (r.items ?? []).length
        if (offset > 1000) break
      }
      return { items: all }
    }
    Promise.all([
      safeFetch(fetchAllRankings),
      safeFetch(fetchAllReviews),
      safeFetch(() => listMacroCandidateRuleValidations({ limit: 2000 })),
      safeFetch(() => listEvidenceReviews({ promotion_status: 'promoted', page_size: 200 })
        .then(r => r.items)),
    ]).then(([rk, rv, rvRules, pr]) => {
      if (cancelled) return
      setRankings(rk?.items ?? [])
      setReviews(rv?.items ?? [])
      setRuleValidations(rvRules?.items ?? [])
      setPromoted(pr ?? [])
      if (!rk) setError('Macro 候选数据暂不可用(仅展示灰度,现有功能不受影响)')
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [epoch])

  // 详情(含 hierarchy)按需加载排序前 100 条中的未加载项(规则检查第 6 项需要)
  useEffect(() => {
    if (rankings.length === 0) return
    let cancelled = false
    const todo = rankings.slice(0, 100)
      .filter(r => !details.has(r.id))
      .slice(0, 30)
    if (todo.length === 0) return
    Promise.all(
      todo.map(async r => {
        try {
          const { getMacroCandidateRankingDetail } = await import('../../../api/endpoints')
          return await getMacroCandidateRankingDetail(r.id)
        } catch {
          return null
        }
      }),
    ).then(list => {
      if (cancelled) return
      setDetails(prev => {
        const next = new Map(prev)
        for (const d of list) if (d) next.set(d.id, d)
        return next
      })
    }).catch(() => undefined)
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rankings, epoch])

  const value = useMemo<MacroCandidatesContextValue>(() => {
    const map = new Map<string, MacroCandidateView>()
    const rankingByPair = new Map<string, MacroCandidateRankingItem[]>()
    for (const r of rankings) {
      const k = pairKey(r.source_region_id, r.target_region_id)
      const list = rankingByPair.get(k) ?? []
      rankingByPair.set(k, [...list, r])
    }
    const reviewByPair = new Map<string, MacroCandidateReviewItem>()
    for (const rv of reviews) {
      const k = pairKey(rv.source_region_id, rv.target_region_id)
      if (!reviewByPair.has(k)) reviewByPair.set(k, rv)
    }
    // 规则验证结果(后端优先;无后端数据时前端派生化)
    const ruleByRanking = new Map<string, MacroCandidateRuleValidationItem>()
    for (const rv of ruleValidations) ruleByRanking.set(rv.ranking_id, rv)

    for (const r of rankings) {
      const k = pairKey(r.source_region_id, r.target_region_id)
      const review = reviewByPair.get(k) ?? null
      const detail = details.get(r.id) ?? null
      const reversePairExists = (rankingByPair.get(k) ?? []).length > 1
      const backendRule = ruleByRanking.get(r.id)
      const ruleResult = backendRule
        ? backendRuleToResult(backendRule)
        : summarizeRuleChecks(runRuleChecks(r, review, detail, reversePairExists))
      const input: WorkflowDeriveInput = {
        ranking: r, review, ruleResult,
        humanDecision: null, rollbackAt: null, promotedAt: null,
      }
      const view: MacroCandidateView = {
        key: k,
        ranking: r,
        detail,
        review,
        ruleResult,
        status: deriveWorkflowStatus(input),
        sourceName: r.source_name,
        targetName: r.target_name,
        paperCount: r.paper_count,
        rankScore: r.score,
        reversePairExists,
      }
      if (!map.has(k)) map.set(k, view)
    }
    const promotedAtByTargetId: Record<string, string> = {}
    for (const p of promoted) {
      if (p.target_id && p.promoted_at && !promotedAtByTargetId[p.target_id]) {
        promotedAtByTargetId[p.target_id] = p.promoted_at
      }
    }
    return { candidates: [...map.values()], byKey: map, loading, error, refresh, promotedAtByTargetId }
  }, [rankings, reviews, ruleValidations, details, promoted, loading, error, refresh])

  return <MacroCandidatesContext.Provider value={value}>{children}</MacroCandidatesContext.Provider>
}

export function useMacroCandidates(): MacroCandidatesContextValue {
  const ctx = useContext(MacroCandidatesContext)
  // 无 Provider → 静默空态(独立组件渲染/既有测试不受影响)
  return ctx ?? EMPTY
}

/**
 * 按「证据对象」匹配 Macro 候选并派生出对象级完整状态。
 *
 * 主路径(用户要求):canonical region id 级 ——
 *   Evidence 对象(mirror connection) → candidate_brain_regions.canonical_region_id
 *   → pairKey(canonical_source_id, canonical_target_id) → ranking 命中。
 * 回退:canonical id 缺失(未映射对象)时才用名称级,并输出
 *   [evidence-macro-match] 调试日志。
 */
export function useMacroViewForEvidence(
  targetId: string | null | undefined,
  sourceRegion: string | null | undefined,
  targetRegion: string | null | undefined,
  sourceCanonicalId: string | null | undefined,
  targetCanonicalId: string | null | undefined,
): MacroCandidateView | null {
  const { candidates, byKey, loading, promotedAtByTargetId } = useMacroCandidates()
  return useMemo(() => {
    if (!targetId || loading || candidates.length === 0) return null

    const srcId = sourceCanonicalId || null
    const tgtId = targetCanonicalId || null

    let view: MacroCandidateView | null = null
    let matchedBy = 'none'
    if (srcId && tgtId) {
      view = byKey.get(pairKey(srcId, tgtId)) ?? null
      if (view) matchedBy = 'canonical_id'
    }
    if (!view) {
      // 名称级回退(仅未映射对象;左右前缀/细粒度名通常不命中)
      const keyByName = regionPairKeyForEvidence(sourceRegion, targetRegion)
      view = keyByName
        ? candidates.find(c => regionPairKeyForEvidence(c.sourceName, c.targetName) === keyByName) ?? null
        : null
      if (view) matchedBy = 'name'
    }

    // 调试日志:每次对象匹配判定输出(用户要求 #5)
    // eslint-disable-next-line no-console
    console.log(
      '[evidence-macro-match]',
      JSON.stringify({
        target_id: targetId,
        source_mirror: sourceRegion ?? null,
        canonical_source: srcId,
        target_mirror: targetRegion ?? null,
        canonical_target: tgtId,
        matched: Boolean(view),
        matched_by: matchedBy,
      }),
    )

    if (!view) return null
    const humanDecision = loadReviewStatus(targetId)
    const rollback = latestRollback(targetId)
    const promotedAt = promotedAtByTargetId[targetId] ?? null
    const status = deriveWorkflowStatus({
      ranking: view.ranking,
      review: view.review,
      ruleResult: view.ruleResult,
      humanDecision,
      rollbackAt: rollback?.at ?? null,
      promotedAt,
    })
    return { ...view, status }
  }, [byKey, candidates, loading, targetId, sourceRegion, targetRegion, sourceCanonicalId, targetCanonicalId, promotedAtByTargetId])
}

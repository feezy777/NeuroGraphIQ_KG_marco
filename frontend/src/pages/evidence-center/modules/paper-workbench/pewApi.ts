/**
 * Paper Evidence Workbench — 证据发现工作台 API（任务级:ranking_id 隔离）。
 * 生命周期:检索(不入库) → 入库去重/绑定 → 函数规则初筛 → LLM 语义审核 → 合成候选。
 */
import { getJson, postJson } from '../../../../api/client'

const BASE = '/api/paper-evidence-workbench'

// ── 类型 ──────────────────────────────────────────────────────────────────────

/** multi_search 统一记录(未入库,入库后以 paper_id 为身份) */
export interface PewSearchPaper {
  pmid: string
  doi: string
  title: string
  abstract: string
  authors?: string | null
  journal: string
  year: string
  source: string
  discovery_source?: string
  matched_queries?: string[]
  query_strategy?: string
  [k: string]: unknown
}

export interface PewPaperRow {
  paper_id: string
  role: string
  title: string
  authors: string | null
  journal: string | null
  year: number | null
  pmid: string
  doi: string | null
  abstract_available: boolean
  fulltext_available: boolean
  source: string
  retrieved_at: string | null
  has_segments: boolean
}

/** 待 AI 审核 / 已审核片段段(Step 2 函数筛选产物) */
export interface PewSegment {
  segment_id: string
  paper_id: string
  section: string
  source_type: string
  sentence: string
  context_before: string
  context_after: string
  matched_source: string | null
  matched_target: string | null
  proximity: string
  retrieval_method: string
  rule_score: number | null
  decision: string | null
  confidence: number | null
  evidence_type: string | null
  reason: string | null
  candidate_level: 'strong' | 'medium' | 'weak' | null
  relation_terms: string[]
  paper_title: string
  paper_pmid: string
  paper_doi: string | null
}

/** 审核结果(+Evidence Candidate 合成) */
export interface PewReviewItem {
  segment_id: string
  sentence: string
  section: string
  context_before: string
  context_after: string
  matched_source: string | null
  matched_target: string | null
  proximity: string
  rule_score: number | null
  paper_title: string
  paper_pmid: string
  decision: 'supported' | 'partial_support' | 'uncertain' | 'not_supported'
  confidence: number | null
  evidence_type: string | null
  reason: string | null
  suggested_connection_type: string | null
  direction_support: string | null
  connection_type_supported: string | null
  supporting_phrase: string | null
  contradiction_reason: string | null
  failed: boolean
  model_name: string | null
  candidate: boolean
}

export interface PewSearchParams {
  source_region: string
  target_region: string
  connection_type?: string | null
  query?: string | null
  limit?: number
}

export interface PewRunResult {
  bound?: number
  count?: number
  inserted?: number
  /** 入库分类明细(state: reuse/created) */
  papers?: Array<Record<string, unknown>>
}

/** Step 3 LLM 批量审核结果与汇总 */
export interface PewReviewRunResult {
  results: Array<{
    segment_id: string
    decision: string
    failed: boolean
    model: string
    confidence: number | null
    evidence_type: string | null
    reason: string
    connection_type_supported: string | null
    direction_support: string | null
    supporting_phrase: string | null
    contradiction_reason: string | null
  }>
  model: string | null
  summary: {
    reviewed: number
    skipped: number
    by_decision: Record<string, number>
    failed: number
    total_tokens: { prompt_tokens: number; completion_tokens: number; total_tokens: number }
    elapsed_seconds: number
  }
}

/** Step 2 函数筛选分类统计(零 LLM;每批累加) */
export interface PewScreenStats {
  processed: number
  fulltext: number
  abstract: number
  title: number
  no_text: number
  strong: number
  medium: number
  weak: number
}

export interface PewScreenResult {
  inserted: number
  updated: number
  stats: PewScreenStats
}

/** 可编辑默认检索词(canonical aliases + 连接类型同义词;前端不做脑区名称扩展) */
export interface PwQuery {
  q: string
  label: string
  source: string
}

/** 发现阶段线索自动整备统计(线索数/已存在/新增/无法解析/失败数/当前任务论文) */
export interface PewImportStats {
  clues: number
  existing: number
  created: number
  unresolved: number
  failed: number
  task_papers: number
}

export interface PewTaskInitResult {
  skipped: boolean
  stats: PewImportStats
  failed: Array<{ paper_id: string; title: string | null; reason: string }>
}

// ── 端点 ──────────────────────────────────────────────────────────────────────

export const pewSearch = (params: PewSearchParams) =>
  postJson<{ results: PewSearchPaper[] }>(`${BASE}/search`, params)

/** 检索结果 → Paper Library 去重入库 + 绑定任务工作区 */
export const pewUpsertPapers = (rankingId: string, papers: Array<Record<string, unknown>>) =>
  postJson<PewRunResult>(`${BASE}/papers`, { ranking_id: rankingId, papers })

/** 任务论文工作区列表(按任务隔离) */
export const pewListPapers = (rankingId: string) =>
  getJson<{ ranking_id: string; items: PewPaperRow[] }>(`${BASE}/papers`, { ranking_id: rankingId })

/** 已有 Paper Discovery 线索 → 工作区(线索≠证据;仍需规则初筛+LLM 审核) */
export const pewImportLines = (rankingId: string) =>
  postJson<{ count: number; stats?: PewImportStats }>(`${BASE}/import-lines`, { ranking_id: rankingId })

/** 进入任务自动整备(幂等;已完成非 force → skipped,直接返回现状;失败不阻塞) */
export const pewInitTaskPapers = (rankingId: string, force = false) =>
  postJson<PewTaskInitResult>(`${BASE}/papers/init`, { ranking_id: rankingId, force })

/** 默认检索词建议(2~4 条,可编辑) */
export const pewSuggestQueries = (params: {
  source_region: string
  target_region: string
  connection_type?: string | null
}) =>
  postJson<{ queries: PwQuery[] }>(`${BASE}/queries`, params)

/** 移出当前任务(论文保留在 Paper Library) */
export const pewRemoveTaskPaper = (rankingId: string, paperId: string) =>
  postJson<{ removed: number }>(`${BASE}/papers/remove`, { ranking_id: rankingId, paper_id: paperId })

/** Step 2 函数筛选(零 LLM;幂等,支持分批+按批统计累加) */
export const pewRunSegments = (
  rankingId: string,
  paperIds: string[],
  connectionType?: string | null,
) =>
  postJson<PewScreenResult>(`${BASE}/segments/run`, {
    ranking_id: rankingId,
    paper_ids: paperIds,
    connection_type: connectionType,
  })

export const pewListSegments = (rankingId: string) =>
  getJson<{ ranking_id: string; items: PewSegment[] }>(`${BASE}/segments`, { ranking_id: rankingId })

/** Step 3 LLM 语义审核(批量;同 prompt_version 已审直接复用;单条 retry+失败记录) */
export const pewRunReviews = (
  rankingId: string,
  segmentIds: string[],
  connectionType?: string | null,
  force = false,
) =>
  postJson<PewReviewRunResult>(
    `${BASE}/reviews/run`,
    { ranking_id: rankingId, segment_ids: segmentIds, connection_type: connectionType, force },
  )

/** 审核结果 + Evidence Candidate 计算 */
export const pewListReviews = (rankingId: string) =>
  getJson<{ ranking_id: string; items: PewReviewItem[]; candidates: PewReviewItem[] }>(
    `${BASE}/reviews`,
    { ranking_id: rankingId },
  )

/** Step 4 Evidence Candidate(引用 segment/review;译文为辅助阅读) */
export interface PewEvidenceCandidate {
  segment_id: string
  paper_id: string
  candidate_status: 'candidate' | 'review_required' | 'excluded'
  evidence_type: string | null
  ai_decision: string
  ai_confidence: number | null
  selected_for_review: boolean
  translation_id: string | null
  translated_text: string | null
  translation_language: string | null
  translation_model: string | null
  translation_prompt_version: string | null
  section: string
  sentence: string
  context_before: string
  context_after: string
  candidate_level: string | null
  rule_score: number | null
  matched_source: string | null
  matched_target: string | null
  relation_terms: string[]
  proximity: string
  source_type: string
  paper_title: string
  paper_pmid: string
  paper_doi: string | null
  paper_journal: string
  paper_year: number | null
  reason: string | null
  connection_type_supported: string | null
  direction_support: string | null
  supporting_phrase: string | null
  contradiction_reason: string | null
  failed: boolean
}

export interface PewTranslateResult {
  translated: number
  reused: number
  kept: number
  total_tokens: number
  model: string
  results: Array<{ segment_id: string; status: string; reason?: string }>
}

/** Step 4: Step3 结果 → Evidence Candidate(幂等;Gate 不通过→review_required) */
export const pewSyncCandidates = (rankingId: string) =>
  postJson<{ synced: number; stats: Record<string, number> }>(`${BASE}/candidates/sync`, { ranking_id: rankingId })

export const pewListCandidates = (rankingId: string) =>
  getJson<{ ranking_id: string; items: PewEvidenceCandidate[] }>(`${BASE}/candidates`, { ranking_id: rankingId })

/** 中文辅助翻译(幂等;同版本复用 0 调用;force=覆盖重译) */
export const pewTranslateCandidates = (rankingId: string, segmentIds?: string[], force = false) =>
  postJson<PewTranslateResult>(`${BASE}/candidates/translate`, {
    ranking_id: rankingId, segment_ids: segmentIds ?? null, force,
  })

export const pewSelectCandidate = (rankingId: string, segmentId: string, selected: boolean) =>
  postJson<{ segment_id: string; selected: boolean }>(`${BASE}/candidates/select`, {
    ranking_id: rankingId, segment_id: segmentId, selected,
  })

export const pewExcludeCandidate = (rankingId: string, segmentId: string) =>
  postJson<{ segment_id: string; candidate_status: string }>(`${BASE}/candidates/exclude`, {
    ranking_id: rankingId, segment_id: segmentId,
  })

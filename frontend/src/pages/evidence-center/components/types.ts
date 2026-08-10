export type Direction = 'supports' | 'partial' | 'contradicts' | 'mixed' | 'not_found'
export type PassageDirection = 'supports' | 'partial' | 'contradicts' | 'not_found'
export type EvidenceLevel = 'direct' | 'indirect' | 'interpretive' | 'background'
export type QueueStatus = 'pending' | 'searching' | 'extracting' | 'awaiting_review' | 'completed' | 'skipped' | 'failed'

export interface ClaimComponent {
  component_type: string
  statement: string
  required: boolean
  metadata: Record<string, unknown>
}

export interface WorkbenchPassage {
  hash: string
  paper_id?: string | null
  paper_passage_id?: string | null
  source_scope: 'abstract' | 'fulltext'
  section_title: string | null
  paragraph_index: number | null
  paragraph_id: string | null
  passage: string
  translation_zh: string | null
  direction: PassageDirection
  evidence_level: EvidenceLevel
  reason: string
  confidence: number
  semantic_confidence: number | null
  source_locator: string | null
  source_verified: boolean
  source_verification_method: string | null
  supported_components: string[]
  evidence_dimension?: 'existence' | 'function' | 'mixed' | null
}

export interface CoverageSummary {
  required_components: string[]
  supported_components: string[]
  contradicted_components: string[]
  uncovered_components: string[]
  coverage_ratio: number
  has_conflict: boolean
  full_claim_supported: boolean
}

export interface WorkbenchDraft {
  query: string
  selectedPmid: string
  passages: WorkbenchPassage[]
  translations: Record<string, string>
  reviewerDirection: Direction
  reviewerEvidenceLevel: EvidenceLevel
  reviewerConfidence: string
  note: string
  step: number
}

export interface QueueEntry {
  target_type: string
  target_id: string
  label: string
  confidence: number | null
  status: QueueStatus
  evidenceCount: number
  taskItemId?: string
  draftPmid?: string
  preprocessOutcome?: string | null
  modelDirection?: Direction | null
  /** 粒度(候选模块从 getEvidenceTarget DTO 填充,ContextBar 展示用) */
  granularity?: string | null
  draftPassages?: WorkbenchPassage[]
  draftDirection?: Direction
  draft?: WorkbenchDraft
}

export const QUEUE_STATUS_LABEL: Record<QueueStatus, string> = {
  pending: '待处理',
  searching: '检索中',
  extracting: '提取中',
  awaiting_review: '待审核',
  completed: '已完成',
  skipped: '已跳过',
  failed: '失败',
}

/** 队列条目状态 → 语义色板(ok/warn/bad/info/muted) */
export function queueStatusTone(status: QueueStatus): string {
  switch (status) {
    case 'completed': return 'ok'
    case 'awaiting_review': return 'warn'
    case 'failed': return 'bad'
    case 'pending':
    case 'searching':
    case 'extracting': return 'info'
    case 'skipped': return 'muted'
    default: return 'muted'
  }
}

export const DIRECTION_LABEL: Record<Direction, string> = {
  supports: '支持',
  partial: '部分支持',
  contradicts: '矛盾',
  mixed: '混合证据',
  not_found: '不采用',
}

export const LEVEL_LABEL: Record<EvidenceLevel, string> = {
  direct: '直接证据',
  indirect: '间接证据',
  interpretive: '作者解释',
  background: '背景证据',
}

export const LEVEL_HINT: Record<EvidenceLevel, string> = {
  direct: '实验结果直接支持该子事实',
  indirect: '实验结果支持关键部分，但需要合理推断',
  interpretive: '作者 Discussion/Conclusion 中的解释',
  background: '背景性陈述或引用已有研究',
}

export type EvidenceDimension = 'existence' | 'function' | 'mixed'

export const DIMENSION_LABEL: Record<EvidenceDimension, string> = {
  existence: '存在性证据',
  function: '功能性证据',
  mixed: '混合证据',
}

export const DIMENSION_HINT: Record<EvidenceDimension, string> = {
  existence: '论文证明该对象本身存在（如解剖投射、回路存在），不涉及功能',
  function: '论文描述该对象的功能/效应/角色',
  mixed: '论文同时涉及存在性与功能性',
}

export const COMPONENT_LABEL: Record<string, string> = {
  source_region: '源脑区',
  target_region: '目标脑区',
  relation: '连接关系',
  direction: '方向',
  function: '功能',
  circuit_identity: '回路身份',
  circuit_role: '回路角色',
  step_order: '步骤顺序',
  context: '辅助上下文',
}

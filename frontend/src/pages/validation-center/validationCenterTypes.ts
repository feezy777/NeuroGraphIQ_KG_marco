export type ValidationCenterTabId =
  | 'overview' | 'rule_check' | 'dual_review' | 'review' | 'promotion'

export type MirrorKgSubTab = 'connections' | 'functions' | 'circuits' | 'triples' | 'evidence'
export type MacroClinicalSubTab =
  | 'circuit_steps'
  | 'projection_functions'
  | 'memberships'
  | 'circuit_functions'
  | 'cross_validation'
  | 'dual_model'
export type FinalKgSubTab =
  | 'circuit'
  | 'circuit_step'
  | 'projection'
  | 'projection_function'
  | 'membership'
  | 'region_function'
  | 'circuit_function'
  | 'triple'
  | 'evidence'

export interface ValidationCenterCounts {
  mirrorConnections: number
  mirrorFunctions: number
  mirrorCircuits: number
  mirrorTriples: number
  macroCircuitSteps: number
  macroProjectionFunctions: number
  macroMemberships: number
  macroCrossResults: number
  macroDualResults: number
  finalCircuits: number
  finalProjections: number
  finalSteps: number
  finalFunctions: number
  finalTriples: number
  pendingReview: number
  ruleChecked: number
  promotionReady: number
  hasApiError: boolean
  warnings: string[]
}

export interface ValidationCenterNavState {
  tab: ValidationCenterTabId
  mirrorTab: MirrorKgSubTab
  macroTab: MacroClinicalSubTab
  finalTab: FinalKgSubTab
  batchId: string
  resourceId: string
  sourceAtlas: string
  granularityLevel: string
}

export const VALIDATION_CENTER_TABS: ValidationCenterTabId[] = ['overview', 'rule_check', 'dual_review', 'review', 'promotion']

export const DEFAULT_NAV: ValidationCenterNavState = {
  tab: 'overview',
  mirrorTab: 'connections',
  macroTab: 'circuit_steps',
  finalTab: 'circuit',
  batchId: '',
  resourceId: '',
  sourceAtlas: '',
  granularityLevel: '',
}

// ── Circuit validation types ───────────────────────────────────────────────
export interface CircuitValidationRun {
  id: string; granularity_level: string; status: string
  rule_validation_status: string; dual_review_status: string; adjudication_status: string
  rule_total_count: number; rule_passed_count: number; rule_failed_count: number; rule_blocked_count: number
  dual_review_agreement_count: number; dual_review_conflict_count: number
  reviewer_a_provider: string; reviewer_b_provider: string
  created_at?: string; started_at?: string; completed_at?: string
}

export interface CircuitValidationResult {
  id: string; run_id: string; target_type: string; target_id: string
  object_label?: string; rule_overall_status?: string; rule_blocked: boolean
  rule_validation_result_json: Array<{rule_code: string; severity: string; status: string; message: string}>
  reviewer_a_decision?: string; reviewer_a_confidence?: number
  reviewer_b_decision?: string; reviewer_b_confidence?: number
  adjudication_status?: string; adjudication_confidence_diff?: number
  adjudication_summary?: string; recommended_review_priority?: string
}

export interface CircuitValidationCreateRequest {
  granularity_level: string; circuit_ids: string[]; step_ids: string[]; batch_ids: string[]
  dry_run?: boolean; max_objects?: number
}

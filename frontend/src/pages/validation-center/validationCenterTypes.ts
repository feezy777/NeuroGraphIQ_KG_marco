export type ValidationCenterTabId =
  | 'rule_check'
  | 'dual_model'
  | 'review'
  | 'promotion'
  | 'macro'
  | 'final'

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

export const VALIDATION_CENTER_TABS: ValidationCenterTabId[] = [
  'rule_check',
  'dual_model',
  'review',
  'promotion',
  'macro',
  'final',
]

export const DEFAULT_NAV: ValidationCenterNavState = {
  tab: 'rule_check',
  mirrorTab: 'connections',
  macroTab: 'circuit_steps',
  finalTab: 'circuit',
  batchId: '',
  resourceId: '',
  sourceAtlas: '',
  granularityLevel: '',
}

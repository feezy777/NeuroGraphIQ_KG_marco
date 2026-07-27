export type ValidationCenterTabId =
  | 'mirror'
  | 'promotion'
  | 'macro'
  | 'final'

export type MirrorKgSubTab = 'rule_check' | 'review' | 'dual_model' | 'connections' | 'functions' | 'circuits' | 'triples' | 'evidence'
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
  'mirror',
  'promotion',
  'macro',
  'final',
]

export const DEFAULT_NAV: ValidationCenterNavState = {
  tab: 'mirror',
  mirrorTab: 'rule_check',
  macroTab: 'circuit_steps',
  finalTab: 'circuit',
  batchId: '',
  resourceId: '',
  sourceAtlas: '',
  granularityLevel: '',
}

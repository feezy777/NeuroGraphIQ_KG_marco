/**
 * Phase 1 Knowledge Production — page-level types.
 *
 * IMPORTANT: the granularity vocabulary here is the frozen Gate7B vocabulary
 * (G1_MACRO..G4_MICROSTRUCTURAL_FINE). It deliberately does NOT reuse the
 * global granularity Context (`useGlobalGranularity`), whose legacy vocabulary
 * (macro/meso/sub_connectivity/fine_cyto/molecular_attr) is being retired.
 * Do not add a third vocabulary.
 */

export type KpGranularity =
  | 'G1_MACRO'
  | 'G2_MESO_ANATOMICAL'
  | 'G3_MESO_FINE'
  | 'G4_MICROSTRUCTURAL_FINE'

export interface KpGranularityOption {
  value: KpGranularity
  /** Short button label. Display only — never persist this. */
  label: string
}

export const KP_GRANULARITY_OPTIONS: KpGranularityOption[] = [
  { value: 'G1_MACRO', label: 'G1' },
  { value: 'G2_MESO_ANATOMICAL', label: 'G2' },
  { value: 'G3_MESO_FINE', label: 'G3' },
  { value: 'G4_MICROSTRUCTURAL_FINE', label: 'G4' },
]

/** One canonical BrainRegion usable as a discovery seed (Gate7B authority). */
export interface BrainRegionSeed {
  entity_pk: number
  entity_id: string
  name_en: string | null
  name_zh: string | null
  abbreviation: string | null
  granularity_level: string | null
  region_category: string | null
  hemisphere: string | null
  species_taxon_id: string | null
  record_status: string | null
  review_status: string | null
  atlas_names: string[]
}

export interface BrainRegionSeedListResponse {
  items: BrainRegionSeed[]
  total: number
}

export interface BrainRegionSeedDetail extends BrainRegionSeed {
  definition_en: string | null
  parent_region_pk: number | null
  hierarchy_depth: number | null
  external_region_ids: string[]
  mapping_types: string[]
  mapping_review_statuses: string[]
}

export interface BrainRegionSeedQuery {
  granularityLevel?: KpGranularity | null
  sourceAtlas?: string
  search?: string
  limit: number
  offset: number
}

export interface WorkflowStepDef {
  id: string
  label: string
}

/** Read-only counts backing the Production Index summary row. */
export interface BrainRegionSummary {
  total: number
  by_granularity: Record<string, number>
}

/**
 * BrainRegion Workspace top-level tabs (Phase 1B, frozen in
 * docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8.2).
 *
 * Candidate subtypes (Circuits / Connections / Functions / Related Regions)
 * belong INSIDE Candidates — they are deliberately NOT top-level tabs, and
 * Promotion is deliberately NOT a tab (it becomes a governed action later).
 */
export type WorkspaceTabId =
  | 'overview'
  | 'discovery'
  | 'candidates'
  | 'evidence'
  | 'canonicalization'
  | 'validation'
  | 'history'

export interface WorkspaceTabDef {
  id: WorkspaceTabId
  label: string
}

export const WORKSPACE_TABS: WorkspaceTabDef[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'discovery', label: 'Discovery' },
  { id: 'candidates', label: 'Candidates' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'canonicalization', label: 'Canonicalization' },
  { id: 'validation', label: 'Validation' },
  { id: 'history', label: 'History' },
]

/** High-level lifecycle shown in the workspace. Selection is no longer a step. */
export const WORKSPACE_WORKFLOW_STEPS: WorkflowStepDef[] = [
  { id: 'discover', label: 'Discover' },
  { id: 'canonicalize', label: 'Canonicalize' },
  { id: 'validate', label: 'Validate' },
  { id: 'promote', label: 'Promote' },
]

/**
 * Phase 2A — Discovery Run (workflow / provenance).
 *
 * A run records ONE attempt to discover candidate knowledge around ONE
 * BrainRegion seed. It is NOT knowledge: it never represents a circuit /
 * connection / function / evidence / assertion.
 *
 * Frozen vocabulary, mirroring the CHECK constraints on
 * knowledge_discovery_runs. `status` (execution) and `outcome` (scientific
 * result) are independent — see docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §13.
 */
export type DiscoveryType = 'LLM_DISCOVERY' | 'LITERATURE_DISCOVERY'

export type DiscoveryRunStatus =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'

export type DiscoveryRunOutcome =
  | 'CANDIDATES_FOUND'
  | 'NO_CANDIDATES_FOUND'
  | 'NO_EVIDENCE_FOUND'

export interface DiscoveryRun {
  run_id: string
  seed_entity_id: string
  discovery_type: DiscoveryType
  status: DiscoveryRunStatus
  outcome: DiscoveryRunOutcome | null
  provider: string | null
  model_name: string | null
  prompt_key: string | null
  prompt_version: string | null
  query_strategy_version: string | null
  created_by: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
}

export interface DiscoveryRunListResponse {
  items: DiscoveryRun[]
  total: number
}

export interface DiscoveryRunQuery {
  discoveryType?: DiscoveryType | null
  status?: DiscoveryRunStatus | null
  limit?: number
  offset?: number
}

/** Human label for a run status. Display only — never persist this. */
export const DISCOVERY_STATUS_LABELS: Record<DiscoveryRunStatus, string> = {
  QUEUED: 'Queued',
  RUNNING: 'Running',
  COMPLETED: 'Completed',
  FAILED: 'Failed',
  CANCELLED: 'Cancelled',
}

/**
 * Neutral badge tone per status. Deliberately restrained: a run's status is a
 * lifecycle fact, not a scientific judgement, so only failure/cancellation get
 * a non-neutral tone.
 */
export const DISCOVERY_STATUS_TONES: Record<DiscoveryRunStatus, string> = {
  QUEUED: 'badge-gray',
  RUNNING: 'badge-blue',
  COMPLETED: 'badge-green',
  FAILED: 'badge-red',
  CANCELLED: 'badge-gray',
}

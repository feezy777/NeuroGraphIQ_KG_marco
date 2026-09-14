/**
 * Phase 1 Knowledge Production — page-level types.
 *
 * IMPORTANT: the granularity vocabulary here is the frozen Gate7B vocabulary
 * (G1_MACRO..G4_MICROSTRUCTURAL_FINE). It deliberately does NOT reuse the
 * global granularity Context (`useGlobalGranularity`), whose legacy vocabulary
 * (macro/meso/sub_connectivity/fine_cyto/molecular_attr) is being retired.
 * Do not add a third vocabulary.
 */
import type { Language } from '../../i18n'

export type KpGranularity =
  | 'G1_MACRO'
  | 'G2_MESO_ANATOMICAL'
  | 'G3_MESO_FINE'
  | 'G4_MICROSTRUCTURAL_FINE'

export interface KpGranularityOption {
  value: KpGranularity
  /**
   * Stable short token (G1..G4). This — not the translated label — is what
   * test ids and any logic key off, so localizing never changes behaviour.
   */
  key: string
  /** i18n key for the display label. Never persist the resolved text. */
  labelKey: string
}

// The authority vocabulary stays G1_MACRO..G4_MICROSTRUCTURAL_FINE. `key` is a
// display-side abbreviation only.
export const KP_GRANULARITY_OPTIONS: KpGranularityOption[] = [
  { value: 'G1_MACRO', key: 'G1', labelKey: 'knowledgeProduction.granularity.G1_MACRO' },
  {
    value: 'G2_MESO_ANATOMICAL',
    key: 'G2',
    labelKey: 'knowledgeProduction.granularity.G2_MESO_ANATOMICAL',
  },
  { value: 'G3_MESO_FINE', key: 'G3', labelKey: 'knowledgeProduction.granularity.G3_MESO_FINE' },
  {
    value: 'G4_MICROSTRUCTURAL_FINE',
    key: 'G4',
    labelKey: 'knowledgeProduction.granularity.G4_MICROSTRUCTURAL_FINE',
  },
]

/**
 * Locale-aware BrainRegion naming (docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §16).
 *
 *   zh-CN: primary = name_zh, secondary = name_en
 *   en-US: primary = name_en, secondary = name_zh
 *
 * If the preferred name is empty the OTHER name becomes primary, so a region is
 * never shown nameless. The secondary scientific name is never dropped — it
 * falls back to entity_id only when both names are missing.
 */
export function brainRegionNames(
  region: { name_en: string | null; name_zh: string | null; entity_id: string },
  language: Language,
): { primary: string; secondary: string | null } {
  const en = region.name_en?.trim() || null
  const zh = region.name_zh?.trim() || null
  const preferZh = language === 'zh-CN'
  const primary = (preferZh ? zh : en) ?? (preferZh ? en : zh) ?? region.entity_id
  const other = preferZh ? en : zh
  return { primary, secondary: other && other !== primary ? other : null }
}

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
  /** i18n key. The step's identity is `id`. */
  labelKey: string
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
  /** i18n key. The tab's identity is `id`; only its caption is localizable. */
  labelKey: string
}

export const WORKSPACE_TABS: WorkspaceTabDef[] = [
  { id: 'overview', labelKey: 'knowledgeProduction.tabs.overview' },
  { id: 'discovery', labelKey: 'knowledgeProduction.tabs.discovery' },
  { id: 'candidates', labelKey: 'knowledgeProduction.tabs.candidates' },
  { id: 'evidence', labelKey: 'knowledgeProduction.tabs.evidence' },
  { id: 'canonicalization', labelKey: 'knowledgeProduction.tabs.canonicalization' },
  { id: 'validation', labelKey: 'knowledgeProduction.tabs.validation' },
  { id: 'history', labelKey: 'knowledgeProduction.tabs.history' },
]

/** High-level lifecycle shown in the workspace. Selection is no longer a step. */
export const WORKSPACE_WORKFLOW_STEPS: WorkflowStepDef[] = [
  { id: 'discover', labelKey: 'knowledgeProduction.workflow.discover' },
  { id: 'canonicalize', labelKey: 'knowledgeProduction.workflow.canonicalize' },
  { id: 'validate', labelKey: 'knowledgeProduction.workflow.validate' },
  { id: 'promote', labelKey: 'knowledgeProduction.workflow.promote' },
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

/**
 * i18n key per run status. Display only — never persist the resolved text.
 *
 * The API/DB value (`status` itself) stays the raw enum: business logic must
 * compare `run.status === 'COMPLETED'`, never the translated label.
 */
export const DISCOVERY_STATUS_LABEL_KEYS: Record<DiscoveryRunStatus, string> = {
  QUEUED: 'knowledgeProduction.status.QUEUED',
  RUNNING: 'knowledgeProduction.status.RUNNING',
  COMPLETED: 'knowledgeProduction.status.COMPLETED',
  FAILED: 'knowledgeProduction.status.FAILED',
  CANCELLED: 'knowledgeProduction.status.CANCELLED',
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

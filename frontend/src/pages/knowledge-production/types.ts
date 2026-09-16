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
export type DiscoveryType =
  | 'LLM_DISCOVERY'
  | 'LITERATURE_DISCOVERY'
  | 'EVIDENCE_SEARCH'
  | 'CITATION_CHAINING'

/**
 * The discovery routes that search literature.
 *
 * An EXPLICIT list, deliberately not `discovery_type !== 'LLM_DISCOVERY'`: the
 * complement form would make any future non-literature route (a graph
 * traversal, a citation-only sweep) silently selectable and silently queried
 * against a literature endpoint. Adding a route must be a decision made here.
 */
export const LITERATURE_DISCOVERY_TYPES: readonly DiscoveryType[] = [
  'LITERATURE_DISCOVERY',
  'EVIDENCE_SEARCH',
  'CITATION_CHAINING',
]

/** Whether a run's route searches literature. The single source of that answer. */
export function isLiteratureDiscoveryType(discoveryType: DiscoveryType): boolean {
  return LITERATURE_DISCOVERY_TYPES.includes(discoveryType)
}

/**
 * Whether a run's route is the one that proposes LLM candidates (Phase P0-4A).
 *
 * An EQUALITY test, deliberately not `!isLiteratureDiscoveryType(...)`: the LLM
 * candidate read API admits exactly `LLM_DISCOVERY` and answers every other
 * route with 409, so the complement form would let a future route (a citation
 * sweep, a graph traversal) become selectable and then fail on click. The
 * complement is never the classification.
 */
export function isLlmDiscoveryType(discoveryType: DiscoveryType): boolean {
  return discoveryType === 'LLM_DISCOVERY'
}

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
 * Phase P0-4B — the outcome of ONE synchronous LLM Discovery execution.
 *
 * Only ``run`` is modelled. The endpoint also returns the typed in-memory
 * candidates, their validation warnings and the run's provenance metrics; this
 * workbench consumes none of them (the candidates are read back from the frozen
 * P0-2A read API, which is the only candidate source the UI may use). Mirroring
 * a large DTO field-by-field in order to ignore most of it would be a second
 * authority that could drift from the real one.
 *
 * ``run`` is the PERSISTED record, already terminal when the response arrives —
 * which is what makes polling unnecessary.
 */
export interface LlmDiscoveryExecutionResult {
  run: DiscoveryRun
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

// ---------------------------------------------------------------------------
// Phase 3E.2C — Literature production READ views
// ---------------------------------------------------------------------------
// Mirrors the approved backend read DTOs exactly. These describe the chain
// BrainRegion -> Literature Run -> PublicationDiscoveryHit -> Publication.
//
// A PublicationHit means ONLY "this query found this publication". It is
// retrieval provenance. It is deliberately NOT evidence: there is no supports,
// no contradicts, no evidence_strength, and no Evidence/KnowledgeAssertion
// shape here, because the backend does not return any and inventing one would
// assert a scientific claim the data does not make.

/** One provider's failure. Only the bounded fields the backend exposes. */
export interface ProviderFailureDiagnostic {
  provider: string | null
  status_code: number | null
  retryable: boolean | null
  message: string | null
  query_strategy: string | null
}

/**
 * Bounded view of a run's diagnostics.
 *
 * `all_providers_failed` is what separates a provider OUTAGE from a genuine
 * zero-result search — the two must never be rendered the same way.
 */
export interface LiteratureRunDiagnostics {
  provider_failures: ProviderFailureDiagnostic[]
  partial: boolean
  all_providers_failed: boolean
  papers_found: number | null
}

export interface LiteratureRun {
  run_id: string
  seed_entity_id: string
  discovery_type: DiscoveryType
  status: DiscoveryRunStatus
  outcome: DiscoveryRunOutcome | null
  provider: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
  error_code: string | null
  error_message: string | null
  diagnostics: LiteratureRunDiagnostics
}

export interface LiteratureRunListResponse {
  items: LiteratureRun[]
  total: number
}

/** One retrieval fact: this query found this publication. */
export interface PublicationHit {
  query_text: string
  query_family: string | null
  query_level: string | null
  source: string | null
  result_rank: number | null
  retrieved_at: string
  run_id: string | null
}

export interface Publication {
  entity_id: string
  original_title: string | null
  pmid: string | null
  pmcid: string | null
  doi: string | null
  publication_year: number | null
  source_database: string | null
  hits: PublicationHit[]
}

/**
 * Publications reached by ONE run.
 *
 * `distinct_publications` and `hits_total` are separate on purpose: one
 * publication found by three queries is ONE publication and THREE retrieval
 * facts. Collapsing them would hide the provenance the backend preserves.
 */
export interface PublicationListResponse {
  run_id: string
  items: Publication[]
  distinct_publications: number
  hits_total: number
}

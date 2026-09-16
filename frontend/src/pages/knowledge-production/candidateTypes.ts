/**
 * Phase P0-4A — the LLM Discovery candidate READ contract, as the API returns it.
 *
 * Mirrors the frozen backend DTO (P0-2A `DiscoveryCandidateReadItem` and its
 * `LlmCandidateListResponse` envelope) FIELD FOR FIELD. Nothing is renamed,
 * nothing is added, and nothing is derived: a second vocabulary here is how a
 * read contract drifts from what the backend actually persisted.
 *
 * Its own module rather than an addition to `types.ts` on purpose. The workspace
 * term test forbids the legacy `candidate_id` spelling in the page-level modules,
 * where that name meant the retired parsing Candidate DB. These rows are a
 * different thing entirely — LLM PROPOSALS staged under `discovery_candidates` —
 * and keeping their contract in its own file keeps the two from being confused in
 * either direction.
 *
 * A candidate is a PROPOSAL. It is not canonical knowledge, not validated, and
 * not evidence-backed. `status = accepted` means only "a human accepted it for
 * resolution"; it does NOT mean validated or promoted. No field here says
 * otherwise, and none may be invented to imply it.
 */
/**
 * The four candidate kinds the frozen DB CHECK admits.
 *
 * Display only: the frontend never re-classifies or re-derives this. `payload`
 * is the typed structure the backend persisted; `candidate_type` labels it.
 */
export type DiscoveryCandidateType = 'region' | 'connection' | 'circuit' | 'function'

/**
 * `discovery_candidates.status` — the frozen four.
 *
 * The same word `proposed` also names `kg_entities.record_status`, where it
 * means a CANONICAL row. These are different facts that happen to share a
 * spelling; this type is the candidate-side one.
 */
export type DiscoveryCandidateStatus = 'proposed' | 'accepted' | 'rejected' | 'deferred'

/** One persisted candidate, exactly as `GET .../llm-candidates` returns it. */
export interface LlmDiscoveryCandidate {
  candidate_id: string
  run_id: string
  seed_entity_id: string
  candidate_type: DiscoveryCandidateType
  local_id: string
  name: string
  /** The persisted typed candidate, verbatim. Never reconstructed from `name`. */
  payload: Record<string, unknown>
  confidence: number | null
  status: DiscoveryCandidateStatus
  created_at: string
  updated_at: string
}

export interface LlmCandidateListResponse {
  items: LlmDiscoveryCandidate[]
  total: number
}

/** i18n key per candidate type. Display only — never persist resolved text. */
export const CANDIDATE_TYPE_LABEL_KEYS: Record<DiscoveryCandidateType, string> = {
  region: 'knowledgeProduction.llmCandidates.type.region',
  connection: 'knowledgeProduction.llmCandidates.type.connection',
  circuit: 'knowledgeProduction.llmCandidates.type.circuit',
  function: 'knowledgeProduction.llmCandidates.type.function',
}

/**
 * Badge tone per candidate type.
 *
 * Four CATEGORICAL tones and no red/green: a candidate's kind is a taxonomy, not
 * a verdict. Reusing the red/green pair here would read as bad/good and imply a
 * judgement the data does not make.
 */
export const CANDIDATE_TYPE_TONES: Record<DiscoveryCandidateType, string> = {
  region: 'badge-blue',
  connection: 'badge-purple',
  circuit: 'badge-amber',
  function: 'badge-gray',
}

/** i18n key per candidate status. Display only — never persist resolved text. */
export const CANDIDATE_STATUS_LABEL_KEYS: Record<DiscoveryCandidateStatus, string> = {
  proposed: 'knowledgeProduction.llmCandidates.status.proposed',
  accepted: 'knowledgeProduction.llmCandidates.status.accepted',
  rejected: 'knowledgeProduction.llmCandidates.status.rejected',
  deferred: 'knowledgeProduction.llmCandidates.status.deferred',
}

/**
 * Badge tone per candidate status.
 *
 * Deliberately restrained, and deliberately NOT green for `accepted`. Green is
 * this workbench's "validated" tone; an accepted candidate is still only a
 * proposal that entered resolution. Nothing in this list may be read as
 * approved / canonical / evidence-backed.
 */
export const CANDIDATE_STATUS_TONES: Record<DiscoveryCandidateStatus, string> = {
  proposed: 'badge-gray',
  deferred: 'badge-amber',
  accepted: 'badge-blue',
  rejected: 'badge-gray',
}

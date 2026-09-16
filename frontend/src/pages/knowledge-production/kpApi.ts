/**
 * Phase 1 Knowledge Production — API client.
 *
 * Talks only to the /api/knowledge-production endpoints, which read the Gate7B
 * formal knowledge tables. No legacy staging endpoint is referenced.
 */
import { getJson, postJson } from '../../api/client'
import type { LlmCandidateListResponse } from './candidateTypes'
import type {
  BrainRegionSeedDetail,
  BrainRegionSeedListResponse,
  BrainRegionSeedQuery,
  BrainRegionSummary,
  DiscoveryRunListResponse,
  DiscoveryRunQuery,
  LiteratureRunListResponse,
  LlmDiscoveryExecutionResult,
  PublicationListResponse,
} from './types'

const BASE = '/api/knowledge-production'

export function fetchBrainRegionSeeds(
  q: BrainRegionSeedQuery,
): Promise<BrainRegionSeedListResponse> {
  return getJson<BrainRegionSeedListResponse>(`${BASE}/brain-regions`, {
    granularity_level: q.granularityLevel ?? undefined,
    source_atlas: q.sourceAtlas?.trim() || undefined,
    search: q.search?.trim() || undefined,
    limit: q.limit,
    offset: q.offset,
  })
}

export function fetchBrainRegionSeed(identifier: string): Promise<BrainRegionSeedDetail> {
  return getJson<BrainRegionSeedDetail>(
    `${BASE}/brain-regions/${encodeURIComponent(identifier)}`,
  )
}

/** One aggregate request backing the Production Index summary row. */
export function fetchBrainRegionSummary(): Promise<BrainRegionSummary> {
  return getJson<BrainRegionSummary>(`${BASE}/brain-regions/summary`)
}

/**
 * Phase 2A — Discovery Runs recorded for one BrainRegion, newest first.
 *
 * Read-only: Discovery RUN EXECUTION does not exist yet, so there is deliberately
 * no create/start/cancel function here (those arrive in a later phase, with the
 * lifecycle endpoints).
 */
export function fetchDiscoveryRuns(
  entityId: string,
  q: DiscoveryRunQuery = {},
): Promise<DiscoveryRunListResponse> {
  return getJson<DiscoveryRunListResponse>(
    `${BASE}/brain-regions/${encodeURIComponent(entityId)}/discovery-runs`,
    {
      discovery_type: q.discoveryType ?? undefined,
      status: q.status ?? undefined,
      limit: q.limit,
      offset: q.offset,
    },
  )
}

/**
 * Phase 3E.2C — Literature production, read-only.
 *
 * Two functions only. The run-publications response already carries every
 * publication's full retrieval hits, which is all the first inspection UI
 * needs; the cross-run publication endpoint is deliberately not wired until
 * real pilot data shows the UI actually requires it.
 */

/**
 * Literature runs for one BrainRegion, newest first.
 *
 * The backend admits only the literature routes here: an LLM_DISCOVERY run has
 * no publications and is not a literature resource, so it never appears.
 */
export function fetchLiteratureRuns(entityId: string): Promise<LiteratureRunListResponse> {
  return getJson<LiteratureRunListResponse>(
    `${BASE}/brain-regions/${encodeURIComponent(entityId)}/literature-runs`,
  )
}

/**
 * Publications reached by ONE run, each with all of its retrieval hits.
 *
 * Caller contract: `runId` must belong to a literature run. The backend answers
 * 404 for an LLM_DISCOVERY run — deliberately, since such a run never searched
 * literature and "found nothing" would be a false statement. Gate on
 * `isLiteratureDiscoveryType()` BEFORE calling; do not let a user discover the
 * boundary through a failed request.
 */
export function fetchRunPublications(runId: string): Promise<PublicationListResponse> {
  return getJson<PublicationListResponse>(
    `${BASE}/discovery-runs/${encodeURIComponent(runId)}/publications`,
  )
}

/**
 * Phase P0-4A — the candidates ONE LLM Discovery run proposed, newest contract.
 *
 * Read-only, and the ONLY candidate source: no mock, no cached JSON, no parsing
 * of a run log. The backend orders the rows (type, then local_id) and that order
 * is what the UI shows.
 *
 * Caller contract: `runId` must belong to an LLM_DISCOVERY run. The backend
 * answers 409 for any other route — deliberately, because a literature run
 * proposes no LLM candidates and "found none" would be a false statement about
 * it. Gate on `isLlmDiscoveryType()` BEFORE calling; a user should not discover
 * the boundary by watching a request fail.
 */
export function fetchRunLlmCandidates(runId: string): Promise<LlmCandidateListResponse> {
  return getJson<LlmCandidateListResponse>(
    `${BASE}/discovery-runs/${encodeURIComponent(runId)}/llm-candidates`,
  )
}

/**
 * Phase P0-4C — every LLM candidate proposed around ONE BrainRegion seed.
 *
 * Spans ALL of the region's LLM_DISCOVERY runs (newest run first, as the backend
 * orders them), which is exactly what a candidate POOL is. The Candidate
 * Knowledge tab uses this directly instead of walking the run history and
 * aggregating client-side: the backend is the authority on what belongs to a
 * region, and a client-side union would be a second, weaker answer.
 *
 * Each item carries `run_id`, so a row can still be attributed to its run.
 */
export function fetchBrainRegionLlmCandidates(
  entityId: string,
): Promise<LlmCandidateListResponse> {
  return getJson<LlmCandidateListResponse>(
    `${BASE}/brain-regions/${encodeURIComponent(entityId)}/llm-candidates`,
  )
}

/**
 * Phase P0-4B — START LLM Discovery for one BrainRegion seed.
 *
 * The one WRITE in this module, and the only way this UI can cause a run.
 *
 * No request body: the endpoint is the TRUSTED caller and is the sole author of
 * the run's provider, model and prompt provenance, so a client cannot fabricate
 * any of it. The seed is the only thing the caller supplies.
 *
 * SYNCHRONOUS: the response arrives once the run is already terminal, and its
 * `run` is the persisted record. There is nothing to poll and no run id to
 * invent — the caller takes the id from the response.
 *
 * Failures are typed and must never be flattened into "no candidates":
 *   404 NOT_FOUND                  unknown BrainRegion
 *   409 ACTIVE_RUN_EXISTS          an active run already exists for this seed
 *   502 LLM_*                      the model run failed (run already FAILED)
 */
export function executeLlmDiscovery(
  entityId: string,
): Promise<LlmDiscoveryExecutionResult> {
  return postJson<LlmDiscoveryExecutionResult>(
    `${BASE}/brain-regions/${encodeURIComponent(entityId)}/llm-discovery/execute`,
  )
}

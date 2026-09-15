/**
 * Phase 1 Knowledge Production — API client.
 *
 * Talks only to the /api/knowledge-production endpoints, which read the Gate7B
 * formal knowledge tables. No legacy staging endpoint is referenced.
 */
import { getJson } from '../../api/client'
import type {
  BrainRegionSeedDetail,
  BrainRegionSeedListResponse,
  BrainRegionSeedQuery,
  BrainRegionSummary,
  DiscoveryRunListResponse,
  DiscoveryRunQuery,
  LiteratureRunListResponse,
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

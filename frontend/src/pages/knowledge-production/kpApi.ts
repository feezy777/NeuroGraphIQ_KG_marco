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

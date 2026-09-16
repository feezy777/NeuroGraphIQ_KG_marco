/**
 * Knowledge Production route helpers (hash router — no routing library).
 *
 * TWO CLASSES OF IDENTIFIER, and the difference is the whole rule:
 *
 *   PUBLIC STABLE ID — a Gate7B public identifier. It is allocated by a public
 *   sequence, is stable for the life of the row, and IS the route identity:
 *
 *       entity_id      NGIQ-BR-00000001   -> a BrainRegion workspace
 *       candidate_id   NGIQ-DC-00000001   -> one LLM Discovery candidate
 *
 *   INTERNAL DATABASE KEY — never a route segment, never in a frontend contract,
 *   never in a payload sent to the API:
 *
 *       entity_pk  candidate_pk  review_pk  discovery_run_pk  seed_region_pk
 *
 * A `candidate_id` is a public id in the first sense (the P0-1 Gate7B workflow
 * layer allocates it exactly like `entity_id`); it is NOT the retired parsing
 * Candidate DB's key. An earlier revision of this header lumped the two together
 * and read as if no candidate could ever be addressed by URL, which contradicts
 * `KP_CANDIDATE_PATTERN` below. The rule is: public id in, `*_pk` out.
 */

export const KP_INDEX_PATH = '/knowledge-production'

const KP_WORKSPACE_PREFIX = `${KP_INDEX_PATH}/brain-regions/`

/** Matches a BrainRegion workspace hash path and captures the entity_id. */
export const KP_WORKSPACE_PATTERN = /^\/knowledge-production\/brain-regions\/([^/]+)$/

export function kpWorkspacePath(entityId: string): string {
  return `${KP_WORKSPACE_PREFIX}${encodeURIComponent(entityId)}`
}

export function navigate(path: string): void {
  window.location.hash = `#${path}`
}

export function entityIdFromWorkspacePath(path: string): string | null {
  const m = path.match(KP_WORKSPACE_PATTERN)
  return m ? decodeURIComponent(m[1]) : null
}

/**
 * Phase P0-4C — one Candidate inside a BrainRegion workspace.
 *
 * The `{candidateId}` segment is the PUBLIC `candidate_id` (`NGIQ-DC-*`) — see
 * the identifier rule at the top of this file. It is what makes a direct URL and
 * a browser refresh possible at all: an internal key would be unstable and must
 * never be exposed, and a `local_id` (`circuit_1`) is only unique WITHIN a run,
 * so it cannot address a candidate across a region's whole pool.
 *
 * The shape is `/brain-regions/{entityId}/candidates/{candidateId}`; the route
 * is matched BEFORE the one-segment workspace pattern in `App.tsx`, so a candidate
 * page can never be read as a workspace.
 */
export const KP_CANDIDATE_PATTERN =
  /^\/knowledge-production\/brain-regions\/([^/]+)\/candidates\/([^/]+)$/

export function kpCandidatePath(entityId: string, candidateId: string): string {
  return `${KP_WORKSPACE_PREFIX}${encodeURIComponent(entityId)}/candidates/${encodeURIComponent(candidateId)}`
}

export function candidateRefFromPath(
  path: string,
): { entityId: string; candidateId: string } | null {
  const m = path.match(KP_CANDIDATE_PATTERN)
  return m ? { entityId: decodeURIComponent(m[1]), candidateId: decodeURIComponent(m[2]) } : null
}

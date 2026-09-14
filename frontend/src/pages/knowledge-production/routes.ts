/**
 * Knowledge Production route helpers (hash router — no routing library).
 *
 * Public route identity for a BrainRegion is its Gate7B `entity_id`
 * (e.g. NGIQ-BR-00000001). Internal identifiers (entity_pk, candidate_id,
 * mirror/final ids) must never appear in the URL.
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

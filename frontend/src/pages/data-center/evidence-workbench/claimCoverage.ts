import type { ClaimComponent, CoverageSummary, Direction, WorkbenchPassage } from './types'

/** Frontend temporary coverage preview. Formal attach-preview recomputes server-side. */
export function computeTmpCoverage(
  claimComponents: ClaimComponent[],
  passages: WorkbenchPassage[],
): CoverageSummary {
  const required = new Set(claimComponents.filter(c => c.required).map(c => c.component_type))
  const supported = new Set<string>()
  const contradicted = new Set<string>()
  for (const p of passages) {
    if (!p.source_verified) continue
    const comps = new Set(p.supported_components)
    if (p.direction === 'contradicts') {
      comps.forEach(c => contradicted.add(c))
    } else {
      comps.forEach(c => supported.add(c))
    }
  }
  const supportedInRequired = [...supported].filter(c => required.has(c)).sort()
  const contradictedInRequired = [...contradicted].filter(c => required.has(c)).sort()
  const uncovered = [...required].filter(c => !supported.has(c)).sort()
  const hasConflict = supportedInRequired.length > 0 && contradictedInRequired.length > 0
  return {
    required_components: [...required].sort(),
    supported_components: supportedInRequired,
    contradicted_components: contradictedInRequired,
    uncovered_components: uncovered,
    coverage_ratio: required.size ? Math.round((supportedInRequired.length / required.size) * 10000) / 10000 : 0,
    has_conflict: hasConflict,
    full_claim_supported: required.size > 0 && supportedInRequired.length === required.size && !hasConflict,
  }
}

export function aggregateTmpDirection(coverage: CoverageSummary, passages: WorkbenchPassage[]): Direction {
  const verified = passages.filter(p => p.source_verified)
  if (verified.length === 0) return 'not_found'
  if (coverage.has_conflict) return 'mixed'
  const required = coverage.required_components
  if (required.length === 0) return 'not_found'
  if (required.every(c => coverage.supported_components.includes(c))) return 'supports'
  if (coverage.contradicted_components.length === required.length && coverage.supported_components.length === 0) return 'contradicts'
  if (coverage.supported_components.length > 0 || coverage.contradicted_components.length > 0) return 'partial'
  return 'not_found'
}

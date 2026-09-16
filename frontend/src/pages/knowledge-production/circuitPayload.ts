/**
 * Phase P0-4C — reading a Discovery payload, and resolving ONLY the relations it
 * declares explicitly.
 *
 * The hard scientific rule of this phase, stated once and enforced from here on:
 *
 *   a relationship may be displayed if and only if the Discovery payload STATES
 *   it. Everything below reads declared fields and looks declared refs up in the
 *   SAME RUN's candidates. Nothing here matches names, keywords, semantics,
 *   confidence values or co-occurrence, and nothing infers a missing link.
 *
 * A ref is one of exactly two things, as the frozen schema and parser define:
 *
 *   * the reserved token ``SEED`` — the run's own BrainRegion seed. The prompt
 *     calls it "the one reserved reference"; it is NOT a candidate, so it is
 *     resolved from the run's seed, never from the candidate list.
 *   * a ``local_id`` declared by another candidate IN THE SAME RUN
 *     (``region_1``, ``connection_3``, …). The parser rejects any other value as
 *     a dangling ref, so a stored payload's refs all resolve — this module still
 *     reports anything that does not, rather than dropping it.
 *
 * Pure functions only: no fetching, no React, no store. That is what makes the
 * non-inference rules directly testable.
 */
import type { LlmDiscoveryCandidate } from './candidateTypes'

/** The one reserved ref token (mirrors `SEED_REF` in the frozen backend schema). */
export const SEED_REF = 'SEED'

// ===========================================================================
// defensive readers — every payload field is optional until proven present
// ===========================================================================
function str(raw: unknown): string | null {
  return typeof raw === 'string' && raw.trim() !== '' ? raw : null
}

function num(raw: unknown): number | null {
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : null
}

/** A list of ref strings, or `[]`. Non-string entries are dropped, not coerced. */
function refList(raw: unknown): string[] {
  return Array.isArray(raw) ? raw.filter((r): r is string => typeof r === 'string') : []
}

export interface SpeciesContext {
  scope: string | null
  taxonIds: number[]
}

/** `species_context` is an OBJECT on circuit/connection/function payloads. */
export function readSpeciesContext(raw: unknown): SpeciesContext | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as { scope?: unknown; taxon_ids?: unknown }
  const scope = str(o.scope)
  const taxonIds = Array.isArray(o.taxon_ids)
    ? o.taxon_ids.filter((t): t is number => typeof t === 'number')
    : []
  if (scope === null && taxonIds.length === 0) return null
  return { scope, taxonIds }
}

export interface CircuitPayload {
  name: string | null
  description: string | null
  rationale: string | null
  confidence: number | null
  topologyHint: string | null
  speciesContext: SpeciesContext | null
  /** Verbatim declared refs. `[]` means the payload declared none — not "unknown". */
  regionRefs: string[]
  connectionRefs: string[]
  functionRefs: string[]
}

export function readCircuitPayload(payload: Record<string, unknown>): CircuitPayload {
  return {
    // `summary` is deliberately NOT read: the real payload has no such field, and
    // inventing a fallback would put a field on screen that the model never wrote.
    name: str(payload.name),
    description: str(payload.description),
    rationale: str(payload.rationale),
    confidence: num(payload.confidence),
    topologyHint: str(payload.topology_hint),
    speciesContext: readSpeciesContext(payload.species_context),
    regionRefs: refList(payload.region_refs),
    connectionRefs: refList(payload.connection_refs),
    functionRefs: refList(payload.function_refs),
  }
}

export interface ConnectionPayload {
  localId: string | null
  sourceRef: string | null
  targetRef: string | null
  /** The field is `directionality`; `direction` does not exist in the payload. */
  directionality: string | null
  connectionType: string | null
  rationale: string | null
  speciesContext: SpeciesContext | null
}

export function readConnectionPayload(payload: Record<string, unknown>): ConnectionPayload {
  return {
    localId: str(payload.local_id),
    sourceRef: str(payload.source_ref),
    targetRef: str(payload.target_ref),
    directionality: str(payload.directionality),
    connectionType: str(payload.connection_type),
    rationale: str(payload.rationale),
    speciesContext: readSpeciesContext(payload.species_context),
  }
}

export interface FunctionPayload {
  /** A function candidate's human label lives in `label`, not `name`. */
  label: string | null
  description: string | null
  rationale: string | null
  speciesContext: SpeciesContext | null
}

export function readFunctionPayload(payload: Record<string, unknown>): FunctionPayload {
  return {
    label: str(payload.label),
    description: str(payload.description),
    rationale: str(payload.rationale),
    speciesContext: readSpeciesContext(payload.species_context),
  }
}

// ===========================================================================
// explicit ref resolution
// ===========================================================================
export interface RefResolution {
  /** Declared refs that named a candidate in the same run, in declared order. */
  resolved: { ref: string; candidate: LlmDiscoveryCandidate }[]
  /** Whether the circuit declared the reserved SEED ref. */
  seed: boolean
  /** Declared refs that matched nothing. Reported, never silently dropped. */
  unresolved: string[]
}

/**
 * Resolve declared refs against the SAME RUN's candidates.
 *
 * `SEED` is peeled off first: it resolves to the run's seed BrainRegion, which is
 * not a candidate, so it must never be looked up in the candidate map (that would
 * report a correct ref as broken).
 */
export function resolveRefs(
  refs: string[],
  candidates: LlmDiscoveryCandidate[],
): RefResolution {
  const byLocalId = new Map(candidates.map(c => [c.local_id, c]))
  const resolved: RefResolution['resolved'] = []
  const unresolved: string[] = []
  let seed = false

  for (const ref of refs) {
    if (ref === SEED_REF) {
      seed = true
      continue
    }
    const candidate = byLocalId.get(ref)
    if (candidate) resolved.push({ ref, candidate })
    else unresolved.push(ref)
  }
  return { resolved, seed, unresolved }
}

export interface Edge {
  from: string
  to: string
}

/**
 * The ordered node sequence of an UNAMBIGUOUS linear path, or `null`.
 *
 * Returns a chain only when the explicitly declared edges form exactly one
 * start-to-end path: one node with no incoming edge, every node with at most one
 * incoming and one outgoing edge, and every edge on the walk. A branch, a
 * convergence, a cycle or a disconnected set all return `null` — the caller then
 * shows the connection table alone. Nothing is reordered or guessed to make a
 * prettier picture.
 */
export function linearChain(edges: Edge[]): string[] | null {
  if (edges.length === 0) return null
  const out = new Map<string, string[]>()
  const inDeg = new Map<string, number>()
  for (const { from, to } of edges) {
    out.set(from, [...(out.get(from) ?? []), to])
    inDeg.set(to, (inDeg.get(to) ?? 0) + 1)
    if (!inDeg.has(from)) inDeg.set(from, inDeg.get(from) ?? 0)
  }
  // A branch (two edges leaving one node) or a convergence (two entering) is not
  // a single path, and picking one branch would be an inference.
  for (const targets of out.values()) if (targets.length > 1) return null
  for (const deg of inDeg.values()) if (deg > 1) return null

  const starts = [...inDeg.entries()].filter(([, d]) => d === 0).map(([n]) => n)
  if (starts.length !== 1) return null // a cycle has no start; a split set has several

  const chain = [starts[0]]
  let cursor = starts[0]
  while (out.has(cursor)) {
    cursor = out.get(cursor)![0]
    chain.push(cursor)
  }
  // Every edge must lie on the walk: a dangling tail means the set is not one path.
  return chain.length === edges.length + 1 ? chain : null
}

/** The display label of a ref: the seed's name, or the candidate's name. */
export function refLabel(
  ref: string,
  byLocalId: Map<string, LlmDiscoveryCandidate>,
  seedName: string | null,
): string {
  if (ref === SEED_REF) return seedName ?? SEED_REF
  return byLocalId.get(ref)?.name ?? ref
}

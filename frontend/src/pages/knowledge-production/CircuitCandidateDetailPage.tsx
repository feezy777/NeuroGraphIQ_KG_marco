/**
 * Phase P0-4C — Circuit Candidate detail page (read-only).
 *
 * Every relationship on this page comes from a ref the Discovery payload
 * DECLARED, resolved against the same run's candidates. Nothing is matched by
 * name, keyword, similarity, confidence or co-occurrence, and nothing is filled
 * in when a relation is absent: an empty relation says so in words.
 *
 * The page is addressed by `entityId` + `candidateId` and re-reads everything
 * from them, so a direct URL or a browser refresh recovers the same view: the
 * region's candidate pool (to find the target and its run), then that RUN's
 * candidates (to resolve refs) and the region's run history (for provenance).
 *
 * This module is the CONTAINER. It owns fetching, the load states, the SEED
 * identity and — since P0-4C closeout — the ONLY call to `resolveRefs`; the
 * surfaces that draw the six sections live in `CircuitDetailSections.tsx` and are
 * handed already-resolved data. Splitting the file moved no decision out of here.
 */
import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import {
  fetchBrainRegionLlmCandidates,
  fetchBrainRegionSeed,
  fetchDiscoveryRuns,
  fetchRunLlmCandidates,
} from './kpApi'
import {
  CANDIDATE_STATUS_LABEL_KEYS,
  CANDIDATE_STATUS_TONES,
  type LlmDiscoveryCandidate,
} from './candidateTypes'
import {
  SEED_REF,
  linearChain,
  readCircuitPayload,
  readConnectionPayload,
  resolveRefs,
  type Edge,
} from './circuitPayload'
import {
  CircuitConnectionsSection,
  CircuitFunctionsSection,
  CircuitOverviewSection,
  CircuitProvenanceSection,
  CircuitRawSection,
  CircuitRegionsSection,
  CircuitStructureSection,
} from './CircuitDetailSections'
import { brainRegionNames, type BrainRegionSeedDetail, type DiscoveryRun } from './types'

type Props = {
  entityId: string
  candidateId: string
  onBack: () => void
}

export function CircuitCandidateDetailPage({ entityId, candidateId, onBack }: Props) {
  const { language, t } = useI18n()
  const [candidate, setCandidate] = useState<LlmDiscoveryCandidate | null>(null)
  const [runCandidates, setRunCandidates] = useState<LlmDiscoveryCandidate[]>([])
  const [run, setRun] = useState<DiscoveryRun | null>(null)
  // The seed's own record, so its display name can be derived at RENDER time:
  // storing the resolved string would freeze it at the language it was fetched in.
  const [seedDetail, setSeedDetail] = useState<BrainRegionSeedDetail | null>(null)
  const [state, setState] = useState<'loading' | 'ready' | 'notFound' | 'wrongType' | 'error'>(
    'loading',
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setState('loading')
    setError(null)

    const load = async () => {
      // 1. The region's pool finds the target — the ONLY entry point, so no page
      //    state is required and a refresh recovers the same view.
      const pool = await fetchBrainRegionLlmCandidates(entityId)
      if (cancelled) return
      const target = pool.items.find(c => c.candidate_id === candidateId) ?? null
      if (!target) {
        setState('notFound')
        return
      }
      // 2. Ref resolution is same-RUN, so the payload is read against the run the
      //    candidate itself belongs to — never the region-wide pool. Provenance
      //    comes from the existing run-history API rather than a second source.
      //    The seed's canonical NAME comes from the region's own read API: the
      //    run row carries only its entity_id, and `SEED` is a declared ref to
      //    that very BrainRegion, so showing an identifier where every other ref
      //    shows a name would be a display defect, not a scientific one. Its own
      //    identity is still listed verbatim under provenance.
      const [runRes, history, seedRegion] = await Promise.all([
        fetchRunLlmCandidates(target.run_id),
        fetchDiscoveryRuns(entityId),
        fetchBrainRegionSeed(target.seed_entity_id),
      ])
      if (cancelled) return
      setCandidate(target)
      setRunCandidates(runRes.items)
      setRun(history.items.find(r => r.run_id === target.run_id) ?? null)
      setSeedDetail(seedRegion)
      setState(target.candidate_type === 'circuit' ? 'ready' : 'wrongType')
    }

    load().catch((e: unknown) => {
      if (!cancelled) {
        setError(e instanceof Error ? e.message : String(e))
        setState('error')
      }
    })
    return () => {
      cancelled = true
    }
  }, [entityId, candidateId])

  // The seed's display name, in the ACTIVE language. `SEED` is a declared ref to
  // this very BrainRegion, so it is labelled with the region's own name — the
  // same locale-aware policy the workspace header uses — and falls back to the
  // raw identifier only when the name is unavailable.
  const seedName = seedDetail ? brainRegionNames(seedDetail, language).primary : null

  const back = (
    <button type="button" className="kp-back" data-testid="kp-circuit-back" onClick={onBack}>
      ← {t('knowledgeProduction.candidateKnowledge.backToPool')}
    </button>
  )

  // ---- load states. Each is its own answer; none is dressed up as another. ----
  if (state === 'loading') {
    return (
      <div className="page kp-page" data-testid="kp-circuit-detail">
        {back}
        <p className="kp-muted" data-testid="kp-circuit-loading">
          {t('knowledgeProduction.loading')}
        </p>
      </div>
    )
  }
  if (state === 'error') {
    return (
      <div className="page kp-page" data-testid="kp-circuit-detail">
        {back}
        <div className="state-box state-err" data-testid="kp-circuit-error">
          <p>{error}</p>
        </div>
      </div>
    )
  }
  if (state === 'notFound') {
    return (
      <div className="page kp-page" data-testid="kp-circuit-detail">
        {back}
        <div className="state-box" data-testid="kp-circuit-not-found">
          <p>{t('knowledgeProduction.candidateKnowledge.notFound')}</p>
          <p className="kp-muted">{candidateId}</p>
        </div>
      </div>
    )
  }
  if (state === 'wrongType') {
    // NOT dressed up as a circuit page: the page states what it supports and
    // what the candidate actually is.
    return (
      <div className="page kp-page" data-testid="kp-circuit-detail">
        {back}
        <div className="state-box" data-testid="kp-circuit-wrong-type">
          <p>{t('knowledgeProduction.candidateKnowledge.circuitOnly')}</p>
          <p className="kp-muted">
            {candidateId} · {candidate?.candidate_type}
          </p>
        </div>
      </div>
    )
  }

  // ---- structure: the page is the ONLY caller of the declared-ref resolver. ----
  const payload = readCircuitPayload(candidate!.payload)
  const byLocalId = new Map(runCandidates.map(c => [c.local_id, c]))
  const regions = resolveRefs(payload.regionRefs, runCandidates)
  const connections = resolveRefs(payload.connectionRefs, runCandidates)
  const functions = resolveRefs(payload.functionRefs, runCandidates)

  /** A ref rendered for a human: the seed's name, or the candidate's name. */
  const refName = (ref: string | null): string => {
    if (ref === null) return '—'
    if (ref === SEED_REF) return seedName ?? SEED_REF
    return byLocalId.get(ref)?.name ?? ref
  }

  // Edges ONLY from declared source/target refs. A connection missing either
  // endpoint contributes no edge — nothing is guessed to complete it.
  const edges: Edge[] = connections.resolved
    .map(({ candidate: c }) => readConnectionPayload(c.payload))
    .filter((p): p is typeof p & { sourceRef: string; targetRef: string } =>
      Boolean(p.sourceRef && p.targetRef))
    .map(p => ({ from: p.sourceRef, to: p.targetRef }))

  return (
    <div className="page kp-page" data-testid="kp-circuit-detail">
      {back}

      <header className="kp-ws-header">
        <h1 className="kp-ws-name" data-testid="kp-circuit-name">
          {payload.name ?? candidate!.name}
        </h1>
        <p className="kp-ws-id" data-testid="kp-circuit-ids">
          {candidate!.candidate_id} · {candidate!.local_id}
        </p>
        <div className="kp-badge-row" data-testid="kp-circuit-badges">
          <span className="badge badge-blue">
            {t('knowledgeProduction.llmCandidates.type.circuit')}
          </span>
          <span className={`badge ${CANDIDATE_STATUS_TONES[candidate!.status]}`}>
            {t(CANDIDATE_STATUS_LABEL_KEYS[candidate!.status])}
          </span>
          {payload.confidence !== null && (
            <span className="badge badge-gray" data-testid="kp-circuit-confidence">
              confidence {payload.confidence}
            </span>
          )}
          <span className="kp-chip kp-chip--accent" data-testid="kp-circuit-workspace">
            {seedName ?? entityId}
          </span>
        </div>
      </header>

      <div className="kp-detail-grid">
        <div className="kp-detail-main">
          <CircuitOverviewSection payload={payload} candidate={candidate!} />
          <CircuitRegionsSection
            regions={regions}
            seedName={seedName}
            seedEntityId={seedDetail?.entity_id ?? null}
          />
          <CircuitConnectionsSection
            connections={connections}
            chain={linearChain(edges)}
            edgeCount={edges.length}
            refName={refName}
          />
          <CircuitFunctionsSection functions={functions} />
        </div>

        <aside className="kp-detail-side">
          <CircuitStructureSection
            counts={{
              regions: (regions.seed ? 1 : 0) + regions.resolved.length,
              connections: connections.resolved.length,
              functions: functions.resolved.length,
              unresolved:
                regions.unresolved.length +
                connections.unresolved.length +
                functions.unresolved.length,
            }}
          />
          <CircuitProvenanceSection candidate={candidate!} run={run} />
        </aside>
      </div>

      <CircuitRawSection payload={candidate!.payload} />
    </div>
  )
}

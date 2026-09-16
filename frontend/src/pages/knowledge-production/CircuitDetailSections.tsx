/**
 * Phase P0-4C closeout — the Circuit detail page's PRESENTATIONAL sections.
 *
 * Split out of `CircuitCandidateDetailPage` so that module holds the page's job
 * (fetch, state, ref resolution, composition) and each surface below holds one
 * rendering job. Nothing here decides what a circuit CONTAINS:
 *
 *   * every section receives an already-resolved `RefResolution`, so `resolveRefs`
 *     still has exactly ONE caller — the page — and there is no second resolver;
 *   * every payload field is read through `circuitPayload.ts`, the single
 *     structural authority, and an absent field renders `—` rather than a
 *     substitute;
 *   * `data-testid`s and wording are unchanged from the pre-split page, so the
 *     scientific assertions still point at the same facts.
 */
import { useI18n } from '../../i18n-context'
import {
  CANDIDATE_STATUS_LABEL_KEYS,
  CANDIDATE_STATUS_TONES,
  type LlmDiscoveryCandidate,
} from './candidateTypes'
import {
  SEED_REF,
  readConnectionPayload,
  readFunctionPayload,
  type CircuitPayload,
  type RefResolution,
} from './circuitPayload'
import { formatTimestamp, orDash } from './kpFormat'
import type { DiscoveryRun } from './types'

/** One labelled read-only value. `testId` is only for values a test asserts. */
function Field({
  label,
  value,
  testId,
}: {
  label: string
  value: string | number | null
  testId?: string
}) {
  return (
    <div className="kp-field">
      <span className="kp-field-label">{label}</span>
      <span className="kp-field-value" data-testid={testId}>
        {orDash(value)}
      </span>
    </div>
  )
}

/**
 * A resolved-ref table, or the explicit statement that nothing was declared.
 *
 * The caller builds the cells, so this component never looks a ref up and cannot
 * quietly substitute a value. An empty ref list is NOT an empty table: it renders
 * the caller's sentence instead, because "declared nothing" and "declared
 * something that renders blank" are different facts.
 */
function RefTable({
  rows,
  columns,
  noneText,
  testId,
}: {
  rows: string[][]
  columns: string[]
  noneText: string
  testId: string
}) {
  if (rows.length === 0) {
    return (
      <p className="kp-muted" data-testid={`${testId}-none`}>
        {noneText}
      </p>
    )
  }
  return (
    <div className="table-wrap" data-testid={testId}>
      <table>
        <thead>
          <tr>
            {columns.map(c => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row[0] + row[1]}>
              {row.map((cell, i) => (
                <td key={i}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** The refs a section declared but could not resolve. Listed, never hidden. */
function UnresolvedRefs({ refs, testId }: { refs: string[]; testId: string }) {
  const { t } = useI18n()
  if (refs.length === 0) return null
  return (
    <ul className="kp-unresolved" data-testid={testId}>
      {refs.map(ref => (
        <li key={ref}>{t('knowledgeProduction.circuitDetail.unresolvedRef', { ref })}</li>
      ))}
    </ul>
  )
}

function SectionTitle({ keyName }: { keyName: string }) {
  const { t } = useI18n()
  return <h3 className="kp-section-title">{t(keyName)}</h3>
}

// ===========================================================================
// A — OVERVIEW
// ===========================================================================
export function CircuitOverviewSection({
  payload,
  candidate,
}: {
  payload: CircuitPayload
  candidate: LlmDiscoveryCandidate
}) {
  const { t } = useI18n()
  const f = (name: string) => t(`knowledgeProduction.circuitDetail.field.${name}`)
  return (
    <section className="kp-section" data-testid="kp-circuit-overview">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.overview" />
      <div className="kp-field-grid">
        <Field label={f('name')} value={payload.name} testId="kp-circuit-field-name" />
        <Field label="candidate_id" value={candidate.candidate_id} />
        <Field label="local_id" value={candidate.local_id} />
        <Field label={f('description')} value={payload.description} testId="kp-circuit-description" />
        <Field
          label={f('topologyHint')}
          value={payload.topologyHint}
          testId="kp-circuit-topology-hint"
        />
        <Field label={t('knowledgeProduction.llmCandidates.field.status')} value={candidate.status} />
        <Field
          label={t('knowledgeProduction.llmCandidates.col.confidence')}
          value={payload.confidence}
        />
        <Field
          label={f('speciesScope')}
          value={payload.speciesContext?.scope ?? null}
          testId="kp-circuit-species-scope"
        />
        <Field
          label={f('taxonIds')}
          value={payload.speciesContext?.taxonIds.join(', ') || null}
          testId="kp-circuit-species-taxa"
        />
        <Field label={f('rationale')} value={payload.rationale} />
      </div>
    </section>
  )
}

// ===========================================================================
// B — INVOLVED REGIONS (declared region_refs only)
// ===========================================================================
export function CircuitRegionsSection({
  regions,
  seedName,
  seedEntityId,
}: {
  regions: RefResolution
  seedName: string | null
  seedEntityId: string | null
}) {
  const { t } = useI18n()
  // The SEED row names the region and shows its identifier where a candidate row
  // shows its candidate_id — the seed is not a candidate, so it has neither.
  const seedRow: string[] = [SEED_REF, '—', seedName ?? seedEntityId ?? '—', '—', '—']
  const rows: string[][] = [
    ...(regions.seed ? [seedRow] : []),
    ...regions.resolved.map(({ ref, candidate: c }) => [
      ref,
      c.candidate_id,
      c.name,
      orDash(c.confidence),
      c.status,
    ]),
  ]
  return (
    <section className="kp-section">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.regions" />
      <RefTable
        rows={rows}
        testId="kp-circuit-regions"
        noneText={t('knowledgeProduction.circuitDetail.noRegionRefs')}
        columns={[
          t('knowledgeProduction.circuitDetail.col.ref'),
          t('knowledgeProduction.circuitDetail.col.candidateId'),
          t('knowledgeProduction.llmCandidates.col.name'),
          t('knowledgeProduction.llmCandidates.col.confidence'),
          t('knowledgeProduction.llmCandidates.col.status'),
        ]}
      />
      <UnresolvedRefs refs={regions.unresolved} testId="kp-circuit-regions-unresolved" />
    </section>
  )
}

// ===========================================================================
// C — CONNECTION COMPOSITION (declared connection_refs only)
// ===========================================================================
export function CircuitConnectionsSection({
  connections,
  chain,
  edgeCount,
  refName,
}: {
  connections: RefResolution
  /** The chain, when the declared edges form one path. `null` = not drawable. */
  chain: string[] | null
  /**
   * How many DECLARED EDGES exist — connections carrying both endpoints. The
   * no-chain note is gated on THIS, not on the row count: a connection without
   * endpoints contributes no edge, so claiming "there is a branch or a loop"
   * when there is simply nothing to order would be a false statement.
   */
  edgeCount: number
  refName: (ref: string | null) => string
}) {
  const { t } = useI18n()
  const rows: string[][] = connections.resolved.map(({ ref, candidate: c }) => {
    const p = readConnectionPayload(c.payload)
    return [
      ref,
      c.candidate_id,
      refName(p.sourceRef),
      refName(p.targetRef),
      orDash(p.directionality),
      orDash(p.connectionType),
      orDash(c.confidence),
    ]
  })
  return (
    <section className="kp-section">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.connections" />
      <RefTable
        rows={rows}
        testId="kp-circuit-connections"
        noneText={t('knowledgeProduction.circuitDetail.noConnectionRefs')}
        columns={[
          t('knowledgeProduction.circuitDetail.col.ref'),
          t('knowledgeProduction.circuitDetail.col.candidateId'),
          t('knowledgeProduction.circuitDetail.col.source'),
          t('knowledgeProduction.circuitDetail.col.target'),
          t('knowledgeProduction.circuitDetail.col.directionality'),
          t('knowledgeProduction.circuitDetail.col.connectionType'),
          t('knowledgeProduction.llmCandidates.col.confidence'),
        ]}
      />
      <UnresolvedRefs refs={connections.unresolved} testId="kp-circuit-connections-unresolved" />

      {/* A chain is drawn ONLY when the declared edges form one unambiguous path.
          A branch, a convergence or a loop gets the table above and this note —
          no ordering is invented to make a prettier picture. */}
      {chain ? (
        <div data-testid="kp-circuit-chain">
          <h4 className="kp-section-title">{t('knowledgeProduction.circuitDetail.chainTitle')}</h4>
          <pre className="kp-chain">{chain.map(refName).join('\n   ↓\n')}</pre>
          <p className="kp-muted">{t('knowledgeProduction.circuitDetail.chainNote')}</p>
        </div>
      ) : (
        edgeCount > 0 && (
          <p className="kp-muted" data-testid="kp-circuit-no-chain">
            {t('knowledgeProduction.circuitDetail.noLinearChain')}
          </p>
        )
      )}
    </section>
  )
}

// ===========================================================================
// D — EXPLICIT FUNCTIONS (declared function_refs only)
// ===========================================================================
export function CircuitFunctionsSection({ functions }: { functions: RefResolution }) {
  const { t } = useI18n()
  const rows: string[][] = functions.resolved.map(({ ref, candidate: c }) => {
    const p = readFunctionPayload(c.payload)
    return [ref, c.candidate_id, p.label ?? c.name, orDash(p.description), orDash(c.confidence)]
  })
  return (
    <section className="kp-section">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.functions" />
      <RefTable
        rows={rows}
        testId="kp-circuit-functions"
        noneText={t('knowledgeProduction.circuitDetail.noFunctionRefs')}
        columns={[
          t('knowledgeProduction.circuitDetail.col.ref'),
          t('knowledgeProduction.circuitDetail.col.candidateId'),
          t('knowledgeProduction.circuitDetail.col.functionLabel'),
          t('knowledgeProduction.circuitDetail.field.description'),
          t('knowledgeProduction.llmCandidates.col.confidence'),
        ]}
      />
      {/* The small print explains WHY the list is empty, so it is not read as
          "this circuit has no function". */}
      {rows.length === 0 && functions.unresolved.length === 0 && (
        <p className="kp-muted" data-testid="kp-circuit-functions-note">
          {t('knowledgeProduction.circuitDetail.noFunctionRefsNote')}
        </p>
      )}
      <UnresolvedRefs refs={functions.unresolved} testId="kp-circuit-functions-unresolved" />
    </section>
  )
}

// ===========================================================================
// E — STRUCTURE SUMMARY (every number from explicit ref resolution)
// ===========================================================================
export function CircuitStructureSection({
  counts,
}: {
  counts: { regions: number; connections: number; functions: number; unresolved: number }
}) {
  const { t } = useI18n()
  const c = (name: string) => t(`knowledgeProduction.circuitDetail.count.${name}`)
  return (
    <section className="kp-section" data-testid="kp-circuit-structure">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.structure" />
      <div className="kp-field-grid">
        <Field label={c('regions')} value={counts.regions} testId="kp-circuit-count-regions" />
        <Field
          label={c('connections')}
          value={counts.connections}
          testId="kp-circuit-count-connections"
        />
        <Field label={c('functions')} value={counts.functions} testId="kp-circuit-count-functions" />
        <Field label={c('unresolved')} value={counts.unresolved} testId="kp-circuit-count-unresolved" />
      </div>
    </section>
  )
}

// ===========================================================================
// F — DISCOVERY PROVENANCE (from the run history; no second source)
// ===========================================================================
export function CircuitProvenanceSection({
  candidate,
  run,
}: {
  candidate: LlmDiscoveryCandidate
  run: DiscoveryRun | null
}) {
  const { t } = useI18n()
  const f = (name: string) => t(`knowledgeProduction.circuitDetail.field.${name}`)
  return (
    <section className="kp-section" data-testid="kp-circuit-provenance">
      <SectionTitle keyName="knowledgeProduction.circuitDetail.section.provenance" />
      <div className="kp-field-grid">
        <Field label="run_id" value={candidate.run_id} testId="kp-circuit-run-id" />
        <Field label="seed_entity_id" value={candidate.seed_entity_id} />
        {/* A dedicated label: the literature key reads "retrieval source", which
            is the wrong word for the model provider of an LLM run. */}
        <Field label={f('provider')} value={run?.provider ?? null} />
        <Field label={f('model')} value={run?.model_name ?? null} testId="kp-circuit-model" />
        <Field label={f('promptKey')} value={run?.prompt_key ?? null} />
        <Field label={f('promptVersion')} value={run?.prompt_version ?? null} />
        {/* The run read API does not carry schema_version (it lives in the
            execution response's metrics, which are not persisted), so this is
            stated as absent rather than borrowed from somewhere else. */}
        <Field label={f('schemaVersion')} value={null} testId="kp-circuit-schema-version" />
        <Field
          label={t('knowledgeProduction.llmCandidates.field.createdAt')}
          value={formatTimestamp(candidate.created_at)}
        />
      </div>
    </section>
  )
}

// ===========================================================================
// G — RAW PAYLOAD (collapsed; the scientific audit fallback)
// ===========================================================================
export function CircuitRawSection({ payload }: { payload: Record<string, unknown> }) {
  const { t } = useI18n()
  return (
    <section className="kp-section">
      <details data-testid="kp-circuit-raw">
        <summary className="kp-section-title">
          {t('knowledgeProduction.circuitDetail.section.raw')}
        </summary>
        <pre className="kp-json" data-testid="kp-circuit-raw-json">
          {JSON.stringify(payload, null, 2)}
        </pre>
      </details>
    </section>
  )
}

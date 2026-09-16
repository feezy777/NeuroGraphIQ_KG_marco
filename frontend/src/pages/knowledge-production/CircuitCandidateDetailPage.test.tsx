/**
 * Phase P0-4C — Circuit Candidate detail page.
 *
 * The payloads below are shaped exactly like the real E2E run
 * (673a88f4-fe84-4233-85a3-abf1719cac0a): `region_refs` / `connection_refs` /
 * `function_refs`, the reserved `SEED` token, `source_ref` / `target_ref` /
 * `directionality` / `connection_type`, and a function's `label`.
 *
 * The scientific block is the important one: relations come ONLY from declared
 * refs, so a circuit that declares no functions shows none even when the run is
 * full of them, and a set of connections that is not a single linear path gets no
 * invented order.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { CircuitCandidateDetailPage } from './CircuitCandidateDetailPage'
import type { LlmDiscoveryCandidate } from './candidateTypes'
import type { DiscoveryRun } from './types'

const getCandidatePool = vi.fn()
const getRunCandidates = vi.fn()
const getRuns = vi.fn()
const getSeed = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionLlmCandidates: (...a: unknown[]) => getCandidatePool(...a),
  fetchRunLlmCandidates: (...a: unknown[]) => getRunCandidates(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
  fetchLiteratureRuns: vi.fn(),
  fetchRunPublications: vi.fn(),
  executeLlmDiscovery: vi.fn(),
}))

const SEED_ID = 'NGIQ-BR-00001169'
const RUN_ID = '673a88f4-fe84-4233-85a3-abf1719cac0a'

function cand(
  localId: string,
  type: LlmDiscoveryCandidate['candidate_type'],
  name: string,
  payload: Record<string, unknown>,
  over: Partial<LlmDiscoveryCandidate> = {},
): LlmDiscoveryCandidate {
  return {
    candidate_id: `NGIQ-DC-${localId}`,
    run_id: RUN_ID,
    seed_entity_id: SEED_ID,
    candidate_type: type,
    local_id: localId,
    name,
    payload,
    confidence: 0.9,
    status: 'proposed',
    created_at: '2026-09-16T12:08:00Z',
    updated_at: '2026-09-16T12:08:00Z',
    ...over,
  }
}

/** The declared shapes of circuit_2 of the real run (a clean linear chain). */
const CIRCUIT_2 = cand('circuit_2', 'circuit', 'Papez circuit', {
  local_id: 'circuit_2',
  name: 'Papez circuit',
  description: 'Extended hippocampal-diencephalic-cortical memory loop.',
  rationale: 'Classic anatomical circuit.',
  confidence: 0.8,
  topology_hint: 'LOOP',
  region_refs: ['SEED', 'region_6', 'region_7', 'region_8'],
  connection_refs: ['connection_8', 'connection_9', 'connection_10'],
  function_refs: ['function_4'],
  species_context: { scope: 'MIXED', taxon_ids: [9606, 10090, 10116] },
})

const RUN_CANDIDATES: LlmDiscoveryCandidate[] = [
  CIRCUIT_2,
  cand('region_6', 'region', 'Mammillary bodies', { local_id: 'region_6' }),
  cand('region_7', 'region', 'Anterior thalamic nuclei', { local_id: 'region_7' }),
  cand('region_8', 'region', 'Cingulate cortex', { local_id: 'region_8' }),
  // Ten more regions exist in the run — none of them is referenced, so none may
  // appear on circuit_2's page (§19.B).
  ...Array.from({ length: 10 }, (_, i) =>
    cand(`region_9${i}`, 'region', `Unreferenced region ${i}`, { local_id: `region_9${i}` }),
  ),
  cand('connection_8', 'connection', 'SEED -> Mammillary bodies [PROJECTION]', {
    local_id: 'connection_8', source_ref: 'SEED', target_ref: 'region_6',
    directionality: 'DIRECTED', connection_type: 'PROJECTION', confidence: 0.85,
  }),
  cand('connection_9', 'connection', 'Mammillary bodies -> Anterior thalamic nuclei [PROJECTION]', {
    local_id: 'connection_9', source_ref: 'region_6', target_ref: 'region_7',
    directionality: 'DIRECTED', connection_type: 'PROJECTION', confidence: 0.8,
  }),
  cand('connection_10', 'connection', 'Anterior thalamic nuclei -> Cingulate cortex [PROJECTION]', {
    local_id: 'connection_10', source_ref: 'region_7', target_ref: 'region_8',
    directionality: 'DIRECTED', connection_type: 'PROJECTION', confidence: 0.75,
  }),
  cand('function_4', 'function', 'Declarative memory consolidation', {
    local_id: 'function_4', label: 'Declarative memory consolidation',
    description: 'Stabilization of declarative memories over time.',
    related_circuit_refs: ['circuit_2'],
  }),
  // Twenty functions exist and only ONE is referenced (§19.A).
  ...Array.from({ length: 20 }, (_, i) =>
    cand(`function_9${i}`, 'function', `Unreferenced function ${i}`, {
      local_id: `function_9${i}`, label: `Unreferenced function ${i}`,
    }),
  ),
]

/** The seed BrainRegion's own record — the source of `SEED`'s display name. */
const SEED_DETAIL = {
  entity_pk: 2989,
  entity_id: SEED_ID,
  name_en: 'Left Hippocampus',
  name_zh: '左侧海马',
  abbreviation: null,
  granularity_level: 'G1_MACRO',
  region_category: null,
  hemisphere: 'left',
  species_taxon_id: '9606',
  record_status: 'active',
  review_status: 'approved',
  atlas_names: [],
  definition_en: null,
  parent_region_pk: null,
  hierarchy_depth: null,
  external_region_ids: [],
  mapping_types: [],
  mapping_review_statuses: [],
}

const HISTORY_RUN: DiscoveryRun = {
  run_id: RUN_ID,
  seed_entity_id: SEED_ID,
  discovery_type: 'LLM_DISCOVERY',
  status: 'COMPLETED',
  outcome: 'CANDIDATES_FOUND',
  provider: 'deepseek',
  model_name: 'deepseek-flash',
  prompt_key: 'knowledge_production.llm_discovery',
  prompt_version: '1.2.0',
  query_strategy_version: null,
  created_by: null,
  created_at: '2026-09-16T12:07:43Z',
  started_at: '2026-09-16T12:07:43Z',
  finished_at: '2026-09-16T12:08:53Z',
  error_code: null,
  error_message: null,
}

function renderDetail(candidateId = 'NGIQ-DC-circuit_2', entityId = SEED_ID) {
  const onBack = vi.fn()
  render(
    <I18nProvider>
      <CircuitCandidateDetailPage
        entityId={entityId}
        candidateId={candidateId}
        onBack={onBack}
      />
    </I18nProvider>,
  )
  return { onBack }
}

const detailRows = (testId: string) =>
  within(screen.getByTestId(testId)).getAllByRole('row')

beforeEach(() => {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en-US')
  getCandidatePool.mockReset()
  getCandidatePool.mockResolvedValue({ items: RUN_CANDIDATES, total: RUN_CANDIDATES.length })
  getRunCandidates.mockReset()
  getRunCandidates.mockResolvedValue({ items: RUN_CANDIDATES, total: RUN_CANDIDATES.length })
  getRuns.mockReset()
  getRuns.mockResolvedValue({ items: [HISTORY_RUN], total: 1 })
  getSeed.mockReset()
  getSeed.mockResolvedValue(SEED_DETAIL)
})

// ===========================================================================
// §23.8-11, §23.18 — the page loads, renders, and can be linked to
// ===========================================================================
describe('circuit detail', () => {
  it('11. renders the header, the overview and the workspace context', async () => {
    renderDetail()
    expect(await screen.findByTestId('kp-circuit-name')).toHaveProperty(
      'textContent',
      'Papez circuit',
    )
    expect(screen.getByTestId('kp-circuit-ids').textContent).toContain('NGIQ-DC-circuit_2')
    expect(screen.getByTestId('kp-circuit-ids').textContent).toContain('circuit_2')
    const badges = within(screen.getByTestId('kp-circuit-badges'))
    expect(badges.getByText('Circuit')).toBeTruthy()
    expect(badges.getByText('Pending review')).toBeTruthy()
    expect(badges.getByText('confidence 0.8')).toBeTruthy()
    // Workspace context: the seed BrainRegion, by its canonical NAME.
    expect(badges.getByTestId('kp-circuit-workspace').textContent).toBe('Left Hippocampus')

    const overview = within(screen.getByTestId('kp-circuit-overview'))
    expect(overview.getByTestId('kp-circuit-description').textContent).toContain(
      'diencephalic-cortical',
    )
    expect(overview.getByTestId('kp-circuit-topology-hint').textContent).toBe('LOOP')
    expect(overview.getByTestId('kp-circuit-species-scope').textContent).toBe('MIXED')
    expect(overview.getByTestId('kp-circuit-species-taxa').textContent).toBe(
      '9606, 10090, 10116',
    )
  })

  it('9 + 10. the page fetches by URL: pool first, then the SAME run + provenance', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-name')

    // 1. the region pool — the only entry point, so no page state is needed
    expect(getCandidatePool).toHaveBeenCalledWith(SEED_ID)
    // 2. refs resolve against the candidate's OWN run, never the region pool
    expect(getRunCandidates).toHaveBeenCalledWith(RUN_ID)
    // 3. provenance comes from the existing run-history API
    expect(getRuns).toHaveBeenCalledWith(SEED_ID)
  })

  it('10b. a refresh with no prior navigation still recovers the page', async () => {
    // A cold render IS the refresh case: the component receives only the two ids.
    renderDetail()
    expect(await screen.findByTestId('kp-circuit-regions')).toBeTruthy()
    expect(screen.getByTestId('kp-circuit-connections')).toBeTruthy()
  })

  it('back navigation calls the caller’s handler', async () => {
    const { onBack } = renderDetail()
    fireEvent.click(await screen.findByTestId('kp-circuit-back'))
    expect(onBack).toHaveBeenCalledTimes(1)
  })

  it('18. renders discovery provenance from the run history', async () => {
    renderDetail()
    const prov = within(await screen.findByTestId('kp-circuit-provenance'))
    expect(prov.getByTestId('kp-circuit-run-id').textContent).toBe(RUN_ID)
    expect(prov.getByText(SEED_ID)).toBeTruthy()
    expect(prov.getByText('deepseek')).toBeTruthy()
    // A dedicated label: the literature key says "retrieval source", which is the
    // wrong word for the model provider of an LLM run.
    expect(prov.getByText('Provider')).toBeTruthy()
    expect(prov.queryByText('retrieval source')).toBeNull()
    expect(prov.getByTestId('kp-circuit-model').textContent).toBe('deepseek-flash')
    expect(prov.getByText('knowledge_production.llm_discovery')).toBeTruthy()
    expect(prov.getByText('1.2.0')).toBeTruthy()
    // The run read API does not carry schema_version: it is shown as absent
    // rather than borrowed from a different response.
    expect(prov.getByTestId('kp-circuit-schema-version').textContent).toBe('—')
  })
})

// ===========================================================================
// §23.12-14, §19.B/C — declared refs resolve, and ONLY those
// ===========================================================================
describe('explicit ref resolution', () => {
  it('12. resolves the declared region_refs, with SEED named as the seed', async () => {
    renderDetail()
    // The page loads in stages (pool, then run + history), so wait for the
    // section before reading its rows.
    await screen.findByTestId('kp-circuit-regions')
    const rows = detailRows('kp-circuit-regions')
    // 1 header + SEED + 3 declared regions
    expect(rows).toHaveLength(5)
    const text = screen.getByTestId('kp-circuit-regions').textContent ?? ''
    expect(text).toContain('SEED')
    // The seed row names the region; its identifier stays in provenance.
    expect(text).toContain('Left Hippocampus')
    expect(text).toContain('Mammillary bodies')
    expect(text).toContain('Anterior thalamic nuclei')
    expect(text).toContain('Cingulate cortex')
  })

  it('19.B. shows ONLY the declared regions, never the run’s other regions', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-regions')
    const text = screen.getByTestId('kp-circuit-regions').textContent ?? ''
    // Ten unreferenced regions exist in the same run.
    for (let i = 0; i < 10; i++) {
      expect(text).not.toContain(`Unreferenced region ${i}`)
    }
    expect(
      (await screen.findByTestId('kp-circuit-count-regions')).textContent,
    ).toContain('4')
  })

  it('13. resolves the declared connection_refs with real payload fields', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-connections')
    const rows = detailRows('kp-circuit-connections')
    expect(rows).toHaveLength(4) // header + 3
    const text = screen.getByTestId('kp-circuit-connections').textContent ?? ''
    // source / target resolved to NAMES, plus the real directionality & type
    expect(text).toContain('Mammillary bodies')
    expect(text).toContain('DIRECTED')
    expect(text).toContain('PROJECTION')
    expect((await screen.findByTestId('kp-circuit-count-connections')).textContent).toContain('3')
  })

  it('19.C. shows ONLY the declared connections', async () => {
    getRunCandidates.mockResolvedValue({
      items: [
        ...RUN_CANDIDATES,
        cand('connection_99', 'connection', 'Unreferenced connection', {
          local_id: 'connection_99', source_ref: 'region_6', target_ref: 'region_7',
          directionality: 'DIRECTED', connection_type: 'PROJECTION',
        }),
      ],
      total: RUN_CANDIDATES.length + 1,
    })
    renderDetail()
    await screen.findByTestId('kp-circuit-connections')
    expect(screen.getByTestId('kp-circuit-connections').textContent).not.toContain(
      'Unreferenced connection',
    )
  })

  it('14. resolves the declared function_refs', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-functions')
    const rows = detailRows('kp-circuit-functions')
    expect(rows).toHaveLength(2) // header + 1
    const text = screen.getByTestId('kp-circuit-functions').textContent ?? ''
    expect(text).toContain('Declarative memory consolidation')
    expect((await screen.findByTestId('kp-circuit-count-functions')).textContent).toContain('1')
  })
})

// ===========================================================================
// §23.15-16, §19.A/D/E — the non-inference proofs
// ===========================================================================
describe('scientific non-inference', () => {
  it('19.A. a circuit that declares NO functions shows none, though 20 exist', async () => {
    getCandidatePool.mockResolvedValue({
      items: [cand('circuit_5', 'circuit', 'Hippocampal-accumbal-VTA reward circuit', {
        local_id: 'circuit_5', name: 'Hippocampal-accumbal-VTA reward circuit',
        region_refs: ['SEED', 'region_11'], connection_refs: [], function_refs: [],
      })],
      total: 1,
    })
    renderDetail('NGIQ-DC-circuit_5')

    const section = within(await screen.findByTestId('kp-circuit-functions-none'))
    expect(section.getByText('No explicit associated functions')).toBeTruthy()
    // The small print says WHY, so an empty list is not read as "no functions".
    expect(
      screen.getByTestId('kp-circuit-functions-note').textContent,
    ).toContain('does not explicitly declare')
    // Not one of the twenty unreferenced functions may appear.
    expect(screen.queryByTestId('kp-circuit-functions')).toBeNull()
    const body = document.body.textContent ?? ''
    expect(body).not.toContain('Unreferenced function 0')
    expect((await screen.findByTestId('kp-circuit-count-functions')).textContent).toContain('0')
  })

  it('16. an unresolved ref is REPORTED, never silently dropped', async () => {
    getCandidatePool.mockResolvedValue({
      items: [cand('circuit_x', 'circuit', 'Circuit with a dangling ref', {
        local_id: 'circuit_x', name: 'Circuit with a dangling ref',
        region_refs: ['SEED', 'region_404'],
        connection_refs: ['connection_404'],
        function_refs: [],
      })],
      total: 1,
    })
    renderDetail('NGIQ-DC-circuit_x')

    const unresolvedRegions = within(await screen.findByTestId('kp-circuit-regions-unresolved'))
    expect(unresolvedRegions.getByText('unresolved ref: region_404')).toBeTruthy()
    const unresolvedConn = within(screen.getByTestId('kp-circuit-connections-unresolved'))
    expect(unresolvedConn.getByText('unresolved ref: connection_404')).toBeTruthy()
    // Counted, and the count comes from the resolution — not from a guess.
    expect((await screen.findByTestId('kp-circuit-count-unresolved')).textContent).toContain('2')
  })

  it('19.E. a branch or a loop draws NO chain, only the connection table', async () => {
    // circuit_1 of the real run: Entorhinal -> SEED branch plus a five-edge cycle,
    // so no single linear order exists.
    const trisynaptic = cand('circuit_1', 'circuit', 'Hippocampal trisynaptic circuit', {
      local_id: 'circuit_1',
      name: 'Hippocampal trisynaptic circuit',
      region_refs: ['SEED', 'region_1', 'region_2', 'region_3', 'region_4', 'region_5'],
      connection_refs: ['connection_1', 'connection_3', 'connection_4', 'connection_5', 'connection_6', 'connection_7'],
      function_refs: [],
    })
    const regions = ['region_1', 'region_2', 'region_3', 'region_4', 'region_5'].map((r, i) =>
      cand(r, 'region', `R${i}`, { local_id: r }),
    )
    const edges: [string, string, string][] = [
      ['connection_1', 'region_1', 'SEED'],
      ['connection_3', 'region_1', 'region_2'],
      ['connection_4', 'region_2', 'region_3'],
      ['connection_5', 'region_3', 'region_4'],
      ['connection_6', 'region_4', 'region_5'],
      ['connection_7', 'region_5', 'region_1'],
    ]
    getCandidatePool.mockResolvedValue({ items: [trisynaptic], total: 1 })
    getRunCandidates.mockResolvedValue({
      items: [
        trisynaptic,
        ...regions,
        ...edges.map(([id, from, to]) =>
          cand(id, 'connection', `${from} -> ${to}`, {
            local_id: id, source_ref: from, target_ref: to,
            directionality: 'DIRECTED', connection_type: 'PROJECTION',
          }),
        ),
      ],
      total: 12,
    })
    renderDetail('NGIQ-DC-circuit_1')

    // The table is the whole statement.
    await screen.findByTestId('kp-circuit-connections')
    expect(detailRows('kp-circuit-connections')).toHaveLength(7)
    // …and no order is invented from it.
    expect(screen.queryByTestId('kp-circuit-chain')).toBeNull()
    expect((await screen.findByTestId('kp-circuit-no-chain')).textContent).toContain(
      'do not form a single linear path',
    )
  })

  it('19.E (positive). a unique declared path IS shown, labelled as declared', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-chain')
    const chain = within(screen.getByTestId('kp-circuit-chain'))
    // The chain is ONE <pre>, so it is read as text rather than matched node by
    // node. Every name in it comes from a declared source/target ref.
    const text = screen.getByTestId('kp-circuit-chain').textContent ?? ''
    // `SEED` is labelled with the seed BrainRegion's own name, not its id.
    expect(text).toContain('Left Hippocampus')
    for (const node of ['Mammillary bodies', 'Anterior thalamic nuclei', 'Cingulate cortex']) {
      expect(text).toContain(node)
    }
    expect(chain.getByText(/Chained only from source/)).toBeTruthy()
    expect(screen.queryByTestId('kp-circuit-no-chain')).toBeNull()
  })

  it('does not invent a `summary` field the payload never carries', async () => {
    renderDetail()
    const overview = within(await screen.findByTestId('kp-circuit-overview'))
    // Absent means absent: no fallback to the description, no synthesized text.
    expect(overview.queryByText(/^summary$/i)).toBeNull()
  })
})

// ===========================================================================
// §23.17, §23.20 — raw payload, and the states that must not pretend
// ===========================================================================
describe('raw payload and failure states', () => {
  it('17. exposes the raw payload, collapsed by default', async () => {
    renderDetail()
    const raw = await screen.findByTestId('kp-circuit-raw')
    expect(raw).toHaveProperty('open', false)
    const json = screen.getByTestId('kp-circuit-raw-json').textContent ?? ''
    // Verbatim: every declared ref is in the JSON, unedited.
    expect(json).toContain('"topology_hint": "LOOP"')
    expect(json).toContain('"connection_10"')

    fireEvent.click(within(raw).getByText('Raw discovery data'))
    await waitFor(() => expect(screen.getByTestId('kp-circuit-raw')).toHaveProperty('open', true))
  })

  it('20. an unknown candidate_id says the candidate does not exist', async () => {
    renderDetail('NGIQ-DC-99999999')
    const box = await screen.findByTestId('kp-circuit-not-found')
    expect(box.textContent).toContain('Candidate not found')
    expect(screen.queryByTestId('kp-circuit-overview')).toBeNull()
  })

  it('20b. a non-circuit candidate is not dressed up as a circuit page', async () => {
    getCandidatePool.mockResolvedValue({
      items: [cand('region_1', 'region', 'Entorhinal cortex', { local_id: 'region_1' })],
      total: 1,
    })
    renderDetail('NGIQ-DC-region_1')
    const box = await screen.findByTestId('kp-circuit-wrong-type')
    expect(box.textContent).toContain('supports circuit candidates only')
    // It also names what the candidate actually is.
    expect(box.textContent).toContain('region')
    expect(screen.queryByTestId('kp-circuit-overview')).toBeNull()
    expect(screen.queryByTestId('kp-circuit-functions-none')).toBeNull()
  })

  it('an API failure is an ERROR, never a not-found and never empty sections', async () => {
    getCandidatePool.mockRejectedValue(new Error('HTTP 500: boom'))
    renderDetail()
    const err = await screen.findByTestId('kp-circuit-error')
    expect(err.textContent).toContain('HTTP 500: boom')
    expect(screen.queryByTestId('kp-circuit-not-found')).toBeNull()
    expect(screen.queryByTestId('kp-circuit-overview')).toBeNull()
  })

  it('21. offers no review control anywhere on the page', async () => {
    renderDetail()
    await screen.findByTestId('kp-circuit-overview')
    const labels = screen
      .getAllByRole('button')
      .map(b => (b.textContent ?? '').toLowerCase())
    // Only the back control exists.
    expect(labels).toHaveLength(1)
    expect(labels[0]).toContain('back to candidate knowledge')
    for (const word of ['accept', 'reject', 'defer', '接受', '拒绝', '延后']) {
      expect(labels.some(l => l.includes(word)), word).toBe(false)
    }
  })

  it('22. no scientific inference: every rendered relation is a declared ref', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    const src = readFileSync(join(__dirname, 'CircuitCandidateDetailPage.tsx'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
    // No similarity / keyword / proximity machinery may exist on this path.
    for (const forbidden of [
      'includes(', 'toLowerCase()', 'similarity', 'levenshtein', 'levenshteinDistance',
      'fuzzy', 'cooccurrence', 'co-occurrence', 'Math.abs(',
    ]) {
      expect(src.includes(forbidden), `detail page must not use "${forbidden}"`).toBe(false)
    }
    // And it resolves through the ONE declared-ref resolver.
    expect(src).toContain('resolveRefs')
  })
})

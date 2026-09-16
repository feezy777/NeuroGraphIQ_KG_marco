/**
 * Phase P0-4A — the run → candidate list flow, plus the read-only boundary.
 *
 * Two render targets, on purpose:
 *
 *   * the WORKSPACE, for everything about run selection — which run gets
 *     queried, what the panel does while a request is in flight, and that a
 *     slower answer for a previously selected run can never replace the current
 *     one. Those states only exist in the run's company.
 *   * the PANEL alone, for presentation — the four candidate kinds, the status,
 *     and the seven columns. A run fixture would only be noise there.
 *
 * The last describe block is the phase boundary: this round adds NO review
 * action. That is asserted against the sources AND against the real API module,
 * not only against the rendered output.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import { LlmCandidateList } from './LlmCandidateList'
import type { LlmDiscoveryCandidate } from './candidateTypes'
import type { BrainRegionSeedDetail, DiscoveryRun } from './types'

const getSeed = vi.fn()
const getRuns = vi.fn()
const getLiteratureRuns = vi.fn()
const getRunPublications = vi.fn()
const getLlmCandidates = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
  fetchLiteratureRuns: (...a: unknown[]) => getLiteratureRuns(...a),
  fetchRunPublications: (...a: unknown[]) => getRunPublications(...a),
  fetchRunLlmCandidates: (...a: unknown[]) => getLlmCandidates(...a),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
}))

const RUN_A = '11111111-2222-3333-4444-555555555555'
const RUN_B = '99999999-8888-7777-6666-555555555555'
const SEED_ID = 'NGIQ-BR-00000001'

function run(over: Partial<DiscoveryRun> = {}): DiscoveryRun {
  return {
    run_id: RUN_A,
    seed_entity_id: SEED_ID,
    discovery_type: 'LLM_DISCOVERY',
    status: 'COMPLETED',
    outcome: 'CANDIDATES_FOUND',
    provider: 'deepseek',
    model_name: 'deepseek-flash',
    prompt_key: null,
    prompt_version: null,
    query_strategy_version: null,
    created_by: null,
    created_at: '2026-09-15T10:00:00Z',
    started_at: '2026-09-15T10:00:10Z',
    finished_at: '2026-09-15T10:02:00Z',
    error_code: null,
    error_message: null,
    ...over,
  }
}

/** One persisted candidate, as P0-2A returns it. */
function candidate(over: Partial<LlmDiscoveryCandidate> = {}): LlmDiscoveryCandidate {
  return {
    candidate_id: 'NGIQ-DC-00000001',
    run_id: RUN_A,
    seed_entity_id: SEED_ID,
    candidate_type: 'region',
    local_id: 'region_1',
    name: 'CA1 field',
    payload: { local_id: 'region_1', name: 'CA1 field' },
    confidence: 0.72,
    status: 'proposed',
    created_at: '2026-09-15T10:01:00Z',
    updated_at: '2026-09-15T10:01:00Z',
    ...over,
  }
}

const DETAIL: BrainRegionSeedDetail = {
  entity_pk: 3,
  entity_id: SEED_ID,
  name_en: 'Left Hippocampus',
  name_zh: '左侧海马',
  abbreviation: null,
  granularity_level: 'G3_MESO_FINE',
  region_category: 'cortical_region',
  hemisphere: 'left',
  species_taxon_id: '9606',
  record_status: 'active',
  review_status: 'approved',
  atlas_names: ['Human Brainnetome Atlas'],
  definition_en: null,
  parent_region_pk: null,
  hierarchy_depth: 0,
  external_region_ids: [],
  mapping_types: [],
  mapping_review_statuses: [],
}

function renderWorkspace() {
  return render(
    <I18nProvider>
      <BrainRegionWorkspacePage entityId={SEED_ID} />
    </I18nProvider>,
  )
}

function renderPanel(props: Parameters<typeof LlmCandidateList>[0]) {
  return render(
    <I18nProvider>
      <LlmCandidateList {...props} />
    </I18nProvider>,
  )
}

/** The Nth DATA row of the run history (row 0 is the header). */
function runHistoryRow(index: number): HTMLElement {
  const rows = within(screen.getByTestId('kp-run-history')).getAllByRole('row')
  return rows[index + 1]
}

/** Open the Discovery tab with a run history in place. */
async function openDiscoveryWith(runs: DiscoveryRun[]) {
  getRuns.mockResolvedValue({ items: runs, total: runs.length })
  renderWorkspace()
  fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
  await waitFor(() => expect(screen.getByTestId('kp-run-history')).toBeTruthy())
}

beforeEach(() => {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en-US')
  getSeed.mockReset()
  getSeed.mockResolvedValue(DETAIL)
  getRuns.mockReset()
  getRuns.mockResolvedValue({ items: [], total: 0 })
  getLiteratureRuns.mockReset()
  getLiteratureRuns.mockResolvedValue({ items: [], total: 0 })
  getRunPublications.mockReset()
  getRunPublications.mockResolvedValue({
    run_id: 'x',
    items: [],
    distinct_publications: 0,
    hits_total: 0,
  })
  getLlmCandidates.mockReset()
  getLlmCandidates.mockResolvedValue({ items: [], total: 0 })
  window.location.hash = ''
})

// ===========================================================================
// §13.1-4 — selection, the request, and what is shown while it is in flight
// ===========================================================================
describe('run selection', () => {
  it('1. prompts the user to pick a run when none is selected', async () => {
    await openDiscoveryWith([run()])
    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(panel.getByTestId('kp-llm-candidates-select-prompt')).toBeTruthy()
    expect(
      panel.getByText('Select an LLM discovery run to see the candidates it proposed'),
    ).toBeTruthy()
    // Not selected means NOT queried: the prompt is not an empty result.
    expect(getLlmCandidates).not.toHaveBeenCalled()
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
  })

  it('2 + 3. selecting a run queries the API with THAT run_id', async () => {
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledTimes(1))
    expect(getLlmCandidates).toHaveBeenCalledWith(RUN_A)
    // The candidate endpoint only — never a publications request.
    expect(getRunPublications).not.toHaveBeenCalled()
  })

  it('4. shows a loading state until the answer arrives', async () => {
    let resolveCandidates: (v: unknown) => void = () => {}
    getLlmCandidates.mockReturnValue(new Promise(r => (resolveCandidates = r)))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByTestId('kp-llm-candidates-loading')).toBeTruthy()
    // Loading is not empty and not an error.
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
    expect(panel.queryByTestId('kp-llm-candidates-error')).toBeNull()

    resolveCandidates({ items: [candidate()], total: 1 })
    expect(await panel.findByText('NGIQ-DC-00000001')).toBeTruthy()
  })

  it('deselecting a run returns to the prompt and issues no further request', async () => {
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))
    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledTimes(1))

    fireEvent.click(runHistoryRow(0))
    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByTestId('kp-llm-candidates-select-prompt')).toBeTruthy()
    expect(getLlmCandidates).toHaveBeenCalledTimes(1)
  })
})

// ===========================================================================
// §13.5-6 — a zero-candidate run and an unreadable one are DIFFERENT facts
// ===========================================================================
describe('empty and error are not the same thing', () => {
  it('5. a run that proposed nothing shows a clean empty state, not an error', async () => {
    getLlmCandidates.mockResolvedValue({ items: [], total: 0 })
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    const empty = await panel.findByTestId('kp-llm-candidates-empty')
    expect(empty.textContent).toContain('This discovery run proposed no candidates')
    expect(panel.queryByTestId('kp-llm-candidates-error')).toBeNull()
    expect(panel.queryByTestId('kp-llm-candidates-loading')).toBeNull()
  })

  it('6. an unreadable candidate list is an ERROR, never an empty result', async () => {
    getLlmCandidates.mockRejectedValue(new Error('HTTP 500: boom'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    const err = await panel.findByTestId('kp-llm-candidates-error')
    expect(err.textContent).toContain('HTTP 500: boom')
    // The failure must NOT be reported as "proposed nothing".
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
  })
})

// ===========================================================================
// §13.10-11 — a stale run can never masquerade as the selected one
// ===========================================================================
describe('stale run protection', () => {
  it('10. switching runs clears the previous run’s candidates immediately', async () => {
    let resolveB: (v: unknown) => void = () => {}
    getLlmCandidates.mockResolvedValueOnce({ items: [candidate()], total: 1 })
    getLlmCandidates.mockReturnValueOnce(new Promise(r => (resolveB = r)))

    await openDiscoveryWith([run(), run({ run_id: RUN_B })])
    fireEvent.click(runHistoryRow(0))
    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByText('NGIQ-DC-00000001')).toBeTruthy()

    // Switch to the OTHER run, whose answer has not arrived.
    fireEvent.click(runHistoryRow(1))
    expect(await panel.findByTestId('kp-llm-candidates-loading')).toBeTruthy()
    expect(panel.queryByText('NGIQ-DC-00000001')).toBeNull()

    resolveB({ items: [candidate({ candidate_id: 'NGIQ-DC-00000002', run_id: RUN_B })], total: 1 })
    expect(await panel.findByText('NGIQ-DC-00000002')).toBeTruthy()
    expect(panel.queryByText('NGIQ-DC-00000001')).toBeNull()
  })

  it('11. a late answer for the PREVIOUS run cannot overwrite the current one', async () => {
    let resolveA: (v: unknown) => void = () => {}
    getLlmCandidates.mockReturnValueOnce(new Promise(r => (resolveA = r)))
    getLlmCandidates.mockResolvedValueOnce({
      items: [candidate({ candidate_id: 'NGIQ-DC-00000002', run_id: RUN_B })],
      total: 1,
    })

    await openDiscoveryWith([run(), run({ run_id: RUN_B })])
    fireEvent.click(runHistoryRow(0)) // A — slow, still in flight
    fireEvent.click(runHistoryRow(1)) // B — answers first

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByText('NGIQ-DC-00000002')).toBeTruthy()

    // A finally answers. It is no longer the selected run, so it is discarded.
    resolveA({ items: [candidate({ candidate_id: 'NGIQ-DC-00000001' })], total: 1 })
    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledTimes(2))
    expect(panel.queryByText('NGIQ-DC-00000001')).toBeNull()
    expect(panel.getByText('NGIQ-DC-00000002')).toBeTruthy()
  })

  it('states which run the candidates belong to, so rows cannot be misattributed', async () => {
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))
    const ctx = within(await screen.findByTestId('kp-llm-candidates-run'))
    expect(ctx.getByText(RUN_A)).toBeTruthy()
  })
})

// ===========================================================================
// §13.7-9 — the list itself
// ===========================================================================
describe('candidate list rendering', () => {
  it('7. renders one row per candidate with the six contract columns', async () => {
    getLlmCandidates.mockResolvedValue({
      items: [candidate(), candidate({ candidate_id: 'NGIQ-DC-00000002', local_id: 'region_2' })],
      total: 2,
    })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    await screen.findByText('NGIQ-DC-00000002')
    const table = screen.getByRole('table')
    expect(within(table).getAllByRole('columnheader').map(h => h.textContent)).toEqual([
      'candidate_id',
      'Type',
      'local_id',
      'Name',
      'Confidence',
      'Status',
    ])
    // 1 header row + one row per candidate.
    expect(within(table).getAllByRole('row')).toHaveLength(3)
  })

  it('8. the four candidate kinds are visually distinct, and never re-typed here', async () => {
    getLlmCandidates.mockResolvedValue({
      items: [
        candidate({ candidate_id: 'NGIQ-DC-00000001', candidate_type: 'region' }),
        candidate({ candidate_id: 'NGIQ-DC-00000002', candidate_type: 'connection' }),
        candidate({ candidate_id: 'NGIQ-DC-00000003', candidate_type: 'circuit' }),
        candidate({ candidate_id: 'NGIQ-DC-00000004', candidate_type: 'function' }),
      ],
      total: 4,
    })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    await waitFor(() => expect(screen.getByText('NGIQ-DC-00000004')).toBeTruthy())
    const badges = screen.getAllByTestId('kp-candidate-type-badge')
    // The caption is localized; the tone keys off the RAW enum, so the four must
    // differ in BOTH — one shared tone would make the taxonomy unreadable.
    expect(badges.map(b => b.textContent)).toEqual(['Region', 'Connection', 'Circuit', 'Function'])
    expect(new Set(badges.map(b => b.className)).size).toBe(4)
  })

  it('9. shows the real status of every candidate', async () => {
    getLlmCandidates.mockResolvedValue({
      items: [
        candidate({ candidate_id: 'NGIQ-DC-00000001', status: 'proposed' }),
        candidate({ candidate_id: 'NGIQ-DC-00000002', status: 'accepted' }),
        candidate({ candidate_id: 'NGIQ-DC-00000003', status: 'rejected' }),
        candidate({ candidate_id: 'NGIQ-DC-00000004', status: 'deferred' }),
      ],
      total: 4,
    })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    await waitFor(() => expect(screen.getByText('NGIQ-DC-00000004')).toBeTruthy())
    expect(screen.getAllByTestId('kp-candidate-status-badge').map(b => b.textContent)).toEqual([
      'Pending review',
      'Accepted',
      'Rejected',
      'Deferred',
    ])
  })

  it('9b. `accepted` is never dressed as validated or canonical', async () => {
    getLlmCandidates.mockResolvedValue({
      items: [candidate({ status: 'accepted' })],
      total: 1,
    })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    const badge = await screen.findByTestId('kp-candidate-status-badge')
    // Green is this workbench's "validated" tone. An accepted candidate has only
    // entered resolution, so it must not wear it.
    expect(badge.className).not.toContain('badge-green')
  })

  it('marks the selected row, and toggles the mark off on a second click', async () => {
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    // Scoped to the TABLE: once a candidate is selected its id also appears in
    // the detail grid below, so an unscoped query would match twice.
    const cell = () => within(screen.getByRole('table')).getByText('NGIQ-DC-00000001')
    const row = () => cell().closest('tr')
    await waitFor(() => expect(cell()).toBeTruthy())
    expect(row()?.className).not.toContain('kp-candidate-selected')

    fireEvent.click(cell())
    await waitFor(() => expect(row()?.className).toContain('kp-candidate-selected'))

    fireEvent.click(cell())
    await waitFor(() => expect(row()?.className).not.toContain('kp-candidate-selected'))
  })

  it('shows the selected candidate’s persisted fields, verbatim', async () => {
    getLlmCandidates.mockResolvedValue({
      items: [candidate({ payload: { local_id: 'region_1', relation_to_seed: 'AFFERENT' } })],
      total: 1,
    })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    await screen.findByRole('table')
    fireEvent.click(within(screen.getByRole('table')).getByText('NGIQ-DC-00000001'))
    const detail = within(await screen.findByTestId('kp-candidate-detail'))
    // Every contract field is present. Identifiers keep their raw column names;
    // only the descriptive captions are localized.
    for (const label of ['candidate_id', 'run_id', 'seed_entity_id', 'local_id',
      'Candidate type', 'Status', 'Confidence', 'Created', 'Updated']) {
      expect(detail.getByText(label), label).toBeTruthy()
    }
    expect(detail.getByText('NGIQ-DC-00000001')).toBeTruthy()
    // The payload is shown as stored — not summarized, not rebuilt from `name`.
    expect(detail.getByTestId('kp-candidate-payload').textContent).toContain('AFFERENT')
  })

  it('reports the API’s own total rather than counting what it rendered', async () => {
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 42 })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })
    expect((await screen.findByTestId('kp-llm-candidates-total')).textContent).toBe('42')
  })

  it('A. a seed with no LLM run says so, instead of prompting for a run', () => {
    renderPanel({ llmRuns: [], selectedRunId: null })
    expect(screen.getByTestId('kp-llm-candidates-noruns')).toBeTruthy()
    expect(screen.queryByTestId('kp-llm-candidates-select-prompt')).toBeNull()
  })

  it('B. an UNKNOWN run list is loading, never "there are none"', () => {
    renderPanel({ llmRuns: null, selectedRunId: null })
    expect(screen.getByTestId('kp-llm-candidates-runs-loading')).toBeTruthy()
    expect(screen.queryByTestId('kp-llm-candidates-noruns')).toBeNull()
    expect(screen.queryByTestId('kp-llm-candidates-select-prompt')).toBeNull()
  })

  it('C. a literature run is not a candidate source and asks for nothing', async () => {
    await openDiscoveryWith([run({ discovery_type: 'LITERATURE_DISCOVERY' })])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(panel.getByTestId('kp-llm-candidates-noruns')).toBeTruthy()
    expect(getLlmCandidates).not.toHaveBeenCalled()
  })
})

// ===========================================================================
// §13.12-14 — this phase has NO review action
// ===========================================================================
describe('no review coupling', () => {
  it('12. the panel offers no interactive control at all', async () => {
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })

    await screen.findByText('NGIQ-DC-00000001')
    const panel = within(screen.getByTestId('kp-llm-candidates'))
    // Selecting a row is allowed; acting on a candidate is not. With no button
    // and no form in here, there is nothing that could submit a decision.
    expect(panel.queryAllByRole('button')).toHaveLength(0)
    expect(panel.queryAllByRole('textbox')).toHaveLength(0)
    expect(panel.queryAllByRole('combobox')).toHaveLength(0)
  })

  it('12b. no candidate source mentions a review decision or endpoint', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    // No review endpoint and no review decision, anywhere on this path.
    const reviewTerms = ['/review', '/reviews', 'reviewJson', 'ACCEPT', 'REJECT', 'DEFER']
    // P0-4B gave kpApi.ts exactly ONE write: the LLM Discovery execution POST.
    // It lives THERE and nowhere else — no component issues its own request —
    // so the write verbs stay banned outright in every UI module.
    const writeTerms = ['postJson', 'putJson', 'patchJson', 'deleteJson']
    const strip = (src: string) =>
      src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')

    for (const f of [
      'LlmCandidateList.tsx',
      'candidateTypes.ts',
      'workspaceTabs.tsx',
      'types.ts',
    ]) {
      const code = strip(readFileSync(join(__dirname, f), 'utf8'))
      for (const term of [...reviewTerms, ...writeTerms]) {
        expect(code.includes(term), `${f} must not reference "${term}"`).toBe(false)
      }
    }
    const api = strip(readFileSync(join(__dirname, 'kpApi.ts'), 'utf8'))
    for (const term of reviewTerms) {
      expect(api.includes(term), `kpApi.ts must not reference "${term}"`).toBe(false)
    }
  })

  it('13 + 14. the real API module exposes no review or history function', async () => {
    const actual = await vi.importActual<typeof import('./kpApi')>('./kpApi')
    const names = Object.keys(actual)
    // Positive control: the candidate READ function is there, so "nothing
    // matched" means "no review function exists", not "the module failed to load".
    expect(names).toContain('fetchRunLlmCandidates')
    expect(names).toContain('fetchRunPublications')
    const suspect = names.filter(n => /review|accept|reject|defer/i.test(n))
    expect(suspect).toEqual([])
    // Every exported function is a read: kpApi imports getJson and nothing that
    // could send a body.
    const src = (await import('node:fs')).readFileSync(
      (await import('node:path')).join(__dirname, 'kpApi.ts'),
      'utf8',
    )
    expect(src).toContain('getJson')
    // P0-4B added the module's ONE write. Capping the count is a STRONGER guard
    // than the blanket ban it replaces: a second write cannot appear unnoticed,
    // and the one that exists must be the execution route, not a review.
    expect(src.match(/postJson</g) ?? []).toHaveLength(1)
    const afterPost = src.split('postJson<')[1] ?? ''
    expect(afterPost).toContain('llm-discovery/execute')
    expect(afterPost).not.toContain('review')
  })

  it('14b. rendering the whole panel performs no non-GET request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    renderPanel({ llmRuns: [run()], selectedRunId: RUN_A })
    await screen.findByText('NGIQ-DC-00000001')

    for (const call of fetchSpy.mock.calls) {
      const init = call[1] as RequestInit | undefined
      expect(init?.method ?? 'GET').toBe('GET')
    }
    fetchSpy.mockRestore()
  })
})

// ===========================================================================
// §13.15 — the existing workspace behaviour still holds
// ===========================================================================
describe('no regression in the existing workspace', () => {
  it('15. the seven tabs, the run history and the literature panel are intact', async () => {
    await openDiscoveryWith([run()])
    for (const id of ['overview', 'discovery', 'candidates', 'evidence',
      'canonicalization', 'validation', 'history']) {
      expect(screen.getByTestId(`kp-tab-${id}`)).toBeTruthy()
    }
    expect(screen.getByTestId('kp-run-history')).toBeTruthy()
    // The literature panel is still rendered alongside the candidate panel.
    expect(screen.getByTestId('kp-literature-inspector')).toBeTruthy()
  })

  it('15b. selecting an LLM run leaves the literature panel untouched', async () => {
    getLiteratureRuns.mockResolvedValue({ items: [], total: 0 })
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalled())
    // The LLM run is not a literature resource, so the literature panel neither
    // selects it nor asks for its publications.
    expect(screen.getByTestId('kp-literature-noruns')).toBeTruthy()
    expect(getRunPublications).not.toHaveBeenCalled()
  })
})

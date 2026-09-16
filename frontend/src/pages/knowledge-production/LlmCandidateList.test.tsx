/**
 * Phase P0-4C — the Discovery tab's run RESULT SUMMARY.
 *
 * P0-4A rendered the run's candidate rows here; P0-4C moved them to the Candidate
 * Knowledge tab, which owns a BrainRegion's pool. What this file still pins is
 * everything that did NOT move: the run-scoped fetch, the four render states, the
 * stale-run protection, and the fact that this tab reports a run rather than
 * listing its candidates. The row-rendering assertions now live in
 * `CandidateKnowledgeTab.test.tsx`, where the rows actually are.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { ApiError } from '../../api/client'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import { LlmCandidateList } from './LlmCandidateList'
import type { LlmDiscoveryCandidate } from './candidateTypes'
import type { BrainRegionSeedDetail, DiscoveryRun } from './types'

const getSeed = vi.fn()
const getRuns = vi.fn()
const getLiteratureRuns = vi.fn()
const getRunPublications = vi.fn()
const getLlmCandidates = vi.fn()
const getCandidatePool = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
  fetchLiteratureRuns: (...a: unknown[]) => getLiteratureRuns(...a),
  fetchRunPublications: (...a: unknown[]) => getRunPublications(...a),
  fetchRunLlmCandidates: (...a: unknown[]) => getLlmCandidates(...a),
  fetchBrainRegionLlmCandidates: (...a: unknown[]) => getCandidatePool(...a),
  executeLlmDiscovery: vi.fn().mockResolvedValue({ run: null }),
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
  granularity_level: 'G1_MACRO',
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

function renderPanel(props: Partial<Parameters<typeof LlmCandidateList>[0]> = {}) {
  const onOpenCandidates = props.onOpenCandidates ?? vi.fn()
  const utils = render(
    <I18nProvider>
      <LlmCandidateList
        llmRuns={[run()]}
        selectedRunId={RUN_A}
        onOpenCandidates={onOpenCandidates}
        {...props}
      />
    </I18nProvider>,
  )
  return { ...utils, onOpenCandidates }
}

/** An ApiError shaped exactly as the api client builds one. */
function apiFailure(status: number, code?: string): ApiError {
  return new ApiError(status, `HTTP ${status}: boom`, {
    url: '/api/knowledge-production/discovery-runs/x/llm-candidates',
    method: 'GET',
    responseBody: code
      ? { detail: { code, message: 'candidate storage is not enabled' } }
      : { detail: 'boom' },
  })
}

function runHistoryRow(index: number): HTMLElement {
  const rows = within(screen.getByTestId('kp-run-history')).getAllByRole('row')
  return rows[index + 1]
}

async function openDiscoveryWith(runs: DiscoveryRun[]) {
  getRuns.mockResolvedValue({ items: runs, total: runs.length })
  renderWorkspace()
  fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
  await screen.findByTestId('kp-llm-discovery')
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
    run_id: 'x', items: [], distinct_publications: 0, hits_total: 0,
  })
  getLlmCandidates.mockReset()
  getLlmCandidates.mockResolvedValue({ items: [], total: 0 })
  getCandidatePool.mockReset()
  getCandidatePool.mockResolvedValue({ items: [], total: 0 })
  window.location.hash = ''
})

// ===========================================================================
// selection, the request, and what is shown while it is in flight
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
    // The run-scoped candidate endpoint only — never a publications request.
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
    expect(await panel.findByTestId('kp-llm-run-found')).toBeTruthy()
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
// empty and error are not the same thing
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
    expect(panel.queryByTestId('kp-llm-run-summary')).toBeNull()
  })

  it('6. an unreadable candidate list is an ERROR, never an empty result', async () => {
    getLlmCandidates.mockRejectedValue(new Error('HTTP 500: boom'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    const err = await panel.findByTestId('kp-llm-candidates-error')
    expect(err.textContent).toContain('HTTP 500: boom')
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
  })
})

// ===========================================================================
// the database has no candidate storage — a STATE, not a failure
// ===========================================================================
describe('candidate storage not enabled on this database', () => {
  it('shows the unavailable sentence — not the raw 409, not an error, not empty', async () => {
    getLlmCandidates.mockRejectedValue(apiFailure(409, 'DISCOVERY_DATABASE_NOT_READY'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    const notice = await panel.findByTestId('kp-llm-candidates-storage-not-enabled')
    expect(notice.textContent).toBe(
      'Candidate knowledge storage is not enabled on the current database',
    )
    // The three things it must not be mistaken for.
    expect(panel.queryByTestId('kp-llm-candidates-error')).toBeNull()
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
    // ...and no technical payload anywhere in the panel.
    expect(panel.queryByText(/HTTP 409/)).toBeNull()
    expect(panel.queryByText(/DISCOVERY_DATABASE_NOT_READY/)).toBeNull()
  })

  it('shows no candidate counts for a result it never read', async () => {
    getLlmCandidates.mockRejectedValue(apiFailure(409, 'DISCOVERY_DATABASE_NOT_READY'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    await panel.findByTestId('kp-llm-candidates-storage-not-enabled')
    // A count here would be a number nobody measured.
    expect(panel.queryByTestId('kp-llm-run-summary')).toBeNull()
    expect(panel.queryByTestId('kp-llm-run-total')).toBeNull()
    expect(panel.queryByTestId('kp-open-candidates')).toBeNull()
  })

  it('still shows the RUN, whose record is readable even when candidates are not', async () => {
    getLlmCandidates.mockRejectedValue(apiFailure(409, 'DISCOVERY_DATABASE_NOT_READY'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    await panel.findByTestId('kp-llm-candidates-storage-not-enabled')
    expect(panel.getByTestId('kp-llm-run-provider').textContent).toContain('deepseek')
    expect(panel.getByTestId('kp-llm-run-model').textContent).toContain('deepseek-flash')
  })

  it('a 503 DATABASE_UNAVAILABLE stays an ERROR — an outage is not a disabled feature', async () => {
    getLlmCandidates.mockRejectedValue(apiFailure(503, 'DATABASE_UNAVAILABLE'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByTestId('kp-llm-candidates-error')).toBeTruthy()
    expect(panel.queryByTestId('kp-llm-candidates-storage-not-enabled')).toBeNull()
  })

  it('an unknown code stays an ERROR — only the one known code is a state', async () => {
    getLlmCandidates.mockRejectedValue(apiFailure(500, 'SOMETHING_ELSE'))
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect(await panel.findByTestId('kp-llm-candidates-error')).toBeTruthy()
    expect(panel.queryByTestId('kp-llm-candidates-storage-not-enabled')).toBeNull()
  })
})

// ===========================================================================
// a stale run can never masquerade as the selected one
// ===========================================================================
describe('stale run protection', () => {
  it('10. switching runs clears the previous run’s counts immediately', async () => {
    let resolveB: (v: unknown) => void = () => {}
    getLlmCandidates.mockResolvedValueOnce({ items: [candidate()], total: 1 })
    getLlmCandidates.mockReturnValueOnce(new Promise(r => (resolveB = r)))

    await openDiscoveryWith([run(), run({ run_id: RUN_B })])
    fireEvent.click(runHistoryRow(0))
    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect((await panel.findByTestId('kp-llm-run-total')).textContent).toContain('1')

    // Switch to the OTHER run, whose answer has not arrived.
    fireEvent.click(runHistoryRow(1))
    expect(await panel.findByTestId('kp-llm-candidates-loading')).toBeTruthy()
    expect(panel.queryByTestId('kp-llm-run-summary')).toBeNull()

    resolveB({ items: [], total: 0 })
    expect(await panel.findByTestId('kp-llm-candidates-empty')).toBeTruthy()
  })

  it('11. a late answer for the PREVIOUS run cannot overwrite the current one', async () => {
    let resolveA: (v: unknown) => void = () => {}
    getLlmCandidates.mockReturnValueOnce(new Promise(r => (resolveA = r)))
    getLlmCandidates.mockResolvedValueOnce({ items: [candidate()], total: 1 })

    await openDiscoveryWith([run(), run({ run_id: RUN_B })])
    fireEvent.click(runHistoryRow(0)) // A — slow, still in flight
    fireEvent.click(runHistoryRow(1)) // B — answers first

    const panel = within(screen.getByTestId('kp-llm-candidates'))
    expect((await panel.findByTestId('kp-llm-run-total')).textContent).toContain('1')

    // A finally answers. It is no longer the selected run, so it is discarded:
    // the summary must still be B's, and A reported nothing.
    resolveA({ items: [], total: 0 })
    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledTimes(2))
    expect(panel.queryByTestId('kp-llm-candidates-empty')).toBeNull()
    expect(panel.getByTestId('kp-llm-run-summary')).toBeTruthy()
  })

  it('states which run the summary belongs to, so counts cannot be misattributed', async () => {
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))
    const ctx = within(await screen.findByTestId('kp-llm-candidates-run'))
    expect(ctx.getByText(RUN_A)).toBeTruthy()
  })
})

// ===========================================================================
// the run RESULT SUMMARY — the whole report this tab owes the user
// ===========================================================================
describe('run result summary', () => {
  const MIXED = [
    candidate({ candidate_id: 'NGIQ-DC-00000001', candidate_type: 'region' }),
    candidate({ candidate_id: 'NGIQ-DC-00000002', candidate_type: 'region' }),
    candidate({ candidate_id: 'NGIQ-DC-00000003', candidate_type: 'circuit' }),
    candidate({ candidate_id: 'NGIQ-DC-00000004', candidate_type: 'connection' }),
    candidate({ candidate_id: 'NGIQ-DC-00000005', candidate_type: 'function' }),
  ]

  it('reports the total and one count per candidate kind', async () => {
    getLlmCandidates.mockResolvedValue({ items: MIXED, total: MIXED.length })
    renderPanel()
    const panel = within(screen.getByTestId('kp-llm-candidates'))

    await panel.findByTestId('kp-llm-run-summary')
    expect(panel.getByTestId('kp-llm-run-total').textContent).toContain('5')
    expect(panel.getByTestId('kp-llm-run-count-circuit').textContent).toContain('1')
    expect(panel.getByTestId('kp-llm-run-count-connection').textContent).toContain('1')
    expect(panel.getByTestId('kp-llm-run-count-function').textContent).toContain('1')
    expect(panel.getByTestId('kp-llm-run-count-region').textContent).toContain('2')
  })

  it('does NOT list the candidate rows — that is the Candidate Knowledge tab’s job', async () => {
    getLlmCandidates.mockResolvedValue({ items: MIXED, total: MIXED.length })
    renderPanel()
    const panel = within(screen.getByTestId('kp-llm-candidates'))

    await panel.findByTestId('kp-llm-run-summary')
    // Counts, not rows: no candidate id and no per-candidate name appears here.
    expect(panel.queryByText('NGIQ-DC-00000001')).toBeNull()
    expect(panel.queryByText('CA1 field')).toBeNull()
    expect(screen.queryByTestId('kp-candidate-detail')).toBeNull()
    expect(panel.queryByRole('table')).toBeNull()
  })

  it('offers exactly one way forward: to the candidate pool', async () => {
    getLlmCandidates.mockResolvedValue({ items: MIXED, total: MIXED.length })
    const { onOpenCandidates } = renderPanel()
    const panel = within(screen.getByTestId('kp-llm-candidates'))

    const button = await panel.findByTestId('kp-open-candidates')
    expect(button.textContent).toBe('View candidate knowledge')
    fireEvent.click(button)
    expect(onOpenCandidates).toHaveBeenCalledTimes(1)
  })

  it('A. a seed with no LLM run says so, instead of prompting for a run', () => {
    renderPanel({ llmRuns: [] })
    expect(screen.getByTestId('kp-llm-candidates-noruns')).toBeTruthy()
    expect(screen.queryByTestId('kp-llm-candidates-select-prompt')).toBeNull()
  })

  it('B. an UNKNOWN run list is loading, never "there are none"', () => {
    renderPanel({ llmRuns: null })
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
// the phase boundary — no review action
// ===========================================================================
describe('no review coupling', () => {
  it('12. the only control is the navigation button, and it decides nothing', async () => {
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    renderPanel()
    const panel = within(await screen.findByTestId('kp-llm-candidates'))

    const buttons = panel.getAllByRole('button')
    expect(buttons.map(b => b.textContent)).toEqual(['View candidate knowledge'])
    for (const word of ['accept', 'reject', 'defer', '接受', '拒绝', '延后']) {
      expect(buttons.some(b => (b.textContent ?? '').toLowerCase().includes(word)), word).toBe(
        false,
      )
    }
  })

  it('12b. no candidate source mentions a review decision or endpoint', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    // No review endpoint and no review decision, anywhere on this path.
    const reviewTerms = ['/review', '/reviews', 'reviewJson', 'ACCEPT', 'REJECT', 'DEFER']
    // The write verbs stay banned outright in every UI module: components never
    // issue their own requests. kpApi.ts owns the module's one write.
    const writeTerms = ['postJson', 'putJson', 'patchJson', 'deleteJson']
    const strip = (src: string) =>
      src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')

    for (const f of [
      'LlmCandidateList.tsx',
      'CandidateKnowledgeTab.tsx',
      'CircuitCandidateDetailPage.tsx',
      'circuitPayload.ts',
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

  it('13 + 14. the real API module performs exactly one write, and it is not a review', async () => {
    const actual = await vi.importActual<typeof import('./kpApi')>('./kpApi')
    const names = Object.keys(actual)
    // Positive control: the reads are there, so "nothing matched" below means
    // "no review function exists", not "the module failed to load".
    expect(names).toContain('fetchRunLlmCandidates')
    expect(names).toContain('fetchBrainRegionLlmCandidates')
    expect(names.filter(n => /review|accept|reject|defer/i.test(n))).toEqual([])

    const src = (await import('node:fs')).readFileSync(
      (await import('node:path')).join(__dirname, 'kpApi.ts'),
      'utf8',
    )
    expect(src).toContain('getJson')
    expect(src.match(/postJson</g) ?? []).toHaveLength(1)
    const afterPost = src.split('postJson<')[1] ?? ''
    expect(afterPost).toContain('llm-discovery/execute')
    expect(afterPost).not.toContain('review')
  })

  it('14b. rendering the whole summary performs no non-GET request', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch')
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    renderPanel()
    await screen.findByTestId('kp-llm-run-summary')

    for (const call of fetchSpy.mock.calls) {
      const init = call[1] as RequestInit | undefined
      expect(init?.method ?? 'GET').toBe('GET')
    }
    fetchSpy.mockRestore()
  })
})

// ===========================================================================
// the existing workspace behaviour still holds
// ===========================================================================
describe('no regression in the existing workspace', () => {
  it('15. the seven tabs, the run history and the literature panel are intact', async () => {
    await openDiscoveryWith([run()])
    for (const id of ['overview', 'discovery', 'candidates', 'evidence',
      'canonicalization', 'validation', 'history']) {
      expect(screen.getByTestId(`kp-tab-${id}`)).toBeTruthy()
    }
    expect(screen.getByTestId('kp-run-history')).toBeTruthy()
    expect(screen.getByTestId('kp-literature-inspector')).toBeTruthy()
  })

  it('15b. selecting an LLM run leaves the literature panel untouched', async () => {
    getLiteratureRuns.mockResolvedValue({ items: [], total: 0 })
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalled())
    expect(screen.getByTestId('kp-literature-noruns')).toBeTruthy()
    expect(getRunPublications).not.toHaveBeenCalled()
  })

  it('15c. the handoff button switches the workspace to the candidate tab', async () => {
    getLlmCandidates.mockResolvedValue({ items: [candidate()], total: 1 })
    await openDiscoveryWith([run()])
    fireEvent.click(runHistoryRow(0))

    fireEvent.click(await screen.findByTestId('kp-open-candidates'))
    // The page owns the tab state; the pool now loads for THIS region.
    await waitFor(() => expect(getCandidatePool).toHaveBeenCalledWith(SEED_ID))
    expect(await screen.findByTestId('kp-candidate-filters')).toBeTruthy()
  })
})

/**
 * Phase P0-4B — starting a real LLM Discovery from the Workbench.
 *
 * Everything here renders the WORKSPACE and drives it through real clicks: the
 * button, the request, the history refetch and the handoff to the candidate
 * panel are one flow, and testing the pieces separately would not prove the flow.
 *
 * The whole execution chain is the backend's. This layer adds exactly one thing —
 * a request — and the tests below assert that it adds nothing else: no second
 * run, no fabricated run row, no locally invented candidate, and no reading of a
 * failed attempt as an empty result.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { ApiError } from '../../api/client'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import { isLiteratureDiscoveryType, isLlmDiscoveryType } from './types'
import type { BrainRegionSeedDetail, DiscoveryRun } from './types'

const getSeed = vi.fn()
const getRuns = vi.fn()
const getLiteratureRuns = vi.fn()
const getRunPublications = vi.fn()
const getLlmCandidates = vi.fn()
const getCandidatePool = vi.fn()
const postExecute = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
  fetchLiteratureRuns: (...a: unknown[]) => getLiteratureRuns(...a),
  fetchRunPublications: (...a: unknown[]) => getRunPublications(...a),
  fetchRunLlmCandidates: (...a: unknown[]) => getLlmCandidates(...a),
  fetchBrainRegionLlmCandidates: (...a: unknown[]) => getCandidatePool(...a),
  executeLlmDiscovery: (...a: unknown[]) => postExecute(...a),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
}))

const SEED_ID = 'NGIQ-BR-00000252'
const NEW_RUN = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

function run(over: Partial<DiscoveryRun> = {}): DiscoveryRun {
  return {
    run_id: NEW_RUN,
    seed_entity_id: SEED_ID,
    discovery_type: 'LLM_DISCOVERY',
    status: 'COMPLETED',
    outcome: 'CANDIDATES_FOUND',
    provider: 'deepseek',
    model_name: 'deepseek-flash',
    prompt_key: 'llm_discovery',
    prompt_version: 'v1',
    query_strategy_version: null,
    created_by: null,
    created_at: '2026-09-16T10:00:00Z',
    started_at: '2026-09-16T10:00:01Z',
    finished_at: '2026-09-16T10:00:30Z',
    error_code: null,
    error_message: null,
    ...over,
  }
}

const DETAIL: BrainRegionSeedDetail = {
  entity_pk: 745,
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

/** An ApiError shaped exactly as `client.ts` builds one for a structured detail. */
function apiError(status: number, detail: Record<string, unknown>): ApiError {
  return new ApiError(status, `HTTP ${status}`, {
    url: '/api/knowledge-production/x',
    method: 'POST',
    responseBody: { detail },
  })
}

/**
 * Render the Workspace and open its Discovery tab.
 *
 * Deliberately does NOT touch the `getRuns` mock: several tests need to arm a
 * per-call sequence (empty first load, populated refresh), and setting the
 * default here would overwrite that chain. `beforeEach` leaves it returning no
 * runs, which is the state a first execution starts from.
 */
async function openDiscovery() {
  render(
    <I18nProvider>
      <BrainRegionWorkspacePage entityId={SEED_ID} />
    </I18nProvider>,
  )
  fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
  // The run history is absent when the seed has no runs, so wait for the
  // ACTION, not the table.
  await screen.findByTestId('kp-llm-discovery')
}

const llmButton = () => screen.getByTestId('kp-llm-discovery')

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
  postExecute.mockReset()
  window.location.hash = ''
})

// ===========================================================================
// §11.1-5 — the button, the request, and the double-submit guard
// ===========================================================================
describe('the LLM Discovery action', () => {
  it('1. is enabled', async () => {
    await openDiscovery()
    expect(llmButton()).toHaveProperty('disabled', false)
    expect(llmButton().textContent).toBe('Start LLM Discovery')
  })

  it('2. leaves Literature Discovery disabled', async () => {
    await openDiscovery()
    const lit = screen.getByTestId('kp-literature-discovery')
    expect(lit).toHaveProperty('disabled', true)
    // Still explained, rather than silently dead.
    expect(lit.getAttribute('title')).toBeTruthy()
  })

  it('3 + 4. calls the real API client with THIS Workspace’s entity_id', async () => {
    postExecute.mockResolvedValue({ run: run() })
    await openDiscovery()
    fireEvent.click(llmButton())

    await waitFor(() => expect(postExecute).toHaveBeenCalledTimes(1))
    // The route is the BrainRegion authority: the user never re-selects a seed.
    expect(postExecute).toHaveBeenCalledWith(SEED_ID)
  })

  it('5. disables the button while in flight and refuses a second run', async () => {
    let resolveExecute: (v: unknown) => void = () => {}
    postExecute.mockReturnValue(new Promise(r => (resolveExecute = r)))
    await openDiscovery()

    fireEvent.click(llmButton())
    await waitFor(() => expect(llmButton()).toHaveProperty('disabled', true))
    // The busy label replaces the action label, so the state is visible.
    expect(llmButton().textContent).toBe('Starting…')

    fireEvent.click(llmButton())
    fireEvent.click(llmButton())
    expect(postExecute).toHaveBeenCalledTimes(1)

    resolveExecute({ run: run() })
    await waitFor(() => expect(llmButton()).toHaveProperty('disabled', false))
  })
})

// ===========================================================================
// §11.6-8 — refresh, selection, handoff
// ===========================================================================
describe('after a successful run', () => {
  it('6 + 7 + 8. refetches the history, selects the new run, and hands it to the panel', async () => {
    // First load: no runs. After the execution the backend reports the new one.
    getRuns
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [run()], total: 1 })
    postExecute.mockResolvedValue({ run: run() })

    await openDiscovery()
    expect(getRuns).toHaveBeenCalledTimes(1)
    fireEvent.click(llmButton())

    // 6 — the history is REFETCHED from the backend.
    await waitFor(() => expect(getRuns).toHaveBeenCalledTimes(2))
    // 7 — the new run is in the history, and it is the one that got selected.
    const history = within(await screen.findByTestId('kp-run-history'))
    expect(history.getByText('LLM Discovery')).toBeTruthy()
    // 8 — the candidate panel was handed the run id from the RESPONSE.
    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledWith(NEW_RUN))
  })

  it('does not splice a locally built run into the history', async () => {
    // The history answers [] even AFTER the execution: if the UI invented a row
    // from the response, the table would show one anyway.
    getRuns.mockResolvedValue({ items: [], total: 0 })
    postExecute.mockResolvedValue({ run: run() })
    await openDiscovery()
    fireEvent.click(llmButton())

    await waitFor(() => expect(getRuns).toHaveBeenCalledTimes(2))
    expect(screen.queryByTestId('kp-run-history')).toBeNull()
  })

  it('leaves the literature panel alone', async () => {
    getRuns
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [run()], total: 1 })
    postExecute.mockResolvedValue({ run: run() })
    await openDiscovery()
    fireEvent.click(llmButton())

    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalled())
    // An LLM run is not a literature resource, so no publications request.
    expect(getRunPublications).not.toHaveBeenCalled()
  })
})

// ===========================================================================
// §11.9-11 + §9 — a failure is reported as a failure, and invents nothing
// ===========================================================================
describe('launch failures', () => {
  const CASES = [
    [
      '9. an active run already exists (409)',
      apiError(409, { code: 'ACTIVE_RUN_EXISTS', message: 'an active LLM_DISCOVERY run already exists' }),
      'This BrainRegion already has a discovery run in progress. Wait for it to finish.',
      'ACTIVE_RUN_EXISTS',
    ],
    [
      '9b. the BrainRegion does not exist (404)',
      apiError(404, { code: 'NOT_FOUND', message: "BrainRegion 'NGIQ-BR-00000252' not found" }),
      'This BrainRegion does not exist, so no discovery run can be started.',
      'NOT_FOUND',
    ],
  ] as const

  for (const [name, error, headline, code] of CASES) {
    it(name, async () => {
      postExecute.mockRejectedValue(error)
      await openDiscovery()
      fireEvent.click(llmButton())

      const box = within(await screen.findByTestId('kp-llm-execute-error'))
      expect(box.getByTestId('kp-llm-execute-error-headline').textContent).toBe(headline)
      expect(box.getByTestId('kp-llm-execute-error-code').textContent).toBe(code)
      // The backend's own prose, not a JSON dump.
      expect(box.getByText(String(error.meta?.responseBody
        ? (error.meta.responseBody as { detail: { message: string } }).detail.message
        : ''))).toBeTruthy()
    })
  }

  it('10. reports a model-run failure with the run that failed', async () => {
    postExecute.mockRejectedValue(
      apiError(502, {
        code: 'LLM_EMPTY_RESPONSE',
        message: 'the model returned no content to parse',
        run_id: NEW_RUN,
      }),
    )
    await openDiscovery()
    fireEvent.click(llmButton())

    const box = within(await screen.findByTestId('kp-llm-execute-error'))
    expect(box.getByTestId('kp-llm-execute-error-headline').textContent).toContain(
      'the model call failed',
    )
    expect(box.getByTestId('kp-llm-execute-error-code').textContent).toBe('LLM_EMPTY_RESPONSE')
    // The run EXISTS and is inspectable — the id is not thrown away.
    expect(box.getByTestId('kp-llm-execute-error-run').textContent).toContain(NEW_RUN)
  })

  it('10b. restores the button after a failure', async () => {
    postExecute.mockRejectedValue(apiError(502, { code: 'LLM_PROVIDER_TIMEOUT', message: 'timeout' }))
    await openDiscovery()
    fireEvent.click(llmButton())

    await screen.findByTestId('kp-llm-execute-error')
    expect(llmButton()).toHaveProperty('disabled', false)
    expect(llmButton().textContent).toBe('Start LLM Discovery')
  })

  it('11. a failed launch fabricates neither a run nor a candidate result', async () => {
    postExecute.mockRejectedValue(
      apiError(502, { code: 'LLM_DISCOVERY_PARSE_FAILED', message: 'unparseable', run_id: NEW_RUN }),
    )
    await openDiscovery()
    fireEvent.click(llmButton())
    await screen.findByTestId('kp-llm-execute-error')

    // No run was produced, so the history is NOT refetched...
    expect(getRuns).toHaveBeenCalledTimes(1)
    // ...no candidate request is made for a run that does not exist...
    expect(getLlmCandidates).not.toHaveBeenCalled()
    // ...and the run that DID fail is never treated as one that proposed nothing.
    expect(screen.queryByTestId('kp-llm-candidates-empty')).toBeNull()
    expect(screen.queryByTestId('kp-run-history')).toBeNull()
  })

  it('clears the previous failure when a new attempt is made', async () => {
    postExecute.mockRejectedValueOnce(apiError(409, { code: 'ACTIVE_RUN_EXISTS', message: 'busy' }))
    postExecute.mockResolvedValueOnce({ run: run() })
    getRuns
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [run()], total: 1 })
    await openDiscovery()

    fireEvent.click(llmButton())
    await screen.findByTestId('kp-llm-execute-error')

    fireEvent.click(llmButton())
    await waitFor(() => expect(screen.queryByTestId('kp-llm-execute-error')).toBeNull())
  })
})

// ===========================================================================
// §11.12-13 — no provider coupling, no review action
// ===========================================================================
describe('what this phase does NOT add', () => {
  it('12. the frontend reaches no model provider: execution goes through the backend route', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    // Stated positively: the ONE write this page performs targets the backend's
    // own execution route. The provider is reached by the SERVER, never here.
    const api = readFileSync(join(__dirname, 'kpApi.ts'), 'utf8')
    const execute = api.split('executeLlmDiscovery')[1] ?? ''
    expect(execute).toContain('/llm-discovery/execute')
    expect(execute).toContain('${BASE}')

    // And negatively, across the whole execution path: no provider name, no SDK,
    // no external host. A model call from here would bypass the run record.
    const forbidden = ['deepseek', 'kimi', 'openai', 'api.', 'https://']
    for (const f of ['kpApi.ts', 'workspaceTabs.tsx', 'BrainRegionWorkspacePage.tsx']) {
      const code = readFileSync(join(__dirname, f), 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/[^\n]*/g, '')
        .toLowerCase()
      for (const term of forbidden) {
        expect(code.includes(term), `${f} must not reference "${term}"`).toBe(false)
      }
    }
  })

  it('13. adds no review action and calls no review endpoint', async () => {
    postExecute.mockResolvedValue({ run: run() })
    getRuns
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [run()], total: 1 })
    await openDiscovery()

    const tab = within(screen.getByTestId('kp-discovery-tab'))
    const labels = tab.getAllByRole('button').map(b => (b.textContent ?? '').toLowerCase())
    for (const word of ['accept', 'reject', 'defer', '接受', '拒绝', '延后']) {
      expect(labels.some(l => l.includes(word)), word).toBe(false)
    }
  })
})

// ===========================================================================
// §11.14-15 — the existing routes are untouched
// ===========================================================================
describe('route isolation holds', () => {
  it('15. the literature routes are still classified independently', () => {
    expect(isLlmDiscoveryType('LLM_DISCOVERY')).toBe(true)
    expect(isLiteratureDiscoveryType('LLM_DISCOVERY')).toBe(false)
    for (const route of ['LITERATURE_DISCOVERY', 'EVIDENCE_SEARCH', 'CITATION_CHAINING'] as const) {
      expect(isLlmDiscoveryType(route)).toBe(false)
      expect(isLiteratureDiscoveryType(route)).toBe(true)
    }
  })

  it('14. a completed execution hands the new run to the result summary', async () => {
    getRuns
      .mockResolvedValueOnce({ items: [], total: 0 })
      .mockResolvedValue({ items: [run()], total: 1 })
    postExecute.mockResolvedValue({ run: run() })
    getLlmCandidates.mockResolvedValue({
      items: [{
        candidate_id: 'NGIQ-DC-00000001',
        run_id: NEW_RUN,
        seed_entity_id: SEED_ID,
        candidate_type: 'circuit',
        local_id: 'circuit_1',
        name: 'Hippocampal trisynaptic circuit',
        payload: { local_id: 'circuit_1' },
        confidence: 0.9,
        status: 'proposed',
        created_at: '2026-09-16T10:00:20Z',
        updated_at: '2026-09-16T10:00:20Z',
      }],
      total: 1,
    })

    await openDiscovery()
    fireEvent.click(llmButton())

    // P0-4C: the Discovery tab reports the run's RESULT — the run it belongs to
    // and how many candidates it produced — and does not list the rows.
    const panel = within(await screen.findByTestId('kp-llm-candidates'))
    const ctx = within(await panel.findByTestId('kp-llm-candidates-run'))
    expect(ctx.getByText(NEW_RUN)).toBeTruthy()
    expect((await panel.findByTestId('kp-llm-run-total')).textContent).toContain('1')
    expect(panel.getByTestId('kp-llm-run-found').textContent).toBe('Discovery complete')
    expect(panel.queryByText('NGIQ-DC-00000001')).toBeNull()
  })
})

/**
 * Phase P0-4C — Candidate Knowledge tab.
 *
 * The tab renders a BrainRegion's whole candidate POOL from the region-scoped
 * read API, filters it by kind, and opens a circuit's own page. Read-only: the
 * decisions (accept / reject / defer) do not exist here and are asserted absent.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { ApiError } from '../../api/client'
import { CandidateKnowledgeTab } from './CandidateKnowledgeTab'
import type { LlmDiscoveryCandidate } from './candidateTypes'

const getCandidatePool = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionLlmCandidates: (...a: unknown[]) => getCandidatePool(...a),
  fetchRunLlmCandidates: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchDiscoveryRuns: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  fetchBrainRegionSeed: vi.fn(),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
  fetchLiteratureRuns: vi.fn(),
  fetchRunPublications: vi.fn(),
  executeLlmDiscovery: vi.fn(),
}))

const SEED_ID = 'NGIQ-BR-00001169'
const RUN_A = '673a88f4-fe84-4233-85a3-abf1719cac0a'
const RUN_B = '11111111-2222-3333-4444-555555555555'

function candidate(over: Partial<LlmDiscoveryCandidate> = {}): LlmDiscoveryCandidate {
  return {
    candidate_id: 'NGIQ-DC-00000001',
    run_id: RUN_A,
    seed_entity_id: SEED_ID,
    candidate_type: 'circuit',
    local_id: 'circuit_1',
    name: 'Hippocampal trisynaptic circuit',
    payload: { local_id: 'circuit_1' },
    confidence: 0.9,
    status: 'proposed',
    created_at: '2026-09-16T12:08:00Z',
    updated_at: '2026-09-16T12:08:00Z',
    ...over,
  }
}

/** 2 circuits / 3 connections / 1 function / 4 regions = 10. */
const POOL: LlmDiscoveryCandidate[] = [
  candidate({ candidate_id: 'NGIQ-DC-00000001', local_id: 'circuit_1' }),
  candidate({ candidate_id: 'NGIQ-DC-00000002', local_id: 'circuit_2' }),
  candidate({ candidate_id: 'NGIQ-DC-00000003', candidate_type: 'connection', local_id: 'connection_1', name: 'Entorhinal -> SEED [PROJECTION]' }),
  candidate({ candidate_id: 'NGIQ-DC-00000004', candidate_type: 'connection', local_id: 'connection_2' }),
  candidate({ candidate_id: 'NGIQ-DC-00000005', candidate_type: 'connection', local_id: 'connection_3' }),
  candidate({ candidate_id: 'NGIQ-DC-00000006', candidate_type: 'function', local_id: 'function_1', name: 'Pattern separation' }),
  candidate({ candidate_id: 'NGIQ-DC-00000007', candidate_type: 'region', local_id: 'region_1', name: 'Entorhinal cortex' }),
  candidate({ candidate_id: 'NGIQ-DC-00000008', candidate_type: 'region', local_id: 'region_2', name: 'Dentate gyrus' }),
  candidate({ candidate_id: 'NGIQ-DC-00000009', candidate_type: 'region', local_id: 'region_3', name: 'CA3' }),
  candidate({ candidate_id: 'NGIQ-DC-00000010', candidate_type: 'region', local_id: 'region_4', name: 'CA1' }),
]

function renderTab(props: Partial<Parameters<typeof CandidateKnowledgeTab>[0]> = {}) {
  const onOpenCircuit = props.onOpenCircuit ?? vi.fn()
  const utils = render(
    <I18nProvider>
      <CandidateKnowledgeTab entityId={SEED_ID} onOpenCircuit={onOpenCircuit} {...props} />
    </I18nProvider>,
  )
  return { ...utils, onOpenCircuit }
}

const rows = () => within(screen.getByRole('table')).getAllByRole('row')

beforeEach(() => {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en-US')
  getCandidatePool.mockReset()
  getCandidatePool.mockResolvedValue({ items: POOL, total: POOL.length })
})

// ===========================================================================
// §23.1-6 — the pool, its filters and its counts
// ===========================================================================
describe('candidate pool', () => {
  it('1 + 2. loads the BrainRegion pool from the region-scoped API', async () => {
    renderTab()
    await waitFor(() => expect(getCandidatePool).toHaveBeenCalledWith(SEED_ID))
    // One request for the REGION — not a walk over runs, and no run-scoped call.
    expect(getCandidatePool).toHaveBeenCalledTimes(1)
  })

  it('4. shows the total and one count per kind, over the WHOLE pool', async () => {
    renderTab()
    const stats = within(await screen.findByTestId('kp-candidate-pool-stats'))
    expect(stats.getByTestId('kp-candidate-count-total').textContent).toContain('10')
    expect(stats.getByTestId('kp-candidate-count-circuit').textContent).toContain('2')
    expect(stats.getByTestId('kp-candidate-count-connection').textContent).toContain('3')
    expect(stats.getByTestId('kp-candidate-count-function').textContent).toContain('1')
    expect(stats.getByTestId('kp-candidate-count-region').textContent).toContain('4')
  })

  it('4b. the counts do NOT change when a filter is applied', async () => {
    renderTab()
    await screen.findByRole('table')
    fireEvent.click(screen.getByTestId('kp-candidate-filter-circuit'))
    const stats = within(screen.getByTestId('kp-candidate-pool-stats'))
    // They describe the pool, not the view: re-counting the filtered rows would
    // make them a moving target and hide the pool's real composition.
    expect(stats.getByTestId('kp-candidate-count-total').textContent).toContain('10')
    expect(stats.getByTestId('kp-candidate-count-region').textContent).toContain('4')
  })

  it('3. the five filters show exactly their own kind', async () => {
    renderTab()
    await screen.findByRole('table')
    // 1 header + N rows
    expect(rows()).toHaveLength(11)

    const cases: [string, number][] = [
      ['circuit', 2],
      ['connection', 3],
      ['function', 1],
      ['region', 4],
    ]
    for (const [type, expected] of cases) {
      fireEvent.click(screen.getByTestId(`kp-candidate-filter-${type}`))
      await waitFor(() => expect(rows()).toHaveLength(expected + 1))
    }
    fireEvent.click(screen.getByTestId('kp-candidate-filter-all'))
    await waitFor(() => expect(rows()).toHaveLength(11))
  })

  it('5. renders the real status and the source run of every candidate', async () => {
    getCandidatePool.mockResolvedValue({
      items: [candidate({ status: 'deferred' }), candidate({ candidate_id: 'NGIQ-DC-00000002', status: 'accepted', run_id: RUN_B })],
      total: 2,
    })
    renderTab()
    const table = within(await screen.findByRole('table'))
    // Raw enum values, plus their localized captions — never a third vocabulary.
    expect(table.getByText('Deferred')).toBeTruthy()
    expect(table.getByText('Accepted')).toBeTruthy()
    expect(table.getByText(RUN_A)).toBeTruthy()
    expect(table.getByText(RUN_B)).toBeTruthy()
  })

  it('says the POOL is empty when the region proposed nothing', async () => {
    getCandidatePool.mockResolvedValue({ items: [], total: 0 })
    renderTab()
    const empty = await screen.findByTestId('kp-candidate-pool-empty')
    expect(empty.textContent).toBe('This BrainRegion has no candidate knowledge yet')
    // An empty pool is not an error and not a filter problem.
    expect(screen.queryByTestId('kp-candidate-pool-error')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('says the FILTER matched nothing when the pool has other kinds', async () => {
    // A pool holding exactly one CIRCUIT, filtered to Connection: the pool is
    // not empty, so the message must be about the filter, not about the region.
    getCandidatePool.mockResolvedValue({ items: [candidate()], total: 1 })
    renderTab()
    await screen.findByRole('table')

    fireEvent.click(screen.getByTestId('kp-candidate-filter-connection'))
    const empty = await screen.findByTestId('kp-candidate-pool-empty')
    expect(empty.textContent).toBe('No candidates match the current filter')
    expect(
      within(screen.getByTestId('kp-candidate-pool-stats')).getByTestId('kp-candidate-count-total')
        .textContent,
    ).toContain('1')
  })

  it('an unreadable pool is an ERROR, never an empty pool', async () => {
    getCandidatePool.mockRejectedValue(new Error('HTTP 500: boom'))
    renderTab()
    const err = await screen.findByTestId('kp-candidate-pool-error')
    expect(err.textContent).toContain('HTTP 500: boom')
    expect(screen.queryByTestId('kp-candidate-pool-empty')).toBeNull()
  })
})

// ===========================================================================
// Closeout — the database is not enabled for candidates.
//
// A deployment without candidate storage is not a failure and not an empty
// pool: it is a feature that is off, and it must be reported as exactly that.
// ===========================================================================
function apiFailure(status: number, code?: string): ApiError {
  return new ApiError(status, `HTTP ${status}: boom`, {
    url: '/api/knowledge-production/brain-regions/x/llm-candidates',
    method: 'GET',
    responseBody: code
      ? { detail: { code, message: 'candidate storage is not enabled' } }
      : { detail: 'boom' },
  })
}

describe('candidate storage not enabled on this database', () => {
  it('says the feature is NOT ENABLED — never that the region has no candidates', async () => {
    getCandidatePool.mockRejectedValue(
      apiFailure(409, 'DISCOVERY_DATABASE_NOT_READY'),
    )
    renderTab()

    const notice = await screen.findByTestId('kp-candidate-storage-not-enabled')
    expect(notice.textContent).toBe(
      'Candidate knowledge is not enabled on the current database',
    )
    // The three things it must NOT be mistaken for. "暂无候选知识" would assert
    // that this region holds nothing — a claim about a table nobody could read.
    expect(screen.queryByTestId('kp-candidate-pool-empty')).toBeNull()
    expect(screen.queryByTestId('kp-candidate-pool-error')).toBeNull()
    expect(screen.queryByRole('table')).toBeNull()
  })

  it('does not offer filters or a count for a pool it never read', async () => {
    getCandidatePool.mockRejectedValue(
      apiFailure(409, 'DISCOVERY_DATABASE_NOT_READY'),
    )
    renderTab()

    await screen.findByTestId('kp-candidate-storage-not-enabled')
    expect(screen.queryByTestId('kp-candidate-filters')).toBeNull()
    expect(screen.queryByTestId('kp-candidate-pool-stats')).toBeNull()
  })

  it('a 503 DATABASE_UNAVAILABLE stays an ERROR — an outage is not a disabled feature', async () => {
    // The exact failure this closeout removed from the read path. If it ever
    // comes back it must be loud: the database IS down, and hiding that behind
    // a quiet "not enabled" line would bury a real incident.
    getCandidatePool.mockRejectedValue(apiFailure(503, 'DATABASE_UNAVAILABLE'))
    renderTab()

    expect(await screen.findByTestId('kp-candidate-pool-error')).toBeTruthy()
    expect(screen.queryByTestId('kp-candidate-storage-not-enabled')).toBeNull()
  })

  it('an unknown code stays an ERROR — only the one known code is a state', async () => {
    getCandidatePool.mockRejectedValue(apiFailure(500, 'SOMETHING_ELSE'))
    renderTab()

    expect(await screen.findByTestId('kp-candidate-pool-error')).toBeTruthy()
    expect(screen.queryByTestId('kp-candidate-storage-not-enabled')).toBeNull()
  })

  it('a failure with no code at all stays an ERROR', async () => {
    getCandidatePool.mockRejectedValue(new Error('Network Error'))
    renderTab()

    expect(await screen.findByTestId('kp-candidate-pool-error')).toBeTruthy()
    expect(screen.queryByTestId('kp-candidate-storage-not-enabled')).toBeNull()
  })
})

// ===========================================================================
// §23.8 + §23.19 — navigation out, and the kinds that have no page yet
// ===========================================================================
describe('candidate navigation', () => {
  it('8. clicking a CIRCUIT row opens its detail page', async () => {
    const { onOpenCircuit } = renderTab()
    await screen.findByRole('table')

    fireEvent.click(within(screen.getByRole('table')).getByText('NGIQ-DC-00000001'))
    expect(onOpenCircuit).toHaveBeenCalledWith('NGIQ-DC-00000001')
  })

  it('does NOT expand a detail underneath the table', async () => {
    renderTab()
    await screen.findByRole('table')
    fireEvent.click(within(screen.getByRole('table')).getByText('NGIQ-DC-00000001'))
    // The detail is a PAGE. Nothing may open in place here.
    expect(screen.queryByTestId('kp-candidate-detail')).toBeNull()
    expect(screen.queryByTestId('kp-circuit-detail')).toBeNull()
  })

  it('names the kinds whose detail page does not exist yet, instead of faking one', async () => {
    const { onOpenCircuit } = renderTab()
    await screen.findByRole('table')

    fireEvent.click(within(screen.getByRole('table')).getByText('NGIQ-DC-00000003'))
    expect(onOpenCircuit).not.toHaveBeenCalled()
    expect((await screen.findByTestId('kp-candidate-no-detail')).textContent).toBe(
      'A Connection detail page arrives in a later phase',
    )

    fireEvent.click(within(screen.getByRole('table')).getByText('NGIQ-DC-00000006'))
    expect((await screen.findByTestId('kp-candidate-no-detail')).textContent).toBe(
      'A Function detail page arrives in a later phase',
    )
  })
})

// ===========================================================================
// §21 — no review action
// ===========================================================================
describe('read-only boundary', () => {
  it('offers no accept / reject / defer control', async () => {
    renderTab()
    await screen.findByRole('table')
    const labels = screen
      .getAllByRole('button')
      .map(b => (b.textContent ?? '').toLowerCase())
    for (const word of ['accept', 'reject', 'defer', '接受', '拒绝', '延后']) {
      expect(labels.some(l => l.includes(word)), word).toBe(false)
    }
    // The controls that DO exist are the five filters.
    expect(labels.filter(l => ['all', 'circuit', 'connection', 'function', 'region'].includes(l)))
      .toHaveLength(5)
  })
})

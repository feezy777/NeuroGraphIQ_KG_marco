/**
 * Phase 3E.2C — Literature Inspector tests (read-only).
 *
 * Two layers:
 *   * the INSPECTOR in isolation — precise control over run/publication/hit
 *     shapes, including the states the empty authority DB cannot produce;
 *   * the DISCOVERY TAB integration — which run rows are selectable and, just
 *     as important, which are NOT.
 *
 * Core invariant under test: EMPTY != ERROR != FAILED != PARTIAL.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import { LiteratureInspector } from './LiteratureInspector'
import {
  LITERATURE_DISCOVERY_TYPES,
  isLiteratureDiscoveryType,
  type DiscoveryRun,
  type LiteratureRun,
  type PublicationListResponse,
} from './types'

const getSeed = vi.fn()
const getRuns = vi.fn()
const getLiteratureRuns = vi.fn()
const getRunPublications = vi.fn()
const getCandidatePool = vi.fn()
const getLlmCandidates = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
  fetchLiteratureRuns: (...a: unknown[]) => getLiteratureRuns(...a),
  fetchRunPublications: (...a: unknown[]) => getRunPublications(...a),
  // P0-4C: the Candidates tab is the live candidate pool.
  fetchBrainRegionLlmCandidates: (...a: unknown[]) => getCandidatePool(...a),
  // P0-4A. An LLM run row is now selectable, so clicking one reaches this. It is
  // mocked to a spy rather than left undefined: the tests below assert that a
  // literature request is NOT made for an LLM run, and an undefined function
  // would make that assertion pass by throwing instead of by not being called.
  fetchRunLlmCandidates: (...a: unknown[]) => getLlmCandidates(...a),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
}))

const RUN_ID = '11111111-2222-3333-4444-555555555555'

function literatureRun(over: Partial<LiteratureRun> = {}): LiteratureRun {
  return {
    run_id: RUN_ID,
    seed_entity_id: 'NGIQ-BR-00000001',
    discovery_type: 'EVIDENCE_SEARCH',
    status: 'COMPLETED',
    outcome: 'CANDIDATES_FOUND',
    provider: 'europepmc',
    created_at: '2026-09-15T10:00:00Z',
    started_at: '2026-09-15T10:00:01Z',
    finished_at: '2026-09-15T10:00:09Z',
    error_code: null,
    error_message: null,
    diagnostics: {
      provider_failures: [],
      partial: false,
      all_providers_failed: false,
      papers_found: 2,
    },
    ...over,
  }
}

function runRow(over: Partial<DiscoveryRun> = {}): DiscoveryRun {
  return {
    run_id: RUN_ID,
    seed_entity_id: 'NGIQ-BR-00000001',
    discovery_type: 'EVIDENCE_SEARCH',
    status: 'COMPLETED',
    outcome: 'CANDIDATES_FOUND',
    provider: null,
    model_name: null,
    prompt_key: null,
    prompt_version: null,
    query_strategy_version: null,
    created_by: null,
    created_at: '2026-09-15T10:00:00Z',
    started_at: null,
    finished_at: null,
    error_code: null,
    error_message: null,
    ...over,
  }
}

const DETAIL = {
  entity_pk: 3,
  entity_id: 'NGIQ-BR-00000001',
  name_en: 'Left Hippocampus',
  name_zh: '左海马',
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

function renderInspector(props: Parameters<typeof LiteratureInspector>[0]) {
  return render(
    <I18nProvider>
      <LiteratureInspector {...props} />
    </I18nProvider>,
  )
}

function renderWorkspace() {
  return render(
    <I18nProvider>
      <BrainRegionWorkspacePage entityId="NGIQ-BR-00000001" />
    </I18nProvider>,
  )
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
    run_id: RUN_ID,
    items: [],
    distinct_publications: 0,
    hits_total: 0,
  })
  // P0-4A: selecting an LLM run now loads its candidates. Kept a resolved spy so
  // that "the literature request was not made" is proved by absence, not by a
  // thrown TypeError from an unmocked import.
  getCandidatePool.mockReset()
  getCandidatePool.mockResolvedValue({ items: [], total: 0 })
  getLlmCandidates.mockReset()
  getLlmCandidates.mockResolvedValue({ items: [], total: 0 })
  window.location.hash = ''
})

// ===========================================================================
// §12.1-5 — vocabulary and run selectability
// ===========================================================================
describe('literature run vocabulary', () => {
  it('1. mirrors all four approved backend discovery routes', () => {
    // The union must be able to REPRESENT every value the backend accepts. A
    // union missing a value cannot be compared against it at all.
    const everyRoute: DiscoveryRun['discovery_type'][] = [
      'LLM_DISCOVERY',
      'LITERATURE_DISCOVERY',
      'EVIDENCE_SEARCH',
      'CITATION_CHAINING',
    ]
    expect(everyRoute).toHaveLength(4)
    expect(LITERATURE_DISCOVERY_TYPES).toEqual([
      'LITERATURE_DISCOVERY',
      'EVIDENCE_SEARCH',
      'CITATION_CHAINING',
    ])
  })

  it('1b. classifies every route explicitly, never by exclusion', () => {
    expect(isLiteratureDiscoveryType('LITERATURE_DISCOVERY')).toBe(true)
    expect(isLiteratureDiscoveryType('EVIDENCE_SEARCH')).toBe(true)
    expect(isLiteratureDiscoveryType('CITATION_CHAINING')).toBe(true)
    expect(isLiteratureDiscoveryType('LLM_DISCOVERY')).toBe(false)
  })

  for (const route of ['LITERATURE_DISCOVERY', 'EVIDENCE_SEARCH', 'CITATION_CHAINING'] as const) {
    it(`${route} is selectable and loads its publications`, async () => {
      getRuns.mockResolvedValue({ items: [runRow({ discovery_type: route })], total: 1 })
      getLiteratureRuns.mockResolvedValue({ items: [literatureRun({ discovery_type: route })], total: 1 })
      renderWorkspace()
      fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
      await waitFor(() => expect(screen.getByTestId('kp-run-history')).toBeTruthy())

      fireEvent.click(runHistoryRow(0))
      await waitFor(() => expect(getRunPublications).toHaveBeenCalledWith(RUN_ID))
      await waitFor(() => expect(screen.getByTestId('kp-literature-summary')).toBeTruthy())
    })
  }

  it('5. LLM_DISCOVERY opens the CANDIDATE panel and triggers NO publications request', async () => {
    // The realistic state: an LLM run exists but the literature list is empty.
    getRuns.mockResolvedValue({ items: [runRow({ discovery_type: 'LLM_DISCOVERY' })], total: 1 })
    getLiteratureRuns.mockResolvedValue({ items: [], total: 0 })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    await waitFor(() => expect(screen.getByTestId('kp-run-history')).toBeTruthy())

    fireEvent.click(runHistoryRow(0))
    await waitFor(() => expect(screen.getByTestId('kp-literature-noruns')).toBeTruthy())
    // The click is not inert — it is routed by the run's ROUTE, to the panel that
    // has a contract for it. That routing is what keeps the literature response
    // below from being reached, rather than the click being swallowed.
    await waitFor(() => expect(getLlmCandidates).toHaveBeenCalledWith(RUN_ID))
    expect(getRunPublications).not.toHaveBeenCalled()
  })

  it('5b. the gate itself holds even when the literature list disagrees', async () => {
    // Adversarial state, built so that the type gate is the ONLY thing between
    // an LLM row and a literature fetch: the literature list wrongly contains
    // the LLM run's id. The backend never returns that — but the UI must not
    // depend on the backend being well-behaved for this boundary to hold.
    getRuns.mockResolvedValue({ items: [runRow({ discovery_type: 'LLM_DISCOVERY' })], total: 1 })
    getLiteratureRuns.mockResolvedValue({
      items: [literatureRun({ discovery_type: 'LLM_DISCOVERY' })],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    await waitFor(() => expect(screen.getByTestId('kp-run-history')).toBeTruthy())
    await waitFor(() => expect(getLiteratureRuns).toHaveBeenCalled())

    fireEvent.click(runHistoryRow(0))
    // The click selected the run, but the run is on the LLM route, so the
    // literature inspector is handed nothing and still asks the user to pick.
    // The gate is the route test at the hand-off, not the row's clickability.
    expect(screen.getByTestId('kp-literature-select-prompt')).toBeTruthy()
    expect(getRunPublications).not.toHaveBeenCalled()
  })
})

/**
 * The Nth DATA row of the run history (row 0 is the header).
 *
 * Clicking the row rather than a cell's text avoids matching the DiscoveryCard
 * titles, which carry the same captions.
 */
function runHistoryRow(index: number): HTMLElement {
  const rows = within(screen.getByTestId('kp-run-history')).getAllByRole('row')
  return rows[index + 1]
}

// ===========================================================================
// §12.6-9 — empty / failed / partial are DIFFERENT facts
// ===========================================================================
describe('empty and failure semantics', () => {
  it('6. a region with zero literature runs shows a clean empty state, not an error', async () => {
    renderInspector({ literatureRuns: [], error: null, selectedRunId: null })
    const box = await screen.findByTestId('kp-literature-noruns')
    expect(box.textContent).toContain('No literature runs yet')
    expect(screen.queryByText(/error/i)).toBeNull()
  })

  it('6b. an UNREADABLE list is rendered as unknown, never as "none"', async () => {
    renderInspector({ literatureRuns: null, error: 'boom', selectedRunId: null })
    expect(await screen.findByTestId('kp-literature-runs-error')).toBeTruthy()
    expect(screen.queryByTestId('kp-literature-noruns')).toBeNull()
  })

  it('7. a completed run with zero publications says exactly that', async () => {
    renderInspector({
      literatureRuns: [literatureRun()],
      error: null,
      selectedRunId: RUN_ID,
    })
    await waitFor(() => expect(screen.getByTestId('kp-literature-no-publications')).toBeTruthy())
    expect(screen.queryByTestId('kp-literature-all-providers-failed')).toBeNull()
  })

  it('8. all_providers_failed is a FAILURE, never "no publications"', async () => {
    getRunPublications.mockResolvedValue({
      run_id: RUN_ID, items: [], distinct_publications: 0, hits_total: 0,
    })
    renderInspector({
      literatureRuns: [
        literatureRun({
          diagnostics: {
            provider_failures: [
              { provider: 'europepmc', status_code: 503, retryable: true,
                message: 'upstream', query_strategy: 'A_general' },
            ],
            partial: false,
            all_providers_failed: true,
            papers_found: 0,
          },
        }),
      ],
      error: null,
      selectedRunId: RUN_ID,
    })
    await waitFor(() =>
      expect(screen.getByTestId('kp-literature-all-providers-failed')).toBeTruthy())
    // The whole point: an outage must NOT be phrased as a zero-result search.
    expect(screen.queryByTestId('kp-literature-no-publications')).toBeNull()
  })

  it('9. partial=true still renders the publications that DID arrive', async () => {
    getRunPublications.mockResolvedValue({
      run_id: RUN_ID,
      items: [
        { entity_id: 'NGIQ-PUB-1', original_title: 'Found anyway', publication_year: 2024,
          pmid: '1', pmcid: null, doi: null, source_database: null, hits: [] },
      ],
      distinct_publications: 1,
      hits_total: 0,
    })
    renderInspector({
      literatureRuns: [
        literatureRun({
          diagnostics: {
            provider_failures: [
              { provider: 'pubmed', status_code: 429, retryable: true, message: 'slow',
                query_strategy: 'loose' },
            ],
            partial: true,
            all_providers_failed: false,
            papers_found: 1,
          },
        }),
      ],
      error: null,
      selectedRunId: RUN_ID,
    })
    await waitFor(() => expect(screen.getByTestId('kp-literature-partial')).toBeTruthy())
    expect(screen.getByText('Found anyway')).toBeTruthy()
    expect(screen.queryByTestId('kp-literature-all-providers-failed')).toBeNull()
  })

  it('8b. all_providers_failed is rendered as a FIELD in both directions', async () => {
    // The contract requires all four diagnostics to be VISIBLE as labelled
    // values. The failure box alone only ever appears when the flag is true, so
    // on its own it can never show the false case.
    renderInspector({
      literatureRuns: [literatureRun({ diagnostics: {
        provider_failures: [], partial: false, all_providers_failed: false, papers_found: 2,
      } })],
      error: null,
      selectedRunId: RUN_ID,
    })
    const field = await screen.findByTestId('kp-literature-all-providers-failed-value')
    expect(field.textContent).toBe('No')
    // false must NOT raise the outage explanation
    expect(screen.queryByTestId('kp-literature-all-providers-failed')).toBeNull()
  })

  it('8c. all_providers_failed=true shows Yes AND keeps the outage explanation', async () => {
    renderInspector({
      literatureRuns: [literatureRun({ diagnostics: {
        provider_failures: [
          { provider: 'pubmed', status_code: 503, retryable: true, message: 'down',
            query_strategy: 'loose' },
        ],
        partial: false, all_providers_failed: true, papers_found: 0,
      } })],
      error: null,
      selectedRunId: RUN_ID,
    })
    const field = await screen.findByTestId('kp-literature-all-providers-failed-value')
    expect(field.textContent).toBe('Yes')
    // value and explanation are separate concerns: both must be present
    expect(screen.getByTestId('kp-literature-all-providers-failed')).toBeTruthy()
  })

  it('9b. a FAILED run shows its error and is not rendered as an empty result', async () => {
    renderInspector({
      literatureRuns: [
        literatureRun({ status: 'FAILED', error_code: 'SEARCH_PROVIDER_ERROR',
                        error_message: 'rate limited' }),
      ],
      error: null,
      selectedRunId: RUN_ID,
    })
    const failed = await screen.findByTestId('kp-literature-run-failed')
    expect(failed.textContent).toContain('SEARCH_PROVIDER_ERROR')
    expect(failed.textContent).toContain('rate limited')
  })
})

// ===========================================================================
// §12.10-12 — hits, both counts, and the bounded failure projection
// ===========================================================================
describe('publications and retrieval hits', () => {
  const threeHits: PublicationListResponse = {
    run_id: RUN_ID,
    items: [
      {
        entity_id: 'NGIQ-PUB-1',
        original_title: 'Found three ways',
        publication_year: 2024,
        pmid: '40000001',
        pmcid: 'PMC1',
        doi: '10.1/x',
        source_database: 'europepmc',
        hits: [
          { query_text: 'query alpha', query_family: 'A_general', query_level: 'NAME',
            source: 'Europe PMC', result_rank: 1, retrieved_at: '2026-09-15T10:00:02Z',
            run_id: RUN_ID },
          { query_text: 'query beta', query_family: 'A_general', query_level: 'NAME',
            source: 'Europe PMC', result_rank: 2, retrieved_at: '2026-09-15T10:00:03Z',
            run_id: RUN_ID },
          { query_text: 'query gamma', query_family: 'D_functional',
            query_level: 'FUNCTION_EXPANSION', source: 'PubMed', result_rank: 1,
            retrieved_at: '2026-09-15T10:00:04Z', run_id: RUN_ID },
        ],
      },
    ],
    distinct_publications: 1,
    hits_total: 3,
  }

  beforeEach(() => {
    getRunPublications.mockResolvedValue(threeHits)
  })

  it('10. one publication found by three queries renders 1 publication and 3 hits', async () => {
    renderInspector({
      literatureRuns: [literatureRun()], error: null, selectedRunId: RUN_ID,
    })
    await waitFor(() =>
      expect(screen.getAllByTestId('kp-literature-publication')).toHaveLength(1))
    // A single publication opens its hits by default (density is unknown until
    // real pilot data exists), so the three retrieval facts are visible.
    const hits = await screen.findByTestId('kp-literature-hits')
    expect(within(hits).getAllByRole('row')).toHaveLength(4) // 1 header + 3 hits
    for (const q of ['query alpha', 'query beta', 'query gamma']) {
      expect(within(hits).getByText(q)).toBeTruthy()
    }
  })

  it('11. distinct_publications and hits_total are BOTH visible and distinct', async () => {
    renderInspector({
      literatureRuns: [literatureRun()], error: null, selectedRunId: RUN_ID,
    })
    await waitFor(() => expect(screen.getByTestId('kp-literature-distinct')).toBeTruthy())
    expect(screen.getByTestId('kp-literature-distinct').textContent).toBe('1')
    expect(screen.getByTestId('kp-literature-hits-total').textContent).toBe('3')
  })

  it('11b. a stale response for a previously selected run cannot replace the current one', async () => {
    // Run A resolves slowly; the user switches to run B, which resolves fast.
    const runB = '22222222-2222-3333-4444-555555555555'
    let resolveA: ((v: PublicationListResponse) => void) | undefined
    getRunPublications.mockImplementation((id: string) =>
      id === RUN_ID
        ? new Promise<PublicationListResponse>(r => { resolveA = r })
        : Promise.resolve({ ...threeHits, run_id: runB }),
    )
    const { rerender } = render(
      <I18nProvider>
        <LiteratureInspector
          literatureRuns={[literatureRun(), literatureRun({ run_id: runB })]}
          error={null}
          selectedRunId={RUN_ID}
        />
      </I18nProvider>,
    )
    // Switch to B while A is still in flight.
    rerender(
      <I18nProvider>
        <LiteratureInspector
          literatureRuns={[literatureRun(), literatureRun({ run_id: runB })]}
          error={null}
          selectedRunId={runB}
        />
      </I18nProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('kp-literature-summary')).toBeTruthy())
    // Now let the superseded request finish: it must be discarded.
    resolveA?.({ ...threeHits, distinct_publications: 99, hits_total: 99 })
    await new Promise(r => setTimeout(r, 0))
    expect(screen.getByTestId('kp-literature-distinct').textContent).toBe('1')
  })

  it('13. LiteratureInspector reaches kpApi and NO provider/search client', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    // Same forbidden concepts as the workspace boundary guard, so the new
    // component cannot become the hole that guard does not cover. Comments are
    // stripped first, matching that guard's convention — prose may legitimately
    // name the things it forbids.
    const forbidden = [
      'llmprovider', 'llm_provider', 'deepseek', 'kimi', 'openai',
      'pubmed', 'europepmc', 'openalex', 'semanticscholar',
      'paper_search', 'paper_search_multi',
    ]
    // Scans the PRODUCTION file only. The test file next to it legitimately
    // carries provider display values (PubMed / Europe PMC) as fixtures.
    const code = readFileSync(join(__dirname, 'LiteratureInspector.tsx'), 'utf8')
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/\/\/[^\n]*/g, '')
      .toLowerCase()

    for (const term of forbidden) {
      expect(code, `LiteratureInspector.tsx must not reference "${term}"`).not.toContain(term)
    }
    // Not merely "says nothing bad": it must go THROUGH the read API. Absence
    // alone would also pass for a component that fetched nothing at all.
    expect(code).toContain("from './kpapi'")
  })

  it('12. a failure entry cannot leak internal payloads: only bounded fields render', async () => {
    renderInspector({
      literatureRuns: [
        literatureRun({
          diagnostics: {
            provider_failures: [
              {
                provider: 'pubmed',
                status_code: 500,
                retryable: false,
                message: 'upstream',
                query_strategy: 'loose',
                // A future writer may put anything in the jsonb column. The
                // bounded DTO cannot carry it, so it cannot reach the DOM.
                internal_payload: { api_key: 'must-not-leak' },
              } as never,
            ],
            partial: false,
            all_providers_failed: false,
            papers_found: 0,
          },
        }),
      ],
      error: null,
      selectedRunId: RUN_ID,
    })
    const table = await screen.findByTestId('kp-literature-provider-failures')
    expect(table.textContent).toContain('pubmed')
    expect(table.textContent).toContain('upstream')
    expect(document.body.textContent).not.toContain('must-not-leak')
  })
})

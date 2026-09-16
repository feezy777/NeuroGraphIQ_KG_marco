/**
 * BrainRegion Workspace tests (Phase 1B, extended in Phase 2A).
 *
 * One canonical BrainRegion is the operational root. Seven top-level tabs; the
 * candidate subtypes live INSIDE Candidates, not at the same level as
 * Discovery/Validation. Discovery steps are never active: Phase 2A records runs,
 * it does not execute them.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { ApiError } from '../../api/client'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import type { BrainRegionSeedDetail, DiscoveryRun } from './types'

const getSeed = vi.fn()
const getRuns = vi.fn()
const getLiteratureRuns = vi.fn()
const getRunPublications = vi.fn()
const getCandidatePool = vi.fn()
const getLlmCandidates = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...args: unknown[]) => getSeed(...args),
  fetchDiscoveryRuns: (...args: unknown[]) => getRuns(...args),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
  fetchLiteratureRuns: (...args: unknown[]) => getLiteratureRuns(...args),
  fetchRunPublications: (...args: unknown[]) => getRunPublications(...args),
  // P0-4A. Present so a future test that selects an LLM run fails on its own
  // assertion rather than on an undefined import.
  fetchRunLlmCandidates: (...args: unknown[]) => getLlmCandidates(...args),
  // P0-4C. The Candidates tab is now the live candidate pool.
  fetchBrainRegionLlmCandidates: (...args: unknown[]) => getCandidatePool(...args),
}))

/** One persisted Discovery Run row, as the Phase 2A API returns it. */
function run(over: Partial<DiscoveryRun> = {}): DiscoveryRun {
  return {
    run_id: '11111111-2222-3333-4444-555555555555',
    seed_entity_id: 'NGIQ-BR-00000001',
    discovery_type: 'LLM_DISCOVERY',
    status: 'QUEUED',
    outcome: null,
    provider: null,
    model_name: null,
    prompt_key: null,
    prompt_version: null,
    query_strategy_version: null,
    created_by: null,
    created_at: '2026-09-14T10:00:00Z',
    started_at: null,
    finished_at: null,
    error_code: null,
    error_message: null,
    ...over,
  }
}

const DETAIL: BrainRegionSeedDetail = {
  entity_pk: 3,
  entity_id: 'NGIQ-BR-00000001',
  name_en: 'Left Superior frontal gyrus, Brainnetome 7_1',
  name_zh: '左侧额上回',
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
  external_region_ids: ['NGIQ-XREG-00000001'],
  mapping_types: ['exact'],
  mapping_review_statuses: ['approved'],
}

function renderWorkspace(entityId = 'NGIQ-BR-00000001') {
  return render(
    <I18nProvider>
      <BrainRegionWorkspacePage entityId={entityId} />
    </I18nProvider>,
  )
}

beforeEach(() => {
  // Assertions here were written against the English UI; the zh-CN labels are
  // covered in i18nKnowledgeProduction.test.tsx.
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en-US')
  getSeed.mockReset()
  getSeed.mockResolvedValue(DETAIL)
  getRuns.mockReset()
  // Default: a real BrainRegion with no runs yet (accepted Phase 2A state).
  getRuns.mockResolvedValue({ items: [], total: 0 })
  getLiteratureRuns.mockReset()
  // Default: no literature runs — the accepted authority state today.
  getLiteratureRuns.mockResolvedValue({ items: [], total: 0 })
  getRunPublications.mockReset()
  getRunPublications.mockResolvedValue({
    run_id: 'x',
    items: [],
    distinct_publications: 0,
    hits_total: 0,
  })
  getCandidatePool.mockReset()
  getCandidatePool.mockResolvedValue({ items: [], total: 0 })
  getLlmCandidates.mockReset()
  getLlmCandidates.mockResolvedValue({ items: [], total: 0 })
  window.location.hash = ''
})

describe('BrainRegionWorkspacePage', () => {
  it('loads the BrainRegion detail for the routed entity_id', async () => {
    renderWorkspace()
    await waitFor(() => expect(getSeed).toHaveBeenCalledWith('NGIQ-BR-00000001'))
    expect(screen.getByTestId('brain-region-workspace')).toBeTruthy()
  })

  it('renders the identity header with real API fields only', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-ws-name')).toBeTruthy())
    expect(screen.getByTestId('kp-ws-name').textContent).toBe(DETAIL.name_en)
    expect(screen.getByTestId('kp-ws-entity-id').textContent).toBe('NGIQ-BR-00000001')
    const chips = within(screen.getByTestId('kp-ws-chips'))
    expect(chips.getByText('G3_MESO_FINE')).toBeTruthy()
    expect(chips.getByText('left')).toBeTruthy()
    expect(chips.getByText('Human (NCBI:9606)')).toBeTruthy()
    expect(chips.getByText('Human Brainnetome Atlas')).toBeTruthy()
  })

  it('shows production summary placeholders without fabricating zeros', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-workspace-summary')).toBeTruthy())
    // Discovery settles to "Not initialized" once the run history is known.
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain(
        'Not initialized',
      ),
    )
    // Candidates is now a MEASURED count (the pool API is mocked to 0 here), so
    // 0 is a fact, not a fabrication. Evidence and review have no read API yet
    // and must stay unknown — an em dash, never a zero.
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-candidates').textContent).toContain('0'),
    )
    for (const k of ['evidence', 'review']) {
      expect(screen.getByTestId(`kp-ws-summary-${k}`).textContent).toContain('—')
      expect(screen.getByTestId(`kp-ws-summary-${k}`).textContent).not.toContain('0')
    }
  })

  it('shows — for the candidate count while the pool is unreadable', async () => {
    getCandidatePool.mockRejectedValue(new Error('503 unavailable'))
    renderWorkspace()
    const card = await screen.findByTestId('kp-ws-summary-candidates')
    // An unreadable pool is UNKNOWN, not empty: a zero here would claim this
    // region has no candidate knowledge.
    await waitFor(() => expect(card.textContent).toContain('—'))
    expect(card.textContent).not.toContain('0')
  })

  // ---- Closeout: the unknown count has a stated cause when it has one ----
  it('names the reason when this database has no candidate storage', async () => {
    getCandidatePool.mockRejectedValue(
      new ApiError(409, 'HTTP 409: boom', {
        url: '/x/llm-candidates',
        method: 'GET',
        responseBody: {
          detail: { code: 'DISCOVERY_DATABASE_NOT_READY', message: 'not enabled' },
        },
      }),
    )
    renderWorkspace()

    const card = await screen.findByTestId('kp-ws-summary-candidates')
    // Still —, because nothing was measured...
    await waitFor(() => expect(card.textContent).toContain('—'))
    expect(card.textContent).not.toContain('0')
    // ...and now the dash explains itself instead of leaving a bare em dash.
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-candidates-note').textContent).toBe(
        'Candidate knowledge storage is not enabled on the current database',
      ),
    )
  })

  it('leaves the dash UNEXPLAINED for any other failure', async () => {
    // A 503 is an outage, not a deployment choice. Guessing "not enabled" here
    // would be an invented cause, so the dash stays bare.
    getCandidatePool.mockRejectedValue(
      new ApiError(503, 'HTTP 503: boom', {
        url: '/x/llm-candidates',
        method: 'GET',
        responseBody: { detail: { code: 'DATABASE_UNAVAILABLE', message: 'down' } },
      }),
    )
    renderWorkspace()

    const card = await screen.findByTestId('kp-ws-summary-candidates')
    await waitFor(() => expect(card.textContent).toContain('—'))
    expect(screen.queryByTestId('kp-ws-summary-candidates-note')).toBeNull()
  })

  it('shows the pool count the API reports, not a count derived from runs', async () => {
    getRuns.mockResolvedValue({ items: [run({ status: 'COMPLETED' })], total: 1 })
    getCandidatePool.mockResolvedValue({ items: [], total: 68 })
    renderWorkspace()
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-candidates').textContent).toContain('68'),
    )
  })

  // ---- Phase 2A: Discovery summary card is driven by persisted runs ----
  it('shows — for Discovery while the run history is still unknown', async () => {
    let resolveRuns: (v: unknown) => void = () => {}
    getRuns.mockReturnValue(new Promise(r => (resolveRuns = r)))
    renderWorkspace()
    const card = await screen.findByTestId('kp-ws-summary-discovery')
    // Claiming "Not initialized" before the answer arrives would be a
    // fabricated fact, so the unknown state renders as —.
    expect(card.textContent).toContain('—')
    expect(card.textContent).not.toContain('Not initialized')
    resolveRuns({ items: [], total: 0 })
  })

  it.each([
    ['QUEUED', 'Queued'],
    ['RUNNING', 'Running'],
    ['COMPLETED', 'Completed'],
    ['FAILED', 'Failed'],
    ['CANCELLED', 'Cancelled'],
  ] as const)('shows the latest run status %s as "%s"', async (status, label) => {
    getRuns.mockResolvedValue({ items: [run({ status })], total: 1 })
    renderWorkspace()
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain(label),
    )
    expect(screen.getByTestId('kp-ws-summary-discovery').textContent).not.toContain(
      'Not initialized',
    )
  })

  it('does not derive candidate or evidence counts from runs', async () => {
    getRuns.mockResolvedValue({
      items: [run({ status: 'COMPLETED', outcome: 'CANDIDATES_FOUND' })],
      total: 7,
    })
    // The pool is armed to FAIL before render: a run that reported CANDIDATES_FOUND
    // is not a count, so the card must stay unknown rather than infer 7 or 0.
    getCandidatePool.mockRejectedValue(new Error('unavailable'))
    renderWorkspace()
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain('Completed'),
    )
    await waitFor(() => expect(getCandidatePool).toHaveBeenCalled())
    for (const k of ['candidates', 'evidence', 'review']) {
      expect(screen.getByTestId(`kp-ws-summary-${k}`).textContent).toContain('—')
    }
  })

  // ---- Phase 2A: Discovery tab ----
  it('shows an intentional empty state when no runs exist', async () => {
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const panel = within(screen.getByTestId('kp-discovery-tab'))
    expect(panel.getByText('No Discovery Runs yet')).toBeTruthy()
    expect(
      panel.getByText(/This BrainRegion has not entered a discovery run/),
    ).toBeTruthy()
    expect(screen.queryByTestId('kp-run-history')).toBeNull()
  })

  it('shows an error state when the run history cannot be read', async () => {
    getRuns.mockRejectedValue(new Error('503 unavailable'))
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    expect(await screen.findByTestId('kp-discovery-error')).toBeTruthy()
    expect(screen.queryByTestId('kp-run-history')).toBeNull()
  })

  it('renders the run history with type, status, outcome, provider/model and timestamps', async () => {
    getRuns.mockResolvedValue({
      items: [
        run({
          discovery_type: 'LLM_DISCOVERY',
          status: 'COMPLETED',
          outcome: 'CANDIDATES_FOUND',
          provider: 'deepseek',
          model_name: 'deepseek-v4-pro',
          created_at: '2026-09-14T10:00:00Z',
          started_at: '2026-09-14T10:01:00Z',
          finished_at: '2026-09-14T10:04:00Z',
        }),
      ],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const history = within(await screen.findByTestId('kp-run-history'))
    for (const header of ['Type', 'Status', 'Outcome', 'Provider / Model', 'Created', 'Started', 'Finished']) {
      expect(history.getByText(header)).toBeTruthy()
    }
    expect(history.getByText('LLM Discovery')).toBeTruthy()
    expect(history.getByText('Completed')).toBeTruthy()
    expect(history.getByText('Candidates found')).toBeTruthy()
    expect(history.getByText('deepseek · deepseek-v4-pro')).toBeTruthy()
    // every timestamp renders as YYYY-MM-DD HH:mm, not a raw ISO string
    expect(history.getAllByText(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/)).toHaveLength(3)
  })

  it('handles a literature run that has no provider/model cleanly', async () => {
    getRuns.mockResolvedValue({
      items: [
        run({
          discovery_type: 'LITERATURE_DISCOVERY',
          status: 'COMPLETED',
          outcome: 'NO_EVIDENCE_FOUND',
          query_strategy_version: 'v1',
          created_at: '2026-09-14T10:00:00Z',
          started_at: null,
          finished_at: null,
        }),
      ],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const history = within(await screen.findByTestId('kp-run-history'))
    expect(history.getByText('Literature Discovery')).toBeTruthy()
    expect(history.queryByText(/null/)).toBeNull()
    // status != outcome: finished, and "no evidence" is a real answer
    expect(history.getByText('No evidence found')).toBeTruthy()
    // provider/model is absent for this route -> em dash, never blank or "null";
    // started/finished and the prompt are also unset on this row. The run id is
    // always present, so it is NOT one of the dashes.
    //
    // FIVE, not four: the discovery view is a second thing this route has none
    // of. The four views are LLM-discovery questions, so a literature run shows
    // — there rather than a strategy label that would not apply to it. (Its
    // `query_strategy_version` is `v1`, a literature strategy — not a view, and
    // deliberately NOT rendered as one.)
    expect(history.getAllByText('—')).toHaveLength(5)
    // The run id IS present (as its 8-char prefix), so it is not one of them.
    expect(history.getByText('11111111')).toBeTruthy()
  })

  it('shows the DISCOVERY VIEW of a run, not its internal identifier', async () => {
    // Verbatim from the live CA3 Pass A run (8cd2e18a-…).
    getRuns.mockResolvedValue({
      items: [run({ status: 'COMPLETED', outcome: 'CANDIDATES_FOUND',
                    query_strategy_version: 'G4HR1/NAMED_CLASSIC_CIRCUITS' })],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const history = within(await screen.findByTestId('kp-run-history'))
    // The user-facing label leads...
    expect(history.getByText('Named / classic circuits')).toBeTruthy()
    // ...and the machine token is NOT the primary text; it is available on
    // hover instead, so it never competes with the label.
    expect(history.queryByText(/G4HR1\/NAMED_CLASSIC_CIRCUITS/)).toBeNull()
    const cell = document.querySelector('[data-testid^="kp-run-view-"]') as HTMLElement
    expect(cell.getAttribute('title')).toBe('G4HR1/NAMED_CLASSIC_CIRCUITS')
  })

  it('shows GENERAL DISCOVERY for a legacy run, never a G4 view', async () => {
    getRuns.mockResolvedValue({
      items: [run({ status: 'COMPLETED', outcome: 'CANDIDATES_FOUND',
                    query_strategy_version: null })],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const history = within(await screen.findByTestId('kp-run-history'))
    expect(history.getByText('General discovery')).toBeTruthy()
    for (const view of ['Named / classic circuits', 'Local intrinsic circuits',
                        'Afferent circuits', 'Efferent circuits']) {
      expect(history.queryByText(view)).toBeNull()
    }
  })

  it('counts high-recall progress from persisted runs, and invents nothing', async () => {
    getRuns.mockResolvedValue({
      items: [
        run({ status: 'COMPLETED', query_strategy_version: 'G4HR1/NAMED_CLASSIC_CIRCUITS' }),
        run({ run_id: '22222222-3333-4444-5555-666666666666', status: 'COMPLETED',
              query_strategy_version: 'G4HR1/AFFERENT_CIRCUITS' }),
      ],
      total: 2,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    // 2 of the 4 views have runs — a COUNT of runs, not a modelled percentage.
    expect((await screen.findByTestId('kp-high-recall-count')).textContent)
      .toContain('2 / 4')
    expect(screen.queryByText(/50%|% complete/)).toBeNull()
  })

  it('shows NO progress card when no view run exists', async () => {
    getRuns.mockResolvedValue({
      items: [run({ status: 'COMPLETED', query_strategy_version: null })],
      total: 1,
    })
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    await screen.findByTestId('kp-run-history')
    // A seed with no view run is not a pilot at 0% — it is not a pilot.
    expect(screen.queryByTestId('kp-high-recall-progress')).toBeNull()
  })

  it('never queries runs with a candidate, mirror or final identifier', async () => {
    getRuns.mockResolvedValue({ items: [], total: 0 })
    renderWorkspace()
    await waitFor(() => expect(getRuns).toHaveBeenCalled())
    const arg = String(getRuns.mock.calls[0][0])
    expect(arg).toBe('NGIQ-BR-00000001')
    expect(arg).not.toMatch(/candidate|mirror|final/i)
  })

  it('has exactly the seven top-level workspace tabs', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-tabs')).toBeTruthy())
    const ids = [
      'overview',
      'discovery',
      'candidates',
      'evidence',
      'canonicalization',
      'validation',
      'history',
    ]
    for (const id of ids) expect(screen.getByTestId(`kp-tab-${id}`)).toBeTruthy()
    expect(screen.getByTestId('kp-tabs').querySelectorAll('[role="tab"]')).toHaveLength(7)
  })

  it('does NOT promote Circuits / Connections / Functions to top-level tabs', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-tabs')).toBeTruthy())
    for (const id of ['circuits', 'connections', 'functions']) {
      expect(screen.queryByTestId(`kp-tab-${id}`)).toBeNull()
    }
    // P0-4C: they are candidate KINDS, so they are filters inside Candidates —
    // the tab itself is now the BrainRegion's candidate pool, not a placeholder.
    fireEvent.click(screen.getByTestId('kp-tab-candidates'))
    const panel = within(await screen.findByTestId('kp-candidate-filters'))
    // Singular labels: one candidate IS a Circuit / Connection / Function / Region.
    for (const label of ['Circuit', 'Connection', 'Function', 'Region']) {
      expect(panel.getByText(label)).toBeTruthy()
    }
    expect(panel.getByText('All')).toBeTruthy()
  })

  it('shows the four high-level workflow steps with none active', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-workflow-steps')).toBeTruthy())
    for (const id of ['discover', 'canonicalize', 'validate', 'promote']) {
      expect(screen.getByTestId(`kp-step-${id}`).getAttribute('data-state')).toBe('pending')
    }
    // selection is not a workflow step inside the workspace
    expect(screen.queryByTestId('kp-step-select-region')).toBeNull()
    // nothing is running
    expect(
      screen.getByTestId('kp-workflow-steps').querySelectorAll('[aria-current="step"]'),
    ).toHaveLength(0)
  })

  it('keeps Literature disabled while LLM Discovery is a live action (P0-4B)', async () => {
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    // P0-4B wired ONE execution channel. Literature has no execution path yet,
    // so it stays disabled and keeps its explanation.
    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', false)
    expect(screen.getByTestId('kp-literature-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-literature-discovery').getAttribute('title')).toBeTruthy()
  })

  it('renders a read-only placeholder on every non-overview tab', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-overview')).toBeTruthy())
    for (const id of ['evidence', 'canonicalization', 'validation', 'history']) {
      fireEvent.click(screen.getByTestId(`kp-tab-${id}`))
      expect(screen.getByTestId(`kp-${id}-tab`)).toBeTruthy()
    }
  })

  it('groups Overview fields into labelled sections', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-overview')).toBeTruthy())
    const ov = within(screen.getByTestId('kp-overview'))
    for (const s of ['Identity', 'Anatomy', 'Source / Mapping', 'Governance']) {
      expect(ov.getByText(s)).toBeTruthy()
    }
    // hierarchy_depth is 0 — an authoritative value, so the section IS shown
    expect(ov.getByText('Hierarchy')).toBeTruthy()
    expect(ov.getByText('hierarchy depth')).toBeTruthy()
    expect(ov.getByText('NGIQ-XREG-00000001')).toBeTruthy()
  })

  it('SHOWS a section with nothing recorded, with — and a reason', async () => {
    // Phase 1B hid an all-empty section; this phase reverses that deliberately.
    // An inspection surface must be able to answer "where is it in the hierarchy"
    // — a section that vanishes cannot be told apart from a broken page.
    getSeed.mockResolvedValue({
      ...DETAIL,
      parent_region_pk: null,
      hierarchy_depth: null,
      atlas_names: [],
      external_region_ids: [],
      mapping_types: [],
      mapping_review_statuses: [],
    })
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-overview')).toBeTruthy())
    const ov = within(screen.getByTestId('kp-overview'))

    const hierarchy = within(ov.getByText('Hierarchy').closest('section')!)
    expect(hierarchy.getByText('parent region')).toBeTruthy()
    expect(hierarchy.getByText('hierarchy depth')).toBeTruthy()
    // Every unrecorded value answers with an em dash, never a blank or "null".
    expect(hierarchy.getAllByText('—')).toHaveLength(2)
    expect(
      hierarchy.getByText('No parent region or hierarchy depth is recorded for this BrainRegion.'),
    ).toBeTruthy()

    const mapping = within(ov.getByText('Source / Mapping').closest('section')!)
    expect(mapping.getAllByText('—')).toHaveLength(4)
    expect(
      mapping.getByText(/No source Atlas, external mapping or mapping review status/),
    ).toBeTruthy()

    // …and the sections that DO have data are untouched by this.
    expect(ov.getByText('Identity')).toBeTruthy()
  })

  it('navigates back to the Production Index', async () => {
    renderWorkspace()
    await waitFor(() => expect(screen.getByTestId('kp-back-to-index')).toBeTruthy())
    fireEvent.click(screen.getByTestId('kp-back-to-index'))
    await waitFor(() => expect(window.location.hash).toBe('#/knowledge-production'))
  })

  it('shows an error state when the BrainRegion cannot be loaded', async () => {
    getSeed.mockRejectedValue(new Error('404 not found'))
    renderWorkspace('NGIQ-BR-99999999')
    await waitFor(() => expect(screen.getByTestId('kp-workspace-error')).toBeTruthy())
    expect(screen.getByText('404 not found')).toBeTruthy()
  })

  it('uses no legacy terminology in the workspace sources', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    const forbidden = ['candidate_id', 'mirror', 'final_kg', 'finalkg', 'ranking_id', 'task_type']
    for (const f of [
      'BrainRegionWorkspacePage.tsx',
      'workspaceTabs.tsx',
      'routes.ts',
      // Phase 2A additions
      'types.ts',
      'kpApi.ts',
    ]) {
      const code = readFileSync(join(__dirname, f), 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/[^\n]*/g, '')
        .toLowerCase()
      for (const term of forbidden) {
        expect(code, `${f} must not reference "${term}"`).not.toContain(term)
      }
    }
  })

  it('does not execute discovery: no provider or literature-search coupling', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    // Phase 2A is persistence/read only. Nothing on this path may reach an LLM
    // provider or a paper-search client.
    const forbidden = [
      'llmprovider',
      'llm_provider',
      'deepseek',
      'kimi',
      'openai',
      'pubmed',
      'europepmc',
      'openalex',
      'semanticscholar',
      'paper_search',
      'paper_search_multi',
    ]
    for (const f of [
      'BrainRegionWorkspacePage.tsx',
      'workspaceTabs.tsx',
      'kpApi.ts',
      'types.ts',
      'routes.ts',
    ]) {
      const code = readFileSync(join(__dirname, f), 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/[^\n]*/g, '')
        .toLowerCase()
      for (const term of forbidden) {
        expect(code, `${f} must not reference "${term}"`).not.toContain(term)
      }
    }
  })
})

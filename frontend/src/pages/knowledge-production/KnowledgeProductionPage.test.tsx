import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { KnowledgeProductionPage } from './KnowledgeProductionPage'
import type { BrainRegionSeed, BrainRegionSeedDetail } from './types'

const listSeeds = vi.fn()
const getSeed = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeeds: (...args: unknown[]) => listSeeds(...args),
  fetchBrainRegionSeed: (...args: unknown[]) => getSeed(...args),
}))

const SEED: BrainRegionSeed = {
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
}

const DETAIL: BrainRegionSeedDetail = {
  ...SEED,
  definition_en: null,
  parent_region_pk: null,
  hierarchy_depth: 0,
  external_region_ids: ['NGIQ-XREG-00000001'],
  mapping_types: ['exact'],
  mapping_review_statuses: ['approved'],
}

function renderPage() {
  return render(
    <I18nProvider>
      <KnowledgeProductionPage />
    </I18nProvider>,
  )
}

beforeEach(() => {
  listSeeds.mockReset()
  getSeed.mockReset()
  listSeeds.mockResolvedValue({ items: [SEED], total: 770 })
  getSeed.mockResolvedValue(DETAIL)
})

describe('KnowledgeProductionPage', () => {
  it('renders the page shell', async () => {
    renderPage()
    expect(screen.getByTestId('knowledge-production-page')).toBeTruthy()
    // with no seed selected the workspace shows the prompt, not the overview
    await waitFor(() => expect(screen.getByTestId('kp-no-selection')).toBeTruthy())
  })

  it('exposes the G1-G4 granularity filter', () => {
    renderPage()
    for (const label of ['G1', 'G2', 'G3', 'G4']) {
      expect(screen.getByTestId(`kp-gran-${label}`)).toBeTruthy()
    }
  })

  it('requests the selected granularity from the server', async () => {
    renderPage()
    await waitFor(() => expect(listSeeds).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('kp-gran-G1'))
    await waitFor(() =>
      expect(listSeeds).toHaveBeenLastCalledWith(
        expect.objectContaining({ granularityLevel: 'G1_MACRO', offset: 0 }),
      ),
    )
  })

  it('renders the loading state while the list is in flight', () => {
    listSeeds.mockReturnValue(new Promise(() => {}))
    renderPage()
    expect(screen.getByTestId('kp-seed-pane')).toBeTruthy()
    expect(document.querySelector('.state-box')).toBeTruthy()
  })

  it('renders the empty state when no region matches', async () => {
    listSeeds.mockResolvedValue({ items: [], total: 0 })
    renderPage()
    await waitFor(() => expect(screen.getByText('没有匹配的脑区')).toBeTruthy())
  })

  it('renders the error state when the request fails', async () => {
    listSeeds.mockRejectedValue(new Error('boom'))
    renderPage()
    await waitFor(() => expect(screen.getByText('boom')).toBeTruthy())
  })

  it('selecting a BrainRegion updates the workspace overview', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())
    expect(screen.getByTestId('kp-no-selection')).toBeTruthy()

    fireEvent.click(screen.getByText(SEED.name_en!))

    await waitFor(() => expect(getSeed).toHaveBeenCalledWith('NGIQ-BR-00000001'))
    await waitFor(() => expect(screen.getByTestId('kp-overview')).toBeTruthy())
    const overview = within(screen.getByTestId('kp-overview'))
    expect(overview.getByText('NGIQ-BR-00000001')).toBeTruthy()
    expect(overview.getByText('Human Brainnetome Atlas')).toBeTruthy()
    expect(overview.getByText('NGIQ-XREG-00000001')).toBeTruthy()
    expect(overview.getByText('exact')).toBeTruthy()
  })

  it('has exactly the seven workspace tabs', () => {
    renderPage()
    const ids = [
      'overview',
      'circuits',
      'connections',
      'functions',
      'evidence',
      'canonicalization',
      'validation',
    ]
    for (const id of ids) expect(screen.getByTestId(`kp-tab-${id}`)).toBeTruthy()
    expect(screen.getByTestId('kp-tabs').querySelectorAll('[role="tab"]')).toHaveLength(7)
  })

  it('shows a read-only empty state on every non-overview tab', async () => {
    renderPage()
    await waitFor(() => expect(listSeeds).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('kp-tab-circuits'))
    expect(screen.getByTestId('kp-empty-circuits')).toBeTruthy()
    expect(screen.getByText('Phase 1 未实现发现功能。')).toBeTruthy()
  })

  it('keeps both Discovery actions disabled', () => {
    renderPage()
    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-literature-discovery')).toHaveProperty('disabled', true)
  })

  it('shows Select Region as active before any seed is selected', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('kp-step-select-region')).toBeTruthy())
    expect(screen.getByTestId('kp-step-select-region').getAttribute('data-state')).toBe('active')
    for (const id of ['discover', 'canonicalize', 'validate', 'promote']) {
      expect(screen.getByTestId(`kp-step-${id}`).getAttribute('data-state')).toBe('pending')
    }
  })

  it('completes Select Region on selection and never activates Discover (Phase 1)', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())

    fireEvent.click(screen.getByText(SEED.name_en!))
    await waitFor(() => expect(getSeed).toHaveBeenCalledWith('NGIQ-BR-00000001'))

    // step 1 becomes completed, not active
    expect(screen.getByTestId('kp-step-select-region').getAttribute('data-state')).toBe('done')
    // Discovery is NOT implemented, so no step may be running
    expect(screen.getByTestId('kp-step-discover').getAttribute('data-state')).not.toBe('active')
    for (const id of ['discover', 'canonicalize', 'validate', 'promote']) {
      expect(screen.getByTestId(`kp-step-${id}`).getAttribute('data-state')).toBe('pending')
    }
    // no step is marked as the running step
    expect(
      screen.getByTestId('kp-workflow-steps').querySelectorAll('[aria-current="step"]'),
    ).toHaveLength(0)
  })

  it('keeps both Discovery actions disabled after a seed is selected', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())

    fireEvent.click(screen.getByText(SEED.name_en!))
    await waitFor(() => expect(getSeed).toHaveBeenCalled())

    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-literature-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-discovery-state').textContent).toContain('未初始化')
  })

  it('uses no legacy terminology in the page sources', () => {
    const dir = join(__dirname)
    const files = [
      'KnowledgeProductionPage.tsx',
      'BrainRegionSeedList.tsx',
      'WorkflowSteps.tsx',
      'types.ts',
      'kpApi.ts',
    ]
    const forbidden = ['candidate_id', 'mirror', 'final_kg', 'finalkg', 'final-browser', 'task_type']
    for (const f of files) {
      // strip comments: a docstring saying "we do not depend on X" is legitimate
      const code = readFileSync(join(dir, f), 'utf8')
        .replace(/\/\*[\s\S]*?\*\//g, '')
        .replace(/\/\/[^\n]*/g, '')
        .toLowerCase()
      for (const term of forbidden) {
        expect(code, `${f} must not reference "${term}"`).not.toContain(term)
      }
    }
  })
})

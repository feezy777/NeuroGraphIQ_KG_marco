/**
 * Production Index tests (Phase 1B).
 *
 * The index browses and ENTERS a BrainRegion; it must not host the production
 * workflow (that moved to the workspace route).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY } from '../../i18n'
import { KnowledgeProductionPage } from './KnowledgeProductionPage'
import type { BrainRegionSeed } from './types'

const listSeeds = vi.fn()
const fetchSummary = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeeds: (...args: unknown[]) => listSeeds(...args),
  fetchBrainRegionSummary: (...args: unknown[]) => fetchSummary(...args),
  fetchBrainRegionSeed: vi.fn(),
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

function renderIndex() {
  return render(
    <I18nProvider>
      <KnowledgeProductionPage />
    </I18nProvider>,
  )
}

beforeEach(() => {
  // These assertions were written against the English UI. Language is a
  // presentation concern, so the suite pins en-US and the zh-CN labels are
  // covered separately in i18nKnowledgeProduction.test.tsx.
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en-US')
  listSeeds.mockReset()
  fetchSummary.mockReset()
  listSeeds.mockResolvedValue({ items: [SEED], total: 770 })
  fetchSummary.mockResolvedValue({
    total: 770,
    by_granularity: {
      G1_MACRO: 84,
      G2_MESO_ANATOMICAL: 0,
      G3_MESO_FINE: 246,
      G4_MICROSTRUCTURAL_FINE: 440,
    },
  })
  window.location.hash = ''
})

describe('KnowledgeProductionPage (Production Index)', () => {
  it('renders the BrainRegion index', async () => {
    renderIndex()
    expect(screen.getByTestId('knowledge-production-page')).toBeTruthy()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())
  })

  it('shows the summary cards from one aggregate request', async () => {
    renderIndex()
    await waitFor(() => expect(screen.getByTestId('kp-summary-total')).toBeTruthy())
    expect(screen.getByTestId('kp-summary-total').textContent).toContain('770')
    expect(screen.getByTestId('kp-summary-G1_MACRO').textContent).toContain('84')
    expect(screen.getByTestId('kp-summary-G2_MESO_ANATOMICAL').textContent).toContain('0')
    expect(screen.getByTestId('kp-summary-G4_MICROSTRUCTURAL_FINE').textContent).toContain('440')
    expect(fetchSummary).toHaveBeenCalledTimes(1)
  })

  it('exposes the G1-G4 granularity filter and requests the selection', async () => {
    renderIndex()
    for (const label of ['G1', 'G2', 'G3', 'G4']) {
      expect(screen.getByTestId(`kp-gran-${label}`)).toBeTruthy()
    }
    await waitFor(() => expect(listSeeds).toHaveBeenCalled())
    fireEvent.click(screen.getByTestId('kp-gran-G1'))
    await waitFor(() =>
      expect(listSeeds).toHaveBeenLastCalledWith(
        expect.objectContaining({ granularityLevel: 'G1_MACRO', offset: 0 }),
      ),
    )
  })

  it('keeps search working', async () => {
    renderIndex()
    await waitFor(() => expect(listSeeds).toHaveBeenCalled())
    fireEvent.change(screen.getByTestId('kp-search-input'), { target: { value: 'Thalamus' } })
    fireEvent.click(screen.getByTestId('kp-apply'))
    await waitFor(() =>
      expect(listSeeds).toHaveBeenLastCalledWith(
        expect.objectContaining({ search: 'Thalamus', offset: 0 }),
      ),
    )
  })

  it('uses server-side pagination (limit/offset, never all rows)', async () => {
    renderIndex()
    await waitFor(() => expect(listSeeds).toHaveBeenCalled())
    expect(listSeeds).toHaveBeenLastCalledWith(expect.objectContaining({ limit: 50, offset: 0 }))
    fireEvent.click(screen.getByRole('button', { name: '下一页' }))
    await waitFor(() =>
      expect(listSeeds).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 50 })),
    )
  })

  it('does NOT host the production workspace any more', async () => {
    renderIndex()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())
    // the old split-view workspace and its entity tabs are gone from the index
    expect(screen.queryByTestId('kp-workspace')).toBeNull()
    for (const id of [
      'circuits',
      'connections',
      'functions',
      'evidence',
      'canonicalization',
      'validation',
    ]) {
      expect(screen.queryByTestId(`kp-tab-${id}`)).toBeNull()
    }
    // and no drawer is opened on selection
    expect(screen.queryByTestId('kp-overview')).toBeNull()
  })

  it('navigates to the BrainRegion workspace route on row click', async () => {
    renderIndex()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())
    fireEvent.click(screen.getByText(SEED.name_en!))
    await waitFor(() =>
      expect(window.location.hash).toBe('#/knowledge-production/brain-regions/NGIQ-BR-00000001'),
    )
  })

  it('uses entity_id — never candidate/mirror/final ids — in the route', async () => {
    renderIndex()
    await waitFor(() => expect(screen.getByText(SEED.name_en!)).toBeTruthy())
    fireEvent.click(screen.getByText(SEED.name_en!))
    await waitFor(() => expect(window.location.hash).toContain('/NGIQ-BR-'))
    expect(window.location.hash).not.toContain('entity_pk')
    expect(window.location.hash).not.toMatch(/candidate|mirror|final/i)
  })
})

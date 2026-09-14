/**
 * BrainRegion Workspace tests (Phase 1B).
 *
 * One canonical BrainRegion is the operational root. Seven top-level tabs; the
 * candidate subtypes live INSIDE Candidates, not at the same level as
 * Discovery/Validation. No Discovery Run exists, so no step may be active.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider } from '../../i18n-context'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import type { BrainRegionSeedDetail } from './types'

const getSeed = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeed: (...args: unknown[]) => getSeed(...args),
  fetchBrainRegionSeeds: vi.fn(),
  fetchBrainRegionSummary: vi.fn(),
}))

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
  getSeed.mockReset()
  getSeed.mockResolvedValue(DETAIL)
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
    expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain('Not initialized')
    for (const k of ['candidates', 'evidence', 'review']) {
      expect(screen.getByTestId(`kp-ws-summary-${k}`).textContent).toContain('—')
      expect(screen.getByTestId(`kp-ws-summary-${k}`).textContent).not.toContain('0')
    }
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
    // they are listed INSIDE Candidates instead
    fireEvent.click(screen.getByTestId('kp-tab-candidates'))
    const panel = within(screen.getByTestId('kp-candidates-tab'))
    for (const label of ['Circuits', 'Connections', 'Functions', 'Related Regions']) {
      expect(panel.getByText(label)).toBeTruthy()
    }
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

  it('keeps both Discovery actions disabled', async () => {
    renderWorkspace()
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-literature-discovery')).toHaveProperty('disabled', true)
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

  it('omits a section that has nothing authoritative to show', async () => {
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
    expect(ov.queryByText('Hierarchy')).toBeNull()
    expect(ov.queryByText('Source / Mapping')).toBeNull()
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
    for (const f of ['BrainRegionWorkspacePage.tsx', 'workspaceTabs.tsx', 'routes.ts']) {
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

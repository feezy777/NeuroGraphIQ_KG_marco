/**
 * Knowledge Production is fully bilingual (Phase 2B.1).
 *
 * Covers the localized Index / Workspace / tabs / Discovery status & outcome,
 * the locale-aware BrainRegion naming policy, and — importantly — that the
 * language switch is a pure presentation change: the route, the selected tab
 * and every raw API enum value are untouched.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { I18nProvider, useI18n } from '../../i18n-context'
import { LANGUAGE_STORAGE_KEY, type Language } from '../../i18n'
import { KnowledgeProductionPage } from './KnowledgeProductionPage'
import { BrainRegionWorkspacePage } from './BrainRegionWorkspacePage'
import type { BrainRegionSeed, BrainRegionSeedDetail, DiscoveryRun } from './types'

const listSeeds = vi.fn()
const fetchSummary = vi.fn()
const getSeed = vi.fn()
const getRuns = vi.fn()

vi.mock('./kpApi', () => ({
  fetchBrainRegionSeeds: (...a: unknown[]) => listSeeds(...a),
  fetchBrainRegionSummary: (...a: unknown[]) => fetchSummary(...a),
  fetchBrainRegionSeed: (...a: unknown[]) => getSeed(...a),
  fetchDiscoveryRuns: (...a: unknown[]) => getRuns(...a),
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

/** Live language toggle, standing in for the real Settings control. */
function Harness({ children }: { children: React.ReactNode }) {
  const { language, setLanguage } = useI18n()
  return (
    <>
      <button type="button" data-testid="lang-en" onClick={() => setLanguage('en-US')}>
        en
      </button>
      <button type="button" data-testid="lang-zh" onClick={() => setLanguage('zh-CN')}>
        zh
      </button>
      <span data-testid="active-lang">{language}</span>
      {children}
    </>
  )
}

/**
 * The provider reads the persisted language at mount — exactly like the real
 * app — so the requested language is seeded into localStorage first.
 */
function renderWithLanguage(language: Language, ui: React.ReactNode) {
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language)
  return render(<I18nProvider>{<Harness>{ui}</Harness>}</I18nProvider>)
}

function renderIndex(language: Language) {
  return renderWithLanguage(language, <KnowledgeProductionPage />)
}

function renderWorkspace(language: Language) {
  return renderWithLanguage(
    language,
    <BrainRegionWorkspacePage entityId="NGIQ-BR-00000001" />,
  )
}

beforeEach(() => {
  window.localStorage.clear()
  listSeeds.mockReset().mockResolvedValue({ items: [SEED], total: 770 })
  fetchSummary.mockReset().mockResolvedValue({
    total: 770,
    by_granularity: {
      G1_MACRO: 84,
      G2_MESO_ANATOMICAL: 0,
      G3_MESO_FINE: 246,
      G4_MICROSTRUCTURAL_FINE: 440,
    },
  })
  getSeed.mockReset().mockResolvedValue(DETAIL)
  getRuns.mockReset().mockResolvedValue({ items: [], total: 0 })
  window.location.hash = '#/knowledge-production/brain-regions/NGIQ-BR-00000001'
})

// ---------------------------------------------------------------------------
// KNOWLEDGE PRODUCTION — labels
// ---------------------------------------------------------------------------
describe('Knowledge Production localization', () => {
  it('10. renders the Chinese index UI', async () => {
    renderIndex('zh-CN')
    expect(await screen.findByText('知识生产')).toBeTruthy()
    expect(screen.getByText('脑区总数')).toBeTruthy()
    expect(screen.getByText('筛选')).toBeTruthy()
    expect(screen.getByText('重置')).toBeTruthy()
    expect(screen.getByText('刷新')).toBeTruthy()
    expect(screen.getByTestId('kp-gran-G1').textContent).toBe('G1 宏观')
    expect(screen.getByTestId('kp-gran-G2').textContent).toBe('G2 中尺度解剖')
    expect(screen.getByTestId('kp-gran-G4').textContent).toBe('G4 微结构')
  })

  it('11. renders the English index UI', async () => {
    renderIndex('en-US')
    expect(await screen.findByText('Knowledge Production')).toBeTruthy()
    expect(screen.getByText('Total BrainRegions')).toBeTruthy()
    expect(screen.getByText('Filter')).toBeTruthy()
    expect(screen.getByText('Reset')).toBeTruthy()
    expect(screen.getByText('Refresh')).toBeTruthy()
    expect(screen.getByTestId('kp-gran-G1').textContent).toBe('G1 Macro')
    expect(screen.getByTestId('kp-gran-G4').textContent).toBe('G4 Microstructural')
  })

  it('localizes the workspace tabs, workflow and summary in both languages', async () => {
    renderWorkspace('zh-CN')
    // tabs
    expect((await screen.findByTestId('kp-tab-overview')).textContent).toBe('概览')
    expect(screen.getByTestId('kp-tab-discovery').textContent).toBe('知识发现')
    expect(screen.getByTestId('kp-tab-canonicalization').textContent).toBe('归一化')
    expect(screen.getByTestId('kp-tab-history').textContent).toBe('历史记录')
    // workflow
    expect(screen.getByTestId('kp-step-discover').textContent).toContain('发现')
    expect(screen.getByTestId('kp-step-canonicalize').textContent).toContain('归一化')
    // summary
    expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain('知识发现')
    expect(screen.getByTestId('kp-ws-summary-review').textContent).toContain('审核')

    fireEvent.click(screen.getByTestId('lang-en'))
    await waitFor(() =>
      expect(screen.getByTestId('kp-tab-overview').textContent).toBe('Overview'),
    )
    expect(screen.getByTestId('kp-tab-canonicalization').textContent).toBe('Canonicalization')
    expect(screen.getByTestId('kp-step-canonicalize').textContent).toContain('Canonicalize')
    expect(screen.getByTestId('kp-ws-summary-review').textContent).toContain('Review')
  })

  it('localizes the Overview section titles and field labels', async () => {
    renderWorkspace('zh-CN')
    const ov = within(await screen.findByTestId('kp-overview'))
    for (const s of ['身份信息', '解剖信息', '层级关系', '来源与映射', '数据治理']) {
      expect(ov.getByText(s)).toBeTruthy()
    }
    // the raw identifier label stays literal
    expect(ov.getByText('entity_id')).toBeTruthy()
    expect(ov.getByText('NGIQ-BR-00000001')).toBeTruthy()

    fireEvent.click(screen.getByTestId('lang-en'))
    const ovEn = within(screen.getByTestId('kp-overview'))
    for (const s of ['Identity', 'Anatomy', 'Hierarchy', 'Source / Mapping', 'Governance']) {
      expect(ovEn.getByText(s)).toBeTruthy()
    }
  })

  it('localizes the empty states of the future tabs', async () => {
    renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    expect(screen.getByText('暂无发现任务')).toBeTruthy()

    fireEvent.click(screen.getByTestId('kp-tab-validation'))
    expect(screen.getByText('规则验证')).toBeTruthy()
    expect(screen.getByText('人工审核')).toBeTruthy()

    fireEvent.click(screen.getByTestId('lang-en'))
    fireEvent.click(screen.getByTestId('kp-tab-discovery'))
    expect(screen.getByText('No Discovery Runs yet')).toBeTruthy()
    fireEvent.click(screen.getByTestId('kp-tab-candidates'))
    expect(screen.getByText('Circuits')).toBeTruthy()
  })

  it('keeps both discovery buttons disabled in both languages', async () => {
    renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByTestId('kp-literature-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByText('启动 LLM 发现')).toBeTruthy()

    fireEvent.click(screen.getByTestId('lang-en'))
    expect(screen.getByTestId('kp-llm-discovery')).toHaveProperty('disabled', true)
    expect(screen.getByText('Start LLM Discovery')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// DISCOVERY STATUS / OUTCOME
// ---------------------------------------------------------------------------
describe('Discovery Run status and outcome localization', () => {
  it('12. localizes every run status in both languages', async () => {
    const cases: [DiscoveryRun['status'], string, string][] = [
      ['QUEUED', '排队中', 'Queued'],
      ['RUNNING', '运行中', 'Running'],
      ['COMPLETED', '已完成', 'Completed'],
      ['FAILED', '失败', 'Failed'],
      ['CANCELLED', '已取消', 'Cancelled'],
    ]
    for (const [status, zh, en] of cases) {
      getRuns.mockResolvedValue({
        items: [
          run({
            status,
            outcome: status === 'COMPLETED' ? 'CANDIDATES_FOUND' : null,
            started_at: status === 'QUEUED' ? null : '2026-09-14T10:01:00Z',
            finished_at: ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status)
              ? '2026-09-14T10:04:00Z'
              : null,
          }),
        ],
        total: 1,
      })
      const { unmount } = renderWorkspace('zh-CN')
      await waitFor(() =>
        expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain(zh),
      )
      fireEvent.click(screen.getByTestId('lang-en'))
      await waitFor(() =>
        expect(screen.getByTestId('kp-ws-summary-discovery').textContent).toContain(en),
      )
      unmount()
      window.localStorage.clear()
    }
  })

  it('13. localizes every outcome in the run history', async () => {
    const cases: [DiscoveryRun['outcome'], string, string][] = [
      ['CANDIDATES_FOUND', '已发现候选知识', 'Candidates found'],
      ['NO_CANDIDATES_FOUND', '未发现候选知识', 'No candidates found'],
      ['NO_EVIDENCE_FOUND', '未发现证据', 'No evidence found'],
    ]
    for (const [outcome, zh, en] of cases) {
      getRuns.mockResolvedValue({
        items: [
          run({
            discovery_type: 'LITERATURE_DISCOVERY',
            status: 'COMPLETED',
            outcome,
            started_at: '2026-09-14T10:01:00Z',
            finished_at: '2026-09-14T10:04:00Z',
          }),
        ],
        total: 1,
      })
      const { unmount } = renderWorkspace('zh-CN')
      fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
      const hist = within(await screen.findByTestId('kp-run-history'))
      expect(hist.getByText(zh)).toBeTruthy()

      fireEvent.click(screen.getByTestId('lang-en'))
      const histEn = within(screen.getByTestId('kp-run-history'))
      expect(histEn.getByText(en)).toBeTruthy()
      unmount()
      window.localStorage.clear()
    }
  })

  it('14. raw API enums are untouched by localization', async () => {
    const completed = run({
      status: 'COMPLETED',
      outcome: 'CANDIDATES_FOUND',
      started_at: '2026-09-14T10:01:00Z',
      finished_at: '2026-09-14T10:04:00Z',
    })
    getRuns.mockResolvedValue({ items: [completed], total: 1 })
    renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))

    const badgeZh = (await screen.findByTestId('kp-run-history')).querySelector('.badge')
    // the TONE is chosen from the raw enum, so it must not change with language
    expect(badgeZh?.className).toContain('badge-green')
    expect(badgeZh?.textContent).toBe('已完成')

    fireEvent.click(screen.getByTestId('lang-en'))
    const badgeEn = screen.getByTestId('kp-run-history').querySelector('.badge')
    expect(badgeEn?.className).toContain('badge-green')
    expect(badgeEn?.textContent).toBe('Completed')

    // the API payload itself was never rewritten
    expect(completed.status).toBe('COMPLETED')
    expect(completed.outcome).toBe('CANDIDATES_FOUND')
    // a language switch issues no extra request and rewrites no data
    expect(getRuns).toHaveBeenCalledTimes(1)
  })

  it('leaves run_id and model names untranslated', async () => {
    getRuns.mockResolvedValue({
      items: [
        run({
          status: 'RUNNING',
          provider: 'deepseek',
          model_name: 'deepseek-v4-pro',
          started_at: '2026-09-14T10:01:00Z',
        }),
      ],
      total: 1,
    })
    renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('kp-tab-discovery'))
    const hist = within(await screen.findByTestId('kp-run-history'))
    expect(hist.getByText('deepseek · deepseek-v4-pro')).toBeTruthy()
  })
})

// ---------------------------------------------------------------------------
// BRAINREGION NAMING POLICY
// ---------------------------------------------------------------------------
describe('BrainRegion naming policy', () => {
  it('15. Chinese mode: name_zh is the H1, name_en the secondary', async () => {
    renderWorkspace('zh-CN')
    await waitFor(() => expect(screen.getByTestId('kp-ws-name')).toBeTruthy())
    expect(screen.getByTestId('kp-ws-name').textContent).toBe('左侧额上回')
    expect(screen.getByTestId('kp-ws-name').nextElementSibling?.textContent).toBe(
      'Left Superior frontal gyrus, Brainnetome 7_1',
    )
    // entity_id is never translated
    expect(screen.getByTestId('kp-ws-entity-id').textContent).toBe('NGIQ-BR-00000001')
  })

  it('16. English mode: name_en is the H1, name_zh the secondary', async () => {
    renderWorkspace('en-US')
    await waitFor(() => expect(screen.getByTestId('kp-ws-name')).toBeTruthy())
    expect(screen.getByTestId('kp-ws-name').textContent).toBe(
      'Left Superior frontal gyrus, Brainnetome 7_1',
    )
    expect(screen.getByTestId('kp-ws-name').nextElementSibling?.textContent).toBe('左侧额上回')
  })

  it('17. falls back to the other name when the preferred one is empty', async () => {
    getSeed.mockResolvedValue({ ...DETAIL, name_zh: null })
    renderWorkspace('zh-CN')
    await waitFor(() => expect(screen.getByTestId('kp-ws-name')).toBeTruthy())
    expect(screen.getByTestId('kp-ws-name').textContent).toBe(
      'Left Superior frontal gyrus, Brainnetome 7_1',
    )
    // nothing to show secondarily — the primary already IS that name
    expect(screen.getByTestId('kp-ws-name').nextElementSibling?.textContent).toBe(
      'NGIQ-BR-00000001',
    )
  })

  it('applies the same policy to the index table', async () => {
    renderIndex('zh-CN')
    await waitFor(() => expect(screen.getByText('左侧额上回')).toBeTruthy())
    expect(screen.getByText('Left Superior frontal gyrus, Brainnetome 7_1')).toBeTruthy()

    fireEvent.click(screen.getByTestId('lang-en'))
    // both names remain present; only which one leads changes
    expect(screen.getByText('左侧额上回')).toBeTruthy()
    expect(screen.getByText('Left Superior frontal gyrus, Brainnetome 7_1')).toBeTruthy()
  })

  it('switches the H1 in place without losing the workspace', async () => {
    renderWorkspace('zh-CN')
    await waitFor(() => expect(screen.getByTestId('kp-ws-name').textContent).toBe('左侧额上回'))
    fireEvent.click(screen.getByTestId('lang-en'))
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-name').textContent).toBe(
        'Left Superior frontal gyrus, Brainnetome 7_1',
      ),
    )
    fireEvent.click(screen.getByTestId('lang-zh'))
    await waitFor(() => expect(screen.getByTestId('kp-ws-name').textContent).toBe('左侧额上回'))
  })
})

// ---------------------------------------------------------------------------
// ROUTE / STATE STABILITY
// ---------------------------------------------------------------------------
describe('language switching preserves workspace state', () => {
  it('18. the route is unchanged', async () => {
    const route = '#/knowledge-production/brain-regions/NGIQ-BR-00000001'
    window.location.hash = route
    renderWorkspace('zh-CN')
    await waitFor(() => expect(screen.getByTestId('kp-ws-name')).toBeTruthy())

    fireEvent.click(screen.getByTestId('lang-en'))
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-name').textContent).toBe(DETAIL.name_en),
    )
    expect(window.location.hash).toBe(route)

    fireEvent.click(screen.getByTestId('lang-zh'))
    await waitFor(() => expect(screen.getByTestId('kp-ws-name').textContent).toBe(DETAIL.name_zh))
    expect(window.location.hash).toBe(route)
  })

  it('19. the selected tab is unchanged', async () => {
    renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('kp-tab-evidence'))
    expect(screen.getByTestId('kp-evidence-tab')).toBeTruthy()
    expect(screen.getByTestId('kp-tab-evidence').getAttribute('aria-selected')).toBe('true')

    fireEvent.click(screen.getByTestId('lang-en'))
    await waitFor(() =>
      expect(screen.getByTestId('kp-tab-evidence').textContent).toBe('Evidence'),
    )
    // still on Evidence — not reset to Overview by the language change
    expect(screen.getByTestId('kp-evidence-tab')).toBeTruthy()
    expect(screen.queryByTestId('kp-overview')).toBeNull()
    expect(screen.getByTestId('kp-tab-evidence').getAttribute('aria-selected')).toBe('true')

    fireEvent.click(screen.getByTestId('lang-zh'))
    await waitFor(() =>
      expect(screen.getByTestId('kp-tab-evidence').textContent).toBe('证据'),
    )
    expect(screen.getByTestId('kp-evidence-tab')).toBeTruthy()
  })

  it('persists the language across a remount without touching the route', async () => {
    const route = '#/knowledge-production/brain-regions/NGIQ-BR-00000001'
    window.location.hash = route
    const first = renderWorkspace('zh-CN')
    fireEvent.click(await screen.findByTestId('lang-en'))
    await waitFor(() =>
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en-US'),
    )
    first.unmount()

    renderWorkspace('en-US')
    await waitFor(() =>
      expect(screen.getByTestId('kp-ws-name').textContent).toBe(DETAIL.name_en),
    )
    expect(window.location.hash).toBe(route)
  })
})

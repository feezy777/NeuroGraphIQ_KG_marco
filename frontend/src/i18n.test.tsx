/**
 * Global UI language switching (Phase 2B.1).
 *
 * There is exactly ONE language authority: the existing i18n module
 * (`i18n.ts`) plus its `I18nProvider`. These tests exercise that authority and
 * the Settings control that drives it — they do not define a second system.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import {
  LANGUAGE_STORAGE_KEY,
  getInitialLanguage,
  normalizeLanguage,
  saveLanguage,
  translate,
} from './i18n'
import { I18nProvider, useI18n } from './i18n-context'

vi.mock('./api/endpoints', () => ({
  getSettingsOptions: vi.fn().mockResolvedValue({
    // Deliberately the BACKEND's label ('中文'), to prove the control does not
    // take its language endonyms from the API.
    languages: [
      { value: 'zh-CN', label: '中文' },
      { value: 'en-US', label: 'English' },
    ],
    api_providers: [],
    default_models: { deepseek: ['deepseek-chat'] },
  }),
  getRuntimeSettings: vi.fn().mockResolvedValue({
    api_providers: {
      deepseek: {
        api_key_configured: false,
        api_key_masked: null,
        default_model: 'deepseek-chat',
        base_url: 'https://api.deepseek.com/v1',
      },
    },
    basic: { default_page_size: 20, max_page_size: 100, show_debug_panels: false },
  }),
  updateRuntimeSettings: vi.fn().mockResolvedValue({}),
  testDeepSeekConnection: vi.fn().mockResolvedValue({ ok: true }),
}))

const { SettingsPage } = await import('./pages/SettingsPage')

/** Minimal consumer that exposes the language authority to the test. */
function Probe() {
  const { language, setLanguage, t } = useI18n()
  return (
    <div>
      <span data-testid="lang">{language}</span>
      <span data-testid="t-dashboard">{t('nav.dashboard')}</span>
      <span data-testid="t-kp">{t('nav.knowledgeProduction')}</span>
      <button type="button" data-testid="to-en" onClick={() => setLanguage('en-US')}>
        en
      </button>
      <button type="button" data-testid="to-zh" onClick={() => setLanguage('zh-CN')}>
        zh
      </button>
    </div>
  )
}

function renderProbe() {
  return render(
    <I18nProvider>
      <Probe />
    </I18nProvider>,
  )
}

beforeEach(() => {
  window.localStorage.clear()
})

// ---------------------------------------------------------------------------
// I18N CORE
// ---------------------------------------------------------------------------
describe('i18n core', () => {
  it('1. defaults to zh-CN when nothing is stored', () => {
    expect(getInitialLanguage()).toBe('zh-CN')
    renderProbe()
    expect(screen.getByTestId('lang').textContent).toBe('zh-CN')
  })

  it('2. selecting en-US switches the UI immediately', () => {
    renderProbe()
    expect(screen.getByTestId('t-dashboard').textContent).toBe('仪表盘')
    fireEvent.click(screen.getByTestId('to-en'))
    expect(screen.getByTestId('lang').textContent).toBe('en-US')
    expect(screen.getByTestId('t-dashboard').textContent).toBe('Dashboard')
  })

  it('3. the choice is persisted to localStorage', () => {
    renderProbe()
    fireEvent.click(screen.getByTestId('to-en'))
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en-US')
  })

  it('4. a remount picks the persisted language up', () => {
    saveLanguage('en-US')
    renderProbe()
    expect(screen.getByTestId('lang').textContent).toBe('en-US')
    expect(screen.getByTestId('t-dashboard').textContent).toBe('Dashboard')
  })

  it('5. switching back to zh-CN restores Chinese', () => {
    saveLanguage('en-US')
    renderProbe()
    expect(screen.getByTestId('t-dashboard').textContent).toBe('Dashboard')
    fireEvent.click(screen.getByTestId('to-zh'))
    expect(screen.getByTestId('lang').textContent).toBe('zh-CN')
    expect(screen.getByTestId('t-dashboard').textContent).toBe('仪表盘')
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('zh-CN')
  })

  it('6. an invalid stored locale falls back to zh-CN', () => {
    expect(normalizeLanguage('fr-FR')).toBe('zh-CN')
    expect(normalizeLanguage(null)).toBe('zh-CN')
    expect(normalizeLanguage('')).toBe('zh-CN')
    window.localStorage.setItem(LANGUAGE_STORAGE_KEY, 'klingon')
    expect(getInitialLanguage()).toBe('zh-CN')
    renderProbe()
    expect(screen.getByTestId('lang').textContent).toBe('zh-CN')
  })

  it('exposes exactly two locales', () => {
    expect(normalizeLanguage('en-US')).toBe('en-US')
    expect(normalizeLanguage('zh-CN')).toBe('zh-CN')
  })

  it('falls back to the zh-CN string for a key missing in en-US', () => {
    // Deliberate fallback chain: lang -> zh-CN -> key
    expect(translate('en-US', 'definitely.not.a.key')).toBe('definitely.not.a.key')
    expect(translate('zh-CN', 'nav.dashboard')).toBe('仪表盘')
    expect(translate('en-US', 'nav.dashboard')).toBe('Dashboard')
  })

  it('every sidebar label resolves in BOTH languages', () => {
    const keys = [
      'nav.dashboard',
      'nav.resources',
      'nav.files',
      'nav.importBatches',
      'nav.llmExtraction',
      'nav.knowledgeProduction',
      'nav.dataCenter',
      'nav.ontologyCenter',
      'nav.validationCenter',
      'nav.taskCenter',
      'nav.graphExplorer',
      'nav.brain3D',
      'nav.symptomQuery',
      'nav.settings',
    ]
    for (const key of keys) {
      const zh = translate('zh-CN', key)
      const en = translate('en-US', key)
      // a key that only exists in zh-CN would render Chinese in English mode
      expect(zh, key).not.toBe(key)
      expect(en, `${key} must not fall back to Chinese`).not.toBe(key)
      expect(en, `${key} must be English`).not.toBe(zh)
    }
  })
})

// ---------------------------------------------------------------------------
// SETTINGS
// ---------------------------------------------------------------------------
describe('Settings language control', () => {
  it('7/8. renders a language control with exactly two options', async () => {
    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    const select = await screen.findByRole('combobox')
    const options = Array.from(select.querySelectorAll('option'))
    expect(options.map(o => (o as HTMLOptionElement).value)).toEqual(['zh-CN', 'en-US'])
    // endonyms: identical in both modes, never translated
    expect(options.map(o => o.textContent)).toEqual(['简体中文', 'English'])
  })

  it('9. changing the selection takes effect immediately', async () => {
    render(
      <I18nProvider>
        <SettingsPage />
      </I18nProvider>,
    )
    const select = await screen.findByRole('combobox')
    expect(select).toHaveProperty('value', 'zh-CN')

    fireEvent.change(select, { target: { value: 'en-US' } })
    await waitFor(() => expect(select).toHaveProperty('value', 'en-US'))
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('en-US')
    // the surrounding UI re-rendered in English without a reload ('Language'
    // appears as both the tab and the section title, hence findAllBy)
    expect((await screen.findAllByText('Language')).length).toBeGreaterThan(0)
    expect(screen.queryByText('语言设置')).toBeNull()

    fireEvent.change(select, { target: { value: 'zh-CN' } })
    await waitFor(() =>
      expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('zh-CN'),
    )
    expect((await screen.findAllByText('语言设置')).length).toBeGreaterThan(0)
    expect(screen.queryByText('Language')).toBeNull()
  })
})

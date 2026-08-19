import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import * as endpoints from '../../api/endpoints'
import { ValidationCenterPage } from './ValidationCenterPage'
import { GranularityProvider } from '../../hooks/useGlobalGranularity'
import { I18nProvider } from '../../i18n-context'

vi.mock('../../api/endpoints', () => ({
  listPaperEvidenceTasks: vi.fn(),
  listPaperEvidenceTaskItems: vi.fn(),
  listEvidenceReviews: vi.fn(),
  listEvidencePapers: vi.fn(),
  getEvidenceTarget: vi.fn(),
  searchPaperEvidence: vi.fn(),
  extractSelectedPaperEvidence: vi.fn(),
  listPaperEvidence: vi.fn(),
  attachPaperEvidencePreview: vi.fn(),
  attachPaperEvidence: vi.fn(),
  rollbackPaperEvidence: vi.fn(),
  translateEvidenceText: vi.fn(),
  saveTaskItemDraft: vi.fn(),
  validatePassageSelection: vi.fn(),
  resolvePaperEvidenceTaskItem: vi.fn(),
  reopenPaperEvidenceTaskItem: vi.fn(),
  pausePaperEvidenceTask: vi.fn(),
  resumePaperEvidenceTask: vi.fn(),
  retryPaperEvidenceTask: vi.fn(),
  createPaperEvidenceBatch: vi.fn(),
  previewEvidenceBatchScope: vi.fn(),
  buildReview: vi.fn(),
  approveReview: vi.fn(),
  rejectReview: vi.fn(),
}))

describe('Provider smoke', () => {
  afterEach(() => { vi.clearAllMocks(); window.location.hash = '' })
  it('renders validation center without provider error', async () => {
    vi.mocked(endpoints.listPaperEvidenceTasks).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listPaperEvidenceTaskItems).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.listEvidenceReviews).mockResolvedValue({ items: [], total: 0 })
    vi.mocked(endpoints.listEvidencePapers).mockResolvedValue({ items: [] })
    vi.mocked(endpoints.getEvidenceTarget).mockResolvedValue(null)
    window.location.hash = '#/validation-center?tab=paper_evidence'
    const errSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <GranularityProvider>
        <I18nProvider>
          <ValidationCenterPage />
        </I18nProvider>
      </GranularityProvider>,
    )
    await waitFor(() => expect(screen.getByTestId('evidence-center')).toBeTruthy())
    const providerErrors = errSpy.mock.calls.filter(c => String(c[0]).includes('useEvidenceCenter'))
    expect(providerErrors).toHaveLength(0)
  })
})

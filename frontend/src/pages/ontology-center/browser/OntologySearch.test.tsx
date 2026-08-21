import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OntologySearchInput, OntologySearchResults } from './OntologySearch'
import * as ontologyApiModule from '../../../api/ontologyApi'
import type { OntologyTreeNode } from './tree/OntologyTreeNode'

vi.mock('../../../api/ontologyApi', () => ({
  ontologyApi: {
    getTreeChildren: vi.fn(),
    getEntityDetail: vi.fn(),
    getRelations: vi.fn(),
    searchEntities: vi.fn(),
  },
}))

const mocked = vi.mocked(ontologyApiModule.ontologyApi)

const RESULTS: OntologyTreeNode[] = [
  {
    id: 'r-hippo',
    code: 'ng:br:hippocampus',
    name: 'Hippocampus',
    entityType: 'region',
    granularityLevel: 'clinical',
    status: 'active',
  },
  {
    id: 'c-1',
    code: 'ng:cn:hippo-cortex',
    name: 'ng:cn:hippo-cortex',
    entityType: 'connection',
  },
]

beforeEach(() => {
  vi.clearAllMocks()
})

describe('OntologySearchInput', () => {
  it('renders a labelled search box and propagates changes', () => {
    const onChange = vi.fn()
    render(<OntologySearchInput value="" onChange={onChange} />)

    expect(screen.getByPlaceholderText('Search ontology...')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Search ontology'), { target: { value: 'hipp' } })
    expect(onChange).toHaveBeenCalledWith('hipp')
  })
})

describe('OntologySearchResults', () => {
  it('renders nothing below the minimum query length', () => {
    mocked.searchEntities.mockResolvedValue(RESULTS)
    render(<OntologySearchResults query="h" onSelect={() => {}} />)

    expect(screen.queryByText('Hippocampus')).toBeNull()
    expect(mocked.searchEntities).not.toHaveBeenCalled()
  })

  it('searches after debounce and groups results by entity type', async () => {
    mocked.searchEntities.mockResolvedValue(RESULTS)
    render(<OntologySearchResults query="hipp" onSelect={() => {}} />)

    expect(await screen.findByText('Hippocampus', {}, { timeout: 2000 })).toBeTruthy()
    expect(screen.getByText('Brain Region')).toBeTruthy() // 分组头
    expect(screen.getByText('Connection')).toBeTruthy()
    expect(mocked.searchEntities).toHaveBeenCalledWith('hipp', expect.anything())
  })

  it('selecting a result calls onSelect', async () => {
    const onSelect = vi.fn()
    mocked.searchEntities.mockResolvedValue(RESULTS)
    render(<OntologySearchResults query="hipp" onSelect={onSelect} />)

    fireEvent.click(await screen.findByText('Hippocampus', {}, { timeout: 2000 }))
    expect(onSelect).toHaveBeenCalledWith(RESULTS[0])
  })

  it('shows empty state when nothing matches', async () => {
    mocked.searchEntities.mockResolvedValue([])
    render(<OntologySearchResults query="zzz" onSelect={() => {}} />)

    expect(await screen.findByText('No matching entities', {}, { timeout: 2000 })).toBeTruthy()
  })

  it('shows error state and retries on failure', async () => {
    mocked.searchEntities
      .mockRejectedValueOnce(new Error('boom'))
      .mockResolvedValueOnce(RESULTS)
    render(<OntologySearchResults query="hipp" onSelect={() => {}} />)

    expect(await screen.findByText('Search failed', {}, { timeout: 2000 })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(await screen.findByText('Hippocampus', {}, { timeout: 2000 })).toBeTruthy()
  })
})

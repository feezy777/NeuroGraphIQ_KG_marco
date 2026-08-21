import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { OntologyScaleSelector } from './OntologyScaleSelector'
import { DEFAULT_ONTOLOGY_SCALE, type OntologyScaleKey } from './ontologyScale'

/** 受控往返 harness：验证 onChange 驱动 value 的完整闭环 */
function ScaleHarness() {
  const [scale, setScale] = useState<OntologyScaleKey>(DEFAULT_ONTOLOGY_SCALE)
  return <OntologyScaleSelector value={scale} onChange={setScale} />
}

describe('OntologyScaleSelector', () => {
  it('renders seven scales in two labelled groups with the default active', () => {
    render(<ScaleHarness />)

    expect(screen.getAllByRole('radio').length).toBe(7)
    expect(screen.getByText('Brain Region')).toBeTruthy()
    expect(screen.getByText('Biological Layer')).toBeTruthy()
    expect(screen.getByRole('radio', { name: 'Fine' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: 'Meso' }).getAttribute('aria-checked')).toBe('false')
    expect(screen.getByRole('radio', { name: 'Macro' }).getAttribute('aria-checked')).toBe('false')
    expect(screen.getByRole('radio', { name: 'Molecular' }).getAttribute('aria-checked')).toBe('false')
  })

  it('switches the active scale on click (controlled round trip)', () => {
    const { container } = render(<ScaleHarness />)

    fireEvent.click(screen.getByRole('radio', { name: 'Meso' }))
    expect(screen.getByRole('radio', { name: 'Meso' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: 'Macro' }).getAttribute('aria-checked')).toBe('false')
    expect(container.querySelector('.oc-scale-option-active')).toBeTruthy()

    fireEvent.click(screen.getByRole('radio', { name: 'Cyto' }))
    expect(screen.getByRole('radio', { name: 'Cyto' }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByRole('radio', { name: 'Meso' }).getAttribute('aria-checked')).toBe('false')
  })

  it('shows a tooltip hint per scale', () => {
    render(<ScaleHarness />)

    expect(screen.getByTitle('Brain system level')).toBeTruthy()
    expect(screen.getByTitle('Subregional parcellation')).toBeTruthy()
    expect(screen.getByTitle('Cell type taxonomy')).toBeTruthy()
    expect(screen.getByTitle('Gene/protein level')).toBeTruthy()
  })
})

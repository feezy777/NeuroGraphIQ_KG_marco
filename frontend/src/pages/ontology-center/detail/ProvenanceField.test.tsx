import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { ProvenanceField } from './ProvenanceField'
import type { DetailRow } from './types'

const ARRAY_ROW: DetailRow = {
  label: 'original_connection_ids',
  value: JSON.stringify(['e20a1be7-3b2c-4d5e-8f90-1234567890ab', 'b06e96e8-1a2b-3c4d-9e0f-abcdef012345']),
}

describe('ProvenanceField', () => {
  it('renders plain values directly without array UI', () => {
    const { container } = render(<ProvenanceField row={{ label: 'mapping_method', value: 'macro96_canonical_connection_v1' }} />)

    expect(screen.getByText('macro96_canonical_connection_v1')).toBeTruthy()
    expect(container.querySelector('.oc-provenance-count')).toBeNull()
    expect(screen.queryByRole('button', { name: /Expand JSON/ })).toBeNull()
  })

  it('renders non-array JSON (object) as plain text', () => {
    const { container } = render(
      <ProvenanceField row={{ label: 'source_summary', value: JSON.stringify({ atlas: 'AAL3', version: 'v3' }) }} />,
    )

    expect(container.querySelector('.oc-provenance-count')).toBeNull()
    expect(screen.queryByRole('button', { name: /Expand JSON/ })).toBeNull()
  })

  it('marks mono code fields with ellipsis class and full-value tooltip', () => {
    const code = 'ng:cn:structural_3rd_ventricle_to_basal_forebrain'
    const { container } = render(<ProvenanceField row={{ label: 'Code', value: code, mono: true }} />)

    expect(container.querySelector('.oc-detail-value-code')).toBeTruthy()
    expect(screen.getByTitle(code)).toBeTruthy() // hover tooltip 显示完整
  })

  it('renders array fields as item count + per-item previews + Expand JSON', () => {
    const { container } = render(<ProvenanceField row={ARRAY_ROW} />)

    expect(screen.getByText('2 items')).toBeTruthy()
    // 逐项预览：截断 + [ ] 包裹；完整值保留在 title
    expect(screen.getByText('[ e20a1be7-3b2c-4d... ]')).toBeTruthy()
    expect(screen.getByText('[ b06e96e8-1a2b-3c... ]')).toBeTruthy()
    expect(screen.getByTitle('e20a1be7-3b2c-4d5e-8f90-1234567890ab')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Expand JSON/ })).toBeTruthy()
    expect(container.querySelector('.oc-provenance-json')).toBeNull() // 默认折叠
  })

  it('expands and collapses the full JSON payload', () => {
    const { container } = render(<ProvenanceField row={ARRAY_ROW} />)

    fireEvent.click(screen.getByRole('button', { name: /Expand JSON/ }))
    const pre = container.querySelector('.oc-provenance-json')
    expect(pre).toBeTruthy()
    expect(pre?.textContent).toContain('"e20a1be7-3b2c-4d5e-8f90-1234567890ab"') // 完整内容
    expect(pre?.textContent).toContain('"b06e96e8-1a2b-3c4d-9e0f-abcdef012345"')

    fireEvent.click(screen.getByRole('button', { name: /Expand JSON/ }))
    expect(container.querySelector('.oc-provenance-json')).toBeNull()
  })

  it('shows short array items untruncated', () => {
    render(<ProvenanceField row={{ label: 'original_relation_types', value: JSON.stringify(['part_of']) }} />)

    expect(screen.getByText('[ part_of ]')).toBeTruthy()
  })
})

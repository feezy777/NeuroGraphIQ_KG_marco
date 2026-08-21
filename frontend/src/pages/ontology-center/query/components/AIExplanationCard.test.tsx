import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { OntologyLLMResponse } from '../../../../api/ontologyQueryApi'
import { AIExplanationCard } from './AIExplanationCard'

function makeExplanation(overrides: Partial<OntologyLLMResponse> = {}): OntologyLLMResponse {
  return {
    answer: '海马主要参与情景记忆的编码与巩固。',
    summary: '海马是记忆回路的核心节点。',
    key_points: ['情景记忆编码', '空间导航'],
    evidence_entities: ['海马', '内嗅皮层'],
    confidence: 0.9,
    hallucination_warning: [],
    ...overrides,
  }
}

describe('AIExplanationCard', () => {
  it('renders answer, summary, key points and evidence chips', () => {
    render(<AIExplanationCard explanation={makeExplanation()} />)

    expect(screen.getByText('AI Explanation')).toBeTruthy()
    expect(screen.getByText('Generated from Knowledge Graph')).toBeTruthy()
    expect(screen.getByText('海马主要参与情景记忆的编码与巩固。')).toBeTruthy()
    expect(screen.getByText('海马是记忆回路的核心节点。')).toBeTruthy()
    expect(screen.getByText('Key Points')).toBeTruthy()
    expect(screen.getByText('情景记忆编码')).toBeTruthy()
    expect(screen.getByText('空间导航')).toBeTruthy()
    expect(screen.getByText('证据来源')).toBeTruthy()
    expect(screen.getByText('海马')).toBeTruthy()
    expect(screen.getByText('内嗅皮层')).toBeTruthy()
  })

  it('renders confidence percentage', () => {
    render(<AIExplanationCard explanation={makeExplanation({ confidence: 0.9 })} />)
    expect(screen.getByText('90%')).toBeTruthy()
  })

  it('shows hallucination warning names in a role=alert box', () => {
    render(
      <AIExplanationCard
        explanation={makeExplanation({ hallucination_warning: ['颞极', '扣带回'] })}
      />,
    )
    const alert = screen.getByRole('alert')
    expect(alert).toBeTruthy()
    expect(screen.getByText('颞极')).toBeTruthy()
    expect(screen.getByText('扣带回')).toBeTruthy()
  })

  it('hides the warning box when there is no hallucination warning', () => {
    render(<AIExplanationCard explanation={makeExplanation()} />)
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('hides summary, key points and evidence chips when absent', () => {
    render(
      <AIExplanationCard
        explanation={makeExplanation({ summary: '', key_points: [], evidence_entities: [] })}
      />,
    )
    expect(screen.getByText('海马主要参与情景记忆的编码与巩固。')).toBeTruthy()
    expect(screen.queryByText('Key Points')).toBeNull()
    expect(screen.queryByText('证据来源')).toBeNull()
  })
})

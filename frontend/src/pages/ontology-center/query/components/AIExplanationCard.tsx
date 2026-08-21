import { AlertTriangle, Bot, Sparkles } from 'lucide-react'
import type { OntologyLLMResponse } from '../../../../api/ontologyQueryApi'

/**
 * AI Explanation 卡片（中间栏第二模块）。
 *
 * 与结构化证据严格区分：answer 是 LLM 基于结构化结果的医学解释；小标签
 * 「Generated from Knowledge Graph」明确其生成来源；hallucination_warning
 * 是 response_validator 标记的未见于 evidence 的脑区名称（提示但不阻断）；
 * evidence_entities 来自结构化结果（不采信 LLM 自报）。
 */
export function AIExplanationCard({ explanation }: { explanation: OntologyLLMResponse }) {
  const hasWarning = explanation.hallucination_warning.length > 0

  return (
    <section className="oqd-ai" aria-label="AI Explanation">
      <div className="oqd-card-header">
        <Bot size={14} className="oqd-ai-icon" aria-hidden="true" />
        <h3>AI Explanation</h3>
        <span className="oqd-ai-tag">Generated from Knowledge Graph</span>
        <span className="oqd-ai-confidence">{Math.round(explanation.confidence * 100)}%</span>
      </div>
      {hasWarning && (
        <div className="oqd-ai-warning" role="alert">
          <AlertTriangle size={14} className="oqd-ai-warning-icon" aria-hidden="true" />
          <div className="oqd-ai-warning-body">
            <span>检测到回答中出现未见于证据的脑区名称（可能为幻觉）：</span>
            <ul>
              {explanation.hallucination_warning.map(name => (
                <li key={name}>{name}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <p className="oqd-ai-text">{explanation.answer}</p>
      {explanation.summary && (
        <p className="oqd-ai-summary">
          <Sparkles size={12} aria-hidden="true" />
          <span>{explanation.summary}</span>
        </p>
      )}
      {explanation.key_points.length > 0 && (
        <div className="oqd-ai-points">
          <h4>Key Points</h4>
          <ul>
            {explanation.key_points.map((point, index) => (
              <li key={index}>{point}</li>
            ))}
          </ul>
        </div>
      )}
      {explanation.evidence_entities.length > 0 && (
        <div className="oqd-ai-evidence">
          <span className="oqd-ai-evidence-label">证据来源</span>
          {explanation.evidence_entities.map(entity => (
            <span key={entity} className="oqd-ai-evidence-chip">
              {entity}
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

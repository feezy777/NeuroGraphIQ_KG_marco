import { useMemo, useState } from 'react'
import type { ClaimComponent, WorkbenchPassage } from './types'
import { COMPONENT_LABEL } from './types'
import { computeTmpCoverage } from './claimCoverage'
import { PassageEvidenceCard } from './PassageEvidenceCard'

interface Props {
  paper: {
    paperId: string | null
    pmid: string
    doi: string | null
    title: string
    journal: string
    year: string
  }
  components: ClaimComponent[]
  passages: WorkbenchPassage[]
  selectedHashes: Set<string>
  onTogglePassage: (hash: string, checked: boolean) => void
  onBack: () => void
}

/** 论文↔证据视图:← 返回论文列表 + Paper Summary + Claim Coverage + 候选佐证原文 */
export function PaperEvidenceView({
  paper,
  components,
  passages,
  selectedHashes,
  onTogglePassage,
  onBack,
}: Props) {
  const coverage = useMemo(() => computeTmpCoverage(components, passages), [components, passages])
  const supported = new Set(coverage.supported_components)
  const [showContextHash, setShowContextHash] = useState<string | null>(null)

  return (
    <div className="evidence-paper-view" data-testid="evidence-paper-view">
      <button type="button" className="evidence-paper-back" data-testid="evidence-paper-back" onClick={onBack}>
        ← 返回论文列表
      </button>

      <div className="evidence-paper-summary" data-testid="evidence-paper-summary">
        <h4 className="evidence-paper-title">{paper.title || '(无标题)'}</h4>
        <span className="ew-meta">{paper.journal}{paper.year ? ` · ${paper.year}` : ''}</span>
        <span className="ew-meta">PMID {paper.pmid || '—'} · DOI {paper.doi || '—'}</span>
      </div>

      <div className="evidence-paper-coverage" data-testid="evidence-paper-coverage">
        <h4>Claim Coverage</h4>
        <table className="evidence-coverage-table">
          <thead>
            <tr>
              <th>组件</th>
              <th>取值</th>
              <th>覆盖</th>
            </tr>
          </thead>
          <tbody>
            {components.map(c => {
              const ok = supported.has(c.component_type)
              return (
                <tr key={c.component_type} data-testid="evidence-coverage-row">
                  <td>{COMPONENT_LABEL[c.component_type] ?? c.component_type}</td>
                  <td className="evidence-coverage-value">{c.statement}</td>
                  <td className={ok ? 'evidence-coverage-ok' : 'evidence-coverage-miss'}>
                    {ok ? '✓' : '○'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        <div className="evidence-coverage-footer">
          Coverage {coverage.supported_components.length}/{coverage.required_components.length}
        </div>
      </div>

      <div className="evidence-paper-passages">
        <h4>候选佐证原文</h4>
        {passages.length === 0 && <div className="evidence-candidates-empty">该论文暂无候选片段</div>}
        {passages.map(p => (
          <PassageEvidenceCard
            key={p.hash}
            passage={p}
            components={components}
            selected={selectedHashes.has(p.hash)}
            translation=""
            readOnly
            onToggleSelect={checked => onTogglePassage(p.hash, checked)}
            onLevelChange={() => undefined}
            onComponentToggle={() => undefined}
            onTranslationChange={() => undefined}
            onTranslate={() => undefined}
            onCopy={() => undefined}
            onShowContext={() => setShowContextHash(prev => (prev === p.hash ? null : p.hash))}
            showContext={showContextHash === p.hash}
          />
        ))}
      </div>
    </div>
  )
}

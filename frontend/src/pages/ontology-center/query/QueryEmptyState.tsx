import { AlertTriangle } from 'lucide-react'
import type { OntologyQueryCandidate } from '../../../api/ontologyQueryApi'
import { EmptyState } from '../ui/EmptyState'

export type QueryEmptyVariant = 'initial' | 'unresolved' | 'empty'

const VARIANT_CONTENT: Record<QueryEmptyVariant, { title: string; reason: string }> = {
  initial: {
    title: '请输入问题',
    reason: '支持查询脑区亚区、连接、回路、功能、细胞与分子',
  },
  unresolved: {
    title: '未找到匹配脑区',
    reason: '请使用标准脑区名称，例如「海马」「额上回」',
  },
  empty: {
    title: '暂无相关记录',
    reason: '该脑区在当前分类下没有可展示的记录',
  },
}

/** 空/异常状态：未输入、未识别、无结果（附带后端 warnings 说明原因）
 *  unresolved 且后端返回 fuzzy 候选时，渲染可点击候选 chips（点击直接以候选名重新查询）。 */
export function QueryEmptyState({
  variant,
  warnings,
  candidates,
  onPickCandidate,
}: {
  variant: QueryEmptyVariant
  warnings?: string[]
  candidates?: OntologyQueryCandidate[]
  onPickCandidate?: (name: string) => void
}) {
  const content = VARIANT_CONTENT[variant]
  return (
    <div className="oq-empty-state">
      {variant !== 'initial' && (
        <AlertTriangle size={14} className="oq-empty-icon" aria-hidden="true" />
      )}
      <EmptyState title={content.title} reason={content.reason} />
      {warnings && warnings.length > 0 && (
        <ul className="oq-warnings">
          {warnings.map((warning, index) => (
            <li key={index}>{warning}</li>
          ))}
        </ul>
      )}
      {candidates && candidates.length > 0 && (
        <div className="oqd-candidates">
          <span className="oqd-candidates-label">候选脑区（未自动选择，点击直接查询）</span>
          <div className="oqd-candidate-chips">
            {candidates.map(candidate => (
              <button
                key={candidate.candidate}
                type="button"
                className="oqd-candidate-chip"
                title={`点击查询「${candidate.candidate}」`}
                onClick={() => onPickCandidate?.(candidate.candidate)}
              >
                {candidate.candidate}
                {candidate.confidence != null && (
                  <span className="oqd-candidate-conf">
                    {Math.round(candidate.confidence * 100)}%
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

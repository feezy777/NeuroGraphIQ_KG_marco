import type { EvidenceLevel, WorkbenchPassage } from './types'

/**
 * 将后端宽松的候选片段(Record)转换为工作台片段(WorkbenchPassage)。
 * 供证据候选模块 / 人工审核模块 / EvidenceReviewModal 共用。
 */
export function candidatePassagesToWorkbench(
  passages: Array<Record<string, unknown>>,
  paperId: string | null,
): WorkbenchPassage[] {
  return passages
    .filter((p): p is Record<string, unknown> & { passage: string } => Boolean(p.passage))
    .map((p, i) => ({
      hash: `${paperId ?? 'paper'}-${i}-${p.passage}`,
      source_scope: (p.source_scope === 'fulltext' ? 'fulltext' : 'abstract') as 'abstract' | 'fulltext',
      section_title: (p.section_title as string | null) ?? null,
      paragraph_index: (p.paragraph_index as number | null) ?? null,
      paragraph_id: (p.paragraph_id as string | null) ?? null,
      paper_id: (p.paper_id as string | null) ?? null,
      paper_passage_id: (p.paper_passage_id as string | null) ?? null,
      passage: p.passage,
      translation_zh: null,
      direction: (p.direction as WorkbenchPassage['direction']) ?? 'supports',
      evidence_level: (p.evidence_level as EvidenceLevel) ?? 'indirect',
      reason: String(p.reason ?? ''),
      confidence: Number(p.confidence ?? 0),
      semantic_confidence: p.semantic_confidence != null ? Number(p.semantic_confidence) : null,
      source_locator: (p.source_locator as string | null) ?? null,
      source_verified: Boolean(p.source_verified),
      source_verification_method: (p.source_verification_method as string | null) ?? null,
      supported_components: Array.isArray(p.supported_components) ? (p.supported_components as string[]) : [],
      evidence_dimension: (p.evidence_dimension as WorkbenchPassage['evidence_dimension']) ?? null,
    }))
}

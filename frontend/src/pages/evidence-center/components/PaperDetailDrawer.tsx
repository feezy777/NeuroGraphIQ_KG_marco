import { useCallback, useEffect, useState } from 'react'
import {
  getEvidencePaperDetail,
  type EvidencePaperDetail,
  type EvidencePaperParagraph,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'

interface Props {
  paperId: string
  onClose: () => void
}

interface ParagraphGroup {
  section: string
  paragraphs: EvidencePaperParagraph[]
}

function isAbstractParagraph(p: EvidencePaperParagraph): boolean {
  return p.source_scope === 'abstract' || (p.section_title ?? '').toLowerCase() === 'abstract'
}

function groupFulltextParagraphs(paragraphs: EvidencePaperParagraph[]): ParagraphGroup[] {
  const groups: ParagraphGroup[] = []
  for (const p of paragraphs) {
    if (isAbstractParagraph(p)) continue
    const section = p.section_title || '正文'
    const group = groups.find(g => g.section === section)
    if (group) {
      group.paragraphs.push(p)
    } else {
      groups.push({ section, paragraphs: [p] })
    }
  }
  return groups
}

export function PaperDetailDrawer({ paperId, onClose }: Props) {
  const { openTarget } = useEvidenceCenter()
  const [detail, setDetail] = useState<EvidencePaperDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [openSections, setOpenSections] = useState<Set<string>>(new Set())

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setDetail(null)
    setOpenSections(new Set())
    getEvidencePaperDetail(paperId)
      .then(d => { if (!cancelled) setDetail(d) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [paperId])

  const toggleSection = useCallback((section: string) => {
    setOpenSections(prev => {
      const next = new Set(prev)
      if (next.has(section)) {
        next.delete(section)
      } else {
        next.add(section)
      }
      return next
    })
  }, [])

  const paragraphs = detail?.paragraphs ?? []
  const abstractParagraphs = paragraphs.filter(isAbstractParagraph)
  const fulltextGroups = groupFulltextParagraphs(paragraphs)

  return (
    <div className="evidence-drawer-overlay" onClick={onClose}>
      <aside
        className="evidence-drawer"
        role="dialog"
        aria-label="论文详情"
        data-testid="paper-detail-drawer"
        onClick={e => e.stopPropagation()}
      >
        <header className="evidence-drawer-head">
          <h4 className="evidence-drawer-title">{detail?.paper.title ?? '论文详情'}</h4>
          <button type="button" className="evidence-drawer-close" aria-label="关闭" onClick={onClose}>×</button>
        </header>
        <div className="evidence-drawer-body">
          {loading && <div className="paper-drawer-loading">加载中…</div>}
          {!loading && error && (
            <div className="paper-drawer-error">
              <p>论文详情加载失败:{error}</p>
            </div>
          )}
          {!loading && detail && (
            <>
              <div className="paper-drawer-meta">
                <div className="paper-drawer-meta-row">
                  <span className="paper-drawer-meta-label">期刊</span>
                  <span className="paper-drawer-meta-value">
                    {detail.paper.journal || '—'}
                    {detail.paper.publication_year ? ` (${detail.paper.publication_year})` : ''}
                  </span>
                </div>
                <div className="paper-drawer-meta-row">
                  <span className="paper-drawer-meta-label">PMID</span>
                  <span className="paper-drawer-meta-value">{detail.paper.pmid ?? '—'}</span>
                </div>
                <div className="paper-drawer-meta-row">
                  <span className="paper-drawer-meta-label">PMCID</span>
                  <span className="paper-drawer-meta-value">{detail.paper.pmcid ?? '—'}</span>
                </div>
                <div className="paper-drawer-meta-row">
                  <span className="paper-drawer-meta-label">DOI</span>
                  <span className="paper-drawer-meta-value">{detail.paper.doi ?? '—'}</span>
                </div>
                <div className="paper-drawer-meta-row">
                  <span className="paper-drawer-meta-label">关联证据</span>
                  <span className="paper-drawer-meta-value">{detail.evidence_count} 条</span>
                </div>
              </div>

              {abstractParagraphs.length > 0 && (
                <section className="paper-drawer-abstract">
                  <h5 className="paper-drawer-section-title">摘要</h5>
                  {abstractParagraphs.map(p => (
                    <p key={p.paragraph_id} className="paper-drawer-paragraph">{p.passage_text}</p>
                  ))}
                </section>
              )}

              {fulltextGroups.map(group => {
                const isOpen = openSections.has(group.section)
                return (
                  <section key={group.section} className="paper-drawer-section">
                    <button
                      type="button"
                      className="paper-drawer-section-head"
                      onClick={() => toggleSection(group.section)}
                    >
                      <span>{group.section}</span>
                      <span className="paper-drawer-section-toggle">{isOpen ? '收起' : '展开'}</span>
                    </button>
                    {isOpen && (
                      <div className="paper-drawer-section-body">
                        {group.paragraphs.map(p => (
                          <p key={p.paragraph_id} className="paper-drawer-paragraph">{p.passage_text}</p>
                        ))}
                      </div>
                    )}
                  </section>
                )
              })}

              {detail.targets.length > 0 && (
                <section className="paper-drawer-targets">
                  <h5 className="paper-drawer-section-title">关联知识对象</h5>
                  <div className="paper-drawer-target-list">
                    {detail.targets.map(t => (
                      <button
                        key={`${t.target_type}-${t.target_id}`}
                        type="button"
                        className="paper-drawer-target-chip"
                        onClick={() => openTarget(t.target_type, t.target_id)}
                      >
                        {t.target_type} · {t.target_id}
                      </button>
                    ))}
                  </div>
                </section>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}

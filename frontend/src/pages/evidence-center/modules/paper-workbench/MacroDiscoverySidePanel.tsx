/**
 * 证据发现工作台右栏(第 1 阶段):
 *  ① 规则验证(Overall + R1-R6 六卡,有数据按真实状态,无数据 PENDING,禁止伪造 PASS)
 *  ② 处理进度(六项统计,骨架阶段为 0)
 *  ③ 已选候选证据(默认 0 条 + 空态文案,人工选择在后续阶段接入)
 */
import type { MacroCandidateView } from '../../../validation-center/macro-governance/useMacroCandidates'
import { useTaskPaperCount, useTaskReviewStats, useTaskSegmentCount, useTaskCandidatesVersion } from './pewStore'
import { pewListCandidates } from './pewApi'
import { useEffect, useState } from 'react'

type RuleTone = 'pass' | 'existing' | 'warning' | 'block' | 'pending'

const RULE_SPEC: ReadonlyArray<{ code: string; name: string; hint: string }> = [
  { code: 'R1', name: 'Brain Region Exists', hint: '源/目标脑区须在标准词典中存在' },
  { code: 'R2', name: 'Source != Target', hint: '源与目标不得为同一脑区' },
  { code: 'R3', name: 'Connection Type', hint: '连接类型须在合法词表内' },
  { code: 'R4', name: 'Direction', hint: '方向须合法(A→B / B→A / 双向)' },
  { code: 'R5', name: 'Duplicate Existing', hint: '与已有正式连接重复检查' },
  { code: 'R6', name: 'Hierarchy', hint: '父子层级冲突检查' },
]

const TONE_LABEL: Record<RuleTone, string> = {
  pass: 'PASS',
  existing: 'EXISTING',
  warning: 'WARNING',
  block: 'BLOCK',
  pending: 'PENDING',
}

const PROGRESS_ITEMS: ReadonlyArray<{ label: string }> = [
  { label: '论文' },
  { label: '疑似片段' },
  { label: 'AI已审核' },
  { label: 'Supported' },
  { label: 'Partial' },
  { label: 'Uncertain' },
  { label: 'Rejected' },
]

function toneOf(ruleCode: string, view: MacroCandidateView | null): { tone: RuleTone; detail: string } {
  const result = view?.ruleResult
  if (!result) return { tone: 'pending', detail: '待运行' }
  const rule = result.rules.find(r => r.code === ruleCode)
  const spec = RULE_SPEC.find(r => r.code === ruleCode)
  // R5:duplicate 命中已有(Final/Canonical/Mirror)→ “已有连接·证据增强”蓝色态
  if (ruleCode === 'R5' && result.duplicate_existing) {
    const dup = result.duplicate_existing
    const hit = Boolean((dup as Record<string, unknown>).final || (dup as Record<string, unknown>).canonical || (dup as Record<string, unknown>).mirror)
    if (hit) return { tone: 'existing', detail: `已有正式连接镜像(final/${String((dup as Record<string, unknown>).mirror)})` }
  }
  if (!rule) return { tone: 'pending', detail: '待运行' }
  if (rule.passed) return { tone: 'pass', detail: rule.detail || spec?.hint || '' }
  // 未通过:block 级 → BLOCK(红);普通级 → WARNING(黄)
  if (rule.severity === 'block') return { tone: 'block', detail: rule.detail || spec?.hint || '' }
  return { tone: 'warning', detail: rule.detail || spec?.hint || '' }
}

function overallOf(view: MacroCandidateView | null, evidenceEnhance: boolean): { tone: RuleTone; label: string } {
  const result = view?.ruleResult
  if (!result) return { tone: 'pending', label: '规则待运行' }
  // 已有连接·证据增强优先(该场景 R5 duplicate 命中属预期,不视为阻断)
  if (evidenceEnhance) return { tone: 'existing', label: '已有连接·证据增强' }
  if (result.blocked) return { tone: 'block', label: '结构规则阻断' }
  if (result.passed) return { tone: 'pass', label: '规则通过' }
  return { tone: 'warning', label: '结构规则提示' }
}

function Badge({ tone }: { tone: RuleTone }) {
  return <span className={`edw-rule-badge edw-rule-badge-${tone}`} data-testid={`edw-rule-badge-${tone}`}>{TONE_LABEL[tone]}</span>
}

export function MacroDiscoverySidePanel({ view, evidenceEnhance, rankingId }: {
  view: MacroCandidateView | null
  evidenceEnhance: boolean
  rankingId: string
}) {
  // 处理进度「论文」= 当前 Task Paper Workspace 数量(持久化;入库/移出后经 pewStore 即时同步)
  const taskPaperCount = useTaskPaperCount(rankingId)
  // 「疑似片段」= Step 2 函数筛选片段数(零 LLM;筛选后即时同步)
  const taskSegmentCount = useTaskSegmentCount(rankingId)
  const reviewStats = useTaskReviewStats(rankingId)
  const candVersion = useTaskCandidatesVersion(rankingId)
  const [selCands, setSelCands] = useState<Array<{ title: string; pmid: string }>>([])
  const [selStats, setSelStats] = useState({ total: 0, direct: 0, indirect: 0 })
  useEffect(() => {
    let cancelled = false
    pewListCandidates(rankingId)
      .then(r => {
        if (cancelled) return
        const main = r.items.filter(c => c.candidate_status === 'candidate')
        const sel = main.filter(c => c.selected_for_review)
        setSelCands(sel.map(c => ({ title: c.paper_title || '(未命名)', pmid: c.paper_pmid || '—' })))
        setSelStats({
          total: sel.length,
          direct: sel.filter(c => c.evidence_type === 'direct').length,
          indirect: sel.filter(c => c.evidence_type === 'indirect').length,
        })
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [rankingId, candVersion])
  // 已有正式连接(duplicate_existing 命中)→ 证据增强模式(蓝色);优先于 blocked 语义
  const dup = view?.ruleResult?.duplicate_existing
  const dupHit = Boolean(dup && ((dup as Record<string, unknown>).final || (dup as Record<string, unknown>).canonical || (dup as Record<string, unknown>).mirror))
  const isEnhance = evidenceEnhance || dupHit
  const overall = overallOf(view, isEnhance)
  const isBlock = !isEnhance && (view?.ruleResult?.blocked ?? false)

  return (
    <aside className="edw-side" data-testid="edw-side-panel">
      {/* ① 规则验证:Overall + R1-R6 */}
      <section className="edw-side-card" data-testid="edw-rule-validation">
        <h4 className="edw-side-title">规则验证</h4>
        <div className="edw-overall" data-testid="edw-rule-overall">
          <Badge tone={overall.tone} />
          <span className={`edw-overall-label edw-overall-${isBlock ? 'block' : overall.tone}`}>
            {overall.label}
          </span>
        </div>
        <div className="edw-rule-list">
          {RULE_SPEC.map(spec => {
            const { tone, detail } = toneOf(spec.code, view)
            return (
              <div className={`edw-rule edw-rule-${tone}`} data-testid={`edw-rule-${spec.code}`} key={spec.code}>
                <div className="edw-rule-line">
                  <span className="edw-rule-code">{spec.code}</span>
                  <span className="edw-rule-name">{spec.name}</span>
                  <span style={{ flex: 1 }} />
                  <Badge tone={tone} />
                </div>
                <div className="edw-rule-detail">{detail}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ② 处理进度 */}
      <section className="edw-side-card" data-testid="edw-progress">
        <h4 className="edw-side-title">处理进度</h4>
        <div className="edw-progress-grid">
          {PROGRESS_ITEMS.map(item => {
            const value = item.label === '论文' ? taskPaperCount
              : item.label === '疑似片段' ? taskSegmentCount
              : item.label === 'AI已审核' ? reviewStats.reviewed
              : item.label === 'Supported' ? reviewStats.supported
              : item.label === 'Partial' ? reviewStats.partial
              : item.label === 'Uncertain' ? reviewStats.uncertain
              : reviewStats.notSupported
            return (
              <div className="edw-progress-item" key={item.label}>
                <div className="edw-progress-value" data-testid="edw-progress-value">{value}</div>
                <div className="edw-progress-label">{item.label}</div>
              </div>
            )
          })}
        </div>
      </section>

      {/* ③ 已选候选证据(Step 4 实时) */}
      <section className="edw-side-card" data-testid="edw-selected-evidence">
        <h4 className="edw-side-title">
          已选候选证据
          <span className="edw-selected-count" data-testid="edw-selected-count">
            {selStats.total > 0 || candVersion > 0 ? `已选:${selStats.total} / ${selCands.length}` : '0 条'}
          </span>
        </h4>
        {selCands.length === 0 && candVersion === 0 && (
          <p className="edw-selected-empty" data-testid="edw-selected-empty">
            尚未形成可提交证据。<br />
            完成论文检索、片段筛选和 AI 语义审核后,可在此选择证据。
          </p>
        )}
        {selCands.length > 0 && (
          <div data-testid="edw-selected-list" style={{ display: 'grid', gap: 6 }}>
            <div className="edw-muted-hint" style={{ fontSize: 11.5 }}>
              Direct:{selStats.direct} · Indirect:{selStats.indirect} · 来源论文:{new Set(selCands.map(c => c.title)).size}
            </div>
            {selCands.map((c, i) => (
              <div key={i} className="edw-selected-item">
                ✓ {c.title.length > 36 ? `${c.title.slice(0, 36)}…` : c.title}
                <div className="edw-muted-hint">PMID {c.pmid}</div>
              </div>
            ))}
          </div>
        )}
      </section>
    </aside>
  )
}

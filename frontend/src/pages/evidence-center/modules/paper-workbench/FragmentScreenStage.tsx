/**
 * Step 2:系统函数筛选疑似证据片段(零 LLM)。
 * 输入 = 当前 Task Paper Workspace(ranking_id 绑定);文本优先 FullText → Abstract → Title。
 * 分档 strong/medium/weak;幂等(唯一键冲突更新信号,不重复建行);
 * 底部统一 [下一步:AI语义审核](下一阶段批量审核,本阶段不逐条送 AI)。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  pewListSegments,
  pewRunSegments,
  type PewScreenStats,
  type PewSegment,
} from './pewApi'
import { notifyTaskSegmentsChanged } from './pewStore'

export type LevelFilter = 'all' | 'strong' | 'medium' | 'weak'

const LEVEL_LABEL: Record<string, string> = { strong: 'Strong', medium: 'Medium', weak: 'Weak' }
const SOURCE_LABEL: Record<string, string> = { fulltext: '全文', abstract: '摘要', title: '标题' }
const PROXIMITY_LABEL: Record<string, string> = {
  same_sentence: 'Same sentence',
  adjacent_sentence: 'Adjacent sentence',
  same_paragraph: 'Same paragraph',
  same_section: 'Same section',
}

const EMPTY_STATS: PewScreenStats = {
  processed: 0, fulltext: 0, abstract: 0, title: 0, no_text: 0,
  strong: 0, medium: 0, weak: 0,
}

const CHUNK_SIZE = 20

function addStats(a: PewScreenStats, b: PewScreenStats): PewScreenStats {
  return {
    processed: a.processed + b.processed,
    fulltext: a.fulltext + b.fulltext,
    abstract: a.abstract + b.abstract,
    title: a.title + b.title,
    no_text: a.no_text + b.no_text,
    strong: a.strong + b.strong,
    medium: a.medium + b.medium,
    weak: a.weak + b.weak,
  }
}

function errText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export function FragmentScreenStage({ rankingId, connectionType, paperIds, onBackToSearch, onNextToAi }: {
  rankingId: string
  connectionType: string
  paperIds: string[]
  onBackToSearch: () => void
  onNextToAi: () => void
}) {
  const [segments, setSegments] = useState<PewSegment[]>([])
  const [loaded, setLoaded] = useState(false)
  const [running, setRunning] = useState(false)
  const [stats, setStats] = useState<PewScreenStats>(EMPTY_STATS)
  // 运行时进度(正在筛选论文 i / N · 全文 x · 摘要 y · 无文本 z · 已发现片段 n)
  const [progress, setProgress] = useState<{ index: number; total: number }>({ index: 0, total: 0 })
  const [filter, setFilter] = useState<LevelFilter>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [msg, setMsg] = useState<string | null>(null)

  // 进入/刷新 Step2:读取持久化片段(恢复状态;不自动重跑)
  // 筛选行为恒为「全任务论文」,故可用当前 paperIds 长度推导 processed,其余计数来自现有片段
  const loadSegments = useCallback(async () => {
    try {
      const r = await pewListSegments(rankingId)
      setSegments(r.items)
      setStats(prev => {
        if (prev.processed > 0 || r.items.length === 0) return prev
        return {
          processed: paperIds.length,
          fulltext: 0, abstract: 0, title: 0, no_text: 0,
          strong: r.items.filter(s => s.candidate_level === 'strong').length,
          medium: r.items.filter(s => s.candidate_level === 'medium').length,
          weak: r.items.filter(s => s.candidate_level === 'weak').length,
        }
      })
    } catch (err) {
      setMsg(`片段加载失败:${errText(err)}`)
    } finally {
      setLoaded(true)
    }
  }, [rankingId, paperIds.length])

  useEffect(() => { void loadSegments() }, [loadSegments])

  // 分批运行(提供实时进度;每批后端幂等更新)
  const runScreen = useCallback(async () => {
    if (running) return
    setRunning(true)
    setMsg(null)
    setStats(EMPTY_STATS)
    setProgress({ index: 0, total: paperIds.length })
    const acc = { ...EMPTY_STATS }
    try {
      for (let i = 0; i < paperIds.length; i += CHUNK_SIZE) {
        const chunk = paperIds.slice(i, i + CHUNK_SIZE)
        setProgress({ index: Math.min(i + CHUNK_SIZE, paperIds.length), total: paperIds.length })
        const r = await pewRunSegments(rankingId, chunk, connectionType)
        Object.assign(acc, addStats(acc, r.stats))
        setStats({ ...acc })
        setProgress({ index: Math.min(i + CHUNK_SIZE, paperIds.length), total: paperIds.length })
      }
      await loadSegments()
      notifyTaskSegmentsChanged(rankingId)
      setMsg(acc.strong + acc.medium + acc.weak > 0 ? '筛选完成' : '当前论文集合中未发现满足规则的疑似证据片段。')
    } catch (err) {
      setMsg(`筛选失败:${errText(err)}`)
    } finally {
      setRunning(false)
    }
  }, [running, paperIds, rankingId, connectionType, loadSegments])

  // 无候选论文 = 已处理论文数 - 产片段论文数
  const noCandidatePapers = useMemo(() => {
    const withSeg = new Set(segments.map(s => s.paper_id))
    return Math.max(0, stats.processed - withSeg.size)
  }, [stats.processed, segments])

  const visible = useMemo(() => {
    const sorted = segments // 后端已按 score DESC / 等级 / 来源排序
    return filter === 'all' ? sorted : sorted.filter(s => s.candidate_level === filter)
  }, [segments, filter])

  const levelCount = (lv: string) => segments.filter(s => s.candidate_level === lv).length

  const toggleExpanded = (id: string) => {
    setExpanded(prev => {
      const n = new Set(prev)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  }

  const sourceTag = (s: PewSegment) => SOURCE_LABEL[s.source_type] ?? s.source_type
  const levelTone = (lv: string | null) =>
    lv === 'strong' ? 'edw-lvl-strong' : lv === 'medium' ? 'edw-lvl-medium' : 'edw-lvl-weak'

  return (
    <div className="edw-stage" data-testid="edw-stage-2">
      {/* 标题 + 右上角动作区:唯一主流程按钮[下一步:AI语义审核]+次级[重新筛选] */}
      <div className="edw-stage-head edw-stage-head-row" data-testid="edw-s2-head">
        <div>
          <h3 className="edw-stage-title">片段筛选</h3>
          <p className="edw-stage-desc">
            系统正在使用脑区别名、关系词和文本位置规则,从当前任务论文中筛选可能包含连接证据的原文片段。本阶段尚未使用大模型。
          </p>
        </div>
        <div className="edw-head-actions">
          <button
            type="button" className="btn"
            disabled={running || paperIds.length === 0}
            data-testid="edw-run-screen-btn"
            onClick={() => void runScreen()}
          >
            {running ? '筛选进行中…' : loaded && (levelCount('strong') + levelCount('medium') + levelCount('weak')) > 0 ? '重新筛选' : '开始筛选'}
          </button>
          <button
            type="button" className="btn btn-primary"
            disabled={running || segments.length === 0}
            title={segments.length === 0 ? '当前没有可进入 AI 审核的疑似片段。' : undefined}
            data-testid="edw-next-ai-btn"
            onClick={onNextToAi}
          >
            下一步:AI语义审核
          </button>
        </div>
      </div>
      <div className="edw-muted-hint" style={{ marginBottom: 10 }}>
        {paperIds.length} 篇论文 · 零 LLM · 重复运行仅更新信号,不生成重复片段
      </div>

      {msg && <div className="edw-feedback" data-testid="edw-screen-msg">{msg}</div>}

      {/* 执行进度 */}
      {running && (
        <div className="edw-screen-progress" data-testid="edw-screen-progress">
          <span>正在筛选论文 {progress.index} / {progress.total}</span>
          <span> · 全文 {stats.fulltext}</span>
          <span> · 摘要 {stats.abstract}</span>
          <span> · 无可用文本 {stats.no_text}</span>
          <span> · 已发现疑似片段 {stats.strong + stats.medium + stats.weak}</span>
        </div>
      )}

      {/* 完成统计 */}
      <div className="edw-stats edw-stats-results" data-testid="edw-screen-stats">
        <div className="edw-stat"><div className="edw-stat-value">{stats.processed}</div><div className="edw-stat-label">处理论文</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-stat-found">{stats.strong + stats.medium + stats.weak}</div><div className="edw-stat-label">发现疑似片段</div></div>
        <div className="edw-stat"><div className="edw-stat-value edw-lvl-strong-txt">{stats.strong}</div><div className="edw-stat-label">Strong</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{stats.medium}</div><div className="edw-stat-label">Medium</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{stats.weak}</div><div className="edw-stat-label">Weak</div></div>
        <div className="edw-stat"><div className="edw-stat-value">{noCandidatePapers}</div><div className="edw-stat-label">无候选论文</div></div>
      </div>

      {/* 等级筛选 */}
      <div className="edw-lvl-tabs" data-testid="edw-lvl-tabs">
        {(['all', 'strong', 'medium', 'weak'] as LevelFilter[]).map(lv => (
          <button key={lv} type="button"
            className={`btn btn-sm ${filter === lv ? 'btn-primary' : ''}`}
            data-testid={`edw-lvl-tab-${lv}`}
            onClick={() => setFilter(lv)}>
            {lv === 'all' ? `全部(${segments.length})` : `${LEVEL_LABEL[lv]}(${levelCount(lv)})`}
          </button>
        ))}
      </div>

      {/* 零结果空态(不降标准、不调用 LLM) */}
      {loaded && !running && segments.length === 0 && (
        <div className="edw-noresult" data-testid="edw-screen-empty">
          <p className="edw-noresult-title">当前论文集合中未发现满足规则的疑似证据片段。</p>
          <p className="edw-muted-hint">未自动调用大模型;不会因 0 结果降低规则标准。</p>
          <button type="button" className="btn btn-sm" data-testid="edw-back-to-search-btn" onClick={onBackToSearch}>
            返回论文检索
          </button>
        </div>
      )}

      {/* 片段列表 */}
      {segments.length > 0 && (
        <div className="edw-frag-list" data-testid="edw-frag-list">
          {visible.map(s => (
            <div className={`edw-frag-card ${levelTone(s.candidate_level)}`} key={s.segment_id} data-testid={`edw-frag-${s.segment_id}`}>
              <div className="edw-frag-head">
                <span className="edw-frag-title">{s.paper_title || '(未命名)'}</span>
                <span className={`edw-badge ${s.candidate_level === 'strong' ? 'edw-badge-created' : s.candidate_level === 'medium' ? 'edw-badge-exists' : 'edw-badge-content'}`} data-testid={`edw-frag-level-${s.segment_id}`}>
                  {LEVEL_LABEL[s.candidate_level ?? ''] ?? s.candidate_level}
                </span>
              </div>
              <div className="edw-muted-hint">
                PMID {s.paper_pmid || '—'}{s.paper_doi ? ` · DOI ${s.paper_doi}` : ''} · Section {s.section || '—'}
              </div>
              <p className="edw-frag-sentence" data-testid={`edw-frag-sentence-${s.segment_id}`}>{s.sentence}</p>
              {expanded.has(s.segment_id) && (
                <div className="edw-frag-context" data-testid={`edw-frag-context-${s.segment_id}`}>
                  {s.context_before && <p className="edw-muted-hint">上一句:{s.context_before}</p>}
                  <p className="edw-muted-hint">当前句:{s.sentence}</p>
                  {s.context_after && <p className="edw-muted-hint">下一句:{s.context_after}</p>}
                </div>
              )}
              <div className="edw-frag-tags">
                <span className="edw-chip">Source ✓ {s.matched_source ?? '—'}</span>
                <span className="edw-chip">Target ✓ {s.matched_target ?? '—'}</span>
                {(s.relation_terms ?? []).slice(0, 3).map(w => <span className="edw-chip" key={w}>{w}</span>)}
                <span className="edw-chip">{PROXIMITY_LABEL[s.proximity] ?? s.proximity}</span>
                <span className="edw-chip">{sourceTag(s)}</span>
                <span className="edw-chip">Rule Score {s.rule_score != null ? s.rule_score.toFixed(2) : '—'}</span>
              </div>
              <div className="edw-frag-actions">
                <button type="button" className="btn btn-sm" data-testid={`edw-frag-toggle-${s.segment_id}`} onClick={() => toggleExpanded(s.segment_id)}>
                  {expanded.has(s.segment_id) ? '收起上下文' : '查看上下文'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}


    </div>
  )
}

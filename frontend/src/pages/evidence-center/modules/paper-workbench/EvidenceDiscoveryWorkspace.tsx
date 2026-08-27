/**
 * Evidence Discovery Workspace — Step 1「论文检索」正式接线(第 2 阶段)。
 * 流程:默认检索词(canonical aliases + 连接类型同义词,可编辑)
 *   → 真实检索(现有 multi_search) → PMID/DOI/标准化标题三级去重
 *   → 自动写入 Paper Library(paper_sources,复用已有) + 绑定当前任务(Task Paper Workspace)
 *   → 任务级持久化(刷新/切任务恢复;pew_papers)。
 * 仅到「Task Papers」为止:不出 Evidence/片段/AI 审核;Stepper 常驻 Step 1,
 * ②片段筛选仅显示 ready 态(不处理点击)。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { listEvidencePapers, type EvidencePaperItem } from '../../../../api/endpoints'
import { PaperDetailDrawer } from '../../components/PaperDetailDrawer'
import {
  pewInitTaskPapers,
  pewListPapers,
  pewRemoveTaskPaper,
  pewSearch,
  pewSuggestQueries,
  pewUpsertPapers,
  type PewImportStats,
  type PewPaperRow,
  type PewSearchPaper,
  type PwQuery,
} from './pewApi'
import { notifyTaskPapersChanged, useTaskSegmentCount } from './pewStore'
import { FragmentScreenStage } from './FragmentScreenStage'
import { AiReviewStage } from './AiReviewStage'
import { EvidenceCandidatesStage } from './EvidenceCandidatesStage'

export type DiscoveryStage = 1 | 2 | 3 | 4

export const DISCOVERY_STAGES: ReadonlyArray<{ no: DiscoveryStage; label: string }> = [
  { no: 1, label: '论文检索' },
  { no: 2, label: '片段筛选' },
  { no: 3, label: 'AI语义审核' },
  { no: 4, label: '候选证据' },
]

type SearchPhase = 'idle' | 'searching' | 'done' | 'search_error'

interface UpsertStats {
  found: number
  reused: number
  created: number
}

interface SearchError {
  kind: 'search_failed' | 'partial_queries' | 'upsert_failed' | 'link_failed'
  message: string
}

function msgText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** PMID > DOI > 标准化标题(三级去重键;不收录 None 的论文) */
function paperKey(p: { pmid?: string | null; doi?: string | null; title?: string | null }): string | null {
  if (p.pmid?.trim()) return `pmid:${p.pmid.trim()}`
  if (p.doi?.trim()) return `doi:${p.doi.trim().toLowerCase()}`
  if (p.title?.trim()) return `title:${p.title.trim().toLowerCase().replace(/\s+/g, ' ')}`
  return null
}

function errTextOf(err: unknown): string {
  return msgText(err).slice(0, 160)
}

export function EvidenceDiscoveryWorkspace({ rankingId, paperCount, workflowModeLabel, sourceRegion, targetRegion, connectionType }: {
  rankingId: string
  paperCount: number | null
  workflowModeLabel: string
  sourceRegion: string
  targetRegion: string
  connectionType: string
}) {
  const [activeStage, setActiveStage] = useState<DiscoveryStage>(1)
  const taskSegmentCount = useTaskSegmentCount(rankingId)
  const hasReviewable = taskSegmentCount > 0

  // ── 默认检索词(进入任务自动生成;点击「修改检索词」展开编辑) ──
  const [queries, setQueries] = useState<Array<PwQuery & { enabled: boolean }>>([])
  const [queryLoadError, setQueryLoadError] = useState<string | null>(null)
  const [editOpen, setEditOpen] = useState(false)

  // ── 检索/入库状态 ──
  const [phase, setPhase] = useState<SearchPhase>('idle')
  const [busy, setBusy] = useState(false)
  const [stats, setStats] = useState<UpsertStats | null>(null)
  const [searchError, setSearchError] = useState<SearchError | null>(null)
  const [failedQueryIds, setFailedQueryIds] = useState<number[]>([])
  const [lastQueryText, setLastQueryText] = useState('')

  // ── 数据:当前任务论文(持久化)+ 本次检索发现状态 ──
  const [taskPapers, setTaskPapers] = useState<PewPaperRow[]>([])
  const [discoveryState, setDiscoveryState] = useState<Map<string, 'created' | 'reused'>>(new Map())

  // ── 发现阶段线索自动整备(进入任务自动执行;无手动导入) ──
  const [initState, setInitState] = useState<'idle' | 'working' | 'done'>('idle')
  const [initStats, setInitStats] = useState<PewImportStats | null>(null)
  const [initFailed, setInitFailed] = useState<Array<{ paper_id: string; title: string | null; reason: string }>>([])
  const [showFailed, setShowFailed] = useState(false)

  // ── 检索完成提示(无二次确认;纯信息) ──
  const [searchDoneMsg, setSearchDoneMsg] = useState<string | null>(null)

  // ── 从论文库选择 Modal ──
  const [libOpen, setLibOpen] = useState(false)
  const [libQuery, setLibQuery] = useState('')
  const [libResults, setLibResults] = useState<EvidencePaperItem[] | null>(null)
  const [libSelected, setLibSelected] = useState<Set<string>>(new Set())
  const [libBusy, setLibBusy] = useState(false)

  // 论文详情(复用 Paper Library 详情抽屉)
  const [detailPaperId, setDetailPaperId] = useState<string | null>(null)

  // 按钮层级:更多 ▾ 菜单 / 卡片 ⋯ 菜单 / 下一步提示
  const [menuOpen, setMenuOpen] = useState(false)
  const [cardMenuPaperId, setCardMenuPaperId] = useState<string | null>(null)
  const [nextHint, setNextHint] = useState(false)

  const refreshPapers = useCallback(async () => {
    try {
      const r = await pewListPapers(rankingId)
      setTaskPapers(r.items)
    } catch {
      setTaskPapers([])
    }
  }, [rankingId])

  // 切任务重置(全部本地状态;数据恢复来自 pew_papers)
  useEffect(() => {
    setQueries([])
    setQueryLoadError(null)
    setEditOpen(false)
    setPhase('idle')
    setBusy(false)
    setStats(null)
    setSearchError(null)
    setFailedQueryIds([])
    setLastQueryText('')
    setTaskPapers([])
    setDiscoveryState(new Map())
    setInitState('idle')
    setInitStats(null)
    setInitFailed([])
    setShowFailed(false)
    setSearchDoneMsg(null)
    setLibOpen(false)
    setLibQuery('')
    setLibResults(null)
    setLibSelected(new Set())
    setDetailPaperId(null)
    setMenuOpen(false)
    setCardMenuPaperId(null)
    setNextHint(false)
    setActiveStage(1)
    void refreshPapers()
  }, [rankingId, refreshPapers])

  // 进入任务自动整备(幂等:仅在 idle 触发一次;force 重试失败项除外)
  const runInit = useCallback(async (force = false) => {
    if (!force && initState !== 'idle') return
    setInitState('working')
    try {
      const r = await pewInitTaskPapers(rankingId, force)
      setInitStats(r.stats)
      setInitFailed(r.failed ?? [])
      setInitState('done')
      await refreshPapers()
      if (!r.skipped) notifyTaskPapersChanged(rankingId)
    } catch (err) {
      setInitState('done')
      setSearchError({ kind: 'link_failed', message: `发现阶段线索自动整理失败:${errTextOf(err)}` })
    }
  }, [rankingId, initState, refreshPapers])

  // 仅在任务切换时触发一次(initState 变化不重跑,避免二次执行重锁 working)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { void runInit() }, [rankingId])

  // 自动生成默认检索词(canonical aliases + 同义词;不做前端脑区扩展)
  useEffect(() => {
    let cancelled = false
    pewSuggestQueries({
      source_region: sourceRegion,
      target_region: targetRegion,
      connection_type: connectionType,
    })
      .then(r => { if (!cancelled) setQueries(r.queries.map(q => ({ ...q, enabled: true }))) })
      .catch(err => { if (!cancelled) setQueryLoadError(errTextOf(err)) })
    return () => { cancelled = true }
  }, [sourceRegion, targetRegion, connectionType])

  const activeQueries = useMemo(
    () => queries.filter(q => q.enabled),
    [queries],
  )

  const toggleQuery = useCallback((i: number) => {
    setQueries(prev => prev.map((q, idx) => (idx === i ? { ...q, enabled: !q.enabled } : q)))
  }, [])

  const textareaQueries = useMemo(
    () => activeQueries.map(q => q.q),
    [activeQueries],
  )

  const handleSearch = useCallback(async (onlyFailed?: boolean) => {
    if (busy) return
    const chosen = onlyFailed
      ? activeQueries.filter((_, i) => failedQueryIds.includes(i))
      : activeQueries
    if (chosen.length === 0) {
      setSearchError({ kind: 'search_failed', message: '未选择任何检索词,请勾选至少一条后重试。' })
      return
    }
    setBusy(true)
    setPhase('searching')
    setSearchError(null)
    setFailedQueryIds([])
    try {
      const results = await Promise.allSettled(chosen.map(q =>
        pewSearch({
          source_region: sourceRegion,
          target_region: targetRegion,
          connection_type: connectionType,
          query: q.q,
          limit: 20,
        }),
      ))
      const merged = new Map<string, PewSearchPaper>()
      const failIdx: number[] = []
      results.forEach((r, i) => {
        if (r.status === 'rejected') {
          failIdx.push(i)
          return
        }
        for (const p of r.value.results) {
          const key = paperKey(p)
          if (key && !merged.has(key)) merged.set(key, p)
        }
      })
      setLastQueryText(chosen.map(q => q.q).join('\n'))
      setFailedQueryIds(failIdx)

      if (merged.size === 0) {
        setPhase('done')
        setStats(null)
        setSearchError(
          failIdx.length === chosen.length
            ? { kind: 'search_failed', message: '论文搜索失败(全部检索词请求未成功,请检查网络后重试)。' }
            : null,
        )
        setBusy(false)
        return
      }

      // 检索 → 自动入 Paper Library(三级去重) + 绑定当前任务
      let upsertErr: SearchError | null = null
      let reused = 0
      let created = 0
      try {
        const resp = await pewUpsertPapers(rankingId, [...merged.values()].map(p => ({
          pmid: p.pmid || null,
          doi: p.doi || null,
          title: p.title || '',
          authors: (p as { authors?: string | null }).authors ?? null,
          journal: p.journal || null,
          year: Number(p.year) > 1900 ? String(p.year) : null,
          abstract_available: Boolean(p.abstract),
          fulltext_available: false,
          source: p.source || 'search',
        })))
        const state = new Map<string, 'created' | 'reused'>()
        for (const p of resp.papers ?? []) {
          const s = (p as { state?: string }).state
          state.set(paperKey(p) ?? (p as { doi?: string }).doi ?? '', s === 'created' ? 'created' : 'reused')
          if (s === 'reused') reused += 1
          else created += 1
        }
        setDiscoveryState(state)
        setStats({ found: merged.size, reused, created })
        // bound=0 属正常(论文已全部在任务);关联失败以 papers 响应缺失为准
        if ((resp.papers?.length ?? 0) === 0 && merged.size > 0) {
          upsertErr = { kind: 'link_failed', message: `任务关联失败(已入库 ${merged.size} 篇,但未能绑定当前任务 workspace)。` }
        } else if ((resp.papers?.length ?? 0) < merged.size) {
          upsertErr = { kind: 'upsert_failed', message: '部分论文入库失败(数量不一致),以下条目可单独重试。' }
        }
      } catch (err) {
        upsertErr = { kind: 'upsert_failed', message: `论文入库失败:${errTextOf(err)}` }
      }
      setPhase('done')
      setSearchError(upsertErr ?? (failIdx.length > 0
        ? { kind: 'partial_queries', message: `有 ${failIdx.length} 条检索词未能检索,其余已并入结果。` }
        : null))
      setSearchDoneMsg(
        upsertErr == null
          ? `本次检索发现 ${merged.size} 篇 · 复用论文库 ${reused} · 新增 ${created} · 已全部加入当前任务`
          : null,
      )
      await refreshPapers()
      notifyTaskPapersChanged(rankingId)
    } catch (err) {
      setPhase('search_error')
      setSearchError({ kind: 'search_failed', message: `论文搜索失败:${errTextOf(err)}` })
    } finally {
      setBusy(false)
    }
  }, [busy, activeQueries, failedQueryIds, rankingId, sourceRegion, targetRegion, connectionType, refreshPapers])

  const handleRemovePaper = useCallback(async (paperId: string) => {
    try {
      await pewRemoveTaskPaper(rankingId, paperId)
      await refreshPapers()
      notifyTaskPapersChanged(rankingId)
    } catch (err) {
      setSearchError({ kind: 'link_failed', message: `移出当前任务失败:${errTextOf(err)}` })
    }
  }, [rankingId, refreshPapers])

  const runLibSearch = useCallback(async () => {
    setLibBusy(true)
    try {
      const r = await listEvidencePapers({ search: libQuery.trim() || undefined, limit: 50 })
      setLibResults(r.items)
      setLibSelected(new Set())
    } catch (err) {
      setLibResults([])
      setSearchError({ kind: 'search_failed', message: `论文库检索失败:${errTextOf(err)}` })
    } finally {
      setLibBusy(false)
    }
  }, [libQuery])

  const addSelectedToTask = useCallback(async () => {
    if (libSelected.size === 0) return
    setLibBusy(true)
    try {
      const chosen = (libResults ?? []).filter(pi => libSelected.has(pi.id))
      await pewUpsertPapers(rankingId, chosen.map(pi => ({
        pmid: pi.pmid || null,
        doi: pi.doi || null,
        title: pi.title || '',
        authors: null,
        journal: pi.journal || null,
        year: pi.publication_year ? String(pi.publication_year) : null,
        abstract_available: pi.abstract_available,
        fulltext_available: pi.fulltext_available,
        source: 'library_pick',
      })))
      await refreshPapers()
      notifyTaskPapersChanged(rankingId)
      setLibOpen(false)
    } catch (err) {
      setSearchError({ kind: 'upsert_failed', message: `加入当前任务失败:${errTextOf(err)}` })
    } finally {
      setLibBusy(false)
    }
  }, [libSelected, libResults, rankingId, refreshPapers])

  // 卡片内容状态
  const contentStatus = (p: PewPaperRow): string =>
    p.fulltext_available ? '全文可用' : p.abstract_available ? '仅摘要' : '待全文获取'

  const assetStatus = useMemo(() => {
    const m = new Map<string, string>()
    for (const p of taskPapers) {
      const key = paperKey(p)
      if (!key) continue
      const st = discoveryState.get(key)
      m.set(key, st === 'created' ? '本次新增' : st === 'reused' ? '论文库已存在' : p.role === 'imported' ? '论文库已存在' : '论文库已存在')
    }
    return m
  }, [taskPapers, discoveryState])

  const hasResults = taskPapers.length > 0 || initStats !== null

  return (
    <div className="edw-root" data-testid="edw-workspace">
      {/* ① 四阶段 Stepper(页面内步骤;当前步蓝 / 完成绿 / 未到灰) */}
      <div className="edw-stepper" data-testid="edw-stepper">
        {DISCOVERY_STAGES.map((s, i) => {
          const active = s.no === activeStage
          const done = s.no < activeStage
          const enterable = s.no === 2 && taskPapers.length > 0 || s.no === 3 && hasReviewable || s.no === 4 && hasReviewable
          const clickable = s.no === 1 || enterable
          return (
            <div
              className={`edw-step${active ? ' edw-step-active' : ''}${done ? ' edw-step-done' : ''}${clickable ? ' edw-step-enterable' : ''}`}
              key={s.no}
              data-testid={`edw-step-${s.no}`}
              onClick={clickable
                ? () => setActiveStage(s.no === 1 ? 1 : s.no === 3 ? 3 : s.no === 4 ? 4 : 2)
                : undefined}
            >
              <span className="edw-step-no">{s.no}</span>
              <span className="edw-step-label">
                {s.label}
              </span>
              {i < DISCOVERY_STAGES.length - 1 && <span className="edw-step-arrow">→</span>}
            </div>
          )
        })}
      </div>

      {/* ② 主工作区:Step 1 论文检索 / Step 2 片段筛选 */}
      {activeStage === 4 ? (
        <EvidenceCandidatesStage
          rankingId={rankingId}
          connectionType={connectionType}
          onBackToAi={() => setActiveStage(3)}
          onNextHumanReview={() => setActiveStage(3)}
        />
      ) : activeStage === 3 ? (
        <AiReviewStage
          rankingId={rankingId}
          connectionType={connectionType}
          onBackToScreen={() => setActiveStage(2)}
          onNextStep4={() => setActiveStage(4)}
        />
      ) : activeStage === 2 ? (
        <FragmentScreenStage
          rankingId={rankingId}
          connectionType={connectionType}
          paperIds={taskPapers.map(p => p.paper_id)}
          onBackToSearch={() => setActiveStage(1)}
          onNextToAi={() => setActiveStage(3)}
        />
      ) : (
      <div className="edw-stage" data-testid="edw-stage-1">
        <div className="edw-stage-head">
          <h3 className="edw-stage-title">论文检索</h3>
          <p className="edw-stage-desc">
            检索与当前知识事实相关的论文,论文会自动去重并保存到系统论文库(paper_sources),
            并加入当前任务 Paper Workspace。
          </p>
        </div>

        {/* 线索提示(自动整备,无手动导入按钮):只显示处理状态 */}
        {paperCount != null && paperCount > 0 && (
          <div className="edw-clue" data-testid="edw-paper-clue">
            <span className="edw-clue-text">
              发现阶段论文线索 <b>{paperCount}</b>
              {initState === 'working' && (
                <span className="edw-clue-stats" data-testid="edw-init-working"> · 自动整理中…</span>
              )}
              {initState === 'done' && initStats && (
                <span className="edw-clue-stats" data-testid="edw-init-stats">
                  {' '}· 已存在论文库 {initStats.existing} · 新增论文 {initStats.created}
                  {' '}· 无法解析 {initStats.unresolved} · 当前任务论文 {initStats.task_papers}
                </span>
              )}
            </span>
            {initState === 'done' && initStats && initStats.failed > 0 && (
              <span className="edw-fail-summary" data-testid="edw-fail-summary">
                自动整理完成 成功 {initStats.clues - initStats.failed} 失败 {initStats.failed}
                <button type="button" className="edw-link-btn" data-testid="edw-show-failed-btn" onClick={() => setShowFailed(o => !o)}>
                  查看失败项
                </button>
              </span>
            )}
          </div>
        )}
        {showFailed && initFailed.length > 0 && (
          <div className="edw-failed-list" data-testid="edw-failed-list">
            {initFailed.map(f => (
              <div key={f.paper_id} className="edw-failed-item">
                <span>{f.title ?? f.paper_id.slice(0, 8)}</span>
                <span className="edw-muted-hint">{f.reason}</span>
              </div>
            ))}
            <button type="button" className="btn btn-sm" data-testid="edw-retry-failed-init" onClick={() => void runInit(true)}>
              重试失败项
            </button>
          </div>
        )}

        {/* 顶栏:检索词摘要(单行) + 唯一主按钮[检索论文] + 低频操作[更多 ▾] */}
        <div className="edw-querybar" data-testid="edw-querybar">
          <div className="edw-query-summary" data-testid="edw-query-summary">
            <span className="edw-query-label">检索词</span>
            <span className="edw-query-text" title={textareaQueries.join('\n')}>
              {queryLoadError
                ? `检索词生成失败:${queryLoadError}`
                : textareaQueries.length > 0
                  ? textareaQueries.join(' ∥ ')
                  : '正在生成检索词…'}
            </span>
          </div>
          <button type="button" className="btn btn-sm btn-primary" disabled={busy} data-testid="edw-search-btn" onClick={() => void handleSearch()}>
            {phase === 'searching' ? '检索中…' : '检索论文'}
          </button>
          <div className="edw-menu-wrap">
            <button type="button" className="btn btn-sm" data-testid="edw-more-btn" onClick={() => setMenuOpen(o => !o)}>
              更多 ▾
            </button>
            {menuOpen && (
              <div className="edw-menu" data-testid="edw-more-menu" onClick={() => setMenuOpen(false)}>
                <button type="button" className="edw-menu-item" data-testid="edw-edit-queries-btn" onClick={() => setEditOpen(o => !o)}>
                  修改检索词
                </button>
                <button type="button" className="edw-menu-item" data-testid="edw-pick-from-library-btn" onClick={() => setLibOpen(true)}>
                  从论文库选择
                </button>
              </div>
            )}
          </div>
        </div>

        {/* 检索词编辑区(展开):勾选/修改后重新搜索 */}
        {editOpen && (
          <div className="edw-query-editor" data-testid="edw-query-editor">
            {queries.map((q, i) => (
              <div key={i} className="edw-query-row">
                <input type="checkbox" checked={q.enabled} onChange={() => toggleQuery(i)} />
                <span className="edw-query-src">{q.source}</span>
                <input
                  className="filter-input"
                  style={{ flex: 1 }}
                  value={q.q}
                  onChange={e => setQueries(prev => prev.map((x, idx) => (idx === i ? { ...x, q: e.target.value } : x)))}
                  data-testid={`edw-query-input-${i}`}
                />
                {failedQueryIds.includes(i) && <span className="edw-error-inline">检索失败</span>}
              </div>
            ))}
            <div className="edw-query-actions">
              <button type="button" className="btn btn-sm btn-primary" disabled={busy} onClick={() => void handleSearch()}>
                {phase === 'searching' ? '检索中…' : '按以上检索词重新搜索'}
              </button>
              {failedQueryIds.length > 0 && (
                <button type="button" className="btn btn-sm" data-testid="edw-retry-failed-btn" onClick={() => void handleSearch(true)}>
                  重试失败检索词({failedQueryIds.length})
                </button>
              )}
              <span className="edw-muted-hint">脑区名称来自 canonical 别名,不自动扩展;连接类型带同义词(projection/connection/pathway/tract/connectivity)</span>
            </div>
          </div>
        )}

        {/* 状态反馈(检索中/失败/无结果) */}
        {phase === 'searching' && (
          <div className="edw-feedback" data-testid="edw-searching">检索中…(正在调用 PubMed/Europe PMC/OpenAlex/S2)</div>
        )}
        {phase === 'search_error' && (
          <div className="edw-feedback edw-feedback-error" data-testid="edw-search-error">论文搜索失败</div>
        )}
        {searchError && (
          <div className={`edw-feedback${searchError.kind.includes('failed') ? ' edw-feedback-error' : ''}`} data-testid="edw-error-banner">
            {searchError.kind === 'search_failed' ? '论文搜索失败:' : ''}
            {searchError.kind === 'upsert_failed' ? '论文入库失败:' : ''}
            {searchError.kind === 'link_failed' ? '任务关联失败:' : ''}
            {searchError.kind === 'partial_queries' ? '' : ''}
            {' '}{searchError.message}
          </div>
        )}
        {searchDoneMsg && !searchError && (
          <div className="edw-feedback" data-testid="edw-search-done">
            {searchDoneMsg}
          </div>
        )}

        {/* 检索结果统计 */}
        {stats && (
          <div className="edw-stats edw-stats-results" data-testid="edw-search-stats">
            <div className="edw-stat"><div className="edw-stat-value edw-stat-found">{stats.found}</div><div className="edw-stat-label">检索发现</div></div>
            <div className="edw-stat"><div className="edw-stat-value">{stats.reused}</div><div className="edw-stat-label">论文库已存在</div></div>
            <div className="edw-stat"><div className="edw-stat-value edw-stat-created">{stats.created}</div><div className="edw-stat-label">本次新增入库</div></div>
            <div className="edw-stat"><div className="edw-stat-value">{taskPapers.length}</div><div className="edw-stat-label">当前任务论文</div></div>
          </div>
        )}

        {/* 无结果反馈(非纯空白) */}
        {phase === 'done' && stats === null && taskPapers.length === 0 && (
          <div className="edw-noresult" data-testid="edw-no-results">
            <p className="edw-noresult-title">本次检索未找到匹配论文。</p>
            <p className="edw-muted-hint">检索词:{lastQueryText || '(空)'}</p>
          </div>
        )}

        {/* Step1 数据统计(发现阶段线索/当前任务论文/后续阶段为 0) */}
        <div className="edw-stats" data-testid="edw-stage1-stats">
          <div className="edw-stat"><div className="edw-stat-value">{paperCount ?? 0}</div><div className="edw-stat-label">发现阶段论文线索</div></div>
          <div className="edw-stat"><div className="edw-stat-value" data-testid="edw-task-paper-count">{taskPapers.length}</div><div className="edw-stat-label">当前任务论文</div></div>
          <div className="edw-stat"><div className="edw-stat-value">0</div><div className="edw-stat-label">疑似片段</div></div>
          <div className="edw-stat"><div className="edw-stat-value">0</div><div className="edw-stat-label">AI已审核</div></div>
        </div>

        {/* 当前任务论文卡片(统一卡片:资产/内容/任务状态;仅 Task Papers,非 Evidence) */}
        {hasResults && (
          <div className="edw-papers" data-testid="edw-task-papers">
            <div className="edw-papers-head">
              <h4 className="edw-papers-title">当前任务论文({taskPapers.length})</h4>
              <span style={{ flex: 1 }} />
              {taskPapers.length > 0 && (
                <button
                  type="button" className="btn btn-sm btn-primary"
                  data-testid="edw-next-step-btn"
                  onClick={() => setActiveStage(2)}
                >
                  下一步:片段筛选
                </button>
              )}
            </div>
            {nextHint && taskPapers.length > 0 && (
              <p className="edw-muted-hint" data-testid="edw-next-hint" style={{ margin: '0 0 8px' }}>
                片段筛选将在后续阶段接入(当前仅完成论文检索与任务工作区)。
              </p>
            )}
            {taskPapers.length === 0 ? (
              <p className="edw-muted-hint">暂未纳入论文。检索入库、从论文库选择或导入发现阶段线索后展示。</p>
            ) : (
              <div className="edw-paper-list">
                {taskPapers.map(p => {
                  const key = paperKey(p) ?? ''
                  return (
                    <div className="edw-paper-card" key={p.paper_id} data-testid={`edw-paper-${p.paper_id}`}>
                      <div className="edw-paper-main">
                        <div className="edw-paper-title">{p.title || '(未命名)'}</div>
                        <div className="edw-paper-meta">
                          {p.authors ? `${p.authors} · ` : ''}
                          {p.journal ? `${p.journal} · ` : ''}
                          {p.year ? `${p.year}` : ''}
                        </div>
                        <div className="edw-paper-ids">
                          <span className="edw-chip">PMID {p.pmid || '—'}</span>
                          <span className="edw-chip">DOI {p.doi || '—'}</span>
                        </div>
                      </div>
                      <div className="edw-paper-badges">
                        <span className={`edw-badge ${assetStatus.get(key) === '本次新增' ? 'edw-badge-created' : 'edw-badge-exists'}`} data-testid={`edw-asset-${p.paper_id}`}>
                          {assetStatus.get(key) ?? (p.role === 'imported' ? '论文库已存在' : '论文库已存在')}
                        </span>
                        <span className="edw-badge edw-badge-content">{contentStatus(p)}</span>
                        <span className="edw-badge edw-badge-in-task" data-testid={`edw-task-badge-${p.paper_id}`}>已纳入任务</span>
                      </div>
                      <div className="edw-paper-actions">
                        <button type="button" className="btn btn-sm" data-testid={`edw-view-paper-${p.paper_id}`} onClick={() => setDetailPaperId(p.paper_id)}>查看论文</button>
                        <div className="edw-menu-wrap">
                          <button
                            type="button" className="btn btn-sm edw-card-menu-btn"
                            data-testid={`edw-card-menu-${p.paper_id}`}
                            onClick={() => setCardMenuPaperId(prev => (prev === p.paper_id ? null : p.paper_id))}
                          >
                            ⋯
                          </button>
                          {cardMenuPaperId === p.paper_id && (
                            <div className="edw-menu" data-testid={`edw-card-menu-list-${p.paper_id}`} onClick={() => setCardMenuPaperId(null)}>
                              <button type="button" className="edw-menu-item" data-testid={`edw-remove-paper-${p.paper_id}`} onClick={() => void handleRemovePaper(p.paper_id)}>
                                移出当前任务
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )}

        <div className="edw-meta" data-testid="edw-task-meta">
          Task ID:{rankingId.slice(0, 8)} · Workflow Mode:{workflowModeLabel}
        </div>
      </div>
      )}

      {/* 从论文库选择 Drawer/Modal:搜索 Title/Author/PMID/DOI + 多选加入当前任务 */}
      {libOpen && (
        <div className="edw-modal-backdrop" data-testid="edw-picker" onClick={() => setLibOpen(false)}>
          <div className="edw-modal" onClick={e => e.stopPropagation()}>
            <h4 className="edw-modal-title">从论文库选择</h4>
            <div className="edw-picker-search">
              <input
                className="filter-input" style={{ flex: 1 }}
                placeholder="搜索标题 / 作者 / PMID / DOI"
                value={libQuery}
                onChange={e => setLibQuery(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') void runLibSearch() }}
              />
              <button type="button" className="btn btn-sm btn-primary" disabled={libBusy} onClick={() => void runLibSearch()}>搜索</button>
            </div>
            <div className="edw-picker-list">
              {(libResults ?? []).map(pi => (
                <label className="edw-picker-row" key={pi.id}>
                  <input
                    type="checkbox"
                    checked={libSelected.has(pi.id)}
                    onChange={e => setLibSelected(prev => {
                      const n = new Set(prev)
                      if (e.target.checked) n.add(pi.id)
                      else n.delete(pi.id)
                      return n
                    })}
                  />
                  <span className="edw-picker-info">
                    <b>{pi.title || '(未命名)'}</b>
                    <span className="edw-muted-hint">{pi.journal ? `${pi.journal} · ` : ''}{pi.publication_year ?? ''} · PMID {pi.pmid || '—'} · DOI {pi.doi || '—'}</span>
                  </span>
                </label>
              ))}
              {libResults !== null && libResults.length === 0 && (
                <p className="edw-muted-hint" data-testid="edw-picker-empty">论文库中未找到匹配论文。</p>
              )}
            </div>
            <div className="edw-picker-actions">
              <span className="edw-muted-hint">仅建立任务关联,不复制论文。</span>
              <span style={{ flex: 1 }} />
              <button type="button" className="btn btn-sm" onClick={() => setLibOpen(false)}>取消</button>
              <button
                type="button" className="btn btn-sm btn-primary"
                disabled={libBusy || libSelected.size === 0}
                data-testid="edw-picker-add"
                onClick={() => void addSelectedToTask()}
              >
                加入当前任务({libSelected.size})
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 论文详情:复用 Paper Library 详情抽屉(Information/Abstract/Full Text) */}
      {detailPaperId && <PaperDetailDrawer paperId={detailPaperId} onClose={() => setDetailPaperId(null)} />}
    </div>
  )
}

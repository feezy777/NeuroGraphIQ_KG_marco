/**
 * Task Paper Workspace 轻量共享状态:中栏工作台(入库/移出)与右栏处理进度(论文计数)跨组件同步。
 * 模块级 cache + event 通知;数据本体在 pew_papers(后端持久化),此处仅缓存计数。
 */
import { useSyncExternalStore } from 'react'
import { pewListPapers, pewListReviews, pewListSegments } from './pewApi'

type Listener = () => void
const listeners = new Set<Listener>()
const countCache = new Map<string, number>()
const loading = new Set<string>()

function emit(): void {
  for (const l of listeners) l()
}

function getSnapshot(rankingId: string): number {
  return countCache.get(rankingId) ?? 0
}

function subscribe(cb: Listener): () => void {
  listeners.add(cb)
  return () => { listeners.delete(cb) }
}

function subscribeKey(rankingId: string, cb: Listener): () => void {
  return subscribe(cb)
}

/** 拉取并缓存任务论文数(幂等;并发用序号防旧结果覆盖新值) */
const fetchSeq = new Map<string, number>()
export async function refreshTaskPaperCount(rankingId: string): Promise<number> {
  const seq = (fetchSeq.get(rankingId) ?? 0) + 1
  fetchSeq.set(rankingId, seq)
  try {
    const r = await pewListPapers(rankingId)
    if (fetchSeq.get(rankingId) === seq) countCache.set(rankingId, r.items.length)
  } catch {
    // 计数拉取失败保持旧值(仅展示层,不阻断工作台)
  } finally {
    loading.delete(rankingId)
    emit()
  }
  return getSnapshot(rankingId)
}

/** 中栏工作台在入库/移出/导入后调用 → 右栏计数即时同步 */
export function notifyTaskPapersChanged(rankingId: string): void {
  void refreshTaskPaperCount(rankingId)
}

/** 右栏处理进度「论文」计数(任务级;刷新/切任务自动恢复) */
export function useTaskPaperCount(rankingId: string | null): number {
  const unloaded = rankingId !== null && !countCache.has(rankingId) && !loading.has(rankingId)
  if (rankingId && unloaded) {
    loading.add(rankingId)
    void refreshTaskPaperCount(rankingId)
  }
  return useSyncExternalStore(
    (cb: Listener) => subscribeKey(rankingId ?? '', cb),
    () => getSnapshot(rankingId ?? ''),
  )
}

/** Step 2 疑似片段计数(右栏「疑似片段」;与论文计数同机制) */
const segCache = new Map<string, number>()
const segLoading = new Set<string>()
const segSeq = new Map<string, number>()

function segSnapshot(rankingId: string): number {
  return segCache.get(rankingId) ?? 0
}

export async function refreshTaskSegmentCount(rankingId: string): Promise<number> {
  const seq = (segSeq.get(rankingId) ?? 0) + 1
  segSeq.set(rankingId, seq)
  try {
    const r = await pewListSegments(rankingId)
    if (segSeq.get(rankingId) === seq) segCache.set(rankingId, r.items.length)
  } catch {
    // 保持旧值
  } finally {
    segLoading.delete(rankingId)
    emit()
  }
  return segSnapshot(rankingId)
}

export function notifyTaskSegmentsChanged(rankingId: string): void {
  void refreshTaskSegmentCount(rankingId)
}

export function useTaskSegmentCount(rankingId: string | null): number {
  const unloaded = rankingId !== null && !segCache.has(rankingId) && !segLoading.has(rankingId)
  if (rankingId && unloaded) {
    segLoading.add(rankingId)
    void refreshTaskSegmentCount(rankingId)
  }
  return useSyncExternalStore(
    (cb: Listener) => subscribeKey(rankingId ?? '', cb),
    () => segSnapshot(rankingId ?? ''),
  )
}

/** Step 3 审核统计(右栏 AI已审核/Supported/Partial/Rejected/Uncertain) */
export interface ReviewStats {
  reviewed: number
  supported: number
  partial: number
  uncertain: number
  notSupported: number
  failed: number
}

const revCache = new Map<string, ReviewStats>()
const revLoading = new Set<string>()
const revSeq = new Map<string, number>()

// 共享空态引用:useSyncExternalStore getSnapshot 必须按引用稳定
const EMPTY_REVIEW_STATS: ReviewStats = { reviewed: 0, supported: 0, partial: 0, uncertain: 0, notSupported: 0, failed: 0 }

function revSnapshot(rankingId: string): ReviewStats {
  return revCache.get(rankingId) ?? EMPTY_REVIEW_STATS
}

function emptyStats(): ReviewStats {
  return { reviewed: 0, supported: 0, partial: 0, uncertain: 0, notSupported: 0, failed: 0 }
}

export async function refreshTaskReviewStats(rankingId: string): Promise<ReviewStats> {
  const seq = (revSeq.get(rankingId) ?? 0) + 1
  revSeq.set(rankingId, seq)
  try {
    const r = await pewListReviews(rankingId)
    if (revSeq.get(rankingId) !== seq) return revSnapshot(rankingId)
    const st = emptyStats()
    for (const it of r.items) {
      st.reviewed += 1
      if (it.failed) st.failed += 1
      else if (it.decision === 'supported') st.supported += 1
      else if (it.decision === 'partial_support') st.partial += 1
      else if (it.decision === 'uncertain') st.uncertain += 1
      else if (it.decision === 'not_supported') st.notSupported += 1
    }
    revCache.set(rankingId, st)
  } catch {
    // 保持旧值
  } finally {
    revLoading.delete(rankingId)
    emit()
  }
  return revSnapshot(rankingId)
}

export function notifyTaskReviewsChanged(rankingId: string): void {
  void refreshTaskReviewStats(rankingId)
}

export function useTaskReviewStats(rankingId: string | null): ReviewStats {
  const unloaded = rankingId !== null && !revCache.has(rankingId) && !revLoading.has(rankingId)
  if (rankingId && unloaded) {
    revLoading.add(rankingId)
    void refreshTaskReviewStats(rankingId)
  }
  return useSyncExternalStore(
    (cb: Listener) => subscribeKey(rankingId ?? '', cb),
    () => revSnapshot(rankingId ?? ''),
  )
}

/** Step 4 候选统计通知(侧栏【已选候选证据】持有自己拉取的列表;以此版本号触发刷新) */
const candVersion = new Map<string, number>()

export function notifyTaskCandidatesChanged(rankingId: string): void {
  candVersion.set(rankingId, (candVersion.get(rankingId) ?? 0) + 1)
  emit()
}

export function useTaskCandidatesVersion(rankingId: string | null): number {
  return useSyncExternalStore(
    (cb: Listener) => subscribeKey(rankingId ?? '', cb),
    () => candVersion.get(rankingId ?? '') ?? 0,
  )
}

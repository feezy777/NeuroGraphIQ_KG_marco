import { useState, useEffect, useCallback, useRef } from 'react'
import { ApiError } from '../../../api/client'
import {
  createCandidatePool,
  getCandidatePool,
  addPoolMembers,
  removePoolMembers,
  deleteCandidatePool,
  listCandidatePools,
  replaceCandidatePool,
  type CandidatePool,
  type CandidatePoolMember,
} from '../../../api/endpoints'

export interface PoolScope {
  sourceAtlas: string
  granularityLevel: string
  granularityFamily: string | null
}

export class PoolSetupError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PoolSetupError'
  }
}

function scopeKey(s: PoolScope): string {
  return `${s.sourceAtlas}::${s.granularityLevel}::${s.granularityFamily ?? ''}`
}

function isPoolNotFoundError(err: unknown): boolean {
  if (err instanceof ApiError && err.status === 404) return true
  const msg = err instanceof Error ? err.message : String(err)
  return msg.includes('Pool not found') || msg.includes('404')
}

function logPoolDebug(label: string, data: Record<string, unknown>) {
  if (import.meta.env.DEV) {
    console.info(`[useCandidatePool] ${label}`, data)
  }
}

export function useCandidatePool(scope: PoolScope | null) {
  const [pool, setPool] = useState<CandidatePool | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const mountedRef = useRef(true)
  const fetchGenRef = useRef(0)
  const addBusyRef = useRef(false)
  const replaceInFlightRef = useRef<Promise<CandidatePool> | null>(null)
  const currentKey = scope ? scopeKey(scope) : null

  const listScopePools = useCallback(async () => {
    if (!scope) return []
    const { items } = await listCandidatePools({
      source_atlas: scope.sourceAtlas,
      granularity_level: scope.granularityLevel,
      granularity_family: scope.granularityFamily ?? '',
      status: 'active',
      limit: 100,
    })
    return items
  }, [scope?.sourceAtlas, scope?.granularityLevel, scope?.granularityFamily])

  // Fetch newest pool when scope changes (ignore stale in-flight responses)
  useEffect(() => {
    mountedRef.current = true
    if (!scope) {
      setPool(null)
      return
    }

    const gen = ++fetchGenRef.current
    let cancelled = false
    setIsLoading(true)

    ;(async () => {
      try {
        const items = await listScopePools()
        if (!mountedRef.current || cancelled || gen !== fetchGenRef.current) return

        if (items.length > 0) {
          try {
            const full = await getCandidatePool(items[0].id)
            if (!mountedRef.current || cancelled || gen !== fetchGenRef.current) return
            setPool(full)
          } catch (err) {
            if (!mountedRef.current || cancelled || gen !== fetchGenRef.current) return
            if (isPoolNotFoundError(err)) {
              setPool(null)
            }
          }
        } else {
          setPool(null)
        }
      } catch (err) {
        console.warn('[useCandidatePool] fetch failed:', err)
      } finally {
        if (mountedRef.current && !cancelled && gen === fetchGenRef.current) setIsLoading(false)
      }
    })()

    return () => { cancelled = true }
  }, [currentKey, listScopePools])

  useEffect(() => {
    return () => { mountedRef.current = false }
  }, [])

  const pooledCandidateIds = new Set(
    pool?.memberships?.map((m: CandidatePoolMember) => m.candidate_id) ?? []
  )

  const addCandidates = useCallback(async (candidateIds: string[]) => {
    if (!scope || candidateIds.length === 0) return
    if (addBusyRef.current) return

    const newIds = candidateIds.filter(id => !pooledCandidateIds.has(id))
    if (newIds.length === 0) return

    addBusyRef.current = true
    try {
      let currentPool = pool
      if (!currentPool) {
        currentPool = await createCandidatePool({
          candidate_ids: newIds,
          source_atlas: scope.sourceAtlas,
          granularity_level: scope.granularityLevel,
          granularity_family: scope.granularityFamily,
        })
      } else {
        currentPool = await addPoolMembers(currentPool.id, { candidate_ids: newIds })
      }
      // Mutation responses already include full memberships — use them immediately
      // so a transient/refetch 404 never makes the pool look empty.
      if (mountedRef.current) setPool(currentPool)
      try {
        const full = await getCandidatePool(currentPool.id)
        if (mountedRef.current) setPool(full)
      } catch {
        // Best-effort refresh only; keep the mutation response on failure.
      }
    } catch (err) {
      console.error('[useCandidatePool] add failed:', err)
      // Refresh pool state after a failure so retries don't resend duplicates.
      if (mountedRef.current && pool?.id) {
        try {
          const full = await getCandidatePool(pool.id)
          if (mountedRef.current) setPool(full)
        } catch {
          if (mountedRef.current) setPool(null)
        }
      }
    } finally {
      addBusyRef.current = false
    }
  }, [scope, pool?.id, pooledCandidateIds, currentKey])

  /** Replace pool contents with exactly these candidates (no accumulation). Returns the fresh pool. */
  const setPoolCandidates = useCallback(async (
    candidateIds: string[],
    scopeOverride?: PoolScope | null,
  ): Promise<CandidatePool> => {
    const effectiveScope = scopeOverride ?? scope
    const uniqueIds = [...new Set(candidateIds.filter(Boolean))]

    if (uniqueIds.length < 2) {
      throw new PoolSetupError('当前没有可加入提取池的候选脑区（至少需要 2 个）')
    }
    if (!effectiveScope?.sourceAtlas || !effectiveScope?.granularityLevel) {
      throw new PoolSetupError('提取范围尚未就绪，请稍候再试')
    }

    const payload = {
      candidate_ids: uniqueIds,
      source_atlas: effectiveScope.sourceAtlas,
      granularity_level: effectiveScope.granularityLevel,
      granularity_family: effectiveScope.granularityFamily,
    }

    // Deduplicate concurrent replace calls (e.g. double-click / multi-trigger).
    if (replaceInFlightRef.current) return replaceInFlightRef.current

    logPoolDebug('setPoolCandidates request', {
      selectedIdsLength: uniqueIds.length,
      atlas: payload.source_atlas,
      granularity: payload.granularity_level,
      granularityFamily: payload.granularity_family,
      payload,
    })

    ++fetchGenRef.current
    const task = (async () => {
      try {
        const created = await replaceCandidatePool(payload)
        if (mountedRef.current) setPool(created)
        logPoolDebug('setPoolCandidates response', {
          status: 'ok',
          poolId: created.id,
          candidateCount: created.candidate_count,
        })
        try {
          const full = await getCandidatePool(created.id)
          if (mountedRef.current) setPool(full)
          return full
        } catch {
          // Best-effort refresh only; replace already returns full memberships.
          return created
        }
      } catch (err) {
        console.error('[useCandidatePool] setPoolCandidates failed:', err)
        throw err
      }
    })()
    replaceInFlightRef.current = task
    try {
      return await task
    } finally {
      replaceInFlightRef.current = null
    }
  }, [scope, currentKey])

  const removeCandidate = useCallback(async (candidateId: string) => {
    if (!pool) return
    try {
      const updated = await removePoolMembers(pool.id, { candidate_ids: [candidateId] })
      if (mountedRef.current) setPool(updated.candidate_count > 0 ? updated : null)
    } catch (err) {
      if (isPoolNotFoundError(err)) {
        if (mountedRef.current) setPool(null)
        return
      }
      console.warn('[useCandidatePool] remove failed:', err)
    }
  }, [pool?.id])

  const batchRemove = useCallback(async (candidateIds: string[]) => {
    if (!pool || candidateIds.length === 0) return
    try {
      const updated = await removePoolMembers(pool.id, { candidate_ids: candidateIds })
      if (mountedRef.current) setPool(updated.candidate_count > 0 ? updated : null)
    } catch (err) {
      if (isPoolNotFoundError(err)) {
        if (mountedRef.current) setPool(null)
        return
      }
      console.warn('[useCandidatePool] batchRemove failed:', err)
    }
  }, [pool?.id, pool?.candidate_count])

  const searchCandidates = useCallback(async (query: string): Promise<any[]> => {
    if (!query.trim() || !scope) return []
    try {
      const { getJson } = await import('../../../api/client')
      const result: any = await getJson('/api/candidates/brain-regions', {
        source_atlas: scope.sourceAtlas,
        granularity_level: scope.granularityLevel,
        granularity_family: scope.granularityFamily ?? '',
        search: query,
        limit: 20,
      })
      return result.items ?? []
    } catch (err) {
      console.warn('[useCandidatePool] searchCandidates failed:', err)
      return []
    }
  }, [scope])

  const refresh = useCallback(async () => {
    if (!pool?.id) return
    try {
      const full = await getCandidatePool(pool.id)
      if (mountedRef.current) setPool(full.candidate_count > 0 ? full : null)
    } catch (err) {
      if (isPoolNotFoundError(err) && mountedRef.current) {
        setPool(null)
      }
    }
  }, [pool?.id])

  const clearPool = useCallback(async () => {
    if (!pool) return
    try {
      await deleteCandidatePool(pool.id)
    } catch (err) {
      if (!isPoolNotFoundError(err)) {
        console.warn('[useCandidatePool] clear failed:', err)
      }
    } finally {
      if (mountedRef.current) setPool(null)
    }
  }, [pool?.id])

  return {
    pool, pooledCandidateIds, isLoading,
    addCandidates, setPoolCandidates, removeCandidate, batchRemove, clearPool,
    searchCandidates, refresh,
  }
}

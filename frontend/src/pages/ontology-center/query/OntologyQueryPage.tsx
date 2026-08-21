import { useCallback, useEffect, useRef, useState } from 'react'
import { postOntologyExplain } from '../../../api/ontologyQueryApi'
import type {
  OntologyExplainResponse,
  OntologyQueryCandidate,
} from '../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'
import { ErrorState } from '../ui/ErrorState'
import { QueryEmptyState } from './QueryEmptyState'
import { QueryInput } from './QueryInput'
import { AIExplanationCard } from './components/AIExplanationCard'
import { EvidenceSummary } from './components/EvidenceSummary'
import { QueryResultTable } from './components/QueryResultTable'
import { QuerySummaryCard } from './components/QuerySummaryCard'
import { RightContextPanel } from './components/RightContextPanel'

/** 错误归一化：AbortError 不展示；其余取 Error message */
function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    if (error.name === 'AbortError') return ''
    return error.message
  }
  return '查询失败，请稍后重试'
}

type ExplainState =
  | { status: 'initial' }
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'done'; response: OntologyExplainResponse }

const RECENT_KEY = 'ngiq.ontology-query.recent'
const RECENT_MAX = 5

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === 'string') : []
  } catch {
    return []
  }
}

function saveRecent(questions: string[]) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(questions.slice(0, RECENT_MAX)))
  } catch {
    // localStorage 不可用（隐私模式等）时静默跳过
  }
}

/** 自然语言查询 Dashboard：左查询工作台 + 中知识答案 + 右实体/证据上下文 */
export function OntologyQueryPage() {
  const [question, setQuestion] = useState('')
  const [state, setState] = useState<ExplainState>({ status: 'initial' })
  const [recent, setRecent] = useState<string[]>(() => loadRecent())
  const abortRef = useRef<AbortController | null>(null)

  // 卸载时中止在途请求，避免 unmounted setState
  useEffect(() => () => abortRef.current?.abort(), [])

  const runQuery = useCallback(async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading' })
    try {
      const response = await postOntologyExplain(trimmed, controller.signal)
      if (controller.signal.aborted) return
      setState({ status: 'done', response })
      const nextRecent = [trimmed, ...recent.filter(q => q !== trimmed)].slice(0, RECENT_MAX)
      setRecent(nextRecent)
      saveRecent(nextRecent)
    } catch (error) {
      if (controller.signal.aborted) return
      const message = getErrorMessage(error)
      if (!message) return
      setState({ status: 'error', message })
    }
  }, [recent])

  const handleSubmit = useCallback(() => {
    void runQuery(question)
  }, [question, runQuery])

  /** 示例问题 / 最近查询：填入输入框并立即执行 */
  const handlePick = useCallback(
    (picked: string) => {
      setQuestion(picked)
      void runQuery(picked)
    },
    [runQuery],
  )

  const handleRetry = useCallback(() => {
    void runQuery(question)
  }, [question, runQuery])

  const handleOpenDetail = useCallback((entityType: OntologyEntityType, entityId: string) => {
    // 复用 OntologyBrowser 的 URL 详情跳转：切换 tab 后浏览器 remount 消费参数
    window.location.hash = `#/ontology-center?tab=browser&entity_type=${entityType}&entity=${encodeURIComponent(entityId)}`
  }, [])

  const handleOpenBrowser = useCallback(() => {
    window.location.hash = '#/ontology-center?tab=browser'
  }, [])

  const loading = state.status === 'loading'

  const renderAnswer = () => {
    if (state.status === 'initial') return <QueryEmptyState variant="initial" />
    if (state.status === 'loading') {
      return (
        <div className="oqd-skeleton-block" aria-busy="true" aria-label="查询中">
          <div className="oqd-skeleton oqd-skeleton-title" />
          <div className="oqd-skeleton-grid">
            <div className="oqd-skeleton oqd-skeleton-card" />
            <div className="oqd-skeleton oqd-skeleton-card" />
            <div className="oqd-skeleton oqd-skeleton-card" />
            <div className="oqd-skeleton oqd-skeleton-card" />
          </div>
          <div className="oqd-skeleton oqd-skeleton-body" />
          <div className="oqd-skeleton oqd-skeleton-body" />
        </div>
      )
    }
    if (state.status === 'error') {
      return <ErrorState message={state.message} onRetry={handleRetry} />
    }

    const { query_result, explanation } = state.response
    const entity = query_result.entity
    if (!entity) {
      // 后端 fuzzy 候选随 source_entities 返回（{candidate, confidence} 形状，未自动选择）
      const candidates: OntologyQueryCandidate[] = query_result.source_entities.flatMap(item => {
        if (typeof item !== 'object' || item === null) return []
        const candidate = (item as { candidate?: unknown }).candidate
        if (typeof candidate !== 'string' || !candidate.trim()) return []
        const confidence = (item as { confidence?: unknown }).confidence
        const out: OntologyQueryCandidate = {
          candidate,
          confidence: typeof confidence === 'number' ? confidence : null,
        }
        return [out]
      })
      return (
        <QueryEmptyState
          variant="unresolved"
          warnings={query_result.warnings}
          candidates={candidates}
          onPickCandidate={handlePick}
        />
      )
    }
    if (query_result.results.length === 0) {
      return <QueryEmptyState variant="empty" warnings={query_result.warnings} />
    }
    return (
      <>
        <QuerySummaryCard
          response={query_result}
          question={state.response.question}
          onOpenDetail={handleOpenDetail}
        />
        {explanation?.answer && <AIExplanationCard explanation={explanation} />}
        <EvidenceSummary items={query_result.results} />
        <QueryResultTable items={query_result.results} onOpenDetail={handleOpenDetail} />
      </>
    )
  }

  return (
    <div className="oqd-layout">
      <aside className="oqd-workspace-col">
        <QueryInput
          value={question}
          onChange={setQuestion}
          onSubmit={handleSubmit}
          onPick={handlePick}
          recent={recent}
          loading={loading}
          disabled={!question.trim() || loading}
        />
      </aside>
      <main className="oqd-answer-col">{renderAnswer()}</main>
      {state.status === 'done' && (
        <RightContextPanel
          response={state.response.query_result}
          onOpenDetail={handleOpenDetail}
          onOpenBrowser={handleOpenBrowser}
        />
      )}
    </div>
  )
}

/**
 * 知识路径探索区（Path Explorer，画布下方）：
 * From → To 输入 → 路径链条展示（每步：relation type / evidence count / confidence）。
 *
 * 接口约定（防止伪造数据）：
 * - 组件不内置任何数据：`onExplore(from, to)` 由页面注入；
 * - 后端暂无路径查询端点 → 页面返回 null + reason，
 *   组件显示「接口待接入」诚实空态，不填充虚构路径。
 */
import { useCallback, useState } from 'react'
import { GitBranch, Loader2, Search } from 'lucide-react'

// ── 路径模型（组件与页面之间的接口，后端端点接入后直接映射此模型） ──────────────

export interface KgPathStep {
  label: string
  relationType: string
  evidenceCount: number | null
  confidence: number | null
}

export interface KgPathResult {
  from: string
  to: string
  steps: KgPathStep[]
}

export interface KgPathExploreOutcome {
  path: KgPathResult | null
  reason?: string
}

interface KgPathExplorerProps {
  /** 探索路径；后端接口不存在时 resolve { path: null, reason }（页面保证不伪造） */
  onExplore: (from: string, to: string) => Promise<KgPathExploreOutcome>
  /** 左侧已选中心名称（显示在 From 快捷位，可选） */
  currentCenterLabel?: string | null
}

function confidenceText(value: number | null): string {
  if (value == null) return '—'
  return String(Math.round(value * 100) / 100)
}

export function KgPathExplorer({ onExplore, currentCenterLabel }: KgPathExplorerProps) {
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<KgPathExploreOutcome | null>(null)

  const handleExplore = useCallback(async () => {
    const f = (from || currentCenterLabel || '').trim()
    const t = to.trim()
    if (!f || !t) return
    setBusy(true)
    setOutcome(null)
    try {
      setOutcome(await onExplore(f, t))
    } finally {
      setBusy(false)
    }
  }, [from, to, currentCenterLabel, onExplore])

  return (
    <section className="kg-path-explorer" aria-label="知识路径探索">
      <div className="kg-path-explorer-head">
        <span className="kg-path-explorer-icon">
          <GitBranch size={14} />
        </span>
        <span className="kg-path-explorer-title">路径探索</span>
        <span className="kg-path-explorer-desc">探索两个实体之间的知识路径（Beta）</span>
      </div>

      <div className="kg-path-explorer-controls">
        <div className="kg-path-field">
          <label className="kg-path-field-label" htmlFor="kg-path-from">
            From
          </label>
          <input
            id="kg-path-from"
            className="cg-input"
            type="text"
            placeholder={currentCenterLabel ?? 'Hippocampus'}
            value={from}
            onChange={e => setFrom(e.target.value)}
          />
        </div>
        <div className="kg-path-field">
          <label className="kg-path-field-label" htmlFor="kg-path-to">
            To
          </label>
          <input
            id="kg-path-to"
            className="cg-input"
            type="text"
            placeholder="Prefrontal Cortex"
            value={to}
            onChange={e => setTo(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="btn btn-sm btn-primary kg-path-explore-btn"
          onClick={handleExplore}
          disabled={busy || (!from && !currentCenterLabel) || !to}
        >
          {busy ? (
            <Loader2 size={13} className="kg-spin" />
          ) : (
            <Search size={13} />
          )}
          探索路径
        </button>
      </div>

      {outcome && (() => {
        const path = outcome.path
        if (path === null) {
          return (
            <div className="kg-path-empty">
              <span>路径分析接口待接入：</span>
              <span>{outcome.reason ?? '后端暂无图谱路径查询端点'}</span>
            </div>
          )
        }
        const steps = path.steps
        return (
          <div className="kg-path-chain">
            {steps.map((step, i) => (
              <span key={`${step.label}-${i}`} className="kg-path-step-wrap">
                <span className="kg-path-step">
                  <span className="kg-path-step-label">{step.label}</span>
                  <span className="kg-path-step-meta">
                    {step.relationType && <span className="kg-path-step-relation">{step.relationType}</span>}
                    {step.evidenceCount != null && (
                      <span className="kg-path-step-count">evidence {step.evidenceCount}</span>
                    )}
                    {step.confidence != null && (
                      <span className="kg-path-step-conf">confidence {confidenceText(step.confidence)}</span>
                    )}
                  </span>
                </span>
                {i < steps.length - 1 && <span className="kg-path-arrow">↓</span>}
              </span>
            ))}
          </div>
        )
      })()}
    </section>
  )
}

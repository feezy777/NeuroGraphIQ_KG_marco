import { useState, useEffect } from 'react'
import { Zap, Sparkles } from 'lucide-react'

interface Tier1Stats {
  source_atlas_backfill: number; provenance_backfill: number
  enum_normalization: number; topology_fix: number
  region_creation: number; total: number
}

interface Tier2Stats {
  evidence_text: number; description: number
  function_crosscheck: number; topology_flags: number
  total: number
}

interface EnhancementResult {
  run_id: string
  tier1_fixes: Tier1Stats
  tier2_suggestions: Tier2Stats
  quality_score_change: { before_avg: number; after_avg: number }
  circuit_scores: Array<{ circuit_id: string; before: number; after: number }>
}

interface Props {
  runId: string
  circuitCount: number
  onClose: () => void
}

export function EnhancementModal({ runId, circuitCount, onClose }: Props) {
  const [phase, setPhase] = useState<'loading' | 'running' | 'done' | 'error'>('loading')
  const [result, setResult] = useState<EnhancementResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    async function run() {
      try {
        setPhase('running')
        const resp = await fetch('/api/validation/circuit/selection/enhance', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ run_id: runId, tier2_enabled: true }),
        })
        if (!resp.ok) throw new Error(`API: ${resp.status}`)
        const data = await resp.json()
        if (!cancelled) {
          setResult(data)
          setPhase('done')
        }
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : '增强失败')
          setPhase('error')
        }
      }
    }
    run()
    return () => { cancelled = true }
  }, [runId])

  return (
    <div className="vw-modal-overlay" onClick={onClose}>
      <div className="vw-modal vw-modal-wide" onClick={e => e.stopPropagation()} style={{ maxHeight: '85vh' }}>
        <div className="vw-modal-hd">
          <h3><Sparkles size={18} style={{ marginRight: 6 }} />数据增强</h3>
          <span className="badge">{circuitCount} 回路</span>
          {phase !== 'running' && <button className="vw-modal-close" onClick={onClose}>✕</button>}
        </div>

        <div className="vw-modal-body">
          {phase === 'loading' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <p style={{ color: 'var(--text-muted)' }}>准备中...</p>
            </div>
          )}
          {phase === 'running' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <div style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>
                <Sparkles size={32} color="var(--primary)" />
              </div>
              <p style={{ marginTop: 12 }}>正在增强 {circuitCount} 条回路...</p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)' }}>Tier 1 自动修复 + Tier 2 LLM 建议生成中</p>
            </div>
          )}
          {phase === 'error' && (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <p style={{ color: 'var(--danger)' }}>{error}</p>
              <button className="btn btn-sm btn-primary" onClick={onClose} style={{ marginTop: 12 }}>关闭</button>
            </div>
          )}
          {phase === 'done' && result && (
            <div>
              {/* Quality score delta */}
              <div className="vpm-cards" style={{ marginBottom: 16 }}>
                <div className="vpm-card">
                  <span className="vpm-card-num">{result.quality_score_change.before_avg}</span>
                  <span>增强前均分</span>
                </div>
                <div className="vpm-card vpm-card-green">
                  <span className="vpm-card-num">{result.quality_score_change.after_avg}</span>
                  <span>增强后均分</span>
                </div>
                <div className="vpm-card vpm-card-blue">
                  <span className="vpm-card-num">
                    +{(result.quality_score_change.after_avg - result.quality_score_change.before_avg).toFixed(1)}
                  </span>
                  <span>提升</span>
                </div>
              </div>

              {/* Tier 1 summary */}
              <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                <Zap size={14} style={{ marginRight: 4 }} />
                Tier 1 自动修复 ({result.tier1_fixes.total} 项)
              </h4>
              <div style={{ fontSize: 13, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginBottom: 16 }}>
                <div>source_atlas 回填: <strong>{result.tier1_fixes.source_atlas_backfill}</strong></div>
                <div>溯源链补全: <strong>{result.tier1_fixes.provenance_backfill}</strong></div>
                <div>枚举标准化: <strong>{result.tier1_fixes.enum_normalization}</strong></div>
                <div>区域关联创建: <strong>{result.tier1_fixes.region_creation}</strong></div>
              </div>

              {/* Tier 2 summary */}
              <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                <Sparkles size={14} style={{ marginRight: 4 }} />
                Tier 2 LLM 建议 ({result.tier2_suggestions.total} 条，待审核)
              </h4>
              <div style={{ fontSize: 13, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                <div>证据文本: <strong>{result.tier2_suggestions.evidence_text}</strong></div>
                <div>描述补全: <strong>{result.tier2_suggestions.description}</strong></div>
                <div>功能交叉验证: <strong>{result.tier2_suggestions.function_crosscheck}</strong></div>
                <div>拓扑标志: <strong>{result.tier2_suggestions.topology_flags}</strong></div>
              </div>
            </div>
          )}
        </div>

        <div className="vw-modal-ft">
          {phase === 'done' && (
            <button className="btn btn-sm btn-primary" onClick={onClose}>完成</button>
          )}
        </div>
      </div>
    </div>
  )
}

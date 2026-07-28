import { useState, useCallback } from 'react'
import type { CircuitValidationRun } from '../validationCenterTypes'

interface Props {
  open: boolean
  granularityLevel?: string
  onClose: () => void
  onCreated: (run: CircuitValidationRun) => void
}

export function CreateRunModal({ open, granularityLevel, onClose, onCreated }: Props) {
  const [granularity, setGranularity] = useState(granularityLevel || 'all')
  const [maxObjects, setMaxObjects] = useState(20)
  const [dryRun, setDryRun] = useState(false)
  const [mode, setMode] = useState<'rule_only' | 'rule_and_dual_llm' | 'full_pipeline'>('rule_only')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [previewData, setPreviewData] = useState<{
    matched_candidate_count: number
    circuits: Array<{ id: string; label: string }>
  } | null>(null)

  const handlePreview = useCallback(async () => {
    setLoading(true)
    setError(null)
    setPreviewData(null)
    try {
      const body = {
        granularity_level: granularity,
        target_types: mode === 'rule_only' ? ['circuit'] : ['circuit', 'step'],
        dry_run: true,
        max_objects: maxObjects || undefined,
      }
      const res = await fetch('/api/validation/circuit/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errText = await res.text().catch(() => '')
        throw new Error(`API错误: ${res.status} ${errText.slice(0, 200)}`)
      }
      const data = await res.json()
      setPreviewData({
        matched_candidate_count: data.scan_stats?.matched_candidate_count ?? 0,
        circuits: data.scan_stats?.circuits ?? [],
      })
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '未知错误')
    } finally {
      setLoading(false)
    }
  }, [granularity, maxObjects, mode])

  const handleCreate = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const body = {
        granularity_level: granularity,
        target_types: mode === 'rule_only' ? ['circuit'] : ['circuit', 'step'],
        dry_run: dryRun,
        max_objects: maxObjects || undefined,
      }
      const res = await fetch('/api/validation/circuit/runs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) {
        const errText = await res.text().catch(() => '')
        throw new Error(`API错误: ${res.status} ${errText.slice(0, 200)}`)
      }
      const data = await res.json()
      // Strip scan_stats from the response for the CircuitValidationRun type
      const { scan_stats, ...runData } = data
      onCreated(runData as CircuitValidationRun)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '未知错误')
    } finally {
      setLoading(false)
    }
  }, [granularity, maxObjects, dryRun, mode, onCreated])

  if (!open) return null

  const ruleCount = 11
  const modeLabels: Record<string, string> = {
    rule_only: '仅规则校验 (11 项确定性检查)',
    rule_and_dual_llm: '规则 + 双模型盲审',
    full_pipeline: '完整流水线 (规则 + 盲审 + 人工审核就绪)',
  }

  return (
    <div className="vr-modal-overlay" onClick={onClose}>
      <div className="vr-modal" style={{ width: 560, maxHeight: '80vh' }} onClick={e => e.stopPropagation()}>
        <div className="vr-modal-hd">
          <h3>新建验证任务</h3>
          <button className="vr-modal-close" onClick={onClose}>✕</button>
        </div>
        <div className="vr-modal-body">
          {error && <div className="vr-error">{error}</div>}

          {/* Granularity */}
          <div className="vr-section">
            <h4>粒度</h4>
            <select
              className="form-select"
              value={granularity}
              onChange={e => setGranularity(e.target.value)}
              style={{ width: '100%', padding: '6px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)' }}
            >
              <option value="all">全部</option>
              <option value="macro_clinical">Major (宏观临床)</option>
              <option value="molecular_attr">Molecular (分子属性)</option>
              <option value="meso_anatomical">Sub (中观解剖)</option>
            </select>
          </div>

          {/* Max Objects */}
          <div className="vr-section">
            <h4>最大处理数量: {maxObjects}</h4>
            <input
              type="range"
              min={1}
              max={100}
              value={maxObjects}
              onChange={e => setMaxObjects(Number(e.target.value))}
              style={{ width: '100%' }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: 'var(--text-muted)' }}>
              <span>1</span><span>50</span><span>100</span>
            </div>
          </div>

          {/* Mode */}
          <div className="vr-section">
            <h4>运行模式</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {(['rule_only', 'rule_and_dual_llm', 'full_pipeline'] as const).map(m => (
                <label key={m} style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
                  <input type="radio" name="mode" checked={mode === m} onChange={() => setMode(m)} />
                  {modeLabels[m]}
                </label>
              ))}
            </div>
          </div>

          {/* Dry Run */}
          <div className="vr-section">
            <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 13 }}>
              <input type="checkbox" checked={dryRun} onChange={e => setDryRun(e.target.checked)} disabled={mode !== 'rule_only'} />
              仅 Dry Run (不保存结果，仅预览匹配数据)
            </label>
          </div>

          {/* Preview */}
          {previewData && (
            <div className="vr-section" style={{ background: '#f6ffed', padding: 12, borderRadius: 'var(--radius)' }}>
              <h4 style={{ color: 'var(--success)' }}>预览结果</h4>
              <p style={{ fontSize: 13 }}>匹配回路: <strong>{previewData.matched_candidate_count}</strong></p>
              <p style={{ fontSize: 13 }}>规则总数: <strong>{previewData.matched_candidate_count} x {ruleCount} = {previewData.matched_candidate_count * ruleCount}</strong></p>
              {previewData.circuits.length > 0 && (
                <div style={{ marginTop: 8, maxHeight: 120, overflowY: 'auto' }}>
                  {previewData.circuits.map((c, i) => (
                    <div key={c.id} style={{ fontSize: 12, padding: '2px 0' }}>
                      #{i + 1} {c.label}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="vr-modal-ft">
          <button className="btn btn-outline" onClick={onClose} disabled={loading}>取消</button>
          <button className="btn btn-outline" onClick={handlePreview} disabled={loading} style={{ borderColor: 'var(--primary)', color: 'var(--primary)' }}>
            {loading ? '处理中…' : '预览'}
          </button>
          <button className="btn btn-primary" onClick={handleCreate} disabled={loading}>
            {loading ? '创建中…' : dryRun ? '模拟创建' : '创建任务'}
          </button>
        </div>
      </div>
    </div>
  )
}

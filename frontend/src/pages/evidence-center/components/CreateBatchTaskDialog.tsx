import { useEffect, useState } from 'react'
import { createPaperEvidenceBatch, previewEvidenceBatchScope } from '../../../api/endpoints'

interface Props {
  open: boolean
  granularity: string
  onClose: () => void
  onCreated: (taskId: string) => void
  selectedIds?: string[]
}

export function CreateBatchTaskDialog({ open, granularity, onClose, onCreated, selectedIds = [] }: Props) {
  const [name, setName] = useState('')
  const [targetType, setTargetType] = useState('connection')
  const [mode, setMode] = useState<'function' | 'existence'>('function')
  const [scope, setScope] = useState('low_confidence')
  const [confidenceLt, setConfidenceLt] = useState('0.5')
  const [maxPapers, setMaxPapers] = useState('3')
  const [onlyOa, setOnlyOa] = useState(false)
  const [stopAfterStrong, setStopAfterStrong] = useState(false)
  const [limit, setLimit] = useState('20')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ estimated_target_count: number; over_limit: boolean; message: string | null } | null>(null)
  const [previewing, setPreviewing] = useState(false)

  useEffect(() => {
    if (!open) return
    setPreview(null)
    setPreviewing(true)
    const t = setTimeout(() => {
      void previewEvidenceBatchScope({
        target_type: targetType,
        scope,
        confidence_lt: scope === 'low_confidence' ? parseFloat(confidenceLt) || undefined : undefined,
        granularity_level: granularity || undefined,
        selected_ids: scope === 'selected' && selectedIds.length > 0 ? selectedIds.join(',') : undefined,
      }).then(r => setPreview({
        estimated_target_count: r.estimated_target_count,
        over_limit: r.over_limit,
        message: r.message,
      })).catch(() => setPreview(null)).finally(() => setPreviewing(false))
    }, 300)
    return () => clearTimeout(t)
  }, [open, targetType, scope, confidenceLt, granularity, selectedIds])

  if (!open) return null

  const create = async () => {
    setBusy(true)
    setMessage(null)
    try {
      const r = await createPaperEvidenceBatch({
        target_type: targetType,
        scope: scope === 'selected' ? 'selected' : scope,
        mode,
        max_papers_per_object: parseInt(maxPapers, 10) || 3,
        limit: parseInt(limit, 10) || 20,
        name: name || undefined,
        granularity_level: granularity || undefined,
        only_oa: onlyOa,
        confidence_lt: scope === 'low_confidence' ? parseFloat(confidenceLt) || undefined : undefined,
        stop_after_strong_support: stopAfterStrong,
        target_ids: scope === 'selected' ? selectedIds : undefined,
        filter_snapshot: scope !== 'selected' ? {
          target_type: targetType,
          granularity_level: granularity || undefined,
          confidence_lt: scope === 'low_confidence' ? parseFloat(confidenceLt) || undefined : undefined,
        } : undefined,
      })
      setMessage(`任务已创建（${r.task_ids?.length ?? r.target_count} 个对象任务）`)
      onCreated(r.task_id)
    } catch (err) {
      setMessage(`创建失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="ontology-modal-overlay" onClick={onClose}>
      <div className="ontology-modal" onClick={e => e.stopPropagation()} data-testid="create-batch-dialog">
        <div className="ontology-modal-header">
          <span className="ontology-card-title">创建论文佐证批量任务</span>
          <button type="button" className="btn btn-xs" onClick={onClose}>关闭</button>
        </div>
        <div className="ontology-modal-body">
          <div className="ontology-detail-row"><span>任务名称</span><input className="filter-input" value={name} onChange={e => setName(e.target.value)} placeholder="可选" /></div>
          <div className="ontology-detail-row"><span>对象类型</span>
            <select className="filter-select" value={targetType} onChange={e => {
              const t = e.target.value
              setTargetType(t)
              // connection/projection verify object existence by default
              if (t === 'connection' || t === 'projection') setMode('existence')
            }}>
              {['connection', 'projection_function', 'circuit', 'circuit_function', 'circuit_step', 'region_function'].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          <div className="ontology-detail-row"><span>佐证模式</span>
            <select className="filter-select" value={mode} onChange={e => setMode(e.target.value as 'function' | 'existence')}>
              <option value="function">功能佐证</option>
              <option value="existence">存在性佐证（只用区域检索，判断对象存在）</option>
            </select>
          </div>
          <div className="ontology-detail-row"><span>目标范围</span>
            <select className="filter-select" value={scope} onChange={e => setScope(e.target.value)}>
              <option value="selected">当前勾选对象（{selectedIds.length} 条）</option>
              <option value="low_confidence">当前颗粒度低置信对象</option>
            </select>
          </div>
          {scope === 'low_confidence' && (
            <div className="ontology-detail-row"><span>Confidence &lt;</span><input className="filter-input" style={{ width: 90 }} value={confidenceLt} onChange={e => setConfidenceLt(e.target.value)} /></div>
          )}
          <div className="ontology-detail-row"><span>每对象最多论文</span><input className="filter-input" style={{ width: 90 }} value={maxPapers} onChange={e => setMaxPapers(e.target.value)} /></div>
          <div className="ontology-detail-row"><span>最大对象数（limit）</span><input className="filter-input" style={{ width: 110 }} value={limit} onChange={e => setLimit(e.target.value)} /></div>
          <div className="ontology-detail-row"><span>仅 OA</span><input type="checkbox" checked={onlyOa} onChange={e => setOnlyOa(e.target.checked)} /></div>
          <div className="ontology-detail-row"><span>强支持后停止</span><input type="checkbox" checked={stopAfterStrong} onChange={e => setStopAfterStrong(e.target.checked)} /></div>
          <p className="ew-meta">颗粒度：{granularity || '当前'} · 预估对象数：{previewing ? '计算中…' : (preview?.estimated_target_count ?? '—')}</p>
          {preview && preview.estimated_target_count > 10000 && !preview.over_limit && (
            <div className="ew-meta">该任务包含大量对象，将在后台分批生成处理队列并执行。</div>
          )}
          {preview?.over_limit && <div className="ew-bad">{preview.message}</div>}
          {message && <div className="ontology-page-message">{message}</div>}
          <div className="ontology-modal-actions">
            <button type="button" data-testid="create-batch-confirm" className="btn btn-sm btn-primary" disabled={busy} onClick={create}>{busy ? '创建中…' : '创建任务'}</button>
            <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
          </div>
        </div>
      </div>
    </div>
  )
}

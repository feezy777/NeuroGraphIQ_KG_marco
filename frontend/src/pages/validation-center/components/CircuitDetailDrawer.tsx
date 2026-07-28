import { useState, useEffect } from 'react'

// ── Types ──────────────────────────────────────────────────────────────────
interface CircuitDetail {
  circuit: CircuitInfo
  granularity: GranularityInfo
  topology: TopologyInfo
  steps: StepInfo[]
  regions: RegionInfo[]
  functions: FunctionInfo[]
  evidence: EvidenceInfo[]
  validation: { results: ValidationResultInfo[] }
  extraction: ExtractionInfo
  raw_fields: { circuit: Record<string, string> }
}

interface CircuitInfo {
  id: string; circuit_name: string; name_cn?: string | null
  circuit_type: string; description?: string | null; function_association?: string | null
  confidence?: number | null; granularity_level: string; granularity_family?: string | null
  source_atlas: string; source_version?: string | null
  mirror_status: string; review_status: string; promotion_status: string
  evidence_text?: string | null; uncertainty_reason?: string | null
  canonical_start_region_id?: string | null; canonical_end_region_id?: string | null
  circuit_strength?: number | null
  created_at?: string | null; updated_at?: string | null
  resource_id?: string | null; batch_id?: string | null; llm_run_id?: string | null
}

interface GranularityInfo {
  level: string; family?: string | null; atlas: string; version?: string | null
  region_pool_match: boolean; mixed_granularity_warning?: string | null
}

interface TopologyInfo {
  circuit_type: string; closed_loop: boolean; canonical_key?: string | null
  node_count: number; start_region?: string | null; end_region?: string | null
}

interface StepInfo {
  step_order: number; step_name: string; step_type: string; role: string
  description?: string | null; confidence?: number | null
  evidence_text?: string | null; region_candidate_id?: string | null
  source_atlas?: string | null; granularity_level?: string | null
}

interface RegionInfo {
  role: string; sort_order: number; candidate_id?: string | null
  candidate?: { id: string; name: string; granularity_level?: string | null; source_atlas?: string | null } | null
}

interface FunctionInfo {
  id: string; function_term_en?: string | null; function_term_cn?: string | null
  function_domain?: string | null; function_role?: string | null; effect_type?: string | null
  confidence_score?: number | null; evidence_level?: string | null
  description?: string | null; evidence_text?: string | null
}

interface EvidenceInfo {
  id: string; evidence_type?: string | null; evidence_text?: string | null; source?: string | null
}

interface ValidationResultInfo {
  id: string; run_id: string; rule_overall_status?: string | null; rule_blocked?: boolean | null
  rule_validation_result_json?: unknown[] | null
  reviewer_a_decision?: string | null; reviewer_a_confidence?: number | null
  reviewer_b_decision?: string | null; reviewer_b_confidence?: number | null
  adjudication_status?: string | null
}

interface ExtractionInfo {
  resource_id?: string | null; batch_id?: string | null; llm_run_id?: string | null
  source_atlas?: string | null; confidence?: number | null
}

// ── Tab definitions ────────────────────────────────────────────────────────
type TabId = 'overview' | 'granularity' | 'topology' | 'steps' | 'regions' | 'functions' | 'evidence' | 'validation' | 'raw'

const TABS: Array<{ id: TabId; label: string }> = [
  { id: 'overview', label: '概览' },
  { id: 'granularity', label: '粒度' },
  { id: 'topology', label: '拓扑' },
  { id: 'steps', label: '步骤' },
  { id: 'regions', label: '脑区' },
  { id: 'functions', label: '功能' },
  { id: 'evidence', label: '证据' },
  { id: 'validation', label: '验证' },
  { id: 'raw', label: '原始' },
]

// ── Helpers ────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  pending: '#faad14',
  approved: '#52c41a',
  rejected: '#ff4d4f',
  not_promoted: '#86909c',
  promoted_to_final: '#2f54eb',
  llm_suggested: '#2f54eb',
  passed: '#52c41a',
  failed: '#ff4d4f',
  blocked: '#faad14',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待审核', approved: '已通过', rejected: '已拒绝',
  not_promoted: '未晋升', promoted_to_final: '已晋升',
  llm_suggested: 'LLM建议', passed: '通过', failed: '失败',
  blocked: '阻塞',
}

function statusStyle(status: string | null | undefined): { color: string; label: string } {
  const s = status ?? 'unknown'
  const color = STATUS_COLORS[s] || '#86909c'
  const label = STATUS_LABELS[s] || s
  return { color, label }
}

function badgeHtml(status: string | null | undefined): React.ReactNode {
  const { color, label } = statusStyle(status)
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 10,
      fontSize: 11, fontWeight: 600,
      background: color + '1a', color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  )
}

function fmt(s: string | number | null | undefined, fallback = '—'): string {
  if (s === null || s === undefined || s === '') return fallback
  return String(s)
}

function fmtConf(v: number | null | undefined): string {
  if (v === null || v === undefined || v === 0) return '—'
  return (v * 100).toFixed(0) + '%'
}

function fmtTime(s: string | null | undefined): string {
  if (!s) return '—'
  try { return s.slice(0, 16).replace('T', ' ') } catch { return s }
}

// ── Props ──────────────────────────────────────────────────────────────────
interface Props {
  circuitId: string | null
  onClose: () => void
}

// ── Detail row component ───────────────────────────────────────────────────
function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="vcd-row">
      <span className="vcd-row-label">{label}</span>
      <span className="vcd-row-value">{value}</span>
    </div>
  )
}

function SectionHeader({ title, count }: { title: string; count?: number }) {
  return (
    <div className="vcd-section-header">
      <span className="vcd-section-title">{title}</span>
      {count !== undefined && <span className="vcd-section-count">{count}</span>}
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return <div className="vcd-empty">{message}</div>
}

function LoadingState() {
  return <div className="vcd-loading">加载中…</div>
}

function ErrorState({ message }: { message: string }) {
  return <div className="vcd-error">{message}</div>
}

// ── Main Component ────────────────────────────────────────────────────────
export function CircuitDetailDrawer({ circuitId, onClose }: Props) {
  const [data, setData] = useState<CircuitDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabId>('overview')

  useEffect(() => {
    if (!circuitId) { setData(null); return }
    setLoading(true)
    setError(null)
    setActiveTab('overview')
    fetch(`/api/validation/circuit/candidates/${circuitId}`)
      .then(r => { if (!r.ok) throw new Error(`API错误: ${r.status}`); return r.json() })
      .then(d => setData(d))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : '加载失败'))
      .finally(() => setLoading(false))
  }, [circuitId])

  if (!circuitId) return null

  const c = data?.circuit
  const g = data?.granularity
  const t = data?.topology

  return (
    <div className="vcd-overlay" onClick={onClose}>
      <div className="vcd-drawer" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="vcd-header">
          <div className="vcd-header-text">
            <div className="vcd-header-name">
              <span className="vcd-circuit-name">{c?.circuit_name || circuitId.slice(0, 12)}</span>
              {c && <span className="vcd-type-badge">{c.circuit_type}</span>}
            </div>
            <div className="vcd-header-meta">
              {c && (
                <>
                  {badgeHtml(c.mirror_status)}
                  {badgeHtml(c.review_status)}
                  {badgeHtml(c.promotion_status)}
                </>
              )}
              {c && <span className="vcd-header-source">{c.source_atlas}</span>}
            </div>
          </div>
          <button className="vcd-close" onClick={onClose}>✕</button>
        </div>

        {/* Tabs */}
        <div className="vcd-tabs">
          {TABS.map(tab => (
            <button
              key={tab.id}
              className={`vcd-tab${activeTab === tab.id ? ' active' : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="vcd-body">
          {loading && <LoadingState />}
          {error && <ErrorState message={error} />}
          {!loading && !error && !data && <EmptyState message="无数据" />}
          {!loading && !error && data && activeTab === 'overview' && (
            <OverviewTab c={c!} g={g!} t={t!} />
          )}
          {!loading && !error && data && activeTab === 'granularity' && (
            <GranularityTab g={g!} />
          )}
          {!loading && !error && data && activeTab === 'topology' && (
            <TopologyTab t={t!} steps={data.steps} />
          )}
          {!loading && !error && data && activeTab === 'steps' && (
            <StepsTab steps={data.steps} />
          )}
          {!loading && !error && data && activeTab === 'regions' && (
            <RegionsTab regions={data.regions} />
          )}
          {!loading && !error && data && activeTab === 'functions' && (
            <FunctionsTab functions={data.functions} />
          )}
          {!loading && !error && data && activeTab === 'evidence' && (
            <EvidenceTab evidence={data.evidence} />
          )}
          {!loading && !error && data && activeTab === 'validation' && (
            <ValidationTab validation={data.validation} />
          )}
          {!loading && !error && data && activeTab === 'raw' && (
            <RawTab raw={data.raw_fields} />
          )}
        </div>
      </div>
    </div>
  )
}

// ── Tab Components ─────────────────────────────────────────────────────────

function OverviewTab({ c, g, t }: { c: CircuitInfo; g: GranularityInfo; t: TopologyInfo }) {
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="基本信息" />
      <div className="vcd-grid">
        <Row label="回路名称" value={c.circuit_name} />
        <Row label="中文名" value={fmt(c.name_cn)} />
        <Row label="回路类型" value={<span className="vcd-type-badge">{c.circuit_type}</span>} />
        <Row label="描述" value={fmt(c.description)} />
        <Row label="功能关联" value={fmt(c.function_association)} />
        <Row label="置信度" value={fmtConf(c.confidence)} />
        <Row label="回路强度" value={fmt(c.circuit_strength)} />
        <Row label="证据摘要" value={fmt(c.evidence_text)} />
        <Row label="不确定性原因" value={fmt(c.uncertainty_reason)} />
        <Row label="创建时间" value={fmtTime(c.created_at)} />
        <Row label="更新时间" value={fmtTime(c.updated_at)} />
      </div>

      <SectionHeader title="状态" />
      <div className="vcd-grid">
        <Row label="Mirror 状态" value={badgeHtml(c.mirror_status)} />
        <Row label="审核状态" value={badgeHtml(c.review_status)} />
        <Row label="晋升状态" value={badgeHtml(c.promotion_status)} />
      </div>

      <SectionHeader title="溯源" />
      <div className="vcd-grid">
        <Row label="资源 ID" value={<code>{fmt(c.resource_id)}</code>} />
        <Row label="批次 ID" value={<code>{fmt(c.batch_id)}</code>} />
        <Row label="LLM 运行 ID" value={<code>{fmt(c.llm_run_id)}</code>} />
      </div>
    </div>
  )
}

function GranularityTab({ g }: { g: GranularityInfo }) {
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="粒度信息" />
      <div className="vcd-grid">
        <Row label="粒度级别" value={g.level} />
        <Row label="粒度家族" value={fmt(g.family)} />
        <Row label="数据源图谱" value={g.atlas} />
        <Row label="源版本" value={fmt(g.version)} />
        <Row label="脑区池匹配" value={g.region_pool_match ? '是' : '否'} />
        <Row label="混合粒度警告" value={fmt(g.mixed_granularity_warning)} />
      </div>
    </div>
  )
}

function TopologyTab({ t, steps }: { t: TopologyInfo; steps: StepInfo[] }) {
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="拓扑信息" />
      <div className="vcd-grid">
        <Row label="回路类型" value={<span className="vcd-type-badge">{t.circuit_type}</span>} />
        <Row label="闭环" value={t.closed_loop ? '是' : '否'} />
        <Row label="Canonical Key" value={fmt(t.canonical_key)} />
        <Row label="节点数" value={String(t.node_count)} />
        <Row label="起始脑区" value={fmt(t.start_region)} />
        <Row label="终止脑区" value={fmt(t.end_region)} />
      </div>

      {steps.length > 0 && (
        <>
          <SectionHeader title="步骤链" count={steps.length} />
          <div className="vcd-step-chain">
            {steps.map((s, i) => (
              <div key={i} className="vcd-step-node">
                <div className="vcd-step-order">{s.step_order}</div>
                <div className="vcd-step-info">
                  <span className="vcd-step-name">{s.step_name}</span>
                  <span className="vcd-step-type">{s.step_type}</span>
                </div>
                {i < steps.length - 1 && <div className="vcd-step-arrow">→</div>}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function StepsTab({ steps }: { steps: StepInfo[] }) {
  if (steps.length === 0) return <EmptyState message="无步骤数据" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="回路步骤" count={steps.length} />
      <table className="vcd-table">
        <thead>
          <tr>
            <th>序号</th>
            <th>名称</th>
            <th>类型</th>
            <th>角色</th>
            <th>置信度</th>
            <th>粒度</th>
          </tr>
        </thead>
        <tbody>
          {steps.map((s, i) => (
            <tr key={i} className={i % 2 === 1 ? 'even' : ''}>
              <td style={{ textAlign: 'center' }}>{s.step_order}</td>
              <td className="vcd-td-name">{s.step_name}</td>
              <td><span className="vcd-tag">{s.step_type}</span></td>
              <td>{s.role}</td>
              <td>{fmtConf(s.confidence)}</td>
              <td style={{ fontSize: 12 }}>{fmt(s.granularity_level)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RegionsTab({ regions }: { regions: RegionInfo[] }) {
  if (regions.length === 0) return <EmptyState message="无脑区数据" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="涉及脑区" count={regions.length} />
      <table className="vcd-table">
        <thead>
          <tr>
            <th>角色</th>
            <th>排序</th>
            <th>脑区名称</th>
            <th>粒度</th>
            <th>数据源</th>
          </tr>
        </thead>
        <tbody>
          {regions.map((r, i) => (
            <tr key={i} className={i % 2 === 1 ? 'even' : ''}>
              <td><span className="vcd-tag">{r.role}</span></td>
              <td style={{ textAlign: 'center' }}>{r.sort_order}</td>
              <td className="vcd-td-name">{r.candidate?.name || fmt(r.candidate_id)}</td>
              <td style={{ fontSize: 12 }}>{fmt(r.candidate?.granularity_level)}</td>
              <td style={{ fontSize: 12 }}>{fmt(r.candidate?.source_atlas)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FunctionsTab({ functions }: { functions: FunctionInfo[] }) {
  if (functions.length === 0) return <EmptyState message="无功能数据" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="回路功能" count={functions.length} />
      <table className="vcd-table">
        <thead>
          <tr>
            <th>英文术语</th>
            <th>中文术语</th>
            <th>领域</th>
            <th>角色</th>
            <th>效应类型</th>
            <th>置信度</th>
            <th>证据等级</th>
          </tr>
        </thead>
        <tbody>
          {functions.map((f, i) => (
            <tr key={f.id} className={i % 2 === 1 ? 'even' : ''}>
              <td className="vcd-td-name">{fmt(f.function_term_en)}</td>
              <td>{fmt(f.function_term_cn)}</td>
              <td>{fmt(f.function_domain)}</td>
              <td>{fmt(f.function_role)}</td>
              <td>{fmt(f.effect_type)}</td>
              <td>{fmtConf(f.confidence_score)}</td>
              <td>{fmt(f.evidence_level)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EvidenceTab({ evidence }: { evidence: EvidenceInfo[] }) {
  if (evidence.length === 0) return <EmptyState message="无证据记录" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="证据记录" count={evidence.length} />
      {evidence.map((e, i) => (
        <div key={e.id} className="vcd-evidence-card">
          <div className="vcd-evidence-header">
            <span className="vcd-tag">{fmt(e.evidence_type)}</span>
            <span className="vcd-evidence-source">{fmt(e.source)}</span>
          </div>
          <div className="vcd-evidence-text">{e.evidence_text || '—'}</div>
        </div>
      ))}
    </div>
  )
}

function ValidationTab({ validation }: { validation: { results: ValidationResultInfo[] } }) {
  const results = validation.results
  if (results.length === 0) return <EmptyState message="无验证结果" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="验证结果" count={results.length} />
      {results.map((v, i) => {
        const ruleBadge = statusStyle(v.rule_overall_status)
        const adjBadge = statusStyle(v.adjudication_status)
        const aDecBadge = statusStyle(v.reviewer_a_decision)
        const bDecBadge = statusStyle(v.reviewer_b_decision)
        return (
          <div key={v.id} className="vcd-validation-card">
            <div className="vcd-validation-row">
              <span className="vcd-validation-label">运行 ID</span>
              <code>{fmt(v.run_id)}</code>
            </div>
            <div className="vcd-validation-row">
              <span className="vcd-validation-label">规则状态</span>
              <span style={{ color: ruleBadge.color, fontWeight: 600 }}>{ruleBadge.label}</span>
            </div>
            {v.rule_blocked && <div className="vcd-validation-blocked">规则校验阻塞</div>}
            <div className="vcd-validation-row">
              <span className="vcd-validation-label">Reviewer A</span>
              <span>{aDecBadge.label} ({fmtConf(v.reviewer_a_confidence)})</span>
            </div>
            <div className="vcd-validation-row">
              <span className="vcd-validation-label">Reviewer B</span>
              <span>{bDecBadge.label} ({fmtConf(v.reviewer_b_confidence)})</span>
            </div>
            <div className="vcd-validation-row">
              <span className="vcd-validation-label">裁决状态</span>
              <span style={{ color: adjBadge.color, fontWeight: 600 }}>{adjBadge.label}</span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function RawTab({ raw }: { raw: { circuit: Record<string, string> } }) {
  const entries = Object.entries(raw.circuit || {})
  if (entries.length === 0) return <EmptyState message="无原始字段" />
  return (
    <div className="vcd-tab-content">
      <SectionHeader title="原始字段" count={entries.length} />
      <table className="vcd-table vcd-table-compact">
        <thead>
          <tr>
            <th>字段名</th>
            <th>值</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([k, v], i) => (
            <tr key={k} className={i % 2 === 1 ? 'even' : ''}>
              <td className="vcd-td-key"><code>{k}</code></td>
              <td className="vcd-td-val" style={{ wordBreak: 'break-all', fontSize: 12 }}>{v}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

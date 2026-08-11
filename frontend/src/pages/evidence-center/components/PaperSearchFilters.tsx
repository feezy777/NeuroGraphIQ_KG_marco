/** 佐证提取模式:auto=按对象类型自动推导 / function=功能性 / existence=存在性 */
export type EvidenceMode = 'auto' | 'function' | 'existence'

/** 年份下拉可选项(下限过滤:仅保留该年份及以后的论文) */
const YEAR_OPTIONS = ['2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026']

interface Props {
  /** 仅 OA 过滤开关 */
  oaOnly: boolean
  onOaOnlyChange: (checked: boolean) => void
  /** 证据模式(自动/存在性/功能性) */
  mode: EvidenceMode
  onModeChange: (mode: EvidenceMode) => void
  /** 年份下限过滤('' = 不限) */
  year: string
  onYearChange: (year: string) => void
  /** 恢复默认:重置 仅OA/模式/年份 为默认值 */
  onRestoreDefaults: () => void
  /** 已排除论文数(>0 时提示可通过 [恢复排除] 找回) */
  excludedCount: number
  onRestoreExcluded: () => void
}

/** 检索过滤层:☐仅OA / 证据模式 / 年份 / [恢复默认] + [恢复排除](被排除论文找回) */
export function PaperSearchFilters({
  oaOnly,
  onOaOnlyChange,
  mode,
  onModeChange,
  year,
  onYearChange,
  onRestoreDefaults,
  excludedCount,
  onRestoreExcluded,
}: Props) {
  return (
    <div className="evidence-search-layer">
      <h4 className="evidence-search-title">检索过滤</h4>
      <div className="evidence-search-row">
        <label className="evidence-search-filter">
          <input type="checkbox" checked={oaOnly} onChange={e => onOaOnlyChange(e.target.checked)} />
          仅 OA
        </label>
        <label className="evidence-search-filter">
          证据模式
          <select
            className="filter-select"
            value={mode}
            onChange={e => onModeChange(e.target.value as EvidenceMode)}
          >
            <option value="auto">自动</option>
            <option value="existence">存在性</option>
            <option value="function">功能性</option>
          </select>
        </label>
        <label className="evidence-search-filter">
          年份
          <select
            className="filter-select evidence-search-year"
            value={year}
            onChange={e => onYearChange(e.target.value)}
          >
            <option value="">不限</option>
            {YEAR_OPTIONS.map(y => (
              <option key={y} value={y}>{y} 年</option>
            ))}
          </select>
        </label>
        <button type="button" className="btn btn-xs" onClick={onRestoreDefaults}>
          恢复默认
        </button>
        <button type="button" className="btn btn-xs" disabled={excludedCount === 0} onClick={onRestoreExcluded}>
          恢复排除
        </button>
      </div>
    </div>
  )
}

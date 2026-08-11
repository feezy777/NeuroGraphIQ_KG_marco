interface Props {
  /** 可见搜索结果是否全部勾选(决定 ☐全选 状态) */
  allSelected: boolean
  onToggleAll: (checked: boolean) => void
  /** 当前勾选论文数(按钮文案 N) */
  selectedCount: number
  busy: boolean
  onExtractSelected: () => void
  /** 是否有可选论文(无 → ☐全选 禁用) */
  canSelect: boolean
  /** 是否有检索结果(决定是否显示 [收起检索]) */
  canCollapse: boolean
  onCollapse: () => void
}

/** 批量操作层:☐全选 + [提取所选论文(N)](N=0 禁用)+ [收起检索] */
export function PaperBatchActions({
  allSelected,
  onToggleAll,
  selectedCount,
  busy,
  onExtractSelected,
  canSelect,
  canCollapse,
  onCollapse,
}: Props) {
  return (
    <div className="evidence-search-layer">
      <h4 className="evidence-search-title">批量操作</h4>
      <div className="evidence-search-row">
        <label className="evidence-search-filter">
          <input
            type="checkbox"
            data-testid="paper-batch-select-all"
            checked={allSelected && canSelect}
            disabled={!canSelect || busy}
            onChange={e => onToggleAll(e.target.checked)}
          />
          全选
        </label>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          data-testid="evidence-batch-extract"
          disabled={busy || selectedCount === 0}
          onClick={onExtractSelected}
        >
          提取所选论文（{selectedCount}）
        </button>
        {canCollapse && (
          <button type="button" className="btn btn-xs" onClick={onCollapse}>
            收起检索
          </button>
        )}
      </div>
    </div>
  )
}

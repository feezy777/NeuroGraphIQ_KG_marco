import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import type { DetailRow } from './types'

/** JSON 字符串 → 纯字符串数组；非数组或解析失败 → null（按普通字段直显） */
function parseStringArray(value: string): string[] | null {
  try {
    const parsed: unknown = JSON.parse(value)
    if (Array.isArray(parsed) && parsed.every(item => typeof item === 'string')) {
      return parsed as string[]
    }
  } catch {
    // 普通字符串
  }
  return null
}

const ITEM_PREVIEW_LENGTH = 16

function itemPreview(item: string): string {
  return item.length > ITEM_PREVIEW_LENGTH ? `${item.slice(0, ITEM_PREVIEW_LENGTH)}...` : item
}

/**
 * Detail 行值渲染（Provenance 专业化展示，RowList 通用行共用）：
 * - code 类字段（mono）：等宽 + 单行省略，hover tooltip 显示完整值
 * - 数组字段（如 original_connection_ids / original_relation_types / original_confidence）：
 *   "N items" + 逐项 `[ e20a1be7... ]` 预览 + Expand JSON 折叠区显示完整内容
 * - 普通字段：直接显示（长文本由 CSS word-break / overflow-wrap 处理）
 */
export function ProvenanceField({ row }: { row: DetailRow }) {
  const [expanded, setExpanded] = useState(false)
  const items = parseStringArray(row.value)

  if (!items) {
    return (
      <dd
        className={row.mono ? 'oc-detail-value-code' : undefined}
        title={row.mono ? row.value : undefined}
      >
        {row.value}
      </dd>
    )
  }

  return (
    <dd className="oc-provenance-array">
      <span className="oc-provenance-count">{items.length} items</span>
      <ul className="oc-provenance-item-list">
        {items.map((item, index) => (
          <li key={index} className="oc-provenance-item" title={item}>
            [ {itemPreview(item)} ]
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="oc-provenance-expand"
        aria-expanded={expanded}
        onClick={() => setExpanded(prev => !prev)}
      >
        {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        Expand JSON
      </button>
      {expanded && (
        <pre className="oc-provenance-json">{JSON.stringify(JSON.parse(row.value), null, 2)}</pre>
      )}
    </dd>
  )
}

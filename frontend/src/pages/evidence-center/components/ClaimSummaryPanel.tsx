import { useMemo } from 'react'
import type { ClaimComponent } from './types'
import { COMPONENT_LABEL } from './types'

interface ClaimSummaryPanelProps {
  claimText: string
  components: ClaimComponent[]
  targetType: string
  granularity?: string | null
}

interface Block {
  label: string
  value: string
  icon: string
}

/** component_type → 块图标(字符体系,与「→」「·」等既有排版保持一致) */
const BLOCK_ICON: Record<string, string> = {
  source_region: '◉', // 位置
  target_region: '◎', // 靶点
  relation: '⇄', // 连接
  direction: '→', // 方向
  function: 'ƒ', // 功能
  circuit_identity: '↻', // 回路
  circuit_role: '◈', // 角色
  step_order: '№', // 步骤
  context: 'ⓘ', // 辅助
}

/** 候选模块左栏:「当前需要验证的事实」—— 由 claim_components 动态生成的独立信息块(类型/源脑区/目标脑区/连接关系/方向等);
 * 无 components 时回退为 claimText 单块 */
export function ClaimSummaryPanel({ claimText, components, targetType, granularity }: ClaimSummaryPanelProps) {
  const blocks = useMemo<Block[]>(() => {
    const out: Block[] = []
    if (targetType) out.push({ label: '类型', value: targetType, icon: '#' })
    for (const c of components) {
      if (!c.statement) continue
      out.push({
        label: COMPONENT_LABEL[c.component_type] ?? '信息',
        value: c.statement,
        icon: BLOCK_ICON[c.component_type] ?? '•',
      })
    }
    return out
  }, [components, targetType])

  const fallback = blocks.length === 0

  return (
    <section className="evidence-claim-summary" data-testid="evidence-claim-summary">
      <div className="evidence-claim-head">
        <h4>当前需要验证的事实</h4>
        {granularity && <span className="ew-meta">{granularity}</span>}
      </div>
      {fallback ? (
        <div className="evidence-claim-block" data-testid="evidence-claim-block">
          <span className="evidence-claim-block-icon">•</span>
          <div className="evidence-claim-block-body">
            <div className="evidence-claim-block-label">事实</div>
            <div className="evidence-claim-block-value">{claimText || '—'}</div>
          </div>
        </div>
      ) : (
        <div className="evidence-claim-blocks">
          {blocks.map((b, i) => (
            <div className="evidence-claim-block" data-testid="evidence-claim-block" key={`${b.label}:${i}`}>
              <span className="evidence-claim-block-icon">{b.icon}</span>
              <div className="evidence-claim-block-body">
                <div className="evidence-claim-block-label">{b.label}</div>
                <div className="evidence-claim-block-value">{b.value}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

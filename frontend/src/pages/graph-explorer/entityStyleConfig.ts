/**
 * 实体类型样式配置（唯一事实源）。
 * 节点渲染（GraphVisualizationAdapter 样式）、图例（FinalKgGraphCanvas）、
 * 以及 graphTheme.ts 的兼容导出**必须共同引用本文件** —— 保证节点颜色/图标/
 * 名称标签与 Legend 永远一致（用户规格：统一 Legend 配置）。
 */
import type { CanonicalNodeType } from './adapters/finalKgAdapter'

export interface EntityStyleDef {
  /** 节点主色（图例色块 / 节点描边 / icon 色） */
  color: string
  /** 节点填充色（极浅底,科研白卡系） */
  background: string
  /** 图标（canvas 渲染用 unicode 符号;web 平台有 emoji 字体兜底） */
  icon: string
  /** 图例/类型名 */
  label: string
  /** 节点形状（Cytoscape） */
  shape: 'ellipse' | 'round-rectangle' | 'hexagon' | 'octagon'
  /** 节点尺寸（px,宽=高,非圆用 width/height 分开可扩展） */
  size: number
}

export const ENTITY_STYLE_CONFIG: Record<CanonicalNodeType, EntityStyleDef> = {
  brain_region: {
    color: '#3b82f6',
    background: '#ffffff',
    icon: '🧠',
    label: 'Brain Region',
    shape: 'ellipse',
    size: 56,
  },
  connection: {
    color: '#0ea5a4',
    background: '#f0fdfa',
    icon: '→',
    label: 'Connection',
    shape: 'round-rectangle',
    size: 44,
  },
  circuit: {
    color: '#7c3aed',
    background: '#f5f3ff',
    icon: '◉',
    label: 'Circuit',
    shape: 'hexagon',
    size: 54,
  },
  circuit_step: {
    color: '#64748b',
    background: '#f8fafc',
    icon: '↳',
    label: 'Circuit Step',
    shape: 'ellipse',
    size: 36,
  },
  function: {
    color: '#f59e0b',
    background: '#fff7ed',
    icon: 'ƒ',
    label: 'Function',
    shape: 'ellipse',
    size: 48,
  },
  evidence: {
    color: '#94a3b8',
    background: '#f8fafc',
    icon: '🗎',
    label: 'Evidence',
    shape: 'octagon',
    size: 44,
  },
}

/** 图例顺序（科研图自上而下,核心类型优先） */
export const ENTITY_LEGEND_ORDER: CanonicalNodeType[] = [
  'brain_region',
  'connection',
  'circuit',
  'function',
  'evidence',
]

export function entityStyleOf(type: CanonicalNodeType): EntityStyleDef {
  return ENTITY_STYLE_CONFIG[type]
}

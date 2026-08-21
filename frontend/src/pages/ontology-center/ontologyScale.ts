/**
 * Ontology Center 尺度模型（BR4 multiscale）。
 *
 * 浏览器局部状态，与全局 useGlobalGranularity（旧 workbench 五档键）完全解耦：
 * 全局粒度是数据中心的语境开关，本体中心按后端 canonical 词表
 * （macro/clinical/meso/subregion/fine/cyto/molecular）独立切换，
 * 互不影响（granularity-isolation-principle）。
 *
 * 语义（2026-08-21 修订）：
 * - Brain Region 组 = 粒度透镜：只过滤树的显示深度（level_order ≤ 所选尺度），
 *   树结构始终来自 canonical_region_hierarchy，不再按粒度拍平树顶层；
 * - Biological Layer 组 = 实体根切换：cyto/molecular 切到跨层注册表树
 *   （GET /api/multiscale/cell-types | molecular-entities）。
 * 默认 fine：完整层级（到 subregion/fine）可见，Whole-brain/Macro/Clinical
 * 默认展开、Meso 及以下可见但折叠，由用户逐级展开。
 */

export type OntologyScaleKey =
  | 'macro'
  | 'clinical'
  | 'meso'
  | 'subregion'
  | 'fine'
  | 'cyto'
  | 'molecular'

export interface OntologyScaleOption {
  key: OntologyScaleKey
  label: string
  /** 悬浮提示（英文，按规格） */
  hint: string
}

export const BRAIN_REGION_SCALES: readonly OntologyScaleOption[] = [
  { key: 'macro', label: 'Macro', hint: 'Brain system level' },
  { key: 'clinical', label: 'Clinical', hint: 'Clinical region hierarchy' },
  { key: 'meso', label: 'Meso', hint: 'Regional organization' },
  { key: 'subregion', label: 'Subregion', hint: 'Subregional parcellation' },
  { key: 'fine', label: 'Fine', hint: 'Fine cytoarchitectonic areas' },
]

export const BIOLOGICAL_LAYER_SCALES: readonly OntologyScaleOption[] = [
  { key: 'cyto', label: 'Cyto', hint: 'Cell type taxonomy' },
  { key: 'molecular', label: 'Molecular', hint: 'Gene/protein level' },
]

export const ONTOLOGY_SCALES: readonly OntologyScaleOption[] = [
  ...BRAIN_REGION_SCALES,
  ...BIOLOGICAL_LAYER_SCALES,
]

export const DEFAULT_ONTOLOGY_SCALE: OntologyScaleKey = 'fine'

/** URL hash（#/ontology-center?oc_scale=…）等外部字符串 → 尺度键的类型守卫。 */
export function isOntologyScaleKey(value: string): value is OntologyScaleKey {
  return ONTOLOGY_SCALES.some(option => option.key === value)
}

/**
 * 统一本体树节点模型（Phase 1 通用 Ontology Tree Explorer）。
 * 六种实体（region/connection/circuit/function/cell_type/molecule）共用同一节点结构，
 * 未来粒度扩展无需改动组件——树只消费 hasChildren/children，不写死层级。
 * BR4：cell_type / molecule 是跨层注册表实体，永不进入脑区 partonomy。
 */

export type OntologyEntityType =
  | 'region'
  | 'connection'
  | 'circuit'
  | 'function'
  | 'cell_type'
  | 'molecule'

export const ENTITY_TYPE_LABELS: Record<OntologyEntityType, string> = {
  region: 'Brain Region',
  connection: 'Connection',
  circuit: 'Circuit',
  function: 'Function',
  cell_type: 'Cell Type',
  molecule: 'Molecule',
}

export interface OntologyTreeNode {
  id: string
  /** 标准代码（ng:br:* / ng:cn:* / ng:ci:* / ng:fn:*）；分类根节点为 null */
  code: string | null
  name: string
  entityType: OntologyEntityType
  /** 粒度层级（whole_brain/macro/clinical/research/...）；无层级实体为 null */
  granularityLevel?: string | null
  status?: string | null
  /**
   * true  = 可展开（懒加载或 children 内联）
   * false = 叶子
   * undefined = 未知（展开时探测一次）
   */
  hasChildren?: boolean
  /** 内联子节点；缺省时按 hasChildren 懒加载 */
  children?: OntologyTreeNode[]
  /** 一级分类节点（Brain Region / Connection / ...）：点击 = 切换展开，不进入选中态 */
  isEntityRoot?: boolean
  /** 虚拟分组节点（connection_type / circuit_type 分组）：仅展开/收起，不可选中 */
  isGroup?: boolean
}

/**
 * BR3 十级交错序（level_order）：whole_brain=0 … molecular=9。
 * 仅用于「粒度透镜」显示过滤与默认展开级联——树结构本身
 * 一律来自 canonical_region_hierarchy，level 永不参与父子判定。
 */
export const GRANULARITY_LEVEL_ORDER: Record<string, number> = {
  whole_brain: 0,
  macro: 1,
  clinical: 2,
  meso: 3,
  research: 4,
  subregion: 5,
  fine: 6,
  cyto: 7,
  ultra_fine: 8,
  molecular: 9,
}

/** 面向医生的节点徽章名（不显示 L0-L9 数字，避免误读为临床分级） */
export const GRANULARITY_LEVEL_NAMES: Record<string, string> = {
  whole_brain: 'Whole-brain',
  macro: 'Macro',
  clinical: 'Clinical',
  meso: 'Meso',
  research: 'Research',
  subregion: 'Subregion',
  fine: 'Fine',
  cyto: 'Cyto',
  ultra_fine: 'Ultra-fine',
  molecular: 'Molecular',
}

import type { OntologyQueryCategory, OntologyQueryIntent } from '../../../api/ontologyQueryApi'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'

/** 意图 → 中文标签（结果面板头部意图 chip） */
export const QUERY_INTENT_LABELS: Record<OntologyQueryIntent, string> = {
  region_children: '亚区查询',
  region_connections: '连接查询',
  region_circuits: '回路查询',
  region_functions: '功能查询',
  region_multiscale: '细胞与分子查询',
  unresolved: '未识别',
}

/** 结果条目分类 → 中文标签（分组标题） */
export const QUERY_CATEGORY_LABELS: Record<OntologyQueryCategory, string> = {
  children: '亚区',
  connection: '连接',
  circuit: '回路',
  function: '功能',
  cell_type: '细胞类型',
  molecule: '分子',
}

/** 匹配层级 → 中文说明（Entity Match Card） */
export const MATCHED_BY_LABELS: Record<string, string> = {
  canonical_name_cn: '中文名精确匹配',
  canonical_name_en: '英文名精确匹配',
  alias: '候选别名匹配',
  synonym: '同义词匹配',
}

/** 结果分类 → 本体实体类型（结果项点击跳转本体详情用） */
export const CATEGORY_TO_ENTITY_TYPE: Record<OntologyQueryCategory, OntologyEntityType> = {
  children: 'region',
  connection: 'connection',
  circuit: 'circuit',
  function: 'function',
  cell_type: 'cell_type',
  molecule: 'molecule',
}

/** 结果分组顺序（保持后端语义优先级；未知分类排最后） */
export const QUERY_CATEGORY_ORDER: OntologyQueryCategory[] = [
  'children',
  'connection',
  'circuit',
  'function',
  'cell_type',
  'molecule',
]

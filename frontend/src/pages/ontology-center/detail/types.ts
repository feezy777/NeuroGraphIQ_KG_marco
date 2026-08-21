import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'

/** 指向任意本体实体的引用（详情/关系/图共享） */
export interface EntityRef {
  id: string
  code: string | null
  name: string
  entityType: OntologyEntityType
  granularityLevel?: string | null
  status?: string | null
}

export interface DetailRow {
  label: string
  value: string
  /** code 类字段：等宽字体 + 单行省略，hover tooltip 显示完整值 */
  mono?: boolean
}

/** 跨尺度生物层条目：cell type（relation = mapping_type）/ molecule（relation = evidence_type） */
export interface MultiscaleBioItem {
  ref: EntityRef
  /** 关系/证据类型：cell type 的 mapping_type（如 contains）/ molecule 的 evidence_type（如 expression） */
  relation: string
  confidence: number | null
  /** 补充证据：cell type 的 taxonomy_source / molecule 的 source（如 GTEx 数据来源） */
  detail: string | null
}

/** BR4 multiscale 视图（GET /api/canonical-regions/{id}/multiscale，仅 region 详情携带） */
export interface RegionMultiscaleData {
  /** 全部 meso 级后裔（含直接 meso 子节点） */
  mesoRegions: EntityRef[]
  subregions: EntityRef[]
  fineRegions: EntityRef[]
  cellTypes: MultiscaleBioItem[]
  molecules: MultiscaleBioItem[]
}

/**
 * 统一实体详情数据（EntityDetailAdapter 输出）：
 * 四类实体共用同一结构，EntityDetailPanel 只按该结构渲染，
 * 不为每类实体写独立详情页。
 */
export interface EntityDetailData {
  entityType: OntologyEntityType
  id: string
  name: string
  code: string | null
  status: string | null
  granularityLevel: string | null
  confidence: number | null
  description: string | null
  /** 基本信息补充行（名称/代码/层级/状态之外） */
  basic: DetailRow[]
  /** 层级路径（根 → 自身）；非层级实体为 [自身] */
  path: EntityRef[]
  parent: EntityRef | null
  children: EntityRef[]
  /** provenance 行（source / evidence / atlas 等） */
  provenance: DetailRow[]
  /** BR4 多尺度视图（仅 region：children 粒度桶 + 跨层 cell types / molecules） */
  multiscale?: RegionMultiscaleData | null
  /** Connection 专用：人类可读主标题（如 "Association connection"）；缺省用 name */
  typeTitle?: string | null
  /** Connection 专用：Source / Target 脑区引用（Inspector 端点卡片） */
  source?: EntityRef | null
  target?: EntityRef | null
}

export interface RelationItem {
  ref: EntityRef
  /** 关系修饰（role / direction / relation_type / 置信度…） */
  meta: DetailRow[]
}

export interface RelationGroup {
  key: string
  label: string
  /** 后端 API 暂未提供该关系（→ 显示「暂无数据」，不写假数据） */
  unavailable?: boolean
  /** false = 行不可点击跳转（如对齐候选等非实体记录） */
  navigable?: boolean
  items: RelationItem[]
}

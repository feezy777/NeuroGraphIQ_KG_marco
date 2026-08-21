import {
  getCanonicalCircuit,
  getCanonicalConnection,
  getCanonicalRegion,
  getCanonicalRegionMultiscale,
  getCanonicalRegionParent,
  getOntologyTermDetail,
  listAtlasRegionMappings,
  listAtlasRegions,
  listCanonicalCircuitConnections,
  listCanonicalCircuitFunctions,
  listCanonicalCircuitRegions,
  listCanonicalCircuits,
  listCanonicalConnections,
  listCanonicalRegionAncestors,
  listCanonicalRegionChildren,
  listCanonicalRegionRoots,
  listCanonicalRegions,
  listCellTypes,
  listMolecularEntities,
  listOntologyTerms,
  listRegionCandidates,
  listRegionCellAlignments,
  listRegionCircuits,
  listRegionConnections,
  listRegionFunctions,
  listRegionMolecularAlignments,
  listTermHierarchyChildren,
  listTermHierarchyParents,
  type AtlasRegionItem,
  type CanonicalCircuit,
  type CanonicalConnection,
  type CanonicalRegion,
  type CellTypeItem,
  type HierarchyNodeRead,
  type MolecularEntityItem,
  type OntologyTerm,
} from './endpoints'
import type { OntologyScaleKey } from '../pages/ontology-center/ontologyScale'
import {
  GRANULARITY_LEVEL_ORDER,
  type OntologyEntityType,
  type OntologyTreeNode,
} from '../pages/ontology-center/browser/tree/OntologyTreeNode'
import type {
  DetailRow,
  EntityDetailData,
  EntityRef,
  MultiscaleBioItem,
  RelationGroup,
  RelationItem,
} from '../pages/ontology-center/detail/types'

const ROLE_LABELS: Record<string, string> = {
  core_region: '核心区域',
  input: '输入',
  output: '输出',
  intermediate: '中间',
}

// ─── 通用辅助 ──────────────────────────────────────────────────────────

/** 失败 → null（非主体数据降级为空，不 blank 整个面板） */
async function settled<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise
  } catch {
    return null
  }
}

function confidenceText(value: number | null | undefined): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

function summaryRows(summary: Record<string, unknown>): DetailRow[] {
  return Object.entries(summary).map(([key, value]) => ({
    label: key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }))
}

/** 来源摘要 → Basic Info 单行「来源」文本（字符串值优先，如 atlas 名；去重后连接） */
function sourceSummaryLabel(summary: Record<string, unknown> | null | undefined): string {
  const parts = Object.entries(summary ?? {}).map(([key, value]) =>
    typeof value === 'string' && value.trim() !== '' ? value : key,
  )
  return [...new Set(parts)].join(', ') || '—'
}

// ─── 人类可读名称 / 类型标题（信息优先级：名称 > 关系结构 > code > provenance） ──

function titleCase(value: string): string {
  if (!value) return value
  return value.charAt(0).toUpperCase() + value.slice(1)
}

/** "association" → "Association connection"（Inspector 主标题用） */
function connectionTypeTitle(type: string): string {
  return `${titleCase(type)} connection`
}

/**
 * 连接无人类可读名称字段（只有 connection_code）——从 code 推导展示名：
 * ng:cn:association_pars_triangularis_to_posterior_cingulate
 * → pars triangularis → posterior cingulate（去前缀、去类型前缀、下划线转空格）
 */
function connectionDisplayName(connection: CanonicalConnection): string {
  const code = connection.connection_code
  let name = code.startsWith('ng:cn:') ? code.slice('ng:cn:'.length) : code
  const typePrefix = `${connection.connection_type}_`
  if (name.startsWith(typePrefix)) name = name.slice(typePrefix.length)
  return name.replace(/_to_/g, ' → ').replace(/_/g, ' ')
}

/** 全量 canonical 脑区 → id 映射（一次列表请求，批量解析 source/target 名称） */
async function canonicalRegionMap(signal?: AbortSignal): Promise<Map<string, CanonicalRegion> | null> {
  const regions = await settled(listCanonicalRegions(signal))
  if (!regions) return null
  return new Map(regions.map(region => [region.id, region]))
}

function regionRefFromMap(map: Map<string, CanonicalRegion> | null, regionId: string): EntityRef {
  const region = map?.get(regionId)
  if (region) return regionRef(region)
  return { id: regionId, code: null, name: regionId, entityType: 'region' }
}

/** 连接引用：name = "Source → Target"（真实脑区名，来自批量 map） */
function connectionRefWithRegions(
  connection: CanonicalConnection,
  map: Map<string, CanonicalRegion> | null,
): EntityRef {
  const source = regionRefFromMap(map, connection.source_region_id)
  const target = regionRefFromMap(map, connection.target_region_id)
  return {
    id: connection.id,
    code: connection.connection_code,
    name: `${source.name} → ${target.name}`,
    entityType: 'connection',
    granularityLevel: connection.granularity_level,
    status: connection.status,
  }
}

/** Tree 分组顺序（真实数据值 + 未来值兜底；只生成实际存在的组，不造空组） */
const CONNECTION_TYPE_ORDER = ['structural', 'functional', 'association', 'uncertain']
const CIRCUIT_TYPE_ORDER = ['network', 'pathway', 'functional_loop', 'uncertain']

function orderedGroupKeys<T>(groups: Map<string, T[]>, order: string[]): string[] {
  return [
    ...order.filter(key => groups.has(key)),
    ...[...groups.keys()].filter(key => !order.includes(key)).sort(),
  ]
}

function groupedConnections(connections: CanonicalConnection[]): OntologyTreeNode[] {
  const groups = new Map<string, CanonicalConnection[]>()
  for (const connection of connections) {
    const type = connection.connection_type || 'unknown'
    const bucket = groups.get(type) ?? []
    bucket.push(connection)
    groups.set(type, bucket)
  }
  return orderedGroupKeys(groups, CONNECTION_TYPE_ORDER).map(type => ({
    id: `group:connection:${type}`,
    code: null,
    name: titleCase(type),
    entityType: 'connection',
    isGroup: true,
    hasChildren: true,
    children: (groups.get(type) ?? []).map(connectionToNode),
  }))
}

function groupedCircuits(circuits: CanonicalCircuit[]): OntologyTreeNode[] {
  const groups = new Map<string, CanonicalCircuit[]>()
  for (const circuit of circuits) {
    const type = circuit.circuit_type || 'unknown'
    const bucket = groups.get(type) ?? []
    bucket.push(circuit)
    groups.set(type, bucket)
  }
  return orderedGroupKeys(groups, CIRCUIT_TYPE_ORDER).map(type => ({
    id: `group:circuit:${type}`,
    code: null,
    name: titleCase(type).replace(/_/g, ' '),
    entityType: 'circuit',
    isGroup: true,
    hasChildren: true,
    children: (groups.get(type) ?? []).map(circuitToNode),
  }))
}

// ─── 节点 / 引用工厂（TreeNode 与 EntityRef 共享数据源） ────────────────

function regionRef(region: CanonicalRegion): EntityRef {
  return {
    id: region.id,
    code: region.region_code,
    name: region.canonical_name_en,
    entityType: 'region',
    granularityLevel: region.granularity_level,
    status: region.status,
  }
}

function regionToNode(region: CanonicalRegion): OntologyTreeNode {
  return {
    id: region.id,
    code: region.region_code,
    name: region.canonical_name_en,
    entityType: 'region',
    granularityLevel: region.granularity_level,
    status: region.status,
  }
}

function connectionToNode(connection: CanonicalConnection): OntologyTreeNode {
  return {
    id: connection.id,
    code: connection.connection_code,
    // 人类可读展示名（code 保留在 tooltip）；真实脑区名解析在详情/关系视图按需完成
    name: connectionDisplayName(connection),
    entityType: 'connection',
    granularityLevel: connection.granularity_level,
    status: connection.status,
    hasChildren: false,
  }
}

function circuitToNode(circuit: CanonicalCircuit): OntologyTreeNode {
  return {
    id: circuit.id,
    code: circuit.circuit_code,
    name: circuit.canonical_name_en,
    entityType: 'circuit',
    granularityLevel: circuit.granularity_level,
    status: circuit.status,
    hasChildren: false,
  }
}

function termToNode(term: OntologyTerm): OntologyTreeNode {
  return {
    id: term.id,
    code: term.term_code,
    name: term.canonical_term_en,
    entityType: 'function',
    granularityLevel: null,
    status: term.status,
    hasChildren: false,
  }
}

/** BR4 跨层实体节点（cell_type_registry / molecular_entity_registry，扁平无层级） */
function cellTypeToNode(cellType: CellTypeItem): OntologyTreeNode {
  return {
    id: cellType.id,
    code: cellType.cell_type_code,
    name: cellType.canonical_name_en,
    entityType: 'cell_type',
    granularityLevel: 'cyto',
    status: cellType.status,
    hasChildren: false,
  }
}

function moleculeToNode(entity: MolecularEntityItem): OntologyTreeNode {
  return {
    id: entity.id,
    code: entity.entity_code,
    name: entity.canonical_name_en,
    entityType: 'molecule',
    granularityLevel: 'molecular',
    status: entity.status,
    hasChildren: false,
  }
}

/** 名称解析失败时降级为 id（真实数据，不写假数据） */
async function resolveRegionRef(regionId: string, signal?: AbortSignal): Promise<EntityRef> {
  const region = await settled(getCanonicalRegion(regionId, signal))
  if (region) return regionRef(region)
  return { id: regionId, code: null, name: regionId, entityType: 'region' }
}

async function resolveTermRef(termId: string, signal?: AbortSignal): Promise<EntityRef> {
  const detail = await settled(getOntologyTermDetail(termId, signal))
  const term = detail?.term
  if (term && typeof term.term_code === 'string') {
    return {
      id: termId,
      code: term.term_code,
      name: typeof term.canonical_term_en === 'string' ? term.canonical_term_en : term.term_code,
      entityType: 'function',
      status: typeof term.status === 'string' ? term.status : null,
    }
  }
  return { id: termId, code: null, name: termId, entityType: 'function' }
}

// ─── 搜索（name / chinese name / code / alias，全部现有列表端点） ─────────

/** 任一字段包含查询串（大小写不敏感）即命中 */
function matchesSearch(fields: Array<string | null | undefined>, query: string): boolean {
  return fields.some(field => field != null && field.toLowerCase().includes(query))
}

/** 别名：region.external_mappings 的字符串值（如 uberon/nifstd 之外的别名） */
function mappingValues(mappings: Record<string, unknown> | null | undefined): string[] {
  return Object.values(mappings ?? {}).filter(
    (value): value is string => typeof value === 'string',
  )
}

async function searchEntities(query: string, signal?: AbortSignal): Promise<OntologyTreeNode[]> {
  const q = query.trim().toLowerCase()
  if (!q) return []
  const [regions, connections, circuits, terms, cellTypes, molecules] = await Promise.all([
    settled(listCanonicalRegions(signal)),
    settled(listCanonicalConnections(signal)),
    settled(listCanonicalCircuits(signal)),
    settled(listOntologyTerms({ limit: 500 }, signal)),
    settled(listCellTypes(signal)),
    settled(listMolecularEntities(signal)),
  ])

  const nodes: OntologyTreeNode[] = []
  for (const region of regions ?? []) {
    if (
      matchesSearch(
        [
          region.canonical_name_en,
          region.canonical_name_cn,
          region.region_code,
          ...mappingValues(region.external_mappings),
        ],
        q,
      )
    ) {
      nodes.push(regionToNode(region))
    }
  }
  for (const connection of connections ?? []) {
    if (matchesSearch([connection.connection_code], q)) {
      nodes.push(connectionToNode(connection))
    }
  }
  for (const circuit of circuits ?? []) {
    if (matchesSearch([circuit.canonical_name_en, circuit.canonical_name_cn, circuit.circuit_code], q)) {
      nodes.push(circuitToNode(circuit))
    }
  }
  for (const term of terms?.items ?? []) {
    if (matchesSearch([term.canonical_term_en, term.canonical_term_cn, term.term_code], q)) {
      nodes.push(termToNode(term))
    }
  }
  for (const cellType of cellTypes ?? []) {
    if (matchesSearch([cellType.canonical_name_en, cellType.canonical_name_cn, cellType.cell_type_code], q)) {
      nodes.push(cellTypeToNode(cellType))
    }
  }
  for (const molecule of molecules ?? []) {
    if (matchesSearch([molecule.canonical_name_en, molecule.canonical_name_cn, molecule.entity_code], q)) {
      nodes.push(moleculeToNode(molecule))
    }
  }
  return nodes
}

// ─── Phase 4：统一 client 入口（组件不直接调用 endpoints） ──────────────

/**
 * 粒度透镜（display lens）：scale 只过滤「显示到哪一级」，
 * 树结构本身始终来自 canonical_region_hierarchy —— granularity_level 永不参与父子判定。
 * level_order 超出所选尺度、且未收录于词表的层级被隐藏；未知层级保留（不因过滤断链）。
 */
function isWithinScaleLens(
  level: string | null | undefined,
  scale: OntologyScaleKey,
): boolean {
  const scaleOrder = GRANULARITY_LEVEL_ORDER[scale]
  if (scaleOrder === undefined) return true // cyto/molecular：脑区层级不参与
  if (!level) return true
  const levelOrder = GRANULARITY_LEVEL_ORDER[level]
  if (levelOrder === undefined) return true
  return levelOrder <= scaleOrder
}

async function getEntityRoots(
  entityType: OntologyEntityType,
  scale: OntologyScaleKey,
  signal?: AbortSignal,
): Promise<OntologyTreeNode[]> {
  switch (entityType) {
    case 'region': {
      // 树顶层 = hierarchy 的无父边根（Brain），逐级递归读取 part_of 边，不再按粒度拍平
      const roots = await listCanonicalRegionRoots(signal)
      return roots
        .filter(region => isWithinScaleLens(region.granularity_level, scale))
        .map(regionToNode)
    }
    case 'connection': {
      const connections = await listCanonicalConnections(signal)
      return groupedConnections(connections)
    }
    case 'circuit': {
      const circuits = await listCanonicalCircuits(signal)
      return groupedCircuits(circuits)
    }
    case 'function': {
      const result = await listOntologyTerms({ limit: 500 }, signal)
      return result.items.map(termToNode)
    }
    case 'cell_type': {
      const cellTypes = await listCellTypes(signal)
      return cellTypes.map(cellTypeToNode)
    }
    case 'molecule': {
      const entities = await listMolecularEntities(signal)
      return entities.map(moleculeToNode)
    }
  }
}

async function getTreeChildren(
  node: OntologyTreeNode,
  scale: OntologyScaleKey,
  signal?: AbortSignal,
): Promise<OntologyTreeNode[]> {
  if (node.isEntityRoot) return getEntityRoots(node.entityType, scale, signal)
  if (node.entityType === 'region') {
    // 子节点 = hierarchy part_of 边（child → parent），再套粒度透镜
    const children = await listCanonicalRegionChildren(node.id, signal)
    return children
      .filter(child => isWithinScaleLens(child.granularity_level, scale))
      .map(regionToNode)
  }
  // connection / circuit / function / cell_type / molecule：当前为扁平列表，无层级子节点
  return []
}

// ─── Phase 2：EntityDetailAdapter（按 entityType 分发，不写四套详情页） ──

async function regionDetail(regionId: string, signal?: AbortSignal): Promise<EntityDetailData> {
  const region = await getCanonicalRegion(regionId, signal) // 主体失败 → 整块报错 + 重试
  const [parent, ancestors, children, candidates, multiscale] = await Promise.all([
    settled(getCanonicalRegionParent(regionId, signal)),
    settled(listCanonicalRegionAncestors(regionId, signal)),
    settled(listCanonicalRegionChildren(regionId, signal)),
    settled(listRegionCandidates(regionId, signal)),
    settled(getCanonicalRegionMultiscale(regionId, signal)),
  ])

  const self = regionRef(region)

  // BR4 多尺度视图：children 粒度桶（meso/subregion/fine）+ 跨层生物层对齐
  const cellTypeItems: MultiscaleBioItem[] = (multiscale?.cell_types ?? []).map(item => ({
    ref: {
      id: item.cell_type_id,
      code: item.cell_type_code,
      name: item.canonical_name_en,
      entityType: 'cell_type',
      granularityLevel: 'cyto',
    },
    relation: item.mapping_type,
    confidence: item.confidence,
    detail: item.taxonomy_source,
  }))
  const moleculeItems: MultiscaleBioItem[] = (multiscale?.molecules ?? []).map(item => ({
    ref: {
      id: item.molecular_entity_id,
      code: item.entity_code,
      name: item.canonical_name_en,
      entityType: 'molecule',
      granularityLevel: 'molecular',
    },
    relation: item.evidence_type,
    confidence: item.confidence,
    detail: item.source,
  }))

  return {
    entityType: 'region',
    id: regionId,
    name: region.canonical_name_en,
    code: region.region_code,
    status: region.status,
    granularityLevel: region.granularity_level,
    confidence: region.confidence,
    description: region.description,
    basic: [
      { label: '名称 (CN)', value: region.canonical_name_cn ?? '—' },
      { label: '来源 (Source)', value: sourceSummaryLabel(region.source_summary) },
      { label: '半球策略', value: region.hemisphere_policy },
      { label: '侧别', value: region.laterality },
      { label: '物种', value: region.species },
      { label: '粒度域', value: region.granularity_domain },
      { label: '创建者', value: region.created_by },
    ],
    // 后端返回 nearest-first（depth 1 在前）→ 反转为 root-first（Brain > Cerebrum > ...）
    path: [
      ...[...(ancestors ?? [])].reverse().map(ancestor => ({
        id: ancestor.id,
        code: ancestor.region_code,
        name: ancestor.canonical_name_en,
        entityType: 'region' as const,
      })),
      self,
    ],
    parent: parent ? regionRef(parent) : null,
    children: (children ?? []).map(regionRef),
    provenance: [
      ...summaryRows(region.source_summary),
      { label: '对齐候选', value: String(candidates?.length ?? 0) },
      { label: '跨层 · Cell Types', value: String(multiscale?.cell_types.length ?? 0) },
      { label: '跨层 · Molecules', value: String(multiscale?.molecules.length ?? 0) },
    ],
    multiscale: {
      mesoRegions: (multiscale?.meso_regions ?? []).map(regionRef),
      subregions: (multiscale?.subregions ?? []).map(regionRef),
      fineRegions: (multiscale?.fine_regions ?? []).map(regionRef),
      cellTypes: cellTypeItems,
      molecules: moleculeItems,
    },
  }
}

async function connectionDetail(
  connectionId: string,
  signal?: AbortSignal,
): Promise<EntityDetailData> {
  const connection = await getCanonicalConnection(connectionId, signal)
  const regionMap = await canonicalRegionMap(signal)
  const self: EntityRef = {
    id: connection.id,
    code: connection.connection_code,
    name: connectionDisplayName(connection),
    entityType: 'connection',
    granularityLevel: connection.granularity_level,
    status: connection.status,
  }
  return {
    entityType: 'connection',
    id: connectionId,
    name: connection.connection_code,
    code: connection.connection_code,
    status: connection.status,
    granularityLevel: connection.granularity_level,
    confidence: connection.confidence,
    description: null,
    // Inspector 主标题 = 人类可读类型标题（如 "Association connection"），code 下沉到 Properties
    typeTitle: connectionTypeTitle(connection.connection_type),
    source: regionRefFromMap(regionMap, connection.source_region_id),
    target: regionRefFromMap(regionMap, connection.target_region_id),
    basic: [
      { label: '连接类型', value: connection.connection_type },
      { label: '方向策略', value: connection.directionality_policy },
      { label: '物种', value: connection.species },
      { label: '置信度', value: confidenceText(connection.confidence) },
    ],
    path: [self],
    parent: null,
    children: [],
    provenance: [
      ...summaryRows(connection.source_summary),
      ...summaryRows(connection.evidence_summary),
      ...summaryRows(connection.provenance_json),
    ],
  }
}

async function circuitDetail(
  circuitId: string,
  signal?: AbortSignal,
): Promise<EntityDetailData> {
  const circuit = await getCanonicalCircuit(circuitId, signal)
  const self: EntityRef = {
    id: circuit.id,
    code: circuit.circuit_code,
    name: circuit.canonical_name_en,
    entityType: 'circuit',
    granularityLevel: circuit.granularity_level,
    status: circuit.status,
  }
  return {
    entityType: 'circuit',
    id: circuitId,
    name: circuit.canonical_name_en,
    code: circuit.circuit_code,
    status: circuit.status,
    granularityLevel: circuit.granularity_level,
    confidence: circuit.confidence,
    description: circuit.description,
    basic: [
      { label: '名称 (CN)', value: circuit.canonical_name_cn ?? '—' },
      { label: '回路类型', value: circuit.circuit_type },
      { label: '物种', value: circuit.species },
      { label: '置信度', value: confidenceText(circuit.confidence) },
    ],
    path: [self],
    parent: null,
    children: [],
    provenance: [
      ...summaryRows(circuit.source_summary),
      ...summaryRows(circuit.provenance_json),
      { label: '创建者', value: circuit.created_by ?? '—' },
    ],
  }
}

async function functionDetail(
  termId: string,
  signal?: AbortSignal,
): Promise<EntityDetailData> {
  const detail = await getOntologyTermDetail(termId, signal)
  const term = detail.term
  // Function hierarchy（/api/ontology/hierarchy/terms/{id}/parents|children）；
  // 失败/无数据 → null/[]（层级为空不 blank 面板）
  const [parents, children] = await Promise.all([
    settled(listTermHierarchyParents(termId, signal)),
    settled(listTermHierarchyChildren(termId, signal)),
  ])
  const read = (key: string): string => {
    const value = term[key]
    if (value == null) return '—'
    return typeof value === 'string' ? value : JSON.stringify(value)
  }
  const hierarchyRef = (node: HierarchyNodeRead): EntityRef => ({
    id: node.term_id,
    code: node.term_code,
    name: node.canonical_term_en ?? node.term_code ?? node.term_id,
    entityType: 'function',
    status: node.term_status,
  })
  const name = typeof term.canonical_term_en === 'string' ? term.canonical_term_en : termId
  const code = typeof term.term_code === 'string' ? term.term_code : null
  const synonyms = detail.synonyms
    .map(item => (typeof item.synonym_text === 'string' ? item.synonym_text : ''))
    .filter(Boolean)
  return {
    entityType: 'function',
    id: termId,
    name,
    code,
    status: typeof term.status === 'string' ? term.status : null,
    granularityLevel: null,
    confidence: null,
    description: typeof term.description === 'string' ? term.description : null,
    basic: [
      { label: '术语类型', value: read('term_type') },
      { label: '类别', value: read('category') },
      { label: '域', value: read('domain') },
      { label: '角色', value: read('role') },
      { label: '效应类型', value: read('effect_type') },
      { label: '同义词', value: synonyms.length > 0 ? synonyms.join('；') : '—' },
    ],
    path: [
      {
        id: termId,
        code,
        name,
        entityType: 'function',
        status: typeof term.status === 'string' ? term.status : null,
      },
    ],
    parent: parents?.items[0] ? hierarchyRef(parents.items[0].parent) : null,
    children: (children?.items ?? []).map(edge => hierarchyRef(edge.child)),
    provenance: [
      { label: '创建者', value: read('created_by') },
      { label: '创建时间', value: read('created_at') },
      { label: '外部映射', value: String(detail.external_mappings.length) },
      { label: '引用数', value: String(detail.references.total) },
    ],
  }
}

// ─── BR4：跨层实体详情（cell type / molecule） ─────────────────────────

function cellTypeRef(cellType: CellTypeItem): EntityRef {
  return {
    id: cellType.id,
    code: cellType.cell_type_code,
    name: cellType.canonical_name_en,
    entityType: 'cell_type',
    granularityLevel: 'cyto',
    status: cellType.status,
  }
}

function moleculeRef(entity: MolecularEntityItem): EntityRef {
  return {
    id: entity.id,
    code: entity.entity_code,
    name: entity.canonical_name_en,
    entityType: 'molecule',
    granularityLevel: 'molecular',
    status: entity.status,
  }
}

async function cellTypeDetail(cellTypeId: string, signal?: AbortSignal): Promise<EntityDetailData> {
  const cellTypes = await listCellTypes(signal) // 注册表无单条端点：全量列表内查找
  const cellType = cellTypes.find(item => item.id === cellTypeId)
  if (!cellType) throw new Error(`cell type not found: ${cellTypeId}`)
  return {
    entityType: 'cell_type',
    id: cellTypeId,
    name: cellType.canonical_name_en,
    code: cellType.cell_type_code,
    status: cellType.status,
    granularityLevel: 'cyto',
    confidence: null,
    description: cellType.description,
    basic: [
      { label: '名称 (CN)', value: cellType.canonical_name_cn ?? '—' },
      { label: '物种', value: cellType.species },
      { label: '分类学来源', value: cellType.taxonomy_source ?? '—' },
      { label: '分类学版本', value: cellType.taxonomy_version ?? '—' },
      { label: '外部 IRI', value: cellType.external_iri ?? '—', mono: true },
    ],
    path: [cellTypeRef(cellType)],
    parent: null,
    children: [],
    provenance: [
      { label: '创建时间', value: cellType.created_at },
      { label: '更新时间', value: cellType.updated_at },
    ],
  }
}

async function moleculeDetail(moleculeId: string, signal?: AbortSignal): Promise<EntityDetailData> {
  const entities = await listMolecularEntities(signal) // 注册表无单条端点：全量列表内查找
  const entity = entities.find(item => item.id === moleculeId)
  if (!entity) throw new Error(`molecular entity not found: ${moleculeId}`)
  return {
    entityType: 'molecule',
    id: moleculeId,
    name: entity.canonical_name_en,
    code: entity.entity_code,
    status: entity.status,
    granularityLevel: 'molecular',
    confidence: null,
    description: entity.description,
    basic: [
      { label: '名称 (CN)', value: entity.canonical_name_cn ?? '—' },
      { label: '实体类型', value: entity.entity_type },
      { label: '物种', value: entity.species },
      { label: '外部 IRI', value: entity.external_iri ?? '—', mono: true },
    ],
    path: [moleculeRef(entity)],
    parent: null,
    children: [],
    provenance: [
      { label: '创建时间', value: entity.created_at },
      { label: '更新时间', value: entity.updated_at },
    ],
  }
}

async function getEntityDetail(
  entityType: OntologyEntityType,
  entityId: string,
  signal?: AbortSignal,
): Promise<EntityDetailData> {
  switch (entityType) {
    case 'region':
      return regionDetail(entityId, signal)
    case 'connection':
      return connectionDetail(entityId, signal)
    case 'circuit':
      return circuitDetail(entityId, signal)
    case 'function':
      return functionDetail(entityId, signal)
    case 'cell_type':
      return cellTypeDetail(entityId, signal)
    case 'molecule':
      return moleculeDetail(entityId, signal)
  }
}

// ─── Phase 3：Relation Explorer 数据（RelationGroup 统一结构） ──────────

async function regionRelations(regionId: string, signal?: AbortSignal): Promise<RelationGroup[]> {
  const [parent, children, connections, circuits, functions, candidates, multiscale, regionMap, atlasMappings] =
    await Promise.all([
      settled(getCanonicalRegionParent(regionId, signal)),
      settled(listCanonicalRegionChildren(regionId, signal)),
      settled(listRegionConnections(regionId, signal)),
      settled(listRegionCircuits(regionId, signal)),
      settled(listRegionFunctions(regionId, signal)),
      settled(listRegionCandidates(regionId, signal)),
      settled(getCanonicalRegionMultiscale(regionId, signal)),
      canonicalRegionMap(signal),
      settled(listAtlasRegionMappings({ canonical_region_id: regionId }, signal)),
    ])
  // 仅在有映射时拉取 atlas 区域表（Allen mouse 1327 行，不浪费请求）
  let atlasRegions: AtlasRegionItem[] | null = null
  if ((atlasMappings ?? []).length > 0) {
    atlasRegions = await settled(listAtlasRegions(signal))
  }

  // 连接卡片 = 连接实体本身，名称 "Source → Target"（点击跳转到连接详情）
  const selfName = regionRefFromMap(regionMap, regionId).name
  const connectionItems: RelationItem[] = (connections ?? []).map(conn => {
    const endpointName = conn.endpoint_region.canonical_name_en
    const sourceName = conn.direction === 'outgoing' ? selfName : endpointName
    const targetName = conn.direction === 'outgoing' ? endpointName : selfName
    return {
      ref: {
        id: conn.connection_id,
        code: conn.connection_code,
        name: `${sourceName} → ${targetName}`,
        entityType: 'connection',
        granularityLevel: conn.endpoint_region.granularity_level,
        status: conn.status,
      },
      meta: [
        { label: '方向', value: conn.direction === 'outgoing' ? '出向' : '入向' },
        { label: '类型', value: conn.connection_type },
        { label: '状态', value: conn.status },
        { label: '置信度', value: confidenceText(conn.confidence) },
      ],
    }
  })

  const circuitItems: RelationItem[] = (circuits ?? []).map(circuit => ({
    ref: {
      id: circuit.circuit_id,
      code: circuit.circuit_code,
      name: circuit.canonical_name_en,
      entityType: 'circuit',
      status: circuit.status,
    },
    meta: [
      { label: '角色', value: ROLE_LABELS[circuit.role] ?? circuit.role },
      { label: '类型', value: circuit.circuit_type },
      { label: '置信度', value: confidenceText(circuit.confidence) },
    ],
  }))

  const functionItems: RelationItem[] = (functions ?? []).map(fn => ({
    ref: {
      id: fn.function_term_id,
      code: fn.term_code,
      name: fn.canonical_term_en,
      entityType: 'function',
    },
    meta: [
      { label: '关系', value: fn.relation_type },
      { label: '经回路', value: fn.circuit_code },
      { label: '置信度', value: confidenceText(fn.confidence) },
    ],
  }))

  const candidateItems: RelationItem[] = (candidates ?? []).map(candidate => ({
    ref: {
      id: candidate.candidate_id,
      code: null,
      name: candidate.raw_name,
      entityType: 'region',
    },
    meta: [
      { label: '图谱', value: candidate.source_atlas },
      { label: '侧别', value: candidate.laterality },
      { label: '对齐', value: candidate.alignment_status },
      { label: '候选状态', value: candidate.candidate_status },
    ],
  }))

  // ── BR4 多尺度桶：更细粒度后裔（仅在有数据时出现，避免空组噪音） ──
  const levelItems = (regions: CanonicalRegion[] | null | undefined): RelationItem[] =>
    (regions ?? []).map(region => ({ ref: regionRef(region), meta: [] }))

  // ── BR4 跨层对齐：cell type / molecular entity（跨层注册表，可跳转详情） ──
  const cellTypeItems: RelationItem[] = (multiscale?.cell_types ?? []).map(item => ({
    ref: {
      id: item.cell_type_id,
      code: item.cell_type_code,
      name: item.canonical_name_en,
      entityType: 'cell_type',
      granularityLevel: 'cyto',
    },
    meta: [
      { label: '映射类型', value: item.mapping_type },
      { label: '分类学', value: item.taxonomy_source ?? '—' },
      { label: '置信度', value: confidenceText(item.confidence) },
    ],
  }))

  const moleculeItems: RelationItem[] = (multiscale?.molecules ?? []).map(item => ({
    ref: {
      id: item.molecular_entity_id,
      code: item.entity_code,
      name: item.canonical_name_en,
      entityType: 'molecule',
      granularityLevel: 'molecular',
    },
    meta: [
      { label: '证据类型', value: item.evidence_type },
      { label: '置信度', value: confidenceText(item.confidence) },
      { label: '来源', value: item.source ?? '—' },
    ],
  }))

  // ── BR3 atlas 映射：atlas 区域 → 本 canonical 脑区（非本体实体，group 不可跳转） ──
  const atlasNameById = new Map((atlasRegions ?? []).map(atlas => [atlas.id, atlas]))
  const atlasItems: RelationItem[] = (atlasMappings ?? []).map(mapping => {
    const atlas = atlasNameById.get(mapping.atlas_region_id)
    return {
      ref: {
        id: mapping.id,
        code: atlas?.atlas_region_id ?? null,
        name: atlas ? atlas.region_name : mapping.atlas_region_id,
        entityType: 'region',
      },
      meta: [
        { label: '图谱', value: atlas?.atlas_name ?? '—' },
        { label: '图谱版本', value: atlas?.atlas_version ?? '—' },
        { label: '映射类型', value: mapping.mapping_type },
        { label: '物种关系', value: mapping.species_relation },
        { label: '置信度', value: confidenceText(mapping.confidence) },
      ],
    }
  })

  const groups: RelationGroup[] = [
    {
      key: 'parent',
      label: '父节点',
      items: parent ? [{ ref: regionRef(parent), meta: [] }] : [],
    },
    { key: 'children', label: '子节点', items: (children ?? []).map(child => ({ ref: regionRef(child), meta: [] })) },
    { key: 'connections', label: 'Related Connections', items: connectionItems },
    { key: 'circuits', label: 'Related Circuits', items: circuitItems },
    { key: 'functions', label: 'Functions（经回路）', items: functionItems },
  ]
  if (atlasItems.length > 0) {
    groups.push({ key: 'atlas', label: 'Atlas Mappings', navigable: false, items: atlasItems })
  }
  const mesoItems = levelItems(multiscale?.meso_regions)
  const subregionItems = levelItems(multiscale?.subregions)
  const fineItems = levelItems(multiscale?.fine_regions)
  if (mesoItems.length > 0) groups.push({ key: 'meso_regions', label: 'Multiscale · Meso', items: mesoItems })
  if (subregionItems.length > 0) groups.push({ key: 'subregions', label: 'Multiscale · Subregions', items: subregionItems })
  if (fineItems.length > 0) groups.push({ key: 'fine_regions', label: 'Multiscale · Fine', items: fineItems })
  groups.push(
    { key: 'cell_types', label: 'Cross Layer · Cell Types', items: cellTypeItems },
    { key: 'molecules', label: 'Cross Layer · Molecules', items: moleculeItems },
    { key: 'candidates', label: 'Evidence · 对齐候选', navigable: false, items: candidateItems },
  )
  return groups
}

async function connectionRelations(
  connectionId: string,
  signal?: AbortSignal,
): Promise<RelationGroup[]> {
  const connection = await getCanonicalConnection(connectionId, signal)
  const regionMap = await canonicalRegionMap(signal)
  return [
    { key: 'source', label: 'Source Region', items: [{ ref: regionRefFromMap(regionMap, connection.source_region_id), meta: [] }] },
    { key: 'target', label: 'Target Region', items: [{ ref: regionRefFromMap(regionMap, connection.target_region_id), meta: [] }] },
    {
      key: 'circuits',
      label: 'Related Circuits',
      unavailable: true,
      items: [],
    },
  ]
}

async function circuitRelations(
  circuitId: string,
  signal?: AbortSignal,
): Promise<RelationGroup[]> {
  const [regionLinks, connectionLinks, functionLinks, regionMap] = await Promise.all([
    settled(listCanonicalCircuitRegions(circuitId, signal)),
    settled(listCanonicalCircuitConnections(circuitId, signal)),
    settled(listCanonicalCircuitFunctions(circuitId, signal)),
    canonicalRegionMap(signal),
  ])

  const regionItems = await Promise.all(
    (regionLinks ?? []).map(async link => ({
      ref: await resolveRegionRef(link.region_id, signal),
      meta: [
        { label: '角色', value: ROLE_LABELS[link.role] ?? link.role },
        { label: '序', value: String(link.order_index) },
        { label: '置信度', value: confidenceText(link.confidence) },
      ],
    })),
  )
  // 连接卡片 = 连接实体，名称 "Source → Target"（批量 map 解析真实脑区名）
  const connectionItems = await Promise.all(
    (connectionLinks ?? []).map(async link => {
      const connection = await settled(getCanonicalConnection(link.connection_id, signal))
      const ref = connection
        ? connectionRefWithRegions(connection, regionMap)
        : {
            id: link.connection_id,
            code: null,
            name: link.connection_id,
            entityType: 'connection' as const,
          }
      return {
        ref,
        meta: [
          { label: '角色', value: link.role },
          { label: '置信度', value: confidenceText(link.confidence) },
        ],
      }
    }),
  )
  const functionItems = await Promise.all(
    (functionLinks ?? []).map(async link => ({
      ref: await resolveTermRef(link.function_term_id, signal),
      meta: [
        { label: '关系', value: link.relation_type },
        { label: '置信度', value: confidenceText(link.confidence) },
      ],
    })),
  )

  return [
    { key: 'regions', label: 'Regions', items: regionItems },
    { key: 'connections', label: 'Connections', items: connectionItems },
    { key: 'functions', label: 'Functions', items: functionItems },
  ]
}

async function functionRelations(
  _termId: string,
  _signal?: AbortSignal,
): Promise<RelationGroup[]> {
  // 后端暂无 term → canonical circuit/region 反向查询 API，显示暂无数据（不写假数据）
  return [
    { key: 'circuits', label: 'Related Circuits', unavailable: true, items: [] },
    { key: 'regions', label: 'Related Regions', unavailable: true, items: [] },
  ]
}

// ─── BR4：跨层实体关系（对齐区域反向查询） ─────────────────────────────

async function cellTypeRelations(cellTypeId: string, signal?: AbortSignal): Promise<RelationGroup[]> {
  const [alignments, regionMap] = await Promise.all([
    settled(listRegionCellAlignments({ cell_type_id: cellTypeId }, signal)),
    canonicalRegionMap(signal),
  ])
  const regionItems: RelationItem[] = (alignments ?? []).map(alignment => ({
    ref: regionRefFromMap(regionMap, alignment.region_id),
    meta: [
      { label: '映射类型', value: alignment.mapping_type },
      { label: '置信度', value: confidenceText(alignment.confidence) },
    ],
  }))
  return [{ key: 'regions', label: 'Aligned Regions', items: regionItems }]
}

async function moleculeRelations(moleculeId: string, signal?: AbortSignal): Promise<RelationGroup[]> {
  const [alignments, regionMap] = await Promise.all([
    settled(listRegionMolecularAlignments({ molecular_entity_id: moleculeId }, signal)),
    canonicalRegionMap(signal),
  ])
  const regionItems: RelationItem[] = (alignments ?? []).map(alignment => ({
    ref: regionRefFromMap(regionMap, alignment.region_id),
    meta: [
      { label: '证据类型', value: alignment.evidence_type },
      { label: '置信度', value: confidenceText(alignment.confidence) },
      { label: '来源', value: alignment.source ?? '—' },
    ],
  }))
  return [{ key: 'regions', label: 'Aligned Regions', items: regionItems }]
}

async function getRelations(
  entityType: OntologyEntityType,
  entityId: string,
  signal?: AbortSignal,
): Promise<RelationGroup[]> {
  switch (entityType) {
    case 'region':
      return regionRelations(entityId, signal)
    case 'connection':
      return connectionRelations(entityId, signal)
    case 'circuit':
      return circuitRelations(entityId, signal)
    case 'function':
      return functionRelations(entityId, signal)
    case 'cell_type':
      return cellTypeRelations(entityId, signal)
    case 'molecule':
      return moleculeRelations(entityId, signal)
  }
}

// ─── Phase 5：Region Research 展开地图（meso 小分支自动展开 + 子计数徽章） ──

/**
 * 按当前尺度派生的研究层级展开视图：
 * - autoExpandIds：meso 节点（可见子节点 1..10 且全部 subregion/fine）→ 默认自动展开；
 * - researchExpandIds：meso 节点（含任意 subregion/fine 子节点）→「展开到研究层级」按钮目标；
 * - researchAncestorIds：研究目标的祖先 id 并集（按钮穿越折叠祖先链用，如临床级祖先
 *   不在级联层级时仍需展开才能到达 meso 目标）；
 * - preloadedChildren：自动展开 meso 的子节点（预载入树缓存，免一次 /children 请求）；
 * - childCountById：折叠 meso 节点的已知子计数（行徽章 (n)，让医生知道为什么展开/折叠）。
 */
export interface RegionResearchView {
  autoExpandIds: string[]
  researchExpandIds: string[]
  researchAncestorIds: string[]
  preloadedChildren: Record<string, OntologyTreeNode[]>
  childCountById: Record<string, number>
}

/** 原始数据（与尺度无关）：meso 节点 id → 其 subregion/fine 子节点 */
interface RegionResearchRaw {
  childrenByMesoId: Map<string, CanonicalRegion[]>
  /** meso 节点 id → 父链（根 → 直系父，不含 meso 自身） */
  ancestorChainByMesoId: Map<string, string[]>
}

/** 会话级缓存：原始地图只构建一次，跨尺度切换复用（约 22 个并发小请求） */
let regionResearchRawCache: Promise<RegionResearchRaw | null> | null = null

/**
 * 追溯一个 region 的父链（根 → 直系父，不含自身）；
 * 每层一次 parent 请求，到 whole_brain 或无父停止。
 */
async function fetchParentChain(regionId: string, signal?: AbortSignal): Promise<string[]> {
  const chain: string[] = []
  let parent: CanonicalRegion | null = await settled(getCanonicalRegionParent(regionId, signal))
  while (parent) {
    chain.unshift(parent.id)
    if (parent.granularity_level === 'whole_brain' || parent.granularity_level === 'brain') break
    parent = await settled(getCanonicalRegionParent(parent.id, signal))
  }
  return chain
}

/**
 * 构建原始研究地图（一次性）：
 * 全量 region 列表（1 请求）→ 筛 subregion/fine → 并发取各自 parent（n 请求）
 * → 去重出 meso 父节点 → 逐个探针其 children（k 请求，k = meso 父数，当前仅 1）
 * → 逐个追溯父链（每层 1 请求，「展开到研究层级」穿越折叠祖先用）。
 * 与树的懒加载互不干扰：不做全量 meso 探针，609 个 meso 的 children 不会一次加载；
 * 上述请求均为一次性构建（会话级缓存），运行期按钮展开不再多发请求。
 */
async function fetchRegionResearchRaw(signal?: AbortSignal): Promise<RegionResearchRaw | null> {
  const regions = await settled(listCanonicalRegions(signal))
  if (!regions) return null
  const researchNodes = regions.filter(
    region => region.granularity_level === 'subregion' || region.granularity_level === 'fine',
  )
  const parents = await Promise.all(
    researchNodes.map(node => settled(getCanonicalRegionParent(node.id, signal))),
  )
  const mesoParentIds = [
    ...new Set(
      parents
        .filter((parent): parent is CanonicalRegion => parent !== null && parent.granularity_level === 'meso')
        .map(parent => parent.id),
    ),
  ]
  const childrenByMesoId = new Map<string, CanonicalRegion[]>()
  const ancestorChainByMesoId = new Map<string, string[]>()
  for (const mesoId of mesoParentIds) {
    const children = await settled(listCanonicalRegionChildren(mesoId, signal))
    if (children) childrenByMesoId.set(mesoId, children)
    ancestorChainByMesoId.set(mesoId, await fetchParentChain(mesoId, signal))
  }
  return { childrenByMesoId, ancestorChainByMesoId }
}

/**
 * 研究地图（原始数据 + 当前尺度透镜）→ 展开视图。
 * 原始数据失败 → 返回 null（树照常工作，只是没有 meso 自动展开与徽章）；
 * 失败不缓存，下一次调用重试。
 */
async function getRegionResearchView(
  scale: OntologyScaleKey,
  signal?: AbortSignal,
): Promise<RegionResearchView | null> {
  if (!regionResearchRawCache) regionResearchRawCache = fetchRegionResearchRaw(signal)
  const raw = await regionResearchRawCache
  if (!raw) {
    regionResearchRawCache = null
    return null
  }
  const view: RegionResearchView = {
    autoExpandIds: [],
    researchExpandIds: [],
    researchAncestorIds: [],
    preloadedChildren: {},
    childCountById: {},
  }
  for (const [mesoId, children] of raw.childrenByMesoId) {
    const visible = children.filter(child => isWithinScaleLens(child.granularity_level, scale))
    const count = visible.length
    if (count === 0) continue
    const allResearch = visible.every(
      child => child.granularity_level === 'subregion' || child.granularity_level === 'fine',
    )
    view.childCountById[mesoId] = count
    if (!allResearch) continue
    view.researchExpandIds.push(mesoId)
    // 规则：children ≤ 10 且全 subregion/fine → 自动展开；> 10（如大规模 BNA）保持折叠
    if (count <= 10) {
      view.autoExpandIds.push(mesoId)
      view.preloadedChildren[mesoId] = visible.map(regionToNode)
    }
  }
  // 研究目标祖先并集（展开按钮穿越折叠祖先链）
  const ancestorSet = new Set<string>()
  for (const mesoId of view.researchExpandIds) {
    for (const ancestorId of raw.ancestorChainByMesoId.get(mesoId) ?? []) {
      ancestorSet.add(ancestorId)
    }
  }
  view.researchAncestorIds = [...ancestorSet]
  return view
}

/**
 * 统一 ontology client：组件不直接调用 endpoints，
 * 未来扩展实体/关系只需在本层加 adapter。
 */
export const ontologyApi = {
  getTreeChildren,
  getEntityDetail,
  getRelations,
  searchEntities,
  getRegionResearchView,
}

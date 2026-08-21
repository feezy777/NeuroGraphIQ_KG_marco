import type { OntologyEntityType, OntologyTreeNode } from './OntologyTreeNode'
import type { OntologyScaleKey } from '../../ontologyScale'

/**
 * 树顶层实体根（尺度感知）：
 * - 脑区尺度（macro/clinical/meso/subregion/fine）→ Brain Region 实体根，
 *   其子节点 = canonical_region_hierarchy 的无父边根（Brain），再逐级递归 part_of；
 *   粒度尺度只作显示透镜（ontologyApi.getTreeChildren 内过滤），不决定树顶层
 * - cyto → Cell Type（cell_type_registry，独立于脑区层级）
 * - molecular → Molecule（molecular_entity_registry，独立于脑区层级）
 * isEntityRoot = true：点击切换展开，不进入选中态；
 * children 由 ontologyApi.getTreeChildren 按 entityType + scale 分发加载。
 */

const STRUCTURAL_ROOTS: OntologyTreeNode[] = [
  {
    id: 'root:connection',
    code: null,
    name: 'Connection',
    entityType: 'connection',
    isEntityRoot: true,
  },
  {
    id: 'root:circuit',
    code: null,
    name: 'Circuit',
    entityType: 'circuit',
    isEntityRoot: true,
  },
  {
    id: 'root:function',
    code: null,
    name: 'Function',
    entityType: 'function',
    isEntityRoot: true,
  },
]

export function buildEntityRoots(scale: OntologyScaleKey): OntologyTreeNode[] {
  switch (scale) {
    case 'cyto':
      return [
        {
          id: 'root:cell_type',
          code: null,
          name: 'Cell Type',
          entityType: 'cell_type',
          isEntityRoot: true,
        },
      ]
    case 'molecular':
      return [
        {
          id: 'root:molecule',
          code: null,
          name: 'Molecule',
          entityType: 'molecule',
          isEntityRoot: true,
        },
      ]
    default:
      return [
        {
          id: 'root:region',
          code: null,
          name: 'Brain Region',
          entityType: 'region',
          isEntityRoot: true,
        },
        ...STRUCTURAL_ROOTS,
      ]
  }
}

/** 搜索结果分组顺序（全六类实体；搜索全局生效，与当前尺度无关） */
export const SEARCH_GROUP_DEFS: ReadonlyArray<{ entityType: OntologyEntityType; name: string }> = [
  { entityType: 'region', name: 'Brain Region' },
  { entityType: 'connection', name: 'Connection' },
  { entityType: 'circuit', name: 'Circuit' },
  { entityType: 'function', name: 'Function' },
  { entityType: 'cell_type', name: 'Cell Type' },
  { entityType: 'molecule', name: 'Molecule' },
]

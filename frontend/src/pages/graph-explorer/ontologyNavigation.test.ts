import { describe, expect, it } from 'vitest'
import type { CandidateCanonicalResolution } from '../../api/endpoints'
import type { CanonicalNode, CanonicalNodeType } from './adapters/finalKgAdapter'
import {
  graphExplorerEntityUrl,
  ontologyCenterEntityUrl,
  ontologyCenterSearchUrl,
  ontologyNavigationUrlFor,
} from './ontologyNavigation'

function makeNode(type: CanonicalNodeType, label: string): CanonicalNode {
  return {
    id: `${type}:1`,
    type,
    label,
    entityId: '1',
    metadata: {
      canonical_id: null,
      source_id: null,
      provenance: {},
      granularity: null,
      confidence: null,
      raw: {},
    },
  }
}

const RESOLVED: CandidateCanonicalResolution = {
  resolved: true,
  canonical_region_id: 'can-region-1',
  region_code: 'ng:br:x',
  canonical_name_en: 'Hippocampus',
}

describe('Phase 8 双向跳转 URL（ontologyNavigation）', () => {
  it('本体中心实体详情 URL：tab=browser + entity_type + entity', () => {
    expect(ontologyCenterEntityUrl('region', 'can-1')).toBe(
      '#/ontology-center?tab=browser&entity_type=region&entity=can-1',
    )
  })

  it('本体中心搜索 URL：tab=browser + search（含编码）', () => {
    expect(ontologyCenterSearchUrl('海马 体')).toBe(
      '#/ontology-center?tab=browser&search=%E6%B5%B7%E9%A9%AC%20%E4%BD%93',
    )
  })

  it('图谱探索实体定位 URL：view=canonical + entity', () => {
    expect(graphExplorerEntityUrl('can-1')).toBe('#/graph-explorer?view=canonical&entity=can-1')
  })

  it('brain_region 解析成功 → 直达本体实体详情', () => {
    const url = ontologyNavigationUrlFor(makeNode('brain_region', 'Hippocampus'), RESOLVED)
    expect(url).toBe('#/ontology-center?tab=browser&entity_type=region&entity=can-region-1')
  })

  it('brain_region 解析失败 → 按名称搜索降级', () => {
    const url = ontologyNavigationUrlFor(makeNode('brain_region', 'Hippocampus'), null)
    expect(url).toBe('#/ontology-center?tab=browser&search=Hippocampus')
  })

  it('brain_region 解析未 resolved → 按名称搜索降级', () => {
    const url = ontologyNavigationUrlFor(makeNode('brain_region', 'Hippocampus'), { resolved: false })
    expect(url).toBe('#/ontology-center?tab=browser&search=Hippocampus')
  })

  it('circuit / function / connection → 按名称搜索', () => {
    expect(ontologyNavigationUrlFor(makeNode('circuit', 'Papez circuit'), null)).toBe(
      '#/ontology-center?tab=browser&search=Papez%20circuit',
    )
    expect(ontologyNavigationUrlFor(makeNode('function', 'memory'), null)).toBe(
      '#/ontology-center?tab=browser&search=memory',
    )
    expect(ontologyNavigationUrlFor(makeNode('connection', 'structural'), null)).toBe(
      '#/ontology-center?tab=browser&search=structural',
    )
  })

  it('circuit_step / evidence 无本体对应 → 不提供跳转', () => {
    expect(ontologyNavigationUrlFor(makeNode('circuit_step', 'Step 1'), null)).toBeNull()
    expect(ontologyNavigationUrlFor(makeNode('evidence', 'Evidence A'), null)).toBeNull()
  })

  it('名称为空 → 不提供搜索跳转', () => {
    expect(ontologyNavigationUrlFor(makeNode('circuit', '   '), null)).toBeNull()
  })
})

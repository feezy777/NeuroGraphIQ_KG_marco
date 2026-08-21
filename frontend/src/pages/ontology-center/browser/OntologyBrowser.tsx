import { useCallback, useEffect, useMemo, useState } from 'react'
import { PanelRightClose, PanelRightOpen } from 'lucide-react'
import { ontologyApi } from '../../../api/ontologyApi'
import type { RegionResearchView } from '../../../api/ontologyApi'
import { EntityDetailPanel } from '../detail/EntityDetailPanel'
import { RelationExplorer } from '../detail/RelationExplorer'
import type { RelationGroup } from '../detail/types'
import { OntologyScaleSelector } from '../OntologyScaleSelector'
import {
  DEFAULT_ONTOLOGY_SCALE,
  isOntologyScaleKey,
  type OntologyScaleKey,
} from '../ontologyScale'
import {
  ONTOLOGY_SEARCH_MIN_LENGTH,
  OntologySearchInput,
  OntologySearchResults,
} from './OntologySearch'
import { buildEntityRoots } from './tree/entityRoots'
import { OntologyTree } from './tree/OntologyTree'
import type { OntologyEntityType, OntologyTreeNode } from './tree/OntologyTreeNode'

type SelectedEntity = { entityType: OntologyEntityType; entityId: string }

const ENTITY_TYPES: readonly string[] = [
  'region',
  'connection',
  'circuit',
  'function',
  'cell_type',
  'molecule',
]

/**
 * 默认展开级联：Whole-brain / Macro / Clinical 自动展开；
 * Meso（609 节点）默认折叠，但小规模 subregion/fine 分支
 * （children ≤ 10，如 Hippocampal formation）由研究地图自动展开，
 * 大规模分支（children > 10）保持折叠（行徽章 (n) 显示原因）。
 */
const DEFAULT_AUTO_EXPAND_LEVELS: readonly string[] = ['whole_brain', 'macro', 'clinical']

/**
 * Phase 8 双向跳转：挂载时从 URL 读取一次跳转参数
 * （#/ontology-center?tab=browser&search=… | &entity_type=…&entity=… | &oc_scale=…）。
 * 仅在挂载时消费，之后完全交由用户交互（树懒加载无法反向高亮，详情直接打开）。
 */
function readBrowserParamsFromHash(): {
  search: string | null
  entityType: OntologyEntityType | null
  entityId: string | null
  scale: OntologyScaleKey
} {
  const hash = window.location.hash.slice(1)
  const query = hash.split('?')[1] ?? ''
  const params = new URLSearchParams(query)
  const entityType = params.get('entity_type')
  const scaleParam = params.get('oc_scale')
  return {
    search: params.get('search'),
    entityType: entityType && ENTITY_TYPES.includes(entityType) ? (entityType as OntologyEntityType) : null,
    entityId: params.get('entity'),
    scale: scaleParam && isOntologyScaleKey(scaleParam) ? scaleParam : DEFAULT_ONTOLOGY_SCALE,
  }
}

/**
 * 通用本体浏览器（BioPortal / Protégé 式三栏布局）：
 * 顶栏（右侧粒度透镜 OntologyScaleSelector）+ 三栏：
 * 左栏 Ontology Explorer（顶部搜索 + 懒加载树）
 * 中栏 Entity Detail（医学本体浏览器详情页：Entity Header + 面包屑 + Section Cards）
 * 右栏 Relation Explorer（Tabs + 关系卡，可折叠）
 * 关系数据由本组件单次拉取（getRelations），共享给详情面板的
 * External Atlas / Knowledge Relations 模块与右栏列表，避免重复请求；
 * 选中态由本组件持有，树/搜索/详情/关系四向驱动。
 *
 * 树结构：region 树 = canonical_region_hierarchy 的 part_of 递归（parent|children），
 * granularity_level 只作节点徽章与显示透镜，永不参与父子判定。
 * BR4 尺度：cyto/molecular 切到跨层注册表树（buildEntityRoots）；
 * 脑区尺度 = 粒度透镜（显示深度过滤）；切换尺度以 key 重挂树。
 */
export function OntologyBrowser() {
  // Phase 8：URL 跳转参数仅在挂载时消费一次（选中态之后由用户交互驱动）
  const [initialParams] = useState(readBrowserParamsFromHash)
  const [selected, setSelected] = useState<SelectedEntity | null>(() =>
    initialParams.entityType && initialParams.entityId
      ? { entityType: initialParams.entityType, entityId: initialParams.entityId }
      : null,
  )
  const [selectedId, setSelectedId] = useState<string | null>(initialParams.entityId)
  const [searchQuery, setSearchQuery] = useState(initialParams.search ?? '')
  const [scale, setScale] = useState<OntologyScaleKey>(initialParams.scale)
  const [relations, setRelations] = useState<RelationGroup[] | null>(null)
  const [relationsError, setRelationsError] = useState(false)
  const [relationsReloadKey, setRelationsReloadKey] = useState(0)
  // 1280 及以下屏幕：右侧关系栏默认折叠（可手动展开）；
  // jsdom 无 matchMedia → 测试环境保持展开
  const [relationsCollapsed, setRelationsCollapsed] = useState(
    () => window.matchMedia?.('(max-width: 1280px)').matches ?? false,
  )
  // 研究地图（meso 小分支自动展开 + 子计数徽章 + 展开到研究层级按钮）
  const [researchView, setResearchView] = useState<RegionResearchView | null>(null)

  const openDetail = (entityType: OntologyEntityType, entityId: string) => {
    setSelectedId(entityId)
    setSelected({ entityType, entityId })
  }

  const handleSelect = (node: OntologyTreeNode) => openDetail(node.entityType, node.id)

  const handleSearchSelect = (node: OntologyTreeNode) => {
    openDetail(node.entityType, node.id)
    setSearchQuery('')
  }

  // BR4：尺度切换 → 状态 + URL hash（oc_scale 参数，保留其余 query 参数）
  const selectScale = useCallback((next: OntologyScaleKey) => {
    setScale(next)
    const hash = window.location.hash.slice(1)
    const [path, queryString] = hash.split('?')
    const params = new URLSearchParams(queryString ?? '')
    params.set('oc_scale', next)
    window.location.hash = `${path}?${params.toString()}`
  }, [])

  const roots = useMemo(() => buildEntityRoots(scale), [scale])

  const getChildren = useCallback(
    (node: OntologyTreeNode, signal?: AbortSignal) => ontologyApi.getTreeChildren(node, scale, signal),
    [scale],
  )

  // 研究地图：脑区尺度下按当前透镜派生（原始数据会话级缓存）；
  // cyto/molecular 是跨层注册表树，无脑区层级 → 不取
  useEffect(() => {
    if (scale === 'cyto' || scale === 'molecular') {
      setResearchView(null)
      return
    }
    const controller = new AbortController()
    let active = true
    setResearchView(null)
    ontologyApi.getRegionResearchView(scale, controller.signal).then(view => {
      if (active) setResearchView(view)
    })
    return () => {
      active = false
      controller.abort()
    }
  }, [scale])

  const mesoAutoExpandSet = useMemo(
    () => new Set(researchView?.autoExpandIds ?? []),
    [researchView],
  )

  const selectedType = selected?.entityType
  const selectedEntityId = selected?.entityId
  const panelKey = selected ? `${selectedType}:${selectedEntityId}` : null

  // 关系数据单次拉取：选中变化 / 手动重试时触发
  useEffect(() => {
    if (!selected) {
      setRelations(null)
      setRelationsError(false)
      return
    }
    const controller = new AbortController()
    let active = true
    setRelations(null)
    setRelationsError(false)
    ontologyApi
      .getRelations(selectedType as OntologyEntityType, selectedEntityId as string, controller.signal)
      .then(groups => {
        if (active) setRelations(groups)
      })
      .catch(() => {
        if (active) setRelationsError(true)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [selectedType, selectedEntityId, relationsReloadKey])

  const showSearchResults = searchQuery.trim().length >= ONTOLOGY_SEARCH_MIN_LENGTH

  const toggleRelations = () => setRelationsCollapsed(value => !value)

  return (
    <div className={`oc-browser ${relationsCollapsed ? 'oc-browser-relations-collapsed' : ''}`}>
      <div className="oc-browser-topbar">
        <span className="oc-browser-topbar-hint">粒度透镜只过滤显示深度，树结构始终来自 canonical_region_hierarchy</span>
        <OntologyScaleSelector value={scale} onChange={selectScale} variant="compact" />
      </div>

      <div className="oc-browser-cols">
        <aside className="oc-browser-tree">
          <div className="oc-browser-col-head">
            <h3 className="oc-browser-col-title">Ontology Explorer</h3>
          </div>
          <OntologySearchInput value={searchQuery} onChange={setSearchQuery} />
          {showSearchResults ? (
            <OntologySearchResults query={searchQuery} onSelect={handleSearchSelect} />
          ) : (
            <OntologyTree
              key={scale}
              roots={roots}
              getChildren={getChildren}
              onSelect={handleSelect}
              selectedId={selectedId}
              autoExpandLevels={DEFAULT_AUTO_EXPAND_LEVELS}
              mesoAutoExpandIds={mesoAutoExpandSet}
              preloadedChildren={researchView?.preloadedChildren}
              childCountById={researchView?.childCountById}
              researchExpandIds={researchView?.researchExpandIds}
              researchAncestorIds={researchView?.researchAncestorIds}
            />
          )}
        </aside>

        <main className="oc-browser-detail">
          <div className="oc-browser-col-head">
            <h3 className="oc-browser-col-title">Entity Detail</h3>
            {relationsCollapsed && (
              <button
                type="button"
                className="oc-browser-toggle-relations"
                aria-label="展开关系栏"
                title="展开关系栏"
                onClick={toggleRelations}
              >
                <PanelRightOpen size={14} />
              </button>
            )}
          </div>
          {selected ? (
            <EntityDetailPanel
              key={panelKey ?? undefined}
              entityType={selectedType as OntologyEntityType}
              entityId={selectedEntityId as string}
              relations={relations}
              relationsError={relationsError}
              onRetryRelations={() => setRelationsReloadKey(k => k + 1)}
              onNavigate={openDetail}
            />
          ) : (
            <div className="oc-panel-hint">点击左侧树节点查看实体详情；层级数据按需加载。</div>
          )}
        </main>

        <aside className="oc-browser-relations">
          <div className="oc-browser-col-head">
            <h3 className="oc-browser-col-title">Relations</h3>
            <button
              type="button"
              className="oc-browser-toggle-relations"
              aria-label="折叠关系栏"
              title="折叠关系栏"
              onClick={toggleRelations}
            >
              <PanelRightClose size={14} />
            </button>
          </div>
          {selected ? (
            <RelationExplorer
              key={panelKey ?? undefined}
              groups={relations}
              hasError={relationsError}
              onRetry={() => setRelationsReloadKey(k => k + 1)}
              onNavigate={openDetail}
            />
          ) : (
            <div className="oc-panel-hint">选中实体后显示关系。</div>
          )}
        </aside>
      </div>
    </div>
  )
}

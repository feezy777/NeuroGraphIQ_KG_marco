import { Fragment, useEffect, useState } from 'react'
import { ArrowRight, ChevronDown, ChevronRight } from 'lucide-react'
import { ontologyApi } from '../../../api/ontologyApi'
import { graphExplorerEntityUrl } from '../../graph-explorer/ontologyNavigation'
import { EntityChip } from '../ui/EntityChip'
import { EmptyState } from '../ui/EmptyState'
import { ErrorState } from '../ui/ErrorState'
import { OntologyBadge } from '../ui/OntologyBadge'
import { RelationCard } from '../ui/RelationCard'
import { SectionCard } from '../ui/SectionCard'
import { Skeleton, SkeletonRows } from '../ui/Skeleton'
import { StatusChip } from '../ui/StatusChip'
import { ProvenanceField } from './ProvenanceField'
import {
  ENTITY_TYPE_LABELS,
  GRANULARITY_LEVEL_NAMES,
  GRANULARITY_LEVEL_ORDER,
  type OntologyEntityType,
} from '../browser/tree/OntologyTreeNode'
import type {
  DetailRow,
  EntityDetailData,
  EntityRef,
  MultiscaleBioItem,
  RegionMultiscaleData,
  RelationGroup,
  RelationItem,
} from './types'

type EntityDetailPanelProps = {
  entityType: OntologyEntityType
  entityId: string
  /** 关系数据由 Browser 单次拉取后共享（null = 加载中，本面板只做计数摘要） */
  relations?: RelationGroup[] | null
  relationsError?: boolean
  onRetryRelations?: () => void
  /** 面板内导航（面包屑/父/子节点点击）→ 宿主在树中重新选中 */
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}

function confidenceText(value: number | null): string {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

/** 粒度层级 → 医生可读名（Whole-brain/Macro/Clinical/…；不显示 L0-L9 编号） */
function levelLabel(value: string | null | undefined): string | null {
  if (!value) return null
  return GRANULARITY_LEVEL_NAMES[value] ?? value
}

function RowList({ rows }: { rows: DetailRow[] }) {
  return (
    <dl className="oc-detail-list">
      {rows.map(row => (
        <div className="oc-detail-row" key={row.label}>
          <dt>{row.label}</dt>
          <ProvenanceField row={row} />
        </div>
      ))}
    </dl>
  )
}

function RefLink({
  entity,
  onNavigate,
  showLevel = false,
}: {
  entity: EntityRef
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
  /** Children 分组行：名称 + 粒度徽章（隐藏 code，防徽章挤压文字） */
  showLevel?: boolean
}) {
  return (
    <button
      type="button"
      className="oc-hierarchy-link"
      onClick={() => onNavigate?.(entity.entityType, entity.id)}
      disabled={!onNavigate}
    >
      <EntityChip
        entityType={entity.entityType}
        name={entity.name}
        code={entity.code}
        status={entity.status}
        hideCode={showLevel}
      />
      {showLevel && entity.granularityLevel && (
        <OntologyBadge variant="level">{levelLabel(entity.granularityLevel)}</OntologyBadge>
      )}
    </button>
  )
}

/** Children 粒度分组条数超过该值时默认折叠（如 Brain 下 609 个 meso 后裔） */
const CHILDREN_GROUP_COLLAPSE_THRESHOLD = 12

const EMPTY_MULTISCALE: RegionMultiscaleData = {
  mesoRegions: [],
  subregions: [],
  fineRegions: [],
  cellTypes: [],
  molecules: [],
}

type ChildrenGroupData = { level: string; label: string; items: EntityRef[] }

function levelOrder(level: string): number {
  return GRANULARITY_LEVEL_ORDER[level] ?? 99
}

/** Children 的一个粒度分组（可折叠；大量 meso 数据默认折叠） */
function ChildrenGroup({
  label,
  items,
  onNavigate,
}: {
  label: string
  items: EntityRef[]
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const [open, setOpen] = useState(items.length <= CHILDREN_GROUP_COLLAPSE_THRESHOLD)
  return (
    <div className="oc-children-group">
      <button
        type="button"
        className="oc-children-group-head"
        aria-expanded={open}
        onClick={() => setOpen(prev => !prev)}
      >
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="oc-children-group-label">{label}</span>
        <span className="oc-section-card-count">{items.length}</span>
      </button>
      {open && (
        <ul className="oc-children-group-list">
          {items.map(item => (
            <li key={item.id}>
              <RefLink entity={item} showLevel onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** 跨层生物层条目 → RelationCard 行（cell type：relation/分类学；molecule：evidence/来源） */
function bioRelationItems(
  items: MultiscaleBioItem[],
  relationLabel: string,
  detailLabel: string,
): RelationItem[] {
  return items.map(item => ({
    ref: item.ref,
    meta: [
      { label: relationLabel, value: item.relation },
      ...(item.detail ? [{ label: detailLabel, value: item.detail }] : []),
      { label: '置信度', value: confidenceText(item.confidence) },
    ],
  }))
}

/** 关系分组渲染为 Section Card（Circuit 拓扑 / Function 关联共用） */
function RelationItemsCard({
  title,
  group,
  relationsError,
  onRetryRelations,
  onNavigate,
}: {
  title: string
  group: RelationGroup | undefined
  relationsError: boolean
  onRetryRelations?: () => void
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}) {
  const count = group && !group.unavailable ? group.items.length : 0
  return (
    <SectionCard title={title} count={count}>
      {relationsError ? (
        <div className="oc-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>Failed to load</span>
          <button type="button" className="btn btn-xs" onClick={onRetryRelations}>
            Retry
          </button>
        </div>
      ) : !group ? (
        <SkeletonRows rows={3} />
      ) : group.unavailable ? (
        <EmptyState title="No canonical relation available" reason="后端 API 待接入（不展示假数据）" />
      ) : group.items.length === 0 ? (
        <EmptyState title="No canonical relation available" reason="该实体暂无此关系记录" />
      ) : (
        <div className="oc-inspector-relation-list">
          {group.items.map(item => (
            <RelationCard
              key={item.ref.id}
              item={item}
              navigable={group.navigable !== false}
              onNavigate={onNavigate}
            />
          ))}
        </div>
      )}
    </SectionCard>
  )
}

function ProvenanceCard({ provenance }: { provenance: DetailRow[] }) {
  return (
    <SectionCard title="Provenance">
      {provenance.length > 0 ? (
        <RowList rows={provenance} />
      ) : (
        <EmptyState title="No provenance on record" />
      )}
    </SectionCard>
  )
}

function RelationsFailedBlock({
  onRetryRelations,
}: {
  onRetryRelations?: () => void
}) {
  return (
    <div className="oc-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span>Failed to load</span>
      <button type="button" className="btn btn-xs" onClick={onRetryRelations}>
        Retry
      </button>
    </div>
  )
}

function HierarchySubBlock({
  label,
  items,
  emptyText,
  onNavigate,
}: {
  label: string
  items: EntityRef[]
  emptyText: string
  onNavigate?: (entityType: OntologyEntityType, entityId: string) => void
}) {
  return (
    <div className="oc-detail-sub-block">
      <span className="oc-detail-sub-label">{label}</span>
      {items.length > 0 ? (
        <ul className="oc-hierarchy-list">
          {items.map(item => (
            <li key={item.id}>
              <RefLink entity={item} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      ) : (
        <span className="oc-muted">{emptyText}</span>
      )}
    </div>
  )
}

/**
 * Ontology Inspector（中栏）：按实体类型渲染不同 Header + Section Cards。
 * 信息优先级：人类可读名称 → 关系结构 → code → provenance；
 * code 不进入视觉第一层（Connection 主标题 = 类型标题，code 下沉到 Properties）。
 */
export function EntityDetailPanel({
  entityType,
  entityId,
  relations = null,
  relationsError = false,
  onRetryRelations,
  onNavigate,
}: EntityDetailPanelProps) {
  const [data, setData] = useState<EntityDetailData | null>(null)
  const [hasError, setHasError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    let active = true
    setData(null)
    setHasError(false)
    ontologyApi
      .getEntityDetail(entityType, entityId, controller.signal)
      .then(detail => {
        if (active) setData(detail)
      })
      .catch(() => {
        if (active) setHasError(true)
      })
    return () => {
      active = false
      controller.abort()
    }
  }, [entityType, entityId, reloadKey])

  if (hasError) {
    return (
      <ErrorState
        message="Entity detail failed to load"
        onRetry={() => setReloadKey(k => k + 1)}
      />
    )
  }

  if (!data) {
    return (
      <div className="oc-skeleton-block" aria-label="加载中">
        <Skeleton height={24} width="40%" />
        <Skeleton height={14} width="60%" />
        <SkeletonRows rows={4} />
      </div>
    )
  }

  const typeLine = data.granularityLevel
    ? `${levelLabel(data.granularityLevel) ?? data.granularityLevel} ${ENTITY_TYPE_LABELS[data.entityType]}`
    : ENTITY_TYPE_LABELS[data.entityType]

  const basicRows: DetailRow[] = [
    { label: 'Type', value: ENTITY_TYPE_LABELS[data.entityType] },
    { label: 'Code', value: data.code ?? '—', mono: true },
    { label: 'Granularity', value: levelLabel(data.granularityLevel) ?? '—' },
    { label: 'Confidence', value: confidenceText(data.confidence) },
    { label: 'Status', value: data.status ?? '—' },
    ...data.basic,
  ]

  const group = (key: string) => relations?.find(g => g.key === key)

  // ── Connection：Header = 类型标题 + Source → Target；Source/Target/Properties 卡片 ──
  if (data.entityType === 'connection') {
    return (
      <div className="oc-inspector">
        <header className="oc-entity-header">
          <div className="oc-entity-title-row">
            <h2 className="oc-entity-name">{data.typeTitle ?? data.name}</h2>
            <StatusChip status={data.status} />
          </div>
          {data.source && data.target && (
            <div className="oc-entity-subtitle">
              <span className="oc-entity-subtitle-name">{data.source.name}</span>
              <ArrowRight size={14} className="oc-entity-subtitle-arrow" aria-label="指向" />
              <span className="oc-entity-subtitle-name">{data.target.name}</span>
            </div>
          )}
          <span className="oc-entity-type-line">{typeLine}</span>
        </header>

        <div className="oc-inspector-body">
          <SectionCard title="Source Region">
            {data.source ? (
              <RefLink entity={data.source} onNavigate={onNavigate} />
            ) : (
              <span className="oc-muted">Source unavailable</span>
            )}
          </SectionCard>
          <SectionCard title="Target Region">
            {data.target ? (
              <RefLink entity={data.target} onNavigate={onNavigate} />
            ) : (
              <span className="oc-muted">Target unavailable</span>
            )}
          </SectionCard>
          <SectionCard title="Properties">
            <RowList rows={basicRows} />
          </SectionCard>
          <ProvenanceCard provenance={data.provenance} />
        </div>
      </div>
    )
  }

  // ── Circuit：Header = 回路名；Region topology / Connections / Functions ──
  if (data.entityType === 'circuit') {
    return (
      <div className="oc-inspector">
        <header className="oc-entity-header">
          <div className="oc-entity-title-row">
            <h2 className="oc-entity-name">{data.name}</h2>
            <StatusChip status={data.status} />
          </div>
          {data.code && (
            <span className="oc-entity-code" title={data.code}>
              {data.code}
            </span>
          )}
          <span className="oc-entity-type-line">{typeLine}</span>
        </header>

        <div className="oc-inspector-body">
          <SectionCard title="Overview">
            <RowList rows={basicRows} />
            {data.description && (
              <p className="oc-detail-desc" style={{ marginTop: 8 }}>
                {data.description}
              </p>
            )}
          </SectionCard>
          <RelationItemsCard
            title="Region topology"
            group={group('regions')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <RelationItemsCard
            title="Connections"
            group={group('connections')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <RelationItemsCard
            title="Functions"
            group={group('functions')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <ProvenanceCard provenance={data.provenance} />
        </div>
      </div>
    )
  }

  // ── Function：Header = 功能名；Associated regions/circuits + Hierarchy ──
  if (data.entityType === 'function') {
    return (
      <div className="oc-inspector">
        <header className="oc-entity-header">
          <div className="oc-entity-title-row">
            <h2 className="oc-entity-name">{data.name}</h2>
            <StatusChip status={data.status} />
          </div>
          {data.code && (
            <span className="oc-entity-code" title={data.code}>
              {data.code}
            </span>
          )}
          <span className="oc-entity-type-line">{typeLine}</span>
        </header>

        <div className="oc-inspector-body">
          <SectionCard title="Overview">
            <RowList rows={basicRows} />
            {data.description && (
              <p className="oc-detail-desc" style={{ marginTop: 8 }}>
                {data.description}
              </p>
            )}
          </SectionCard>
          <SectionCard title="Hierarchy" count={data.children.length}>
            <HierarchySubBlock
              label="Parent"
              items={data.parent ? [data.parent] : []}
              emptyText="No parent on record"
              onNavigate={onNavigate}
            />
            <HierarchySubBlock
              label="Children"
              items={data.children}
              emptyText="No subfunctions on record"
              onNavigate={onNavigate}
            />
          </SectionCard>
          <RelationItemsCard
            title="Associated regions"
            group={group('regions')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <RelationItemsCard
            title="Associated circuits"
            group={group('circuits')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <ProvenanceCard provenance={data.provenance} />
        </div>
      </div>
    )
  }

  // ── BR4 跨层实体：Cell Type / Molecule（Header + Overview + 对齐区域 + Provenance） ──
  if (data.entityType === 'cell_type' || data.entityType === 'molecule') {
    return (
      <div className="oc-inspector">
        <header className="oc-entity-header">
          <div className="oc-entity-title-row">
            <h2 className="oc-entity-name">{data.name}</h2>
            <StatusChip status={data.status} />
          </div>
          {data.code && (
            <span className="oc-entity-code" title={data.code}>
              {data.code}
            </span>
          )}
          <span className="oc-entity-type-line">{typeLine}</span>
        </header>

        <div className="oc-inspector-body">
          <SectionCard title="Overview">
            <RowList rows={basicRows} />
            {data.description && (
              <p className="oc-detail-desc" style={{ marginTop: 8 }}>
                {data.description}
              </p>
            )}
          </SectionCard>
          <RelationItemsCard
            title="Aligned Regions"
            group={group('regions')}
            relationsError={relationsError}
            onRetryRelations={onRetryRelations}
            onNavigate={onNavigate}
          />
          <ProvenanceCard provenance={data.provenance} />
        </div>
      </div>
    )
  }

  // ── Region（默认）：医学本体浏览器详情 ——
  // Header（名称/code/类型/面包屑层级路径 = Hierarchy Path，逐级可点击）+
  // Basic Information → Children（按粒度分组）→ External Atlas →
  // Cell Types / Molecules（Biological Layer）→ Connections / Circuits / Functions（Knowledge Relations）→ Provenance
  const ms = data.multiscale ?? EMPTY_MULTISCALE
  const atlasGroup = group('atlas')

  // Children 粒度分组：非 meso/subregion/fine 的直接子节点按粒度分组；
  // meso/subregion/fine 组来自 multiscale 桶（含全部后裔），避免与直接子节点重复计数
  const BUCKET_LEVELS = new Set(['meso', 'subregion', 'fine'])
  const directByLevel = new Map<string, EntityRef[]>()
  for (const child of data.children) {
    const level = child.granularityLevel ?? ''
    if (BUCKET_LEVELS.has(level)) continue
    directByLevel.set(level, [...(directByLevel.get(level) ?? []), child])
  }
  const childrenGroups: ChildrenGroupData[] = []
  for (const [level, items] of directByLevel) {
    childrenGroups.push({
      level,
      label: level ? `${levelLabel(level) ?? level} children` : 'Children',
      items,
    })
  }
  if (ms.mesoRegions.length > 0) {
    childrenGroups.push({ level: 'meso', label: 'Meso children', items: ms.mesoRegions })
  }
  if (ms.subregions.length > 0) {
    childrenGroups.push({ level: 'subregion', label: 'Subregion children', items: ms.subregions })
  }
  if (ms.fineRegions.length > 0) {
    childrenGroups.push({ level: 'fine', label: 'Fine children', items: ms.fineRegions })
  }
  childrenGroups.sort((a, b) => levelOrder(a.level) - levelOrder(b.level))
  const childrenTotal = childrenGroups.reduce((sum, g) => sum + g.items.length, 0)

  return (
    <div className="oc-inspector">
      <header className="oc-entity-header">
        <div className="oc-entity-title-row">
          <h2 className="oc-entity-name">{data.name}</h2>
          <StatusChip status={data.status} />
          {/* Phase 8 双向跳转：图侧解析候选后以 region 为中心加载 */}
          <button
            type="button"
            className="btn btn-xs oc-entity-open-graph"
            onClick={() => {
              window.location.hash = graphExplorerEntityUrl(entityId)
            }}
          >
            Open in Graph
          </button>
        </div>
        {data.code && (
          <span className="oc-entity-code" title={data.code}>
            {data.code}
          </span>
        )}
        <span className="oc-entity-type-line">{typeLine}</span>
        {data.path.length > 0 && (
          <nav className="oc-breadcrumb" aria-label="层级路径">
            {data.path.map((crumb, index) => {
              const isLast = index === data.path.length - 1
              return (
                <Fragment key={crumb.id}>
                  {index > 0 && <span className="oc-breadcrumb-sep">&gt;</span>}
                  <button
                    type="button"
                    className={`oc-breadcrumb-link ${isLast ? 'oc-breadcrumb-current' : ''}`}
                    onClick={() => onNavigate?.(crumb.entityType, crumb.id)}
                  >
                    {crumb.name}
                  </button>
                </Fragment>
              )
            })}
          </nav>
        )}
      </header>

      <div className="oc-inspector-body">
        <SectionCard title="Basic Information">
          <RowList rows={basicRows} />
          {data.description && (
            <p className="oc-detail-desc" style={{ marginTop: 8 }}>
              {data.description}
            </p>
          )}
        </SectionCard>

        <SectionCard title="Children" count={childrenTotal}>
          {childrenGroups.length > 0 ? (
            <div className="oc-children-groups">
              {childrenGroups.map(g => (
                <ChildrenGroup
                  key={g.level || 'none'}
                  label={g.label}
                  items={g.items}
                  onNavigate={onNavigate}
                />
              ))}
            </div>
          ) : (
            <EmptyState title="No subregions on record" reason="该脑区暂无下级分区记录" />
          )}
        </SectionCard>

        <SectionCard title="External Atlas">
          {relationsError ? (
            <RelationsFailedBlock onRetryRelations={onRetryRelations} />
          ) : relations === null ? (
            <SkeletonRows rows={2} />
          ) : !atlasGroup || atlasGroup.unavailable || atlasGroup.items.length === 0 ? (
            <EmptyState title="No atlas mappings on record" reason="该脑区暂无外部图谱映射" />
          ) : (
            <div className="oc-inspector-relation-list">
              {atlasGroup.items.map(item => (
                <RelationCard key={item.ref.id} item={item} navigable={false} />
              ))}
            </div>
          )}
        </SectionCard>

        <SectionCard title="Cell Types">
          {ms.cellTypes.length > 0 ? (
            <div className="oc-inspector-relation-list">
              {bioRelationItems(ms.cellTypes, '关系', '分类学').map(item => (
                <RelationCard key={item.ref.id} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          ) : (
            <EmptyState title="No cell type alignment on record" reason="该脑区暂无细胞类型对齐记录" />
          )}
        </SectionCard>

        <SectionCard title="Molecules">
          {ms.molecules.length > 0 ? (
            <div className="oc-inspector-relation-list">
              {bioRelationItems(ms.molecules, '证据', '来源').map(item => (
                <RelationCard key={item.ref.id} item={item} onNavigate={onNavigate} />
              ))}
            </div>
          ) : (
            <EmptyState title="No molecular entity on record" reason="该脑区暂无分子实体证据记录" />
          )}
        </SectionCard>

        <RelationItemsCard
          title="Connections"
          group={group('connections')}
          relationsError={relationsError}
          onRetryRelations={onRetryRelations}
          onNavigate={onNavigate}
        />
        <RelationItemsCard
          title="Circuits"
          group={group('circuits')}
          relationsError={relationsError}
          onRetryRelations={onRetryRelations}
          onNavigate={onNavigate}
        />
        <RelationItemsCard
          title="Functions"
          group={group('functions')}
          relationsError={relationsError}
          onRetryRelations={onRetryRelations}
          onNavigate={onNavigate}
        />

        <ProvenanceCard provenance={data.provenance} />
      </div>
    </div>
  )
}

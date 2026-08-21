import { Brain, Dna, FunctionSquare, Link2, Microscope, Network, type LucideIcon } from 'lucide-react'
import type { OntologyEntityType } from '../browser/tree/OntologyTreeNode'

/** 六类本体实体的图标（树 / 详情头 / 关系卡片共用） */
const ENTITY_ICONS: Record<OntologyEntityType, LucideIcon> = {
  region: Brain,
  connection: Link2,
  circuit: Network,
  function: FunctionSquare,
  cell_type: Microscope,
  molecule: Dna,
}

export function EntityIcon({
  entityType,
  size = 14,
  className,
}: {
  entityType: OntologyEntityType
  size?: number
  className?: string
}) {
  const Icon = ENTITY_ICONS[entityType]
  return <Icon size={size} className={className} aria-hidden="true" />
}

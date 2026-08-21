import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

/** 可折叠 Section Card（Inspector 的 Overview / Hierarchy / Provenance / Relations 共用） */
export function SectionCard({
  title,
  count,
  defaultOpen = true,
  children,
}: {
  title: string
  count?: number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="oc-section-card">
      <button
        type="button"
        className="oc-section-card-header"
        onClick={() => setOpen(prev => !prev)}
        aria-expanded={open}
      >
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
        <span className="oc-section-card-title">{title}</span>
        {count !== undefined && <span className="oc-section-card-count">{count}</span>}
      </button>
      {open && <div className="oc-section-card-body">{children}</div>}
    </section>
  )
}

import type { ReactNode } from 'react'

export function Modal({ title, children, onClose, busy }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  return (
    <div className="ontology-modal-overlay" onClick={onClose}>
      <div className="ontology-modal" onClick={e => e.stopPropagation()}>
        <div className="ontology-modal-header">
          <span className="ontology-card-title">{title}</span>
          <button type="button" className="btn btn-xs" onClick={onClose}>关闭</button>
        </div>
        <div className="ontology-modal-body">{children}</div>
        {busy && <div className="ontology-empty">处理中…</div>}
      </div>
    </div>
  )
}

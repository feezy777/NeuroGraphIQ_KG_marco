import { useState } from 'react'
import { DuplicatesView } from './DuplicatesView'
import { TermsTable } from './TermsTable'
import { UngroundedView } from './UngroundedView'

type FunctionSubView = 'pending' | 'all' | 'ungrounded' | 'duplicates'

export function FunctionsGovernance({ granularity, role }: { granularity: string; role: string }) {
  const [subView, setSubView] = useState<FunctionSubView>('pending')
  return (
    <div>
      <div className="ontology-subview-tabs">
        {(
          [
            ['pending', '待审核术语'],
            ['all', '全部术语'],
            ['ungrounded', '未锚定记录'],
            ['duplicates', '合并建议'],
          ] as Array<[FunctionSubView, string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`ontology-subview-tab ${subView === key ? 'ontology-subview-tab-active' : ''}`}
            onClick={() => setSubView(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {subView === 'pending' && <TermsTable role={role} />}
      {subView === 'all' && <TermsTable status="all" role={role} />}
      {subView === 'ungrounded' && <UngroundedView granularity={granularity} role={role} />}
      {subView === 'duplicates' && <DuplicatesView />}
    </div>
  )
}

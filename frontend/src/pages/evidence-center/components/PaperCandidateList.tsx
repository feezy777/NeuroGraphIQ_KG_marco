import type { ReactNode } from 'react'
import { FileSearch, FileText } from 'lucide-react'
import { EmptyState } from './EmptyState'

interface Props {
  /** 候选论文总数(标题 (N)) */
  total: number
  /** 是否可手动检索(searchable=false 时为空态提示任务候选场景;为 true 时显示 [调整检索条件]) */
  searchable: boolean
  /** 已排除论文数 */
  excludedCount: number
  onRestoreExcluded: () => void
  /** [调整检索条件]:展开检索面板 */
  onAdjustSearch: () => void
  /** 候选卡列表(有结果时渲染) */
  children: ReactNode
}

/** 候选论文列表:标题「候选论文(N)」+ 空态(EmptyState + 底部轻提示)/ 卡片列表 */
export function PaperCandidateList({
  total,
  searchable,
  excludedCount,
  onRestoreExcluded,
  onAdjustSearch,
  children,
}: Props) {
  return (
    <div className="evidence-candidates-papers">
      <div className="evidence-candidates-papers-head">
        <h4>候选论文（{total}）</h4>
        {excludedCount > 0 && (
          <button type="button" className="btn btn-xs" data-testid="evidence-restore-excluded" onClick={onRestoreExcluded}>
            恢复排除（{excludedCount}）
          </button>
        )}
      </div>
      {total === 0 ? (
        <>
          <EmptyState
            icon={searchable ? <FileSearch size={24} /> : <FileText size={24} />}
            title={searchable ? '暂无候选论文' : '暂无候选证据'}
            description={searchable
              ? '当前还没有找到相关论文，可尝试调整检索条件后重新搜索。'
              : '当前对象暂无候选证据，可尝试重新提取或切换其他对象。'}
            actionLabel={searchable ? '调整检索条件' : undefined}
            onAction={searchable ? onAdjustSearch : undefined}
          />
          <div className="evidence-candidates-hint" data-testid="evidence-candidates-hint">
            勾选论文后可批量操作；被排除的论文可通过「恢复排除」找回。
          </div>
        </>
      ) : (
        children
      )}
    </div>
  )
}

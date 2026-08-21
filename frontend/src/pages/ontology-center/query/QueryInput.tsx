import { Clock, History, Lightbulb, Loader2, Search } from 'lucide-react'

export const EXAMPLE_QUESTIONS: string[] = [
  '海马有哪些亚区？',
  '连接海马的脑区有哪些？',
  '海马参与哪些回路？',
  '海马有哪些细胞和分子？',
]

/** 左侧 Query Workspace：标题 + 输入框 + 查询按钮 + 示例问题 + 最近查询 */
export function QueryInput({
  value,
  onChange,
  onSubmit,
  onPick,
  recent,
  loading,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  /** 点击示例问题 / 最近查询：填词并立即执行 */
  onPick: (question: string) => void
  recent: string[]
  loading: boolean
  disabled: boolean
}) {
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      if (!disabled) onSubmit()
    }
  }
  return (
    <div className="oqd-workspace">
      <div className="oqd-workspace-head">
        <h2 className="oqd-title">NeuroGraphIQ Query</h2>
        <p className="oqd-subtitle">Ask neuroscience knowledge graph</p>
      </div>
      <div className="oqd-query-box">
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={'请输入脑区、连接、回路相关问题\n例如：海马有哪些功能？'}
          disabled={loading}
          aria-label="自然语言问题"
        />
        <button
          type="button"
          className="oqd-submit-btn"
          onClick={onSubmit}
          disabled={disabled}
          aria-busy={loading}
        >
          {loading ? <Loader2 size={14} className="oq-spin" /> : <Search size={14} aria-hidden="true" />}
          查询
        </button>
        <span className="oqd-submit-hint">Ctrl/⌘ + Enter 快速查询</span>
      </div>
      <div className="oqd-examples">
        <span className="oqd-section-label">
          <Lightbulb size={12} aria-hidden="true" />
          示例问题
        </span>
        <div className="oqd-example-chips">
          {EXAMPLE_QUESTIONS.map(question => (
            <button
              key={question}
              type="button"
              className="oqd-example-chip"
              onClick={() => onPick(question)}
            >
              {question}
            </button>
          ))}
        </div>
      </div>
      {recent.length > 0 && (
        <div className="oqd-recent">
          <span className="oqd-section-label">
            <History size={12} aria-hidden="true" />
            最近查询
          </span>
          <ul className="oqd-recent-list">
            {recent.map(question => (
              <li key={question}>
                <button
                  type="button"
                  className="oqd-recent-item"
                  onClick={() => onPick(question)}
                  title={question}
                >
                  <Clock size={12} aria-hidden="true" />
                  <span>{question}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

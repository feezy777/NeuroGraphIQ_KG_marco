/** 统一错误状态 + Retry 按钮 */
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="oc-error-state" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-xs" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  )
}

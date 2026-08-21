/** 通用小徽章：level chip / code 徽章 / 通用标记 */
export function OntologyBadge({
  variant = 'neutral',
  title,
  children,
}: {
  variant?: 'neutral' | 'level' | 'code' | 'primary'
  title?: string
  children: React.ReactNode
}) {
  return (
    <span className={`oc-badge oc-badge-${variant}`} title={title}>
      {children}
    </span>
  )
}

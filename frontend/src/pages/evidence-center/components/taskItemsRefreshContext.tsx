import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

interface TaskItemsRefreshValue {
  version: number
  refresh: () => void
}

const TaskItemsRefreshContext = createContext<TaskItemsRefreshValue>({ version: 0, refresh: () => {} })

/** 共享刷新信号:任一消费方 refresh() 后,所有 useEvidenceTaskItems 实例统一重取(避免各自重复请求) */
export function TaskItemsRefreshProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion(v => v + 1), [])
  return <TaskItemsRefreshContext.Provider value={{ version, refresh }}>{children}</TaskItemsRefreshContext.Provider>
}

export function useTaskItemsRefresh(): TaskItemsRefreshValue {
  return useContext(TaskItemsRefreshContext)
}

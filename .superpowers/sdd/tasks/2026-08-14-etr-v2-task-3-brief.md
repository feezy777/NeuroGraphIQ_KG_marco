# V2 Task 3: 页面三栏常显 + 左栏 Claim + 删除 TaskListPanel

来源：`docs/superpowers/plans/2026-08-14-evidence-tasks-page-v2.md` Task 3（BASE: cc3fe96）

**Files:**
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`（**外科式**;工作树中有未提交的嵌入模式改动,必须保留,只做本任务指定修改）
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`（tasks 布局断言更新）
- Delete: `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`

**Interfaces:**
- Produces: tasks 模块始终三栏;左栏 = ClaimSummaryPanel(与候选模块一致);`isTasksList/isFullWidth` 移除,恢复仅 `isPapers` 控制全宽。

## Steps

### Step 1: 更新页面测试

`EvidenceCenterPage.test.tsx`:
1. **删除**「tasks 列表视图全宽:无左右栏,渲染任务卡片区」整条测试。
2. **删除**「详情视图左栏返回按钮回到任务列表」整条测试(返回按钮已移入中栏,由模块测试覆盖)。
3. **替换**「右栏随 module 切换:…」整条测试为:

```tsx
  it('右栏随 module 切换:tasks 渲染待处理队列,candidates 渲染待处理对象队列', () => {
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    expect(screen.getByTestId('evidence-task-queue')).toBeTruthy()
    fireEvent.click(screen.getByText('证据候选'))
    const title = () => container.querySelector('.evidence-right-panel h4')?.textContent ?? ''
    expect(title()).toContain('待处理对象')
  })
```

4. **新增**:

```tsx
  it('tasks 三栏常显:左栏 Claim 面板,中栏任务区,右栏队列', async () => {
    vi.mocked(listPaperEvidenceTasks).mockResolvedValue({ items: [TASK_FIXTURE], total: 1 })
    window.location.hash = '#/evidence-center?module=tasks'
    const { container } = render(<EvidenceCenterPage />)
    await waitFor(() => expect(screen.getByText('任务A')).toBeTruthy())
    expect(container.querySelector('.evidence-left')).toBeTruthy()
    expect(container.querySelector('.evidence-right')).toBeTruthy()
    expect(container.querySelector('.evidence-center-layout-full')).toBeNull()
  })
```

### Step 2: 运行测试确认失败

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx`
Expected: FAIL —— 新增「tasks 三栏常显」失败(左栏仍渲染 TaskListPanel/全宽条件仍在,evidence-left 在列表视图不存在)

### Step 3: 页面外科式修改

`frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`(保留嵌入模式相关所有现有代码):

1. 删除 `import { TaskListPanel } from './components/TaskListPanel'`。
2. 把:

```tsx
  const isPapers = state.module === 'papers'
  // tasks 列表视图(无 taskId)同论文库一样全宽,隐藏左右栏
  const isTasksList = state.module === 'tasks' && !state.taskId
  const isFullWidth = isPapers || isTasksList
```

改回:

```tsx
  const isPapers = state.module === 'papers'
```

并把本文件中其余三处 `isFullWidth` 改回 `isPapers`(布局 className 一处 + 左栏 aside 条件一处 + 右栏 aside 条件一处)。

3. 左栏分支(原来 `state.module === 'tasks' ? <TaskListPanel /> : <ClaimSummaryPanel .../>`)替换为无条件渲染 ClaimSummaryPanel:

```tsx
        {!isPapers && (
          <aside className="evidence-left">
            <ClaimSummaryPanel
              claimText={candidateClaim?.claimText ?? ''}
              components={candidateClaim?.components ?? []}
              targetType={candidateClaim?.targetType ?? ''}
              granularity={candidateClaim?.granularity ?? null}
            />
          </aside>
        )}
```

注意:该文件工作树中有嵌入模式(embedded prop、EvidenceModuleNavButton、ContextBar/StepPills 条件)等未提交改动——全部保留,只做上述修改。

4. 删除文件 `frontend/src/pages/evidence-center/components/TaskListPanel.tsx`(整文件删除)。

### Step 4: 运行测试确认通过

Run: `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx src/pages/evidence-center/components/TaskItemQueue.test.tsx`
Expected: 三文件全绿(页面测试基线失败只剩 3 个:五模块接线 promotion / 其他模块左栏 ObjectQueue / initial-queue)

## 硬约束

- **不要执行任何 git 操作**——提交与文件删除由控制器做外科式处理。
- 只允许改动上述 3 个文件。EvidenceCenterPage.tsx 已有未提交改动,必须保留,只做本任务指定修改。
- 不改后端、不改候选/审核/晋升模块、不改 ValidationWorkbench。
- 测试断言不要检查 `module=tasks` URL 字符串。

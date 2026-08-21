### Task S5: 佐证任务右栏 Task Summary + 论文库全宽 + 视觉收尾

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`(右栏 Task Summary:任务状态/进度/统计/操作)
- Modify: `frontend/src/pages/evidence-center/modules/PaperLibraryModule.tsx`(全宽布局适配骨架例外)
- Modify: `frontend/src/styles.css`(三栏 grid/ContextBar/StepPills/PaperCard 分层/divider 样式;减少 border)
- Test: 回归(两模块测试适配布局断言)

**行为:**
- 佐证任务:中栏任务列表;右栏选中任务 Summary(状态/进度 total/processed/awaiting/failed/操作:开始处理/打开)
- 论文库:全宽列表 + Detail Drawer(骨架隐藏左右栏)
- 视觉收尾:section spacing + subtle divider;Primary 按钮收敛

**提交:** `feat(evidence-center): 佐证任务右栏摘要 + 论文库全宽 + 视觉收尾`

---


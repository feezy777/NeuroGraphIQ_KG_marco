### Task U3: 中栏搜索面板拆分(Search/Filters/BatchActions/StatusSummary/CandidateList/Empty)

**Files:**
- Create: `components/PaperSearchPanel.tsx`(中栏顶部「查找相关论文」;大搜索框 placeholder「检索式 / 关键词(留空使用系统推荐检索式)」+ [重新搜索] [恢复系统推荐] 同行;Query Chips 浅蓝圆角+×清空可换行)
- Create: `components/PaperSearchFilters.tsx`(细分隔线+「检索过滤」;一行:☐仅OA / 证据模式[自动▼] / 年份[如2020▼] / [恢复默认];控件高度统一)
- Create: `components/PaperBatchActions.tsx`(「批量操作」;☐全选 + [提取所选论文(N)] 蓝主,N=0 禁用)
- Create: `components/PaperStatusSummary.tsx`(浅蓝状态条 48-54px:找到论文 N | AI提取 N | 已核验 N | Coverage N/M | 模型判断(加粗)+ 右侧[进入人工审核] 蓝主)
- Create: `components/PaperCandidateList.tsx`(「候选论文(N)」;空态:文档+放大镜图标/暂无候选论文/说明/调整检索条件按钮/轻提示行;有结果:紧凑 PaperCandidateCard)
- Create: `components/PaperCandidateCard.tsx`(四行层级:标题粗体/作者·Journal·Year/匹配度理由/PMID·DOI·摘要·OA徽章;底部:☐加入提取/[查看详情]/[排除此候选];提取后:AI判断·Coverage·已核验N·[查看证据候选])
- Create: `components/EmptyState.tsx`(统一空态:图标+标题+说明+可选按钮)
- Modify: `EvidenceCandidatesModule.tsx`(检索区/批量/状态条/候选列表替换为上述组件,保留全部逻辑)
- Modify: `styles.css`(搜索面板/过滤/状态条/候选卡/空态样式)
- Test: 每组件渲染与交互(折叠/清 chips/禁用/空态/卡层级);全量回归

**提交:** `feat(evidence-center): 中栏搜索面板组件化拆分`

---


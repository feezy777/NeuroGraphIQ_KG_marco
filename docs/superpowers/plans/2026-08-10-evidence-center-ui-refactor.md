# Evidence Center UI 重构实施计划(视觉稿还原)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(推荐)或 executing-plans。步骤用 `- [ ]` 跟踪。

**Goal:** 按已确认视觉稿(深蓝系统导航/白顶栏/浅灰工作区 #f5f7fa/蓝主色 #1677ff/三栏审核工作站)完整重构 Evidence Center 页面视觉与组件拆分,不改后端与接口语义。

**Architecture:** 基于现有 21 组件 + 5 模块拆分细化:页面骨架(ModuleNav/ContextBar/Stepper)→ 三栏(左 ClaimSummaryPanel / 中 PaperSearch+Status+Candidates / 右 EvidenceQueuePanel)→ 其他四模块同语言;统一 Empty 组件;样式 token 收敛(间距/高度/字体层级)。

**Tech Stack:** React 18 + TS + 现有 styles.css token 体系(不引入新 UI 框架)。

## Global Constraints

- 不改后端;不改变 Europe PMC/DeepSeek/Evidence/Paper/Passage/Coverage/attach/rollback/confidence 接口语义
- 完整页面非弹窗;保留系统侧边栏(220px)与顶栏(52px)+ 全局颗粒度切换器,不重做第二套
- 三栏 `240px minmax(640px,1fr) 340px`,间距 12-16px,三栏独立滚动
- 页面背景 #f5f7fa;内容区白底 + 1px 浅 border + 8-12px radius;少阴影
- 主色沿用 --primary #1677ff;按钮高 32-36px;Input/Select 高度一致
- 字体层级:页面标题 18-20 / 模块标题 15-16 / 正文 13-14 / 辅助 12px
- 空态统一组件;所有已有功能(manual/batch queue/search/extract/translate/verify/attach/rollback/draft/autosave/URL 恢复/race cancel)必须保留
- Claim 信息块动态生成(claim_components),禁止写死 connection 字段
- 浏览器 console 不允许 ReferenceError(ClaimView 为 HMR 陈旧,硬刷即解;重构后需人工确认无报错)
- 禁止 window.prompt/confirm/alert、Modal 套 Modal、巨型 Card、大留白

---

### Task U1: 页面骨架视觉重构(ModuleNav / ContextBar / Stepper / 三栏背景)

**Files:**
- Modify: `pages/evidence-center/EvidenceCenterPage.tsx`(三栏 grid 240/640/340 + 背景 #f5f7fa + 栏内白底 Card 化)
- Modify: `pages/evidence-center/EvidenceCenterHeader.tsx`(模块导航胶囊:选中蓝实底白字/未选浅灰深字/圆角偏大紧凑)
- Create: `components/EvidenceModuleNav.tsx`(从 Header 拆出导航)
- Modify: `components/ContextBar.tsx`(整行浅蓝灰背景;左侧:状态 Badge「等待处理对象」+ 一句完整事实「需要验证:xxx 存在投射连接(方向性:directed)」;右侧 [刷新](白底描边)[返回数据中心](蓝主);不拆散字段)
- Modify: `components/StepPills.tsx`(圆数字+文字+虚线连接;当前蓝/完成绿/未完成浅灰;紧凑)
- Modify: `styles.css`(.evidence-center-* 背景/栏 Card/间距 12-16/gap)

**测试:** 导航选中态;ContextBar 事实句渲染;Stepper 三态;三栏背景类

**提交:** `style(evidence-center): 骨架视觉重构(模块导航/ContextBar/Stepper/三栏背景)`

---

### Task U2: 左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel

**Files:**
- Create: `components/ClaimSummaryPanel.tsx`(左栏「当前需要验证的事实」;5 个独立信息块:类型/源脑区/目标脑区/连接关系/方向;每块浅蓝灰 bg+轻 border+8px radius+左侧小图标(tag/location/target/network/arrow,用现有图标体系或 emoji/字符);中文标签蓝/值深色;块间距 10-12px;**由 claim_components 动态生成,按 component_type 映射块,不写死**)
- Modify: `EvidenceCenterPage.tsx`(左栏 candidates 分支渲染 ClaimSummaryPanel 替代 ClaimView;ClaimView 保留或复用为内部实现)
- Create: `components/EvidenceQueuePanel.tsx`(右栏「待处理对象」+ 数量 Badge + Tabs(待审核 N/已完成 N/失败 N)+ ☐只看未处理 + 紧凑 List Item(名称/类型·confidence/证据数/状态)+ 当前项浅蓝选中 + 空态(托盘图标/队列为空/当前没有待处理对象)+ 底部固定[查看全部对象])
- Modify: `EvidenceCandidatesModule.tsx`(左栏 Claim 推送数据适配 ClaimSummaryPanel;右栏队列由页面级渲染 EvidenceQueuePanel 替代 ObjectQueue——检查 ObjectQueue 与 EvidenceQueuePanel 关系:EvidenceQueuePanel 可直接增强/替换 ObjectQueue,确认其他模块(左栏队列)的复用)
- Test: ClaimSummaryPanel 动态块渲染(connection 类型 5 块;其他 target_type 按 components 生成);EvidenceQueuePanel Tabs/只看未处理/空态/选中

**提交:** `feat(evidence-center): 左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel`

---

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

### Task U4: 其余四模块同语言(Review/Promotion/Tasks)

**Files:**
- Modify: `modules/EvidenceReviewModule.tsx`(标题体系「人工审核」;中栏分区 Claim+Paper+Passage+Coverage;右栏 ReviewerDecisionPanel 严格分区:AI初判(模型方向/Coverage)/分隔线/人工最终判断(方向/等级/置信度/备注)/分隔线/置信度影响(Current/Reviewer/Rule/Maximum/Final)/sticky[驳回][审核通过];无搜索控件)
- Modify: `modules/EvidencePromotionModule.tsx`(右栏 PromotionImpact:当前/Reviewer/晋升后 Confidence + Evidence数 + Passage数 + 最终状态;sticky[退回人工审核][确认晋升];Primary 仅确认晋升)
- Modify: `modules/EvidenceTasksModule.tsx` + `components/TaskSummary.tsx`(同语言:标题/间距/卡片)
- Modify: `styles.css`(review/promotion/tasks 组件样式统一)
- Test: 三模块视觉类断言 + 全量回归

**提交:** `style(evidence-center): Review/Promotion/Tasks 模块统一视觉语言`

---

### Task U5: 样式 token 收敛 + 空态统一 + 字体层级

**Files:**
- Modify: `styles.css`(:root 补 --font-mono(7 处回退);间距节奏 8/12/16/20;按钮高 32-36;Input/Select 高度一致;字体层级 18-20/15-16/13-14/12;5 处复刻空态替换为 EmptyState)
- 清理:重复/死类(勘察发现的)
- Test: build + 全量

**提交:** `style(evidence-center): token 收敛与空态统一`

---

### Task U6: 全量回归 + 分辨率验收

**Files:** 无新增
**行为:**
- `npx vitest run` 全绿 + `npm run build` + `npx tsc --noEmit`
- 浏览器人工验收(implementer 无浏览器时,用 Playwright/curl 不可行则检查布局 CSS 数值 + 报告):
  - 1920×1080 / 1600×900 / 1366×768:无横向滚动;中栏不被压窄;按钮可见;独立滚动;Empty 态;有结果态;长 Claim/标题换行;审核右栏 sticky;console 无错误
  - 至少:构建产物检查 + 报告分辨率适配结论(基于 CSS 媒体查询/数值推理)

**提交:** 如无修复不提交

---

## Self-Review 记录

- **规格覆盖**:用户 25 条 → U1(六/七/十八/十九)/U2(六/十四)/U3(七-十三)/U4(十五-十七)/U5(十八/二十三)/U6(二十五)✓
- **组件拆分**:23 条建议全部落地(U1-U3 新建组件 + 既有复用)✓
- **约束**:不改后端✓;不写死 connection(U2 动态生成)✓;ClaimView 报错说明(U1 备注硬刷新)✓
- **类型一致性**:EmptyState props `{icon?, title, description, actionLabel?, onAction?}`;ClaimSummaryPanel props `{claimText, components, targetType, granularity}`;PaperCandidateCard 复用现有 CandidatePaperData

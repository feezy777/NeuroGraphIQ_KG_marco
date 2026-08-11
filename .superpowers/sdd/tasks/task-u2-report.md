# Task U2 Report:左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel

> 日期:2026-08-11 · Commit:`65982a3` feat(evidence-center): 左栏 ClaimSummaryPanel + 右栏 EvidenceQueuePanel

## 状态

✅ 完成。全量 `npx vitest run` 185/185 通过(20 文件);`npx tsc --noEmit` EXIT 0;`npm run build` 成功(仅既有 chunk 体积告警,与本次无关)。只提交了 U2 相关 14 个文件,后端未动,未改功能逻辑。

## 实现内容

### 新增组件

| 文件 | 说明 |
|---|---|
| `components/ClaimSummaryPanel.tsx` | 候选模块左栏「当前需要验证的事实」。由 `claim_components` 按 `component_type` 动态生成独立信息块:`COMPONENT_LABEL` 提供中文标签(源脑区/目标脑区/连接关系/方向/功能/回路身份/回路角色/步骤顺序/辅助上下文),`BLOCK_ICON` 字符图标映射(◉/◎/⇄/→/ƒ/↻/◈/№/ⓘ),未知类型回退「信息」块(`•`);`targetType` 非空时前置「类型」块(`#`);无任何块时回退为 claimText 单块(标签「事实」);`granularity?` 显示在标题旁 `ew-meta` 徽章。props:`{ claimText, components, targetType, granularity? }` |
| `components/EvidenceQueuePanel.tsx` | 候选模块右栏「待处理对象」队列视觉稿版:标题 + 右上角数量徽标(`evidence-queue-count`)、状态 Tabs(待审核 N / 已完成 N / 失败 N,`role="tablist"`)、☐ 只看未处理、紧凑条目(名称/类型·置信度/证据数/状态色/当前项浅蓝高亮)、空态(📥 收件箱图标 + 「队列为空」+「当前没有待处理的对象」+ 底部 [查看全部对象] 按钮)。Tabs 为交互过滤,默认停在「待审核」Tab;「查看全部对象」重置回全部条目 |
| `components/QueueListItem.tsx` | 从 ObjectQueue 提取的共享紧凑条目(含 `no_evidence_found` 灰色提示),ObjectQueue 与 EvidenceQueuePanel 共用,避免 ~20 行重复 |

### 接线与调整

- `EvidenceCenterPage.tsx`:candidates 左栏 `ClaimView` → `ClaimSummaryPanel`(透传 `candidateClaim` 四字段,含 granularity);其余模块左栏仍渲染 `ObjectQueue`
- `RightPanel.tsx`:candidates 分支 `ObjectQueue` → `EvidenceQueuePanel`(队列点击仍 `openTarget(..., 'candidates')`)
- `ObjectQueue.tsx`:改用共享 `QueueListItem` + `types.ts` 中导出的 `PENDING_STATUSES`/`DONE_STATUSES`(输出与既有测试断言逐字一致,ObjectQueue.test.tsx 未改动即通过)
- `types.ts`:新增 `PENDING_STATUSES`/`DONE_STATUSES` 常量
- 删除 `ClaimView.tsx`(grep 确认替换后无任何引用;`ClaimPanel` 为 review/promotion 中栏组件,保留)
- `EvidenceCenterContext.tsx` / `EvidenceCandidatesModule.tsx`:仅更新指向 ClaimView 的过时注释
- `styles.css`:新增 `.evidence-claim-summary*`(浅蓝灰 `--muted-bg` 块 + 轻 border + 8px 圆角 + 左侧圆形图标,块间距 10px,230px 左栏紧凑变体)与 `.evidence-queue-panel*`(胶囊 Tab 条、虚线空态卡、[查看全部对象] 按钮)样式;复用既有 `.evidence-claim-head` / `.evidence-queue-*` / `.btn` 体系

### 测试

- 新增 `ClaimSummaryPanel.test.tsx`:connection 类型 5 块(标签+值)、每块图标存在、circuit_function 动态生成 + 未知类型「信息」块、无 components 回退单块、granularity 徽章
- 新增 `EvidenceQueuePanel.test.tsx`:标题/数量徽标/Tabs 计数、默认待审核 Tab 只显示未处理项、Tab 切换过滤、只看未处理叠加出空态、空态图标/文案/[查看全部对象] 恢复全部、当前项按原始下标高亮(过滤后仍正确)、点击触发 onSelect
- `EvidenceCenterPage.test.tsx`:三栏骨架断言改为 `evidence-claim-summary` / `evidence-queue-panel`;「左栏 ClaimView」页级测试重写为 ClaimSummaryPanel 信息块断言(类型/源脑区/连接关系 3 块);initial-queue 与右栏队列测试改为新 testid;「ObjectQueue 渲染列表」重写为 EvidenceQueuePanel 默认 Tab + 切 Tab 行为(待审核 1/已完成 1/失败 0)

## 关键决策(勘察结论)

**ObjectQueue 与 EvidenceQueuePanel 关系**:两者为兄弟组件,共用 `QueueListItem`。EvidenceQueuePanel 是视觉稿版(数量徽标 + 交互 Tabs + 丰富空态),仅候选模块右栏(370px)使用;ObjectQueue(统计行 + 简单空态)保留给 tasks/review/promotion 左栏(230px)——Tabs 在 230px 窄栏会过于拥挤,且属最小改动方案。若后续视觉稿统一,可全量切换到 EvidenceQueuePanel。

**其他取舍**:
- EvidenceQueuePanel 默认「待审核」Tab:与面板主题「待处理对象」及空态文案「当前没有待处理的对象」一致(待审核无匹配即出空态);「查看全部对象」重置为全量列表
- 「底部固定」按钮:实现在空态卡底部(margin-top:auto),右栏为滚动容器,按钮不随内容漂移;未做 `position: sticky`(无必要)
- 图标用字符/emoji 体系(项目无图标库):claim 块用字符(◉◎⇄→ƒ↻◈№ⓘ•#),空态用 📥 emoji
- 旧 `.evidence-claim-text/chips` CSS 为死代码但无害,未删(保持最小 diff;ClaimView 删除已获授权)

## 风险 / 遗留

- 无阻塞问题。轻微:右栏队列默认只显示待审核项,用户需点 Tab 看已完成/失败(设计使然,有 Tabs 计数可见)
- `.evidence-claim-chip*` 等 40 行孤儿 CSS 可后续清理(refactor-cleaner 可做)

---

## 修复记录(2026-08-11,U2 Review Important #1 + 清理)

### Finding 1(Important):ClaimSummaryPanel fallback 条件错误

**问题**:`fallback = blocks.length === 0`,而 blocks 含「类型」块(targetType 非空即 push);实际接线(`EvidenceCandidatesModule.tsx` 232-237 行)`targetType: dto.target_type` 恒非空 → DTO 有 claim_text 但 claim_components 为空时,左栏只渲染类型块,claimText 被隐藏。

**修复**:`fallback = (components?.length ?? 0) === 0` —— 基于 components 而非 blocks,与规格「无 components 回退 claimText」一致。`frontend/src/pages/evidence-center/components/ClaimSummaryPanel.tsx`

**测试**:新增用例「components 为空但 targetType 非空时,仍回退为 claimText 单块(类型块不独占)」,先 RED(`'#类型connection'` 不包含「事实」)后 GREEN。

### 清理:孤儿 CSS

删除 `styles.css` 中 ClaimView 死代码区块(原 11590-11636,约 40 行):`.evidence-claim`(卡片)、`.evidence-claim-text`、`.evidence-claim-chips`、`.evidence-claim-chip*`、`.evidence-claim-head-actions` 及对应 `.evidence-left` 变体;保留 ClaimSummaryPanel 实际使用的 `.evidence-claim-head` / `.evidence-claim-head h4` / `.evidence-left .evidence-claim-head h4`(移至 ClaimSummaryPanel 区块注释下)。

### 验证

- 定向:ClaimSummaryPanel.test.tsx + EvidenceCenterPage.test.tsx → 2 files / 26 tests 全绿
- 全量:`npx vitest run` → 20 files / 186 tests 全绿
- `npx tsc --noEmit` 通过;`npm run build` 成功(仅既有 chunk 体积警告)

### Commit

`b57769b` fix(evidence-center): ClaimSummaryPanel components 为空时回退 claimText + 清理孤儿 CSS

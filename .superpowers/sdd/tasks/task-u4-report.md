# U4 报告:Review/Promotion/Tasks 三模块统一视觉语言

- **任务**:`.superpowers/sdd/tasks/task-u4-brief.md`
- **视觉规范**:`docs/superpowers/specs/2026-08-10-evidence-center-design.md` §15-17
- **分支**:`codex/ontology-evidence`
- **Commit**:`f6183cd style(evidence-center): Review/Promotion/Tasks 模块统一视觉语言`(10 files,+213/-22)

## 完成内容

### 1. Review 模块(中栏标题体系 + 右栏严格分区)

- `EvidenceReviewModule.tsx`:新增工具栏标题体系 `人工审核`(h3)+ 模块说明句(`evidence-module-hint`),空态与正常态均渲染;工具栏动作包裹 `evidence-review-toolbar-actions`;佐证原文分区新增 `已选佐证原文`(h4)+ 数量徽标(`evidence-review-passages-count`)。中栏完整标题链:人工审核 → 当前需要验证的事实(ClaimPanel)→ 当前论文 → 已选佐证原文 → Claim 覆盖情况(CoveragePanel)。
- 右栏 `ReviewerDecisionPanel` 分区不变(已符合):AI 初判(模型方向/Coverage)/分隔线/人工最终判断(方向/等级/置信度/备注)/分隔线/置信度影响/sticky `[驳回证据][审核通过]`。
- **无**论文搜索控件(符合规范)。

### 2. 置信度影响 5 格(视觉稿 Maximum 格)

- `confidenceImpact.ts`:新增 `maximum` 字段 = `max(current, reviewer)`(公式 `min(cap, max(current, reviewer))` 的 cap 前中间值,与后端 `confidence_rules.py` 变量一一对应);`computeConfidenceImpact` 返回 `{current, reviewer, cap, maximum, final}`。
- `ReviewerDecisionPanel.tsx`:影响网格新增 Maximum 格(`ew-impact-maximum`),位于 Rule 与 Final 之间;preview 分支取 `max(preview.current_confidence, preview.reviewer_confidence)`。
- `styles.css`:`ew-impact-grid` 5 列(340px 右栏适配),单元格/键值字号微调。

### 3. Promotion 模块

- `PromotionImpact.tsx`:字段齐全且标签与规范一致 — `当前置信度`/`Reviewer 置信度`/`晋升后置信度`/`新增 Evidence 数量`/`新增 Passage 数量`/`最终状态`;新增 Reviewer 置信度行(`pi-reviewer`);「晋升后置信度」已有「新增 Evidence/Passage 数量」「最终状态」行。
- sticky `[退回人工审核][确认晋升]` 已存在;**Primary 唯一:「确认晋升」**(`pi-return-btn` 非 primary,已有测试锁定)。

### 4. Tasks 模块(同语言)

- `EvidenceTasksModule.tsx` 已有 h3 `任务列表` + 说明句 + 分组卡(标题/数量徽标)模式,与本任务视觉语言一致,未改功能代码。
- `styles.css`:`.evidence-task-summary` gap 12→10px、h4 margin 统一(与其他右栏面板一致)。
- 右栏 `TaskSummary` Primary 唯一:「开始人工处理」(V2-S5 已收敛,本任务测试锁定)。

### 5. 统一 CSS

- `styles.css` 右栏 h4 统一 13px(原 TaskSummary 经基础规则 14px,现全部一致);间距/卡片样式与 U1-U3 骨架语言对齐。

## 测试

- **新增断言(三模块视觉类)**:
  - Review:中栏标题链(人工审核/当前需要验证的事实/当前论文/已选佐证原文+count/Claim 覆盖情况);置信度影响 5 格 preview 与本地计算;无 preview 时 Maximum=max(current,reviewer);contradicts 时 Maximum 不随 final。
  - Promotion:PromotionImpact 六字段齐全、pi-reviewer 值、`.ew-sticky-actions` 存在、Primary 唯一「确认晋升」。
  - Tasks:工具栏 h3 任务列表 + 说明句 + 分组卡(标题/数量徽标);TaskSummary 标题/进度条/分隔线/统计卡 + Primary 唯一「开始人工处理」。
  - `confidenceImpact.test.ts`:4 处 `toEqual` 补充 `maximum` 字段 + Maximum 专项测试。
- **全量回归**:`npx vitest run` → 27 files / **238 passed**(0 失败);`npx tsc --noEmit` → EXIT 0;`npm run build` → 成功(仅既有 chunk 体积警告)。

## 约束确认

- 只 `git add` 了 U4 相关 10 个文件(components/modules/styles.css);未动后端、未动功能逻辑(仅 class 名/标题/标签/CSS)。
- 修复一个既有测试的脆弱断言:`EvidenceReviewModule.test.tsx` 中 `/进入「证据晋升」/` 正则因新增工具栏说明句产生多匹配,改为精确 toast 文本 `已审核通过，进入「证据晋升」模块待晋升`(断言目标语义不变)。

## 关注点

- Maximum 格为视觉稿要求但与后端概念无直接对应;以 `max(current, reviewer)`(公式中间值)实现,并在注释/测试中说明语义,后续后端若引入独立 maximum 概念可平滑替换。
- 现有测试 238 个(此前为 228 左右 + 新增),全绿。

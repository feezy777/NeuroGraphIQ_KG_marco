# Task Report: Evidence Center candidates 模块三栏重排

## Status

**完成 (DONE)** — 提交 `8d02044` on `codex/ontology-evidence`，后端未改动。

## 目标布局实现

```
三栏(candidates 模块):
├── 左栏(230px): 当前对象验证事实 = ClaimView(Claim 单行 + components chips 可折叠)
├── 中栏(flex): 检索区(折叠条) + 统计信息条 + 候选论文列表
└── 右栏(370px): 待处理对象队列(ObjectQueue)
```

其他模块 (review/promotion/tasks) 保持原布局(左=ObjectQueue,右=各自面板);papers 全宽不变。

## 变更文件(仅前端,8 个)

| 文件 | 变更 |
|------|------|
| `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx` | 新增 `candidateClaim`(claimText/components/granularity/targetType)+ setter,与 candidateSummary/reviewDecision 同模式 |
| `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx` | ① DTO 加载后推送 candidateClaim(卸载/切对象清空) ② 移除中栏 ClaimView ③ 新增 stats memo(CandidateStats)+ CandidateStatsBar(列表态:检索区下方;证据视图态:保留在上方,[进入人工审核] 随勾选实时可用) ④ 折叠条新增 [提取所选论文(N)] primary 按钮(零选中禁用,复用 handleManualExtract) ⑤ 提示文案更新为「中栏统计条」 |
| `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx` | 左栏按模块切换:`candidates` → ClaimView(读 Context candidateClaim);其他模块 → 原 ObjectQueue |
| `frontend/src/pages/evidence-center/components/RightPanel.tsx` | candidates 分支由 CandidateSummary 改为 ObjectQueue(queue 来自 Context,currentIndex 组件内推导,onSelect 留在 candidates 模块);移除 CandidateSummary import |
| `frontend/src/pages/evidence-center/components/CandidateStatsBar.tsx` | **新增** 中栏统计条:找到论文 / AI 提取论文 / 已核验片段 / Coverage(N/M 或 —) / 模型判断(方向+评估) / [进入人工审核](零选中禁用) |
| `frontend/src/styles.css` | `.evidence-stats-bar` 系列、`.evidence-search-collapsed-actions`(按钮组右对齐)、`.evidence-left .evidence-claim` 窄面板紧凑适配(chips 允许换行) |
| `EvidenceCenterPage.test.tsx` / `EvidenceCandidatesModule.test.tsx` | 既有测试适配 + 新测试(见下) |

## 测试

- 新增(页面级):candidates 左栏 ClaimView 渲染(DTO 加载后 Claim 单行 + chips,中栏不再渲染);其他模块左栏仍为 ObjectQueue;右栏随 module 切换含 candidates → 待处理对象;统计条 [进入人工审核] 勾选流程跳转 review
- 新增(模块级):中栏统计条字段(找到 1 / 提取 1 / 核验 1 / Coverage 1/2 / 部分支持 / 模型评估);折叠条 [提取所选论文(N)] 零选中禁用 → 列表勾选后可用计数 → 点击调用 extractSelectedPaperEvidence
- 适配:三栏骨架测试(candidates 左=Claim 右=队列)、右栏切换标题、initial-queue 恢复条目断言位置(右栏)、ClaimView 旧模块级测试改为「不再自渲染」
- **全量 `npx vitest run`:19 文件 172 测试全部通过**;`npx tsc --noEmit` 通过;`npm run build` 通过(仅有既存 chunk size 警告)

## 关键决策 / 说明

1. **ClaimView props 复用**:现有 ClaimView 仅需 claimText/components/targetType;context 中的 granularity 按规格携带(当前 ClaimView 不展示,预留)。
2. **[进入人工审核] 按钮保留在统计条**:规格统计条内容清单未列按钮,但移除会破坏「勾选片段 → 进入人工审核」流程与既有页面测试;统计条替代右栏 CandidateSummary 后承载该主操作,证据视图态也保留统计条使按钮实时可用。
3. **CandidateSummary 组件文件保留**:类型 `CandidateSummaryData` 仍被 Context 与模块引用,且有独立组件测试;candidates 分支不再渲染它。模块仍推送 candidateSummary 到 Context(当前无消费者,保留与既有模式一致)。
4. **hook 规范**:RightPanel 中 queue 下标 useMemo 置于组件顶层(不在条件分支内),符合 rules-of-hooks。
5. 后端零改动;`git add` 仅限上述 8 个相关文件(分支上其他未提交改动未触碰)。

## Concerns

- 左栏 230px 内 Claim chips 采用允许换行(word-break)适配;超长 component statement 会多行显示而非截断。
- `candidateSummary` Context 推送当前无消费方(纯保留);后续如需收敛可随统计条数据源统一处理。

## 清理(2026-08-11,布局审查 Important 项:candidateSummary 无消费方)

- 删除 `EvidenceCandidatesModule.tsx` 中 summary memo 与两条 Context 推送 effect(`setCandidateSummary` 推送/卸载清空);`stats` memo 保留供中栏统计条使用;统计条注释去掉「右栏摘要 Context 推送同源」表述。
- 删除 `EvidenceCenterContext.tsx` 的 `candidateSummary`/`setCandidateSummary` 字段、state、value 与 useMemo deps 引用及 `CandidateSummaryData` type import。
- `git rm` 删除 `components/CandidateSummary.tsx` 与其独立测试 `components/CandidateSummary.test.tsx`(确认全前端零引用)。
- 清理 `styles.css` 中仅被该组件使用的死样式(`.evidence-candidate-summary`、`.evidence-summary-claim(-text)`、`.evidence-summary-model/-direction/-assessment/-review`);`.evidence-summary-label/-stats/-stat` 因 TaskSummary 共用而保留。
- `EvidenceCandidatesModule.test.tsx` 中无 candidateSummary 断言(仅有无关的 `coverage_summary` 数据字段),无需改动;`EvidenceCenterPage.test.tsx` 的 `evidence-candidate-summary` 不存在断言保留(仍通过,防回归)。
- 验证:`npx vitest run` 18 文件 166 测试全部通过;`npx tsc --noEmit` 通过;`npm run build` 通过(仅有既存 chunk size / dynamic import 警告)。
- 前置说明「Concerns: candidateSummary 推送当前无消费方(纯保留)」与「关键决策 3: 模块仍推送 candidateSummary」已由此清理闭环。

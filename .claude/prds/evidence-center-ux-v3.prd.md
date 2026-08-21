# 证据中心 UX 完善:StepPills 真实进度 + 证据候选页一目了然

## Problem

用户在证据候选页完成论文检索后,StepPills 仍停留在「确认对象」(步骤 1),无法反映对象实际处理进度——「查找论文/找到原文/人工审核/确认晋升」的进度感缺失。同时,证据候选页中栏从上到下堆叠 Claim 区 → 检索区(Query/Filter/Batch 三层)→ 候选论文列表,垂直空间被低频的检索控件占据,「需要拖动才能看到所有信息」,页面分区边界不清、无法一目了然。

## Evidence

- 用户观察(2026-08-10):检索出 9 篇论文后,StepPills 仍显示步骤 1「确认对象」。
- 用户观察:页面信息堆叠,Claim/检索/候选列表视觉区分不足,需滚动才能看全;期望"解耦、区分清晰、一目了然"。

## Users

- **Primary**: 领域数据审核员。在证据候选页对对象做论文检索与候选审阅,需要一眼看清"对象验证到哪一步 + 当前有哪些候选论文"。

## Hypothesis

我们相信**让 StepPills 由对象实际状态推导(而非固定 module 映射)、并把检索区改为默认折叠的紧凑条**将**让审核员不滚动即可掌握对象进度与候选全貌**给**领域数据审核员**。
We'll know we're right when **检索后 StepPills 前进到「查找论文」/提取后到「找到原文」,且一屏内可见 Claim + 检索折叠条 + 候选论文首屏**。

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| StepPills 进度真实(检索/提取/审核/晋升各阶段正确推进) | 100% 阶段 | 组件测试:检索后 step≥2,提取后 step≥3 |
| 检索区默认折叠(一屏信息密度) | 折叠态可见 Claim + 候选首屏 | 组件测试:折叠态检索控件不可见,展开可见 |
| 既有 155 前端测试回归 | 全绿 | vitest run |

## Scope

**MVP**:
1. **StepPills 进度真实化**:当前步骤由对象实际状态推导:
   - 进入候选未检索 = 1 确认对象
   - 已有检索结果 = 2 查找论文
   - 已有提取片段(draft/选中片段)= 3 找到原文
   - 已进入审核/有 review 状态 = 4 人工审核
   - 已晋升 = 5 确认晋升
   - 推导状态存 Context(对象级,切对象重置),候选/审核/晋升模块各自推进
2. **证据候选页分区重构**:
   - Claim 区:紧凑(Claim 一行 + chips 可折叠)
   - 检索区:**默认折叠为一条**(显示当前 Query 摘要 + [重新搜索] + [展开]);展开后显示 Query/Filter/Batch 三层
   - 候选论文列表:主视区优先,卡片信息密度优化(标题/引用/标签/操作分层已具备,压缩间距)
   - 检索完成后自动收起检索区,让候选列表占据主视区
3. **测试**:StepPills 阶段推导、检索区折叠/展开、检索后自动收起、全量回归

**Out of scope**:
- 不改后端;不改其他模块(人工审核/晋升/论文库)布局
- 不做响应式窄屏折叠(桌面优先)

## Delivery Milestones

| # | Milestone | Outcome | Status |
|---|---|---|---|
| 1 | StepPills 状态推导 + Context 对象进度 | 检索/提取/审核各阶段 StepPills 正确推进 | pending |
| 2 | 候选页分区重构(Claim 紧凑/检索折叠/列表优先) | 一屏可见关键信息,无需滚动 | pending |
| 3 | 测试 + 全量回归 | 155+ 全绿,build 通过 | pending |

## Open Questions

- [ ] StepPills 步骤 1「确认对象」在何种状态显示?(候选未检索时显示步骤 1 合理;佐证任务/论文库模块是否显示 StepPills?)
- [ ] 检索区折叠的默认态在"已有检索结果重新进入"时是否保持折叠?(建议:有结果即折叠)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 进度推导状态与真实数据脱节(如 draft 被清但状态未重置) | Low | Medium | 状态从现有数据源推导(draft/reviewStatus/result 存在性),不引入冗余布尔 |
| 折叠后用户找不到检索入口 | Low | Medium | 折叠条常显 Query 摘要 + 明确「展开检索」按钮 |
| 检索后自动收起导致用户错过 filters | Low | Low | 仅 Query 层折叠,filters 仍在展开态可见一次 |

---
*Status: DRAFT — requirements only. Implementation planning pending.*

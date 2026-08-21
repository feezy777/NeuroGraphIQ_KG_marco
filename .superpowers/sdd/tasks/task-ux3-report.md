# Task UX3 Report: StepPills 真实进度 + 证据候选页一目了然

## Status: ✅ 完成

## 提交

- `(本任务提交)` feat(evidence-center): StepPills 由对象实际进度推导 + 候选页检索区折叠

## 任务 1:StepPills 进度真实化

**Context 对象级进度**(`EvidenceCenterContext.tsx`):
- 新增 `ObjectProgress { searched, extracted, reviewed, promoted }` + `INITIAL_OBJECT_PROGRESS`
- Context value 新增 `progress` + `setProgress(patch)`(仅置位推进,永不回退)
- `openTask` / `openTarget` 切换对象时重置为全 false(对象级隔离)

**StepPills 推导**(`components/StepPills.tsx`):
- 新增纯函数 `deriveStep(module, progress)`:先看 module(tasks/papers→0 不高亮,review→4,promotion→5),再看 progress(promoted→5 → reviewed→4 → extracted→3 → searched→2 → 否则 1)
- 组件签名改为 `{ module, progress }`,移除固定映射 `MODULE_TO_STEP`
- `EvidenceCenterPage.tsx` 改为 `<StepPills module={state.module} progress={progress} />`

**各模块推进**:
- 候选模块:检索成功 → `searched`;选中片段 / 批量提取成功 → `extracted`;另有数据推导 effect(任务候选已含片段 / 本地已有审核草稿 → extracted,已有审核状态 → reviewed),保证「已有提取片段/已有 review 状态」进入时进度真实(声明在 URL 同步 effect 之后,openTarget 重置后本推导最终生效)
- 审核模块:`commitReviewStatus`(通过/驳回)→ `reviewed`
- 晋升模块:`handlePromote` attach 成功 → `promoted`

## 任务 2:证据候选页分区重构

- **Claim 区紧凑**:`.evidence-claim` padding/gap、claim 文本字号与内边距压缩;`ClaimView` 新增「收起组件」按钮(有组件时显示),chips 区可折叠,折叠后可一键展开(`evidence-claim-chips-toggle`)
- **检索区可折叠**(`EvidenceCandidatesModule.tsx` 模块内 state `searchExpanded`):
  - 无检索结果 → 展开完整检索区(现状)
  - 有检索结果 → 默认折叠为一条 `.evidence-search-collapsed`:「已检索」标签 + Query 摘要(截断,`evidence-search-collapsed-query`,取手动检索式或推荐词拼接或占位)+ [重新搜索](直接执行)+ [展开检索]
  - `runSearch` 成功 → `setSearchExpanded(false)` 自动收起;展开态批量层新增 [收起检索] 按钮
  - 切换目标时重置 `searchExpanded`
- **候选列表优先**:折叠态下 Claim 紧凑 + 检索折叠条 + 候选论文列表占据主视区;`.evidence-candidates-main`/`.evidence-candidates-papers`/`.evidence-candidate-paper`/`.paper-card-candidate` 间距压缩
- 样式追加于 `styles.css`:`.evidence-search-collapsed` 系列、`.evidence-claim-head-actions`;全部改动仅前端,后端零改动

## 任务 3:测试 + 回归

**新增/更新测试**:
- `StepPills.test.tsx` 重写:推导单测(searched→2 / extracted→3 / reviewed→4 / promoted→5 / module 覆盖 review→4、promotion→5、tasks/papers→0)+ 组件高亮渲染
- `EvidenceCandidatesModule.test.tsx` 新增「检索成功后检索区自动折叠为一条:折叠条可见、filters 不可见;展开可恢复;[重新搜索] 直接执行」;3 个既有批量/过滤测试在检索自动折叠后先点 [展开检索]
- `EvidenceCenterPage.test.tsx`:review 模块 StepPills 高亮断言 找到原文 → 人工审核

**全量回归**:
- `npx vitest run`:19 文件 / **166 测试全绿**(基线 155 → 166)
- `npx tsc --noEmit`:通过,零错误
- `npm run build`:通过(2335 modules,built in 2.47s;仅既有 chunk 体积 / dynamic-import warning,非错误)

## 残留检查

- `MODULE_TO_STEP` / `currentStep=` 引用:全库无残留
- 变更文件(11):全部在 `frontend/src/pages/evidence-center/` + `frontend/src/styles.css`,后端未动

## 遗留小项(可选)

- promoted 进度仅在晋升成功事件置位,无数据推导兜底(返回候选后如无草稿/候选片段会显示 3 而非 5;影响面小,切对象时重置)
- 「已检索」折叠条 Query 摘要以最后使用的检索式/推荐词为准,未持久化到 URL

---

## 追加修复:UX V3 评审 2 项 Important

### 提交

- `f95c519` fix(evidence-center): 进度推导依赖候选数据 + 切对象重置手动检索状态

### 修复 1:derive effect 缺 candidate_papers 依赖

**问题**:`EvidenceCandidatesModule.tsx` 进度推导 effect 依赖仅 `[current?.target_id]`(有 eslint-disable)。直达 URL 进入(刷新/深链/返回导航)时,effect 先对 fallback current(`candidate_papers: []`)跑一次;items 加载后 `current?.target_id` 不变(X→X),effect 不重跑 → 已有提取片段的对象显示步骤 1「确认对象」而非 3「找到原文」。

**修复**:依赖数组加入 `current?.candidate_papers` + `setProgress`(context 中为稳定 useCallback 引用),deps 完整后移除 eslint-disable;推导顺序(module → promoted/reviewed/extracted/searched)保持不变。

**测试**:直达 URL 进入(target 在 URL)+ 延迟 items(手动控制 Promise 解析)→ 加载前 StepPills 高亮「确认对象」,items 到达后自动重推导高亮「找到原文」。对未修复代码验证为 RED。

### 修复 2:切对象后 manual 检索状态泄漏

**问题**:目标切换重置 effect 只重置选择状态,不重置 `manualQuery`/`manualResult`/`manualSelected`/`manualResults`。两个非任务对象间切换(数据中心交接队列)时,新对象显示旧对象的检索结果与 query 摘要,折叠条 [重新搜索] 会对新对象执行旧 query。

**修复**:重置 effect 一并清空 `manualQuery('')`/`manualResult(null)`/`manualSelected(new Set())`/`manualResults([])`(`searchExpanded` 原本已重置)。

**测试**:对象 A 检索成功(折叠条显示 A 的 query 摘要)→ hashchange 切到对象 B → 断言折叠条消失、检索区回到展开态、query 输入为空、旧结果卡移除。对未修复代码验证为 RED。

### 验证

- `npx vitest run src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx src/pages/evidence-center/EvidenceCenterPage.test.tsx` → 39 passed
- `npx vitest run`(全量)→ 168 passed(19 files)
- `npx tsc --noEmit` → 0 errors

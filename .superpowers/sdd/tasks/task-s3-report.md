# Task S3 Report: 人工审核模块三栏重构 + review_approved 前端状态

## Status: DONE

## 变更概览

### 1. 左队列移除
- 检查确认 `EvidenceReviewModule` 本身不渲染队列(页面级 `ObjectQueue` 已统一)——无移除动作。
- 顺带修正:`EvidenceCenterBody` 的 `ObjectQueue onSelect` 原先一律跳 `candidates`;现改为在 review/promotion 模块内点击队列项**留在当前模块**,其余模块仍回候选视图(与 spec §15「左:待人工审核 Queue」一致)。

### 2. ReviewerDecisionPanel 升级(`components/ReviewerDecisionPanel.tsx`)
- 标题「人工审核」;新增 **AI 初判区**(`ew-ai-section`):`AI 初判: 支持`(modelDirection)+ Coverage `supported/required`(如有),灰字 AI 推荐样式。
- **分隔线「人工最终判断」**(`ew-divider`,subtle divider 样式)。
- 人工判断区:方向 5 选项 radio(支持/部分支持/矛盾/混合/不采用)、证据等级 select、Reviewer Confidence slider+input(0–0.85)、Reviewer Note textarea——props 保持兼容(新增字段全部可选带默认值)。
- **置信度影响区**(Current / Reviewer / Rule / Final 四格):preview 可用时直接用 `attach-preview` 返回的 current/reviewer_confidence/cap/final_confidence;preview 不可用时本地计算 `min(cap, max(current, reviewer))`,Rule cap 按方向:`supports → 0.85`、`partial → 0.75`、其余无上限(与后端 `confidence_rules.py` 一致)。纯函数抽到 `components/confidenceImpact.ts`。
- **sticky 底部**:`[驳回证据]`(次要)`[审核通过]`(primary,`ew-sticky-actions`,border-top 分隔)。
- 已审核状态反馈行(`已审核通过 · 支持 · 置信度 0.8`,重新进入时展示)。

### 3. ReviewStatusStore(`components/ReviewStatusStore.ts`,新建)
- `REVIEW_STATUS_KEY_PREFIX = 'evidence-center.review-approved.'`(sessionStorage)。
- `saveReviewStatus(targetId, status, meta)` / `loadReviewStatus(targetId)`(损坏 JSON → null)/ `clearReviewStatus(targetId)` / `listReviewApproved()`(扫描前缀,含 rejected,供晋升模块按 `status === 'review_approved'` 过滤)。
- meta 含 `{direction, evidenceLevel, confidence, note, at(ISO 时间戳)}`。

### 4. 审核模块行为(`modules/EvidenceReviewModule.tsx`)
- 「审核通过」→ `saveReviewStatus(review_approved)` + 提示「已审核通过,进入「证据晋升」模块待晋升」,**不调 attach**;「驳回证据」→ 写 `rejected` + 提示。
- 保留 review draft(不清理,供晋升读取);提交状态前同步 `persistDraft()`。
- 目标切换时 `loadReviewStatus` 恢复已有审核状态。
- 右栏接入:模块经 Context `reviewDecision` 推送决策状态(与 S2 `candidateSummary` 同模式),`RightPanel` 对 review 模块渲染 `<ReviewerDecisionPanel>`;`返回证据候选/保存草稿` 移到中栏顶部 toolbar。
- **修复的隐患**:`claimComponents = dto?.claim_components ?? []` 在 dto 未加载时每渲染生成新 `[]`,经 reviewDecision 推送 effect 造成无限重渲染(worker 崩溃)。改为 `useMemo(() => dto?.claim_components ?? [], [dto])`。

### 5. 其他
- `types.ts`:`DIRECTION_LABEL.not_found` 「未找到」→「不采用」(spec §15 选项文案)。
- `styles.css`:`evidence-review` 由 grid(1fr+380px)改为单列;`.ew-ai-section/.ew-divider/.ew-impact-*/.ew-sticky-actions` 新增;`.ew-right-inner` 卡片样式迁移到 `.evidence-right-panel` 作用域。
- `ConfidencePreview.tsx` 现无引用(置信度影响区取代),保留供晋升模块(S4)复用。

## 测试
- 新建 `ReviewStatusStore.test.ts`(7 个:读写/缺失/损坏 JSON/clear/list 扫描与过滤/前缀隔离/坏记录跳过)。
- 新建 `confidenceImpact.test.ts`(4 个:cap 规则/公式/组合输出)。
- 扩展 `EvidenceReviewModule.test.tsx`(16 个):新增审核通过写 store + 提示 + 不调 attach、驳回写 rejected、重新进入显示已审核标记、AI 初判区(Coverage 1/2、分隔线)、置信度影响区(preview 优先 + 无 preview 本地计算 partial cap 0.75)、sticky 按钮层级;测试渲染方式改为 module + RightPanel(panel 已移入右栏)。
- **运行结果**:`evidence-center` 111 通过(基线 94);全量 `npx vitest run` 125 通过;`npm run build` 成功(仅既有 chunk 体积 warning)。

## 提交
`feat(evidence-center): 人工审核三栏重构 + review_approved 前端状态`

## 遗留/关注点
1. `ConfidencePreview.tsx` 成为死代码(未删除,留待 S4 晋升模块复用或届时清理)。
2. 审核通过后留在原地(消息提示),未自动跳转 promotion——brief 允许二选一。
3. 后续 S4 晋升模块可直接用 `listReviewApproved()` 过滤 `review_approved` 构建待晋升列表。

# Phase 2 Report: 前端审核/晋升模块接线后端 Review API

**Date:** 2026-08-11
**Branch:** codex/ontology-evidence
**Commit:** 4da6749

## Summary

将 EvidenceCenter 的审核模块 (Review) 和晋升模块 (Promotion) 从纯 sessionStorage 驱动改为后端 Review API 驱动, sessionStorage 降级为 UI 缓存/后备。

## Changes Made

### 1. EvidenceReviewModule.tsx — 审核通过/驳回双写

- 导入 `buildReview` 并新增 `reviewBusy` 状态
- `commitReviewStatus` 改为 async: 先写 sessionStorage(兼容), 再调 `buildReview`(后端权威)
- `handleApprove`/`handleReject` 改为 async, 用 try/catch 处理 API 失败
- `handleApprove` 成功后提示 "已审核通过, 进入「证据晋升」模块待晋升"
- `handleReject` 成功后提示 "已驳回该证据, 不会进入晋升"
- 失败时提示错误, 保留草稿

### 2. EvidencePromotionModule.tsx — 待晋升列表/晋升/退回调后端

- 新增 `PendingItem` 接口 (`reviewId/targetType/targetId/direction/evidenceLevel/confidence/note/approvedAt`)
- 新增 `mapReviewToPending()` 将 `EvidenceReviewItem` 映射为 `PendingItem`
- `refreshPending` 改为 `async`: 主路径调 `listEvidenceReviews({ review_status: 'approved', promotion_status: 'awaiting_promotion', page_size: 100 })`, catch 降级为 `listReviewApproved()` (sessionStorage)
- `selectedPendingId` 改为后端 `reviewId` (UUID), 匹配逻辑改为 `targetId` 查找
- `handlePromote`: 调用 `promoteReview(reviewId)` 替代原来的 `attachPaperEvidence` (后端在 promote 内完成 evidence attachment)
- `handleReturnToReview`: 调用 `returnReview(reviewId, reason)` 替代纯 sessionStorage 清理
- 草稿恢复仍使用 sessionStorage key (按 targetId), 显示 paper info 等后端不便携带的数据
- 移除未使用的 `attachPaperEvidence` 和 `ReviewStatusRecord` 类型导入

### 3. ReviewerDecisionPanel.tsx — 防重复提交

- 新增可选 prop `reviewBusy?: boolean`
- 审核通过/驳回按钮在 `reviewBusy` 时 disabled, 文案改为 "审核中…"

### 4. 测试更新

- `EvidenceReviewModule.test.tsx`: mock `buildReview`, 验证审核通过/驳回调 `buildReview` + sessionStorage 写入, 新增 `buildReview` 失败时提示错误测试
- `EvidencePromotionModule.test.tsx`: mock `listEvidenceReviews`/`promoteReview`/`returnReview`, 验证待晋升列表来自后端, 晋升调 `promoteReview`, 退回调 `returnReview`, 新增后端失败降级 sessionStorage 测试

## Verification

- `npx vitest run`: **27 files, 241 tests passed**
- `npx tsc -b`: **0 errors**
- `npm run build`: **build successful**

## Key Design Decisions

1. **双写策略**: 审核模块先写 sessionStorage 再写后端 Review, 确保现有晋升模块向后兼容 + 跨标签瞬时提示
2. **sessionStorage 角色**: draft 仍保留 (persistDraft 不变), review-approved store 保留兼容但不作主数据源
3. **reviewId vs targetId**: 晋升模块选中项改用后端 `reviewId` 标识, 通过 `targetId` 查找 sessionStorage 草稿

## Files Changed

| File | Change |
|------|--------|
| `modules/EvidenceReviewModule.tsx` | +82 -30: 双写 buildReview |
| `modules/EvidencePromotionModule.tsx` | +185 -98: 读后端列表 + promoteReview/returnReview |
| `modules/EvidenceReviewModule.test.tsx` | +31 -4: 验证 buildReview 调用 |
| `modules/EvidencePromotionModule.test.tsx` | +86 -64: 验证后端 API 集成 |
| `components/ReviewerDecisionPanel.tsx` | +4 -4: reviewBusy 防重复提交 |

# Evidence Center 审计修复报告

日期:2026-08-11 | Commit: 519f033

## B1 (BLOCKED 已修复):「保存草稿」405
- 根因:前端 `saveTaskItemDraft` 用 `postJson` 调 `POST /api/ontology/evidence/batch/items/{item_id}/draft`,后端 `backend/app/routers/ontology.py` 该路径仅注册 GET + PUT → 405。
- 修复:`frontend/src/api/client.ts` 新增 `putJson<T>`(镜像 postJson,method='PUT',含 204/AbortSignal 处理);`frontend/src/api/endpoints.ts` `saveTaskItemDraft` 改用 `putJson`。
- 消费点 `EvidenceReviewModule.tsx` handleSaveDraft 无需改动(只调 endpoints 函数)。

## P1 (PARTIAL 已修复):切换任务后 URL target 陈旧
- 根因:`EvidenceCenterContext.tsx` `openTask` 只写 `{ taskId, module: 'candidates' }`,残留上一任务的 targetType/targetId → 审核/晋升打开错误对象。
- 修复:
  1. `openTask` 改为 `apply({ taskId, targetType: null, targetId: null, module: 'candidates' })`(`buildEvidenceUrl` 对 null 真值判断会丢弃参数,已由测试验证)。
  2. 兜底:`EvidenceCandidatesModule.tsx` 自动选中 effect 增加 URL 纠错:items 非空且 `current` 与 `state.targetId/targetType` 不一致(含陈旧 target 不匹配回退到 items[0])时,以当前项调 `openTarget` 回写 URL,与「URL 为空选中首个」条件合并。
- 测试:EvidenceTasksModule「打开任务清除 URL 残留的陈旧 target」;EvidenceCenterPage「切换任务后 URL 不再残留上一任务 target,候选加载后回写到新任务首个 item」。

## M3 (顺手):no_evidence_found 提示
- `ObjectQueue.tsx` 对象卡:`preprocessOutcome === 'no_evidence_found'` 时显示灰色提示「该对象预处理未找到有效证据片段」(不阻断显示);`styles.css` 新增 `.evidence-queue-item-hint` 灰色样式。
- 测试:ObjectQueue「no_evidence_found 时卡片显示灰色提示,其余条目不显示」。

## 验证
- `npx vitest run src/pages/evidence-center/`:16 文件 / 141 测试全绿(含新增 3 个)
- `npx vitest run`(全量):19 文件 / 155 测试全绿
- `npx tsc --noEmit`:0 错误

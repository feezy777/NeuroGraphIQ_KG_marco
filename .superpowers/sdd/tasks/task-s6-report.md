# Task S6 Report: 全量回归验证

## Status: DONE(纯验证,无修复)

## 验证清单与结果

### 1. 前端测试 — PASS
```
cd frontend && npx vitest run
Test Files  18 passed (18)
     Tests  146 passed (146)
Duration  3.14s, exit code 0
```
与预期 146 一致,全绿。

### 2. 前端构建 — PASS
```
cd frontend && npm run build
✓ built in 2.38s
```
仅既有 warning(非错误):`src/api/endpoints.ts` 被动态与静态混合 import(chunk 拆分提示)、个别 chunk > 500kB(gzip 409.84 kB)。无 TypeScript 错误。

### 3. 后端测试 — PASS
```
cd backend && .venv/Scripts/python.exe -m pytest \
  tests/test_paper_evidence.py tests/test_paper_evidence_api.py \
  tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py \
  tests/test_paper_evidence_batch_scale.py tests/test_paper_library_api.py \
  tests/test_paper_retrieval_phase2.py -q
62 passed, 2 warnings (FastAPI on_event DeprecationWarning,既有),3.69s,exit code 0
```

### 4. 壳确认 — PASS
`frontend/src/pages/data-center/EvidenceReviewModal.tsx` 共 26 行,仍为纯跳转壳:
- 仅 import `navigateToEvidenceCandidates` + `EvidenceQueueHandoffItem` 类型(来自 `../evidence-center/evidenceCenterUrl`)。
- 组件体:open 时 `navigateToEvidenceCandidates(...)` + `onClose()`,返回 `null`。无任何业务 UI,无业务组件 import。

### 5. review_approved 刷新保留 — PASS
- `frontend/src/pages/evidence-center/components/ReviewStatusStore.ts`:`REVIEW_STATUS_KEY_PREFIX = 'evidence-center.review-approved.'`;`saveReviewStatus` 写 sessionStorage(key = 前缀 + targetId,值含 status/meta{direction, evidenceLevel, confidence, note, at}/targetType)、`loadReviewStatus` 读(损坏 JSON → null)、`clearReviewStatus`、`listReviewApproved`(前缀扫描,晋升模块按 status 过滤)。sessionStorage 同标签页刷新后保留。
- 测试覆盖:`ReviewStatusStore.test.ts` 8 个(读写含 at 时间戳 / 无记录 null / 损坏 JSON / clear / list 扫描含 rejected / 前缀隔离 / 坏记录跳过 / targetType 可选)。
- 模块级:EvidenceReviewModule/EvidencePromotionModule 在目标切换与挂载时经 `loadReviewStatus` 恢复状态(对应模块测试中直接使用该 key,如 `EvidencePromotionModule.test.tsx` 中 sessionStorage.setItem 构造待晋升记录)。

### 6. 服务健康 — PASS
- `curl http://127.0.0.1:8002/api/health` → `{"status":"ok",...,"database":{"connected":true,...}}`
- `curl http://localhost:5173` → HTTP 200(前端 dev server 运行中)

## 发现的问题
无。未发现任何回归,无需修改业务代码。

## 提交
无(本任务为纯验证,无修复故不提交)。

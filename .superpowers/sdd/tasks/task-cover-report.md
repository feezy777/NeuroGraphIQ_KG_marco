# Evidence Center Cover Gap Fixes Report

**Commit**: `994946b` `fix(evidence-center): Coverage 双源标签区分 + Query 推荐/自定义语义 + 删除恢复排除重复入口`

**Date**: 2026-08-11

---

## Fix 1: Coverage 双源 -- 语义标签区分

**问题**: Candidate 卡和状态条都显示 "Coverage N/M",但数据源不同(Candidate 卡用后端 model `coverage_summary`,状态条用 `computeTmpCoverage` 人工调整后),两处可能不同值却同名。

**修改**:

| 文件 | 行 | 改动 |
|------|-----|------|
| `PaperCandidateCard.tsx` | 97 | `Coverage ${N}/${M}` -> `AI 初始覆盖 ${N}/${M}` |
| `PaperCandidateCard.tsx` | 98 | `Coverage ${pct}%` -> `AI 初始覆盖 ${pct}%` |
| `PaperStatusSummary.tsx` | 51 | label `Coverage` -> `人工审核覆盖` |
| `ReviewerDecisionPanel.tsx` | - | 确认不变:"AI 初判"标签已存在 |

**对应测试更新**:

| 文件 | 行 | 改动 |
|------|-----|------|
| `PaperCandidateCard.test.tsx` | 97, 120, 128, 136 | `Coverage` -> `AI 初始覆盖` |
| `PaperCandidateCard.test.tsx` | 120 | `.not.toContain('Coverage')` -> `.not.toContain('AI 初始覆盖')` |
| `EvidenceCandidatesModule.test.tsx` | 213 | `'Coverage 1/3'` -> `'AI 初始覆盖 1/3'` |

---

## Fix 2: Query Chip 清空语义修正

**问题**: `clearedTerms` 是 display-only 过滤,不清除实际检索词。用户 x 掉所有 chips 后搜索仍用后端推荐 `query_terms`,UI 空白但实际请求带词。

**修改**:

| 文件 | 行 | 改动 |
|------|-----|------|
| `EvidenceCandidatesModule.tsx` | 350-351 | 新增 `queryMode` 派生状态:`manualQuery.trim()` 非空或 `clearedTerms.size > 0` -> `'custom'`;否则 `'system'` |
| `EvidenceCandidatesModule.tsx` | 616 | 传递 `queryMode={queryMode}` 给 PaperSearchPanel |
| `PaperSearchPanel.tsx` | 17 | 接口新增 `queryMode?: 'system' \| 'custom'` |
| `PaperSearchPanel.tsx` | 98-104 | Query terms chips 行右侧增加轻量文本指示器:系统推荐时灰色"系统推荐检索式",自定义时蓝色"自定义检索式" |
| `styles.css` | 11892-11899 | 新增 `.evidence-query-mode` / `.evidence-query-mode-custom` CSS |

**不修改 `runSearch` 逻辑**:请求语义不变,仅让 UI 与请求语义一致。

---

## Fix 3: 删除"恢复排除"重复入口

**问题**: 两处"恢复排除"按钮:PaperSearchFilters(检索过滤行) 和 PaperCandidateList(列表头)。重复且混淆。

**修改**:

| 文件 | 行 | 改动 |
|------|-----|------|
| `PaperCandidateList.tsx` | 接口 | 移除 `excludedCount` / `onRestoreExcluded` props |
| `PaperCandidateList.tsx` | 32-35 | 删除列表头 `[恢复排除(N)]` 按钮 |
| `PaperCandidateList.tsx` | 50 | 轻提示文案:`可通过「恢复排除」找回` -> `已隐藏` |
| `EvidenceCandidatesModule.tsx` | 653-654 | 移除 PaperCandidateList 调用处的 `excludedCount` / `onRestoreExcluded` 传参 |

**保留**: PaperSearchFilters.tsx 的"恢复排除"按钮(过滤行)不变;EvidenceCandidatesModule 的 `excludedPaperIds` state 与 `onRestoreExcluded` 回调保留(供过滤器使用)。

**对应测试更新**:

| 文件 | 行 | 改动 |
|------|-----|------|
| `PaperCandidateList.test.tsx` | 9-10 | 移除 renderList 中的 `excludedCount` / `onRestoreExcluded` |
| `PaperCandidateList.test.tsx` | 26 | `'恢复排除'` -> `'已隐藏'` |
| `PaperCandidateList.test.tsx` | 44-49 | 删除"存在被排除论文时标题旁显示 [恢复排除(N)]"测试 |
| `EvidenceCandidatesModule.test.tsx` | 361-370 | 更新排除测试:不再验证列表头恢复按钮,改为验证空态提示"已隐藏" |
| `EvidenceCandidatesModule.test.tsx` | 899-905 | 更新手动检索排除测试:提示改为"已隐藏",移除列表头[恢复排除(N)]断言 |

---

## Fix 4: sessionStorage 持久化检查

**确认**: `ReviewStatusStore.ts` 使用 `sessionStorage` 存储审核状态,前缀 `evidence-center.review-approved.`。

| 场景 | 结果 |
|------|------|
| 审核通过后刷新(同标签页) | 状态恢复 |
| 关闭浏览器再打开 | 状态丢失 |
| 第二天重新访问 | 状态丢失 |
| Draft(`evidence-center.review-draft.*`) | 同样丢失 |

**结论**: `review_approved` / `awaiting_promotion` 需要后端持久化(数据库表/字段)。标记为下一阶段 P0。

---

## Verification Results

| 检查项 | 结果 |
|--------|------|
| `npx vitest run` | 239 passed, 27 test files, 0 failures |
| `npx tsc --noEmit` | 0 errors |
| `npm run build` | passed |

---

## Concerns

1. **Fix 2 (Query Mode)**: 指示器未在 collapsed 折叠条中显示,折叠条仅显示 querySummary。如果要统一指示,需在 PaperSearchPanel collapsed 态也加上,当前保持最小改动。
2. **Fix 3 (恢复排除)**: 任务候选场景(有 taskId 且有 items)下 PaperSearchFilters 不渲染,此时排除论文后唯一恢复途径是切换目标(触发 `excludedPaperIds` 清空)。若确实需要,可考虑在任务候选空态增加内联恢复入口。
3. **Fix 4**: sessionStorage 方案在浏览器重启后丢失已审核状态,晋升模块无法跨会话找到待晋升项。需下一阶段增加后端表 `review_approvals(target_type, target_id, status, meta, reviewed_at)`。

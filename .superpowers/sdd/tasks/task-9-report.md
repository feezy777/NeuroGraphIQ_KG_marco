# Task 9 Report: 证据晋升模块(EvidencePromotionModule)

## Status: DONE

Commit: `96e58ba` on `codex/ontology-evidence` — "feat(evidence): 证据晋升模块(EvidencePromotionModule)-唯一 attach 入口"

## Files Changed (committed, 6 files)

| File | Change |
|------|--------|
| `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx` | NEW — 证据晋升模块(唯一 attach 入口,三分组) |
| `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.test.tsx` | NEW — 6 个测试 |
| `frontend/src/pages/evidence-center/components/PromotionDialog.tsx` | `git mv` AttachDialog 改名,文案「确认入库」→「确认晋升」(git 识别 rename 94%) |
| `frontend/src/pages/evidence-center/components/EvidenceDetailDrawer.tsx` | NEW — 证据详情抽屉(claim snapshot/论文/coverage/reviewer 决策/passages + 回滚) |
| `frontend/src/pages/data-center/EvidenceReviewModal.tsx` | import/JSX `AttachDialog` → `PromotionDialog`(仅 2 行) |
| `frontend/src/styles.css` | 追加 `.evidence-promotion-*` / `.evidence-detail-*` 样式(171 行,纯新增) |

## Implementation Summary

- **布局**:`.evidence-promotion` 三个分组(卡片式 section,带计数徽章):
  - **待晋升**:从 sessionStorage `evidence-center.review-draft.<targetId>` 恢复,**以 T8 实际写入字段为准**(`reviewerDirection`/`reviewerEvidenceLevel`/`reviewerConfidence`/`note`,非简报速记的 direction/evidenceLevel/confidence);条件 = `reviewerDirection` 存在且含 `source_verified` 片段。展示 ClaimPanel(getEvidenceTarget)+ 论文卡 + Reviewer 决策行(方向/等级/置信度/备注/AI 推荐灰字)+ 当前置信度(`dto.current_confidence ?? queue.confidence`)→ 预计晋升后置信度(`attachPaperEvidencePreview`,abortRef 防竞态)。「确认晋升」→ PromotionDialog → `attachPaperEvidence`。
  - **已晋升**:`listPaperEvidence({target_type, target_id, limit: 50})` 过滤 `invalidated_at` 为 null;点击行打开 EvidenceDetailDrawer;抽屉内「回滚」→ ConfirmDialog 输入原因 → `rollbackPaperEvidence(evidenceId, reason)` → 刷新列表(记录移入已失效组)。
  - **已失效**:`invalidated_at` 非空;抽屉只读(无回滚按钮)。
- **晋升动作**:`attachPaperEvidence` body = `{target_type, target_id, pmid, direction, evidence_level, model_direction, model_assessment, reviewer_note, reviewer_confidence, passages[](source_verified: true)}`;成功后:清 sessionStorage draft + 关闭对话框 + `setQueue` 匹配项 status → `completed` + `loadList()` 刷新 + 成功消息。失败保留对话框并显示错误。
- **attach 预览 body** 与 T8/旧模态一致(`source_scope/paragraph_index/passage/direction/reason/confidence/source_locator/source_verified/supported_components`),abort 旧请求(`AbortError` 不报错)。
- **禁止项合规**:无搜索控件 / 无 Europe PMC / 无「确认入库」文案(测试断言)。

## Tests

新增 6 个测试全部通过(`npx vitest run src/pages/evidence-center/modules/EvidencePromotionModule.test.tsx`):
1. 待晋升:draft 渲染 Claim/论文/Reviewer 决策/当前置信度 0.7/预计 0.85(preview mock body 断言含 direction/reviewer_confidence/passages)
2. 「确认晋升」→ PromotionDialog 文案为「确认晋升」(且不含「确认入库」)→ attachPaperEvidence body 断言(evidence_level/direction/reviewer_note/reviewer_confidence/passages)
3. 晋升成功:listPaperEvidence 再次调用(刷新)+ draft 清除(待晋升组消失)
4. 已晋升:行点击打开 EvidenceDetailDrawer;「回滚」→ 原因输入 → `rollbackPaperEvidence('ev-1', '证据不充分')`
5. 已失效:渲染 invalidated 记录(含失效原因),抽屉只读无回滚按钮
6. 禁止项:无检索输入框 / 无 Europe PMC / 无「确认入库」

全量:`npx vitest run` → **10 files / 72 tests passed**;`npm run build`(tsc -b + vite)→ 通过,0 TS 错误(仅预先存在的 chunk-size / dynamic-import 警告)。

## TDD 过程

1. RED:先写 6 个测试,模块不存在 → import 解析失败。
2. GREEN:实现 PromotionDialog(git mv)/EvidenceDetailDrawer/EvidencePromotionModule + CSS → 3/6 通过。
3. 修复 3 处测试自身问题(非实现缺陷):(a) 论文标题在待晋升卡与已晋升行同名 → `getAllByText`;(b)「直接证据」在待晋升决策与抽屉同现 → `getAllByText`;(c) 失效原因与日期同文本节点 → 正则匹配。
4. 实现侧 1 处修正:`attachPaperEvidencePreview` 需传 AbortSignal(与 T8 一致),补充 abortRef 防目标切换竞态。
5. 自审增强:预览失败时显示「置信度预览失败:...」消息(否则对话框确认按钮因 `!preview.allow` 禁用且无反馈,形成死路)。

## Notes / Concerns

1. **模块未接入 `EvidenceCenterPage.tsx`**:与 T6-T8 相同,页内接线由后续任务处理,本任务未触碰该文件(简报文件清单也不含它)。
2. **旧模态文案联动**:EvidenceReviewModal(旧工作台)共用 PromotionDialog,其确认按钮文案由「确认入库」变为「确认晋升」——这是简报明确要求的(git mv 后修复所有引用)。其测试用 `data-testid` 断言,不受影响;`STEPS` 数组中的「确认入库」步骤标签与对话框无关,保留。
3. **预览失败即不可晋升**:与旧逻辑一致(attach 需 preview.allow),失败时有消息提示,无死路。
4. **待晋升为单草稿**:draft 按 targetId 存储,同一时间仅恢复当前 target 的草稿;晋升后即清除,与 T8 的「保存草稿」流程闭环。

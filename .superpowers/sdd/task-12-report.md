# Task 12 Report: 样式 + 全量验收

**Status: DONE_WITH_CONCERNS**

## Step 1: CSS 核对(前序 agent 已追加,逐字一致,无需修正)

`frontend/src/styles.css` 末尾的六组 CSS(`.evidence-task-card-title`、`.evidence-task-card-meta`、`.evidence-task-card-confidence`、`.evidence-task-card-remark`、`.evidence-task-filter-chips`、`.evidence-left-hint` + 注释行 `/* ── 佐证任务对象卡(一对一)── */`)经程序化 diff 与 brief 逐字比对:

```
$ awk '/佐证任务对象卡/{found=1} found' frontend/src/styles.css > /tmp/actual_css.txt
$ diff /tmp/brief_css.txt /tmp/actual_css.txt
CSS MATCHES BRIEF VERBATIM
```

零差异,无需修正。

## Step 2: 前端全量 vitest

```
Run 1 (full):  Test Files 2 failed | 33 passed (35); Tests 2 failed | 311 passed | 1 skipped (314)
Run 2 (full):  Test Files 1 failed | 34 passed (35); Tests 1 failed | 312 passed | 1 skipped (314)
```

- **EvidencePromotionModule.test.tsx**(已知间歇失败):Run 1 失败(`pi-current` 显示 '—' 而非 '0.70',与已知的 `pi-promote-btn` 缺失同类的时序竞态);Run 2 通过;单独运行 3/3 通过。**确认为既有间歇失败(~1/4 概率),与本改造无关**。
- **EvidenceCandidatesErrorState.test.tsx**(确定性失败,3/3 单跑复现):唯一失败用例「返回任务:清 target 保留 taskId」,现象与根因:
  - 测试 `setupHash(true)` 生成 URL `#/validation-center?tab=paper_evidence&task_id=t1&target_type=connection&target_id=c1`,**缺 `module=candidates` 参数**;`parseEvidenceUrl`(evidenceCenterUrl.ts)无 `module` 参数时默认 `module='tasks'`,页面只渲染 EvidenceTasksModule,EvidenceCandidatesModule 永不挂载 → `evidence-target-not-found` 面板永远不会出现,waitFor 超时。
  - 该测试文件为 **untracked WIP**(2026-08-14 13:13 创建,非本次任务产物);同文件其余用例用 `module=candidates` 的 URL 或直接渲染模块,全部通过;Task 11 报告仅跑了 2 个测试文件,全量从未验证过,此测试从未通过。
  - **判定:既存 WIP 测试缺陷(用例设置与路由语义自相矛盾),非 Task 12 引入**(Task 12 仅改 styles.css,不影响 DOM/路由),按指示不扩大修改范围,未改动该文件。

## Step 3: 前端构建

```
npm run build → ✓ built in 2.55s,0 TypeScript 错误
```

仅有既存的 chunk 体积/动态导入警告(非错误)。

## Step 4: 后端全量回归

```
7 failed, 1451 passed, 9 skipped in 17.18s
```

7 个失败用例逐一分析(用独立 worktree 在 HEAD 4150b42 复跑基线):

| 失败用例 | HEAD 基线 | 判定 |
|---|---|---|
| test_circuit_pack_field_coverage::test_build_circuit_orm_covers_datacenter_fields | 同样失败 | 既有失败,与佐证改造无关 |
| test_llm_circuit_projection_extraction::test_normalize_max_projections | 同样失败 | 既有失败,无关 |
| test_llm_composite_workflow::test_circuit_workflow_96_candidates_no_scope_typeerror | 同样 ERROR(collection) | 既有失败,无关 |
| test_llm_projection_circuit_extraction::test_api_too_many_projections | 同样失败 | 既有失败,无关 |
| test_llm_projection_circuit_extraction::test_max_circuits_truncation | 同样失败 | 既有失败,无关 |
| test_paper_evidence_work_status::test_task_list_no_n1_for_missing_summary | 文件不存在(untracked WIP) | 佐证域新测试,状态依赖失败(见下) |
| test_symptom_query::test_graph_returns_circuit_owned_region_graph | 无法 import(引用 WIP 符号) | 既有 WIP 行为差异(4 nodes vs 3),与佐证改造无关 |

**work_status N+1 用例根因**(佐证域、与本改造相关但非 Task 12 引入):
- 测试期望 `list_paper_evidence_tasks` 恰好 3 个 SELECT(列表 + COUNT + 缺失 summary 的一次性批量聚合),实测 5 个。SELECT 追踪显示额外的 2 个为:mirror 实时行批量查询 + task_items 快照批量查询(`_enrich_task_display`,paper_evidence_service.py:3954)。
- 触发条件:测试 DB 中现存 **233 个任务,198 个带 target_id,141 个带 target_id 且缺 summary.counts**(b7d33a9 的 1:1 拆分迁移为历史任务回填了 target_id 后,这些任务落入 enrich 路径),而测试假设 DB 只有自己建的 4 个 NULL-target_id 任务。Task 5 报告(08-14)记录该测试曾 25 passed——当时 DB 无此类遗留任务。属**共享测试库状态依赖的既有 WIP 问题**。

## Step 5: curl API 验收(后端已重启并保持运行)

`GET http://127.0.0.1:8002/api/ontology/evidence/batch?limit=5` 返回任务带全部改造字段(摘录首条):

```json
{
  "id": "688fba6f-...", "target_type": "connection",
  "target_id": "046acd5a-e04d-4c97-b34c-0a5fb774945d",
  "status": "completed", "work_status": "awaiting_review",
  "item_counts": {"total":1,"processing":0,"pending":0,"awaiting_review":1,...},
  "capabilities": {"can_continue_review":true,...},
  "display_name_cn": "初级躯体感觉区，上肢，第6a层 → 斜方体",
  "display_name_en": "Primary somatosensory area, upper limb, layer 6a → trapezoid body",
  "display_confidence": 0.0,
  "display_name_source": "mirror_live", "display_confidence_source": "mirror_live"
}
```

`target_id` / `display_name_cn` / `display_name_en` / `display_confidence` 齐备。前端 dev server (http://localhost:5173,HTTP 200)与后端均已重启,**验收完成后保持运行**供用户使用。

## Step 6: Commit

```
da1ae80 style(evidence-ui): object task card + filter chips + left hint styles
(frontend/src/styles.css,1 file changed,375 insertions(+),3 deletions(-);按指示整文件提交,含会话前既有 CSS WIP,未做 hunk 拆分)
```

## Concerns

1. **EvidenceCandidatesErrorState.test.tsx「返回任务」用例(untracked WIP)确定性失败**:初始 URL 缺 `module=candidates`,任务路由落在 tasks 模块,candidates 面板永不挂载。建议由佐证改造前序任务(9-11)负责人修正 `setupHash(true)` 补 `module=candidates`,或按三.5 语义调整用例。
2. **test_paper_evidence_work_status::test_task_list_no_n1_for_missing_summary 状态依赖失败**:共享测试库中 141 个带 target_id 且缺 summary.counts 的遗留任务触发 enrich 额外 2 SELECT。建议测试改为仅断言自身 4 个任务路径,或清理遗留任务。
3. **5 个 circuit pack/projection 相关用例与 symptom_query 1 例在 HEAD 即失败**,属本分支既有失败,建议后续另行排查(与本改造无关)。
4. 前端手目视验收(卡片标题/排序/跳转/批量创建消息)留给用户,两个 dev 服务已在后台运行。

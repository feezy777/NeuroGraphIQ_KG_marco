# Task NN-7 Report: 前端任务卡徽章 + 证据佐证页提示条(非神经靶标治理的展示层)

**Status:** DONE_WITH_CONCERNS
**Commit:** `25a21a6` feat(evidence-ui): structurally-impossible badge on task cards + banner on evidence page

## 数据通路确认结果(Step 1)

| 数据源 | preprocess_outcome 状态 |
|--------|--------------------------|
| item 类型 `PaperEvidenceTaskItem`(frontend/src/api/endpoints.ts:5623) | ✅ 已有 `preprocess_outcome: string \| null` |
| item 列表接口 `list_paper_evidence_task_items`(backend service ~L4292-4393) | ✅ 已暴露 |
| 任务类型 `PaperEvidenceTask`(endpoints.ts:5677) | ❌ 缺失 → **已补**(`preprocess_outcome: string \| null`) |
| 任务列表接口 `list_paper_evidence_tasks` → `_enrich_task_display` | ❌ 缺失 → **已补**(见下) |

**后端补齐**(`backend/app/services/paper_evidence_service.py` `_enrich_task_display`,唯一改动点):
- snap 查询(DISTINCT ON task_id 那条)SELECT 追加 `preprocess_outcome` 列;
- snap dict 输出 `"preprocess_outcome": r[5]`;
- 任务字典输出追加 `"preprocess_outcome": snap.get(t["id"], {}).get("preprocess_outcome")`(旧任务无 item 时为 None,兼容)。

任务列表接口未返回 `preprocess_outcome` 确认成立(brief Step 1 的假设正确),故按 brief 补齐。未改 `get_batch_task` 详情(其 items 查询本就带该列,任务级输出同样经 snap 兜底,现一并受益)。

## TDD Evidence

- **RED 1**(徽章):`EvidenceTasksModule.test.tsx` 新用例「非神经靶标任务卡显示结构性不存在徽章」——`getByText(/结构性不存在/)` 失败(卡片渲染但无徽章)。1 failed / 10 passed。
- **RED 2**(提示条):`EvidenceCandidatesModule.test.tsx` 新用例「非神经靶标对象:提示条替代候选工作区」——`findByTestId('evidence-non-neural-banner')` 失败。1 failed / 29 passed / 1 skipped。
- **GREEN**:3 个目标测试文件全过(65 passed / 1 skipped);tsc 0 错误;build 成功。后端 `test_paper_evidence_task_display.py` 5 passed(含新增 `test_list_tasks_exposes_preprocess_outcome`);相关 `work_status/rescore/review_linkage` 55 passed。

## 实现清单(brief 代码块逐字)

1. `taskStatus.ts`:`PREPROCESS_OUTCOME_LABELS`(non_neural_target / evidence_negated / no_evidence_found 三标签,逐字)。
2. `EvidenceTasksModule.tsx` TaskCard:meta 行后渲染 `evidence-task-chip evidence-task-chip-bad` 徽章(`non_neural_target` || `evidence_negated` 时),`data-testid=evidence-task-outcome-{id}`。
3. `EvidenceCandidatesModule.tsx`:新增 `const nonNeuralTarget = current?.preprocess_outcome === 'non_neural_target'`;**在外层条件分支**(`evidencePaper ? ... : nonNeuralTarget ? banner : workspace`)替代**整个候选工作区**(检索区 + 状态条 + 提取进度 + 候选列表),渲染 `ontology-page-message evidence-non-neural-banner` 提示条。brief 给出了两个插入点选项(PaperSearchPanel 前拦截 或 外层条件分支),我选外层分支以落实「替代候选工作区」的完整语义——非神经靶标对象无检索/提取/审核意义,整块工作区替换为提示条。
4. `styles.css`:`evidence-non-neural-banner { margin-bottom: 12px; }`(`evidence-task-chip-bad` 样式已存在,复用)。
5. 数据通路:`endpoints.ts` `PaperEvidenceTask` + 后端 `_enrich_task_display`(如上)。

## 测试 / Build 输出

- `npx vitest run EvidenceTasksModule.test.tsx EvidenceCandidatesModule.test.tsx EvidenceCenterPage.test.tsx` → **3 passed, 65 passed | 1 skipped**
- `npx tsc --noEmit -p tsconfig.json` → 0 错误
- `npm run build` → ✓ built in 2.47s(chunk size 警告为既有,非错误)
- 后端:`pytest tests/test_paper_evidence_task_display.py` → 5 passed;`work_status/rescore/review_linkage` → 55 passed
- 全量前端套件:33/34 文件过,1 failed——**非本任务引入**(见 Concerns)

## Concerns / 偏差

1. **既有失败测试(与本任务无关)**:`frontend/src/pages/evidence-center/EvidenceCandidatesErrorState.test.tsx`「返回任务:清 target 保留 taskId」在基线(暂存本任务改动后)同样失败——该文件是前序任务未提交的新文件,URL 回写行为与断言不符。已通过 `git stash push`(仅本任务路径)+ 重跑 + `stash pop` 验证与我的改动无关。未修复(不在本任务范围),建议后续任务处理。
2. **偏差说明(按意图实现)**:brief 提示条伪代码为三层三元(banner / 原候选工作区 / 原空态),真实 JSX 中 `manualTarget` 由 `current` 派生(`current` 存在即非 null),「原空态」分支不存在,故实现为 `nonNeuralTarget ? banner : workspace` 两层分支,语义等价。
3. **提交范围**:9 个文件 = brief 点名的 6 个 + Step 1 数据通路 3 个(前端类型、后端服务、后端测试)。其余工作区既有未提交改动未触碰。
4. 徽章文案与 brief 一致(「结构性不存在:靶标为非神经结构」);`no_evidence_found` 在标签表中但按 brief 不渲染徽章(仅 non_neural_target / evidence_negated 触发)。

## Commit

`25a21a6` feat(evidence-ui): structurally-impossible badge on task cards + banner on evidence page(9 files, +74/-5)

# 终审修复报告:佐证任务一对一 — 深链跳转 + busy 状态清单

Branch: `codex/ontology-evidence` | Commit: `bef134b` | Date: 2026-08-17

## 改动明细

### Fix 1 (Important):module=tasks 携带 target 参数时跳转佐证页

1. **`frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`**
   - React import 恢复 `useEffect`(`import { useEffect, useMemo, useState } from 'react'`);
   - 恢复 `import { useEvidenceCenter } from '../EvidenceCenterContext'`,组件内取 `const { state } = useEvidenceCenter()`;
   - 新增深链 effect:模块为 tasks 且带 targetType/targetId 时,等价于卡片点击调用 `navigateToEvidenceCandidates`(复用 `jumpToCandidates` 的对象拼装逻辑:label 取 `display_name_cn ?? display_name_en`,confidence 取 `display_confidence`),跳转到 candidates 佐证页。

2. **`frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`** — 防回弹:
   - `gotoModule` 改为:切到 `tasks` 时清空 `taskId/taskItemId/targetType/targetId/paperId`(与 `closeTask` 语义一致),否则切到 tasks 列表后上面的深链 effect 会因残留 target 立刻弹回佐证页。

3. **`frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`** — describe 内追加两个用例(复用 `setupDefaultMocks`):
   - 「tasks 深链带 target 参数 → 自动跳转 candidates(右栏点击兼容)」:hash `#/evidence-center?module=tasks&task_id=ta&target_type=connection&target_id=r1-r2` → 断言跳转后 hash 含 `module=candidates`/`task_id=ta`/`target_id=r1-r2`;
   - 「佐证页选中对象后点「佐证任务」导航可回到列表(不回弹)」:hash 为 candidates+target → 点导航按钮 → 断言任务卡片网格渲染、hash 不再含 `target_id=`/`target_type=`/`module=candidates`。

   > **测试断言调整说明**:原定断言 `hash 含 module=tasks` 与页面实际行为不符 —— `buildEvidenceUrl` 有意省略默认模块参数(`module !== 'tasks'` 时才写入,解析时缺省回落 tasks),导航后 hash 实际为 `#/evidence-center`。改为以「任务卡片网格渲染 + target/module=candidates 参数已清空」作为回到列表的断言,语义不变(用户确实回到 tasks 列表且不回弹)。

### Fix 2 (Minor fix-now):busy 去重状态清单补齐 v2 处理器中间状态

- **`backend/app/services/paper_evidence_service.py`**(约 5809 行,`create_batch_task` 的 busy 查询):
  - `status IN ('pending','searching','paper_found','extracting','awaiting_review')`
  - → `status IN ('pending','searching','fetching','retrieving','paper_found','verifying','extracting','awaiting_review')`
  - grep 确认该清单全文件仅此一处(`_set_item_stage` 的 v2 中间状态 'fetching'/'retrieving'/'verifying' 与本文件 3625/6918 行的既有清单一致),只改了 create_batch_task 这一处。

## 验证结果

### 1. 前端单测

```
cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx
Test Files  2 passed (2)
Tests       34 passed (34)   ← 含新增 2 例
```

### 2. 前端构建

```
cd frontend && npm run build
✓ built in 2.47s   ← 0 错误(仅有既存 chunk 体积 / dynamic import 提示)
```

### 3. 后端测试

```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q
15 passed in 4.14s
```

## 提交

- SHA: `bef134b`
- Subject: `fix(evidence): tasks deep-link redirect to candidates; busy-check covers v2 in-flight stages`
- 文件:4 个(EvidenceTasksModule.tsx、EvidenceCenterContext.tsx、EvidenceCenterPage.test.tsx、paper_evidence_service.py),171 insertions / 18 deletions。

## 披露

- **`EvidenceCenterContext.tsx` 携带既有未提交改动**:该文件在本修复前已有本分支 T10/T11 阶段的未提交工作(embedded/`#/validation-center` 支持、`openTaskTarget`/`closeTarget`/`backfillTaskItem`、candidatePassages 等右栏状态),不属于本修复。按指令未动它们,`git add <具体文件>` 整文件提交,已并入 commit `bef134b`。
- 其余工作区未提交改动(.superpowers/sdd/*、.claude/settings.local.json 及分支上其他进行中的 feature 文件)未触碰、未提交。
- 构建产物 dist/ 未被跟踪,无影响。

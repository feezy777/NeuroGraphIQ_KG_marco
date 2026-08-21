# Task 2 Report: 物理迁移 evidence-workbench 组件到 evidence-center/components

**Status:** DONE
**Commit:** `498d59e` refactor(evidence): 迁移 evidence-workbench 组件到 evidence-center/components

## 移动清单（git mv，8 个文件）

`frontend/src/pages/data-center/evidence-workbench/` → `frontend/src/pages/evidence-center/components/`

| 文件 | git rename 相似度 |
|------|-------------------|
| ClaimPanel.tsx | 100% |
| PassageEvidenceCard.tsx | 88% (移动前已有未提交改动) |
| CoveragePanel.tsx | 100% |
| ReviewerPanel.tsx | 100% |
| AttachDialog.tsx | 100% |
| CreateBatchTaskDialog.tsx | 89% (移动前已有未提交改动) |
| claimCoverage.ts | 100% |
| types.ts | 83% (移动前已有未提交改动) |

旧目录 `data-center/evidence-workbench/` 已空，git 无残留跟踪。

## Import 修复明细（4 个消费方文件，11 行 import）

被移动文件内部 import 检查结论：全部无需改动——
- `./types` 相对引用：移动后仍在同目录，不变（claimCoverage.ts / AttachDialog / ClaimPanel / CoveragePanel / PassageEvidenceCard / ReviewerPanel）
- `../../../api/endpoints`：`pages/evidence-center/components/` → `src/api/` 深度与原来相同（3 层），不变（AttachDialog / CreateBatchTaskDialog / ReviewerPanel）

消费方 import 修改：

| 文件 | 修改 |
|------|------|
| `frontend/src/pages/data-center/EvidenceReviewModal.tsx` | 7 处 `./evidence-workbench/X` → `../evidence-center/components/X`（AttachDialog / ClaimPanel / CoveragePanel / PassageEvidenceCard / ReviewerPanel / claimCoverage / types） |
| `frontend/src/pages/data-center/MirrorKgPanel.tsx` | `./evidence-workbench/CreateBatchTaskDialog` → `../evidence-center/components/CreateBatchTaskDialog` |
| `frontend/src/pages/data-center/PaperEvidenceColumn.tsx` | 2 处 `./evidence-workbench/...` → `../evidence-center/components/...`（claimCoverage / types） |
| `frontend/src/pages/BackgroundTaskCenter.tsx` | `./data-center/evidence-workbench/CreateBatchTaskDialog` → `./evidence-center/components/CreateBatchTaskDialog` |

grep `evidence-workbench` 全 `src/` 目录确认零残留文件路径引用。仅剩 2 处**非路径**引用，有意保留：
- `frontend/src/styles.css:11289` `.evidence-workbench {`（CSS 类名）
- `frontend/src/pages/data-center/EvidenceReviewModal.tsx:901` `className="evidence-workbench"`（对应 CSS 类）

## 测试结果

```
npx vitest run src/pages/data-center/EvidenceReviewModal.test.tsx
Test Files  1 passed (1)
Tests       24 passed (24)
Duration    3.02s
```

24/24 通过，行为无损。

## Build 结果

`npm run build` → `✓ built in 2.40s`，TypeScript 0 错误。
仅有与本次迁移无关的既有警告（endpoints.ts 动态/静态混合导入 chunk 提示、chunk > 500kB 提示）。

## Self-review 发现

1. git rename 检测：5 个文件 100% 相似（纯移动），3 个文件 83-89%（移动前工作区已有未提交改动，内容随移动原样保留，无丢失）。
2. 测试文件 `EvidenceReviewModal.test.tsx` 只 import `./EvidenceReviewModal`，不直接引用被移动模块，无需修改。
3. 无其他测试文件引用 `evidence-workbench` 路径。
4. Commit 只含 12 个迁移相关文件（8 移动 + 4 消费方），未使用 `git add -A`；工作区其他 ~80 个无关未提交改动保持未暂存。
5. 注：EvidenceReviewModal.tsx / CreateBatchTaskDialog.tsx / PassageEvidenceCard.tsx / types.ts 移动前即存在未提交改动，这些改动与本次迁移一并进入 commit（文件级 staging，无法只暂存其中几行；属任务允许范围）。

## Concerns

- 无阻塞性问题。仅提示：移动前已存在的未提交改动（见 self-review #5）随文件一起进入 commit，如需与迁移拆分需在后续用 `git log -p` 复核。

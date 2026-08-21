# Task 11 Report: 清理与全量回归

## Status: ✅ 完成

## 提交

- `1c48f87` refactor(evidence-center): 清理旧 evidence-workbench 目录(1 file changed, 90 deletions)

## 残留检查结果(全部符合预期)

| 检查项 | 结果 |
|--------|------|
| `grep -rn "evidence-workbench" frontend/src` | 仅 `styles.css:11289` 的 CSS 类名 `.evidence-workbench`(预期保留,非路径引用) |
| `from.*data-center/evidence-workbench` 导入 | 无匹配 |
| `EvidenceReviewModal` 引用 | 仅剩兼容壳 `EvidenceReviewModal.tsx` + 其测试 `EvidenceReviewModal.test.tsx` + `noNativeDialogs.test.ts` 列表项 + `candidatePassages.ts` 注释(符合预期) |
| `ReviewerPanel` 引用 | 无任何 import;仅 `ReviewerDecisionPanel.tsx` / `ConfidencePreview.tsx` 的迁移来源注释(非引用) |
| `neurographiq.evidenceWorkbench.queue.v1` (STORAGE_KEY) | 无匹配(已随 T10 删除) |
| `git ls-files evidence-workbench/` | 空目录,git 无残留文件,无需 `git rm -r` |
| 后端残留 `evidence-workbench` | 无匹配 |
| `PaperEvidencePanel.tsx` 引用 | 仅 import `../../api/endpoints`,不引用 workbench 组件,无需修改 |
| 大小写不敏感 `evidenceWorkbench` | 仅 `onOpenEvidenceWorkbench` 回调 prop 名(T10 已改为直接跳转 evidence-center,导航语义,非路径引用) |

## 清理动作

1. **`ReviewerPanel.tsx` 删除**(`git rm frontend/src/pages/evidence-center/components/ReviewerPanel.tsx`):
   - 旧人工审核面板,唯一消费方 EvidenceReviewModal 已改为跳转壳;新模块用 `ReviewerDecisionPanel` + `ConfidencePreview`
   - 删除前全库 grep 确认零 import(仅两处迁移来源注释,无需改动)
2. **空目录 `frontend/src/pages/data-center/evidence-workbench/` 移除**(`rmdir`):
   - 该目录已无 git 跟踪文件(组件均已 git mv 至 evidence-center),仅清理文件系统
3. 无其他残留引用需处理;`PaperEvidencePanel.tsx` 无需修改

## 全量回归

### 前端

- `npx vitest run`: **10 个文件 / 62 个测试全部通过**(与期望 62 一致)
- `npm run build`: **通过**(2324 modules,built in 2.35s;仅既有 chunk 体积与 dynamic-import warning,非错误)

### 后端

- `.venv/Scripts/python.exe -m pytest tests/test_paper_evidence*.py tests/test_paper_library_api.py tests/test_paper_retrieval_phase2.py -q`: **98 passed, 4 warnings in 3.71s**(warnings 为 FastAPI on_event 弃用与 mock coroutine 未 await 的既有告警,不影响通过)

## Concerns / 备注

1. **工作区仍有 58 个文件未提交**(LLM 提取/字段补全/validation-center 等另一条工作流线的修改,gitStatus 快照中即存在)。本次按要求只 `git add` 清理相关文件,未纳入提交;提交用 `git commit -m`(非 `-am`)避免误收。
2. `.evidence-workbench` CSS 类保留在 styles.css(任务要求),属死样式但无害;如需可后续单独清理。
3. 后端 4 个 warning 均为既有告警(测试文件 `test_paper_evidence_m2.py` 的 mock coroutine 未 await),非本次引入。

## 相关文件

- 删除:`frontend/src/pages/evidence-center/components/ReviewerPanel.tsx`(git rm,90 行)
- 文件系统清理:`frontend/src/pages/data-center/evidence-workbench/`(空目录 rmdir,无 git 影响)

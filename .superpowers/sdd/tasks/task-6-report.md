# Task 6 Report: 论文库模块(PaperLibraryModule + PaperCard + PaperDetailDrawer)

## Status: DONE

## Commit

- `55e0cb6` feat(evidence): 论文库模块 PaperLibraryModule + PaperCard + PaperDetailDrawer
- Staged only task files (6 files, 789 insertions):
  - `frontend/src/api/endpoints.ts` (modified)
  - `frontend/src/styles.css` (modified)
  - `frontend/src/pages/evidence-center/modules/PaperLibraryModule.tsx` (new)
  - `frontend/src/pages/evidence-center/modules/PaperLibraryModule.test.tsx` (new)
  - `frontend/src/pages/evidence-center/components/PaperCard.tsx` (new)
  - `frontend/src/pages/evidence-center/components/PaperDetailDrawer.tsx` (new)

## TDD Flow

1. Wrote `PaperLibraryModule.test.tsx` first → ran → RED (module import failed, 1 failed file / no tests).
2. Implemented endpoints + 3 components + styles → re-ran → GREEN (6/6).

## What Was Built

- **endpoints.ts**: `EvidencePaperItem` / `EvidencePaperParagraph` / `EvidencePaperDetail` interfaces + `listEvidencePapers(p?)` (GET `/api/ontology/evidence/papers`) + `getEvidencePaperDetail(paperId)` (GET `/api/ontology/evidence/papers/{id}`), per brief code verbatim. Field names verified against backend `paper_evidence_service.list_papers` / `get_paper_detail` (id/pmid/pmcid/doi/title/journal/publication_year/is_oa/abstract_available/fulltext_available/paragraph_count/evidence_count; detail → paper/paragraphs[{paragraph_id, section_title, paragraph_index, passage_text, source_scope}]/evidence_count/targets[{target_type, target_id}]).
- **PaperLibraryModule.tsx**: search bar (搜索 input + 仅开放获取 checkbox + 年份 select(2015–当前年) + 已解析全文 checkbox + 搜索按钮, form submit 支持 Enter)、分页列表(上一页/下一页 + 第 x / y 页 · 共 N 篇)、loading/error/empty 状态、`selectedPaperId` state → PaperDetailDrawer。过滤参数在点击搜索时一次性携带重新请求并重置页码。
- **PaperCard.tsx**: 整卡可点(button);title 加粗、`journal (year)`、PMID/PMCID/DOI 独立 chip、OA / 摘要可用 / 全文可用徽章、段落数(`12 段`)、证据数(`3 条证据`)。
- **PaperDetailDrawer.tsx**: 右侧抽屉(`evidence-drawer-overlay` + `evidence-drawer`,点击遮罩/×关闭,内部点击不冒泡);metadata 网格(期刊/PMID/PMCID/DOI/关联证据 N 条);摘要段落默认展开;全文段落按 section_title 分组折叠(点击头部展开/收起);targets 列表 chip 点击 → `useEvidenceCenter().openTarget(target_type, target_id)`(跳转 candidates 模块)。fetch 带 cancelled flag 防竞态。
- **styles.css**: 追加 `.paper-*` + `.evidence-drawer-*` 样式,复用 `--primary`/`--white`/`--border`/`--card-radius`/`--shadow`/`--text`/`--text-muted`/`--danger` 变量,与 T5 医学蓝风格一致(O 徽章绿色、可用徽章蓝色)。

## Forbidden Items (verified)

- 论文库模块与抽屉均不渲染 Reviewer Confidence / Coverage / Attach / Reviewer Direction / 确认晋升 任何控件或文案;测试以 `queryByText(/确认晋升|Reviewer|Coverage|Attach/i)` 为 null 断言(列表与抽屉两处)。

## Test Summary

- `npx vitest run src/pages/evidence-center/modules/PaperLibraryModule.test.tsx` → 6 passed:
  1. 列表渲染 title/journal(年份)/OA 徽章/摘要可用/全文可用/段落数/证据数/PMID/DOI + 禁止项 null
  2. 搜索+OA+年份+已解析全文 → `listEvidencePapers` 携带 `{search, oa, year, has_fulltext, page:1}` 重新请求;清空搜索重置页码
  3. 点击卡片 → `getEvidencePaperDetail('p1')`;抽屉显示 metadata 行 + abstract 段落(默认展开)+ section 标题(默认折叠,段落隐藏,点击展开后可见)+ 关联证据数 + targets
  4. 点击 target chip → hash 含 `module=candidates&target_type=connection&target_id=conn-1`
  5. 分页:第 1 页上一页禁用 → 下一页请求 page:2 → 下一页禁用 → 上一页回 page:1
  6. 加载失败显示错误 + 重试成功
- 全量 `npx vitest run` → 7 files / 49 tests all passed(无回归,EvidenceCenterPage 测试不受影响)。
- `npm run build`(`tsc -b && vite build`)→ 通过(chunk 大小警告为既有问题,与本次改动无关)。

## Concerns / Notes

- **未接线 EvidenceCenterPage**: task 文件清单不含 `EvidenceCenterPage.tsx`,且提示只提交指定文件,故 `module=papers` 暂未渲染该模块(页面注释 "Task 6-9 接入" 留给集成步骤)。已将模块内 fallback 提示文案改为与页面 MODULE_HINT 不同的文本(`管理系统已获取的真实论文资源,点击卡片查看摘要与全文。`),避免将来接线后 `getByText` 重复元素断言冲突。
- 年份下拉范围 2015–当前年(2026),为展示用固定范围,后端仅支持精确 `publication_year = :yr` 匹配(无范围查询)。
- `listEvidencePapers` 参数类型按 brief 为 `Record<string, string | number | boolean | undefined>`,与 `getJson` 的 QueryParams 兼容;空值(undefined/'')由 client.buildUrl 自动剔除。
- 抽屉 meta 值如 `Nature Neuroscience (2023)` 与卡片文本重复,测试用 `getAllByText(...).length >= 2` 与抽屉独有 label(期刊/PMID/DOI/关联证据)断言结构。

## Verification

- [x] 单测 6/6 通过
- [x] 全量 vitest 49/49 通过
- [x] `npm run build`(含 tsc -b)通过
- [x] 只 commit 任务文件(git status 其余改动未触碰)

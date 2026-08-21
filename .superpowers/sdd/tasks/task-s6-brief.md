### Task S6: 全量回归

**Files:** 无新增
**行为:** 前端 `npx vitest run` 全绿 + `npm run build`;后端 `pytest tests/test_paper_evidence*.py tests/test_paper_library_api.py tests/test_paper_retrieval_phase2.py -q` 全绿;确认 EvidenceReviewModal 仍为跳转壳(无业务 UI);确认 review_approved 状态在刷新后保留(sessionStorage)

**提交:** 如无修复则不提交;有修复则单独 commit

---


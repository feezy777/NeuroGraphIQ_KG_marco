# Task 8 报告:全量验收(非神经靶标治理 + 自动反向检索收尾)

日期:2026-08-19
分支:`codex/ontology-evidence`
状态:**DONE** 附 1 个冒烟修复提交

---

## 1. 后端全量

命令:`cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q`

结果:**6 failed, 1478 passed, 9 skipped, 32 warnings in 31.87s**

失败用例(全部为已知既有基线失败,与本改造无关):

| 用例 | 类型 |
|------|------|
| `test_circuit_pack_field_coverage.py::test_build_circuit_orm_covers_datacenter_fields` | 既有(circuit) |
| `test_llm_circuit_projection_extraction.py::test_normalize_max_projections` | 既有(circuit) |
| `test_llm_composite_workflow.py::test_circuit_workflow_96_candidates_no_scope_typeerror` | 既有(circuit) |
| `test_llm_projection_circuit_extraction.py::test_api_too_many_projections` | 既有(circuit) |
| `test_llm_projection_circuit_extraction.py::test_max_circuits_truncation` | 既有(circuit) |
| `test_symptom_query.py::test_graph_returns_circuit_owned_region_graph` | 既有(symptom_query) |

与 Brief 预期完全一致(5 个 circuit + 1 个 symptom_query)。全部佐证/非神经靶标/反向检索相关用例通过。

补充:修复提交后重点回归证据相关测试文件(含反向检索、非神经靶标分类器、查询构造),**21 passed in 5.19s**。

## 2. 前端全量 + 构建

- 单元测试:`npx vitest run` → **Test Files 1 failed | 33 passed (34);Tests 1 failed | 314 passed | 1 skipped (316)**
  - 唯一失败:`EvidenceCandidatesErrorState.test.tsx`「返回任务」用例(既有 untracked WIP,允许存在)。
- 构建:`npm run build` → **成功,0 错误**(仅既有 chunk 体积与动态/静态混合导入警告,非错误)。

## 3. 端到端冒烟

### 3.1 服务状态

- 后端:重启(`run_server.py` 后台)加载 NN-T1~7 最新代码,`GET /api/health` → `{"status":"ok","database":{"connected":true,...}}`。
- 前端 dev server:`http://localhost:5173` 返回 200,保持运行。

### 3.2 任务列表 preprocess_outcome 字段

`GET /api/ontology/evidence/batch?limit=5&granularity_level=macro` → 任务均带 `preprocess_outcome` 字段(当前为 `no_evidence_found`,来自反向检索自动第二轮)。

### 3.3 非神经靶标验证(真实数据,无需造数)

库中存在真实非神经靶标任务(连接 `cb61dd86…`,`X -> ventricle`):
- 批量列表:`preprocess_outcome='non_neural_target'` 正确返回;
- 任务详情:`GET /api/ontology/evidence/batch/cb61dd86…` 返回 task + counts;
- items:`GET .../items` 返回 item 带 `preprocess_outcome='non_neural_target'`、`status=pending`(不自动检索)。

该真实任务在冒烟期间未被触碰(仍为 paused / item pending),真实数据零污染。

### 3.4 反向检索端到端(造临时数据验证 + 清理)

**问题发现**:Brief 要求「后端日志出现 negative query」,但代码中反向检索轮无任何日志输出(该功能仅通过 DB 状态可观察)。定位后修复(见第 4 节)。

**造数据验证过程**(全部用临时 UUID,验证后清理):
1. 临时插入 1 条合成 mirror 连接(`cef139a7…`,源/靶区名 "Qztrx zone 7alpha" / "Wvbnm zone 9zeta",满足表 CHECK 约束)。
2. 预验证:构造查询经真实 Europe PMC `search_papers` 命中 0。
3. 创建单对象任务(`POST /api/ontology/evidence/batch`,mode=existence,auto_started):正向检索 0 → 宽查询 0 → **反向检索轮触发** → 负向查询亦 0 → item 进入 `awaiting_review`,`preprocess_outcome='no_evidence_found'`,`last_error_code='EUROPE_PMC_NO_RESULT'`。
4. 修复后重启后端再次验证,后端日志出现:
   ```
   [evidence] negative round: item=627caf8c… target=cef139a7… hits=0 query=ABSTRACT:"Qztrx zone 7alpha" AND BODY:… AND (ABSTRACT:"no projection" OR ABSTRACT:"does not connect" OR …)
   ```
   (反向轮执行与负向查询 OR 组确认可见。)
5. 中间产物说明:首次尝试用真实连接(`Supplemental somatosensory area…`)触发反向轮,因 `search_papers` 的 plain-fallback 命中文献进入 extracting,已 cancel 并清理,未消耗额外 LLM 调用。

**清理确认**:3 个临时任务(含 items、ontology_change_logs 审计行)与 1 条合成 mirror 行全部删除;`name='smoke-negative-search-tmp'` 剩余 0;合成行剩余 0;无 running/pending 残留任务;真实任务 `cb61dd86…` 状态未变。

### 3.5 清理脚本干跑(不删除)

`scripts/clean_final_non_neural_edges.py` 逻辑干跑(只扫描不 DELETE):
- `final_region_connections` 表存在但当前为 **0 行**(dev 库 final 尚未有晋升数据),干跑输出 `scanned 0 final connections; would delete 0` — 状态一致,无清理目标。

## 4. 修复

**文件**:`backend/app/services/paper_evidence_service.py`(唯一改动文件,+4 行)

反向检索轮触发处增加 INFO 日志(沿用应用内 `uvicorn.error` logger 约定,与 main.py startup 日志一致):

```python
logging.getLogger("uvicorn.error").info(
    "[evidence] negative round: item=%s target=%s hits=%d query=%s",
    item_id, target_id, len(papers), negative_query,
)
```

**Commit**:`89daa8e fix(evidence): smoke-test fixes`(仅含此 1 个文件)。

修复后:证据相关 21 个测试通过;后端全量仍为 1478 passed / 6 既有失败;反向轮日志实机验证出现。

## 5. Concerns

- 无新增 concern。既有已知失败保持原状(后端 6 例基线失败、前端 1 例 WIP 失败、EvidencePromotionModule 间歇失败未在本轮出现)。
- dev 库 final 区为空,清理脚本的「实际删除」路径未经真实数据演练(干跑 0 目标,属预期)。
- 前后端 dev 服务均保持运行(8002 / 5173),供后续人工 UI 验收。

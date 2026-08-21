# Task 6 Report: final_kg 历史脏边清理脚本(非神经靶标连接删除,镜像留痕)

**Status: DONE**

## Deliverable

- Created `backend/scripts/clean_final_non_neural_edges.py` (60 lines, verbatim per brief; imports Task 1's `classify_target` from `app.services.evidence_target_classifier`)
- Commit: `f6605e4` — `feat(evidence): one-off cleanup script for final-KG non-neural-target edges` (1 file changed, 60 insertions; only the script staged)

## Step 2: 干跑统计(只读)

运行 brief 原命令(连接 `final_region_connections` LEFT JOIN `mirror_region_connections`):

```
final connections: 0 | non-neural target (via mirror): 0
```

另用与脚本完全一致的判定逻辑(含 `raw_payload_json` 回退)做只读复算:

```
script-logic dry-run: scanned 0 | doomed(non_neural): 0 | fallback-to-raw rows: 0
```

环境核查(只读):
- 活动库由 `backend/.env` 的 `DATABASE_URL`/`POSTGRES_DB` 决定 = `neurographiq_kg_v3_mvp1_e2e`(`data/runtime/database.local.json` 不存在)。
- 扫描本机全部 9 个 PostgreSQL 数据库:`final_region_connections` 表仅存在于 `neurographiq_kg_v3_mvp1_e2e`,且为 **0 行**(`mirror_region_connections` = 70029 行);其余库(neurographiq_kg_v3_wb 等)均无此表(UndefinedTable)。
- `raw_payload_json` 为 JSONB(migration 025:32),SQLAlchemy 自动反序列化为 dict,脚本回退逻辑有效。

结论:final 库当前没有任何晋升落库数据,故无脏边可删。M=0 符合 brief 预期("若 M=0 也正常,说明 final 库无脏边")。

## Step 3: 实际执行

```
scanned 0 final connections; deleted 0 non-neural-target edges
```

与干跑预测一致,未删除任何行(表中本就无行);镜像数据未受影响。

## Concerns

1. **final 库为空是当前环境事实,不是清理动作的成果**——`final_region_connections` 在本机任何库中均 0 行,晋升链路尚未产出 final 数据。脚本作为防御性一次性工具保留:未来晋升产生脏边后可直接重跑(`scanned N` 会反映真实数量)。
2. 脚本按 brief 逐字实现,未做修改(含 `payload = raw or {}` 依赖 JSONB 反序列化——已核实列类型为 JSONB,无风险)。
3. 工作树其余既有改动文件未触碰、未提交;仅提交脚本文件。

## Report File

`D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\.superpowers\sdd\task-nn-6-report.md`

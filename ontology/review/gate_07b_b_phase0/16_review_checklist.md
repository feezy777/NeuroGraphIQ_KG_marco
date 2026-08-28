# Gate 7B-B Phase 0 — Human Review Checklist

## 审查清单

- [ ] 目标库名冻结为 `neurographiq_human_brain_v1`（主）+ `_e2e`（测试）
- [ ] 旧名 `neurographiq_macro96_v1` 不再作为主库默认值
- [ ] legacy `neurographiq_kg_v3_wb` 未被触碰（34 表 intact）
- [ ] 两个库已创建（bootstrap 幂等，CREATED/ALREADY_EXISTS）
- [ ] `infra` schema + `infra.schema_migrations` 已建
- [ ] 29 个 per-type NGIQ sequence 已建（NO CYCLE）
- [ ] ID 发号 = per-type sequence（禁 MAX+1）
- [ ] migration runner 只处理 `gate7b_*.sql`（忽略 123 legacy）
- [ ] 重复 NNN → 硬失败；checksum 失配 → fail closed
- [ ] 幂等（二次运行 skip）
- [ ] 8 处旧库名引用已切换（config / guard / .env / .env.example / _db_env.ps1 / 3 test 文件）
- [ ] `kg_entities` 及任何科学表均未创建（public tables = 0）
- [ ] 本体 TTL 未修改（hash 不变）
- [ ] 新增 12 个 Phase 0 单测，相关 28 测试全绿
- [ ] 未 commit / 未 push

## 关键决策点（需人工拍板）

1. **库名 `neurographiq_human_brain_v1`**——是否同意？
2. **29 个 per-type sequence**——是否同意？
3. **`gate7b_<NNN>_*` 独立迁移轨道**——是否同意？

## 审查说明

全部通过后回复 **「Gate 7B-B Phase 0 通过」**，方可进入 Phase 1（建 `kg_entities` 及科学表）。

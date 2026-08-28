# Gate 7B-B Phase 0 — NGIQ Sequence Registry

## 1. 来源

29 项前缀注册表：`ontology/review/gate_07b_a1/05_ngiq_prefix_registry.md`。

## 2. 创建的 29 个 sequence

全部 `CREATE SEQUENCE IF NOT EXISTS infra.ngiq_<suffix>_seq START WITH 1 INCREMENT BY 1 NO CYCLE;`

| suffix | 前缀 | suffix | 前缀 |
|---|---|---|---|
| br | NGIQ-BR | atl | NGIQ-ATL |
| cns | NGIQ-CNS | xreg | NGIQ-XREG |
| nbp | NGIQ-NBP | rmap | NGIQ-RMAP |
| con | NGIQ-CON | ccm | NGIQ-CCM |
| cob | NGIQ-COB | crm | NGIQ-CRM |
| cir | NGIQ-CIR | brh | NGIQ-BRH |
| fun | NGIQ-FUN | fhr | NGIQ-FHR |
| nt | NGIQ-NT | bram | NGIQ-BRAM |
| rcp | NGIQ-RCP | ast | NGIQ-AST |
| gen | NGIQ-GEN | pred | NGIQ-PRED |
| dis | NGIQ-DIS | elk | NGIQ-ELK |
| sym | NGIQ-SYM | src | NGIQ-SRC |
| stu | NGIQ-STU | als | NGIQ-ALS |
| pub | NGIQ-PUB | xrf | NGIQ-XRF |
| evi | NGIQ-EVI | | |

## 3. 发号语义

- `nextval()` 只供数值部分；public ID 拼接为 `NGIQ-<TYPE>-<8位数字>`。
- `NO CYCLE`：编号永不复用。
- 并发安全：PostgreSQL sequence 原生保证，杜绝 MAX+1 竞态。

## 4. 实测

```
infra sequences (expect 29): 29
```

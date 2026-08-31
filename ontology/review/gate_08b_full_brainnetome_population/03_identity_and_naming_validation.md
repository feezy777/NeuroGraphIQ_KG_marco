# Gate 8B — Identity & Naming Validation

## 1. Pilot 20 条复用（硬验收）

Full 前后比较 Gate 8A baseline（`_gate8a_baseline.json`）：

- **20/20 BrainRegion NGIQ-BR IDs unchanged**
- **20/20 ExternalRegion NGIQ-XREG IDs unchanged**
- **20/20 canonical names Left/Right 正确**
- xref / alias / source_name_original 不变。

importer 采用 find → validate → reuse（不删除重建、不 truncate、不重新发号）。

## 2. Canonical 唯一性（全量 246）

- name_en duplicate groups = **0**
- name_zh duplicate groups = **0**
- Left/Right 显式进入 canonical name（L→Left/左侧，R→Right/右侧），无 hemisphere mismatch。

## 3. Native identity 保留

- `source_name_original` = native code（SFG_L_7_1 等）完整。
- native alias（atlas_label）= native code，**无 numeric-only 误存 alias**。
- Brainnetome numeric ID → entity_xrefs（external_id，唯一），**无 L1/R2/BNA-L-001 伪造 ID**。

## 4. 22-point anomaly scan（全 0）

missing name_en/name_zh/source_name_original、dup EN/ZH/xref、missing/dup alias、missing/dup mapping、non-exact mapping、method/source/review 偏离、fake similarity/confidence、非 proposed、非 human、非 G3、hemisphere mismatch、unknown anatomy、aggregation、dup NGIQ —— 全部 0。

## 5. 测试

`tests/test_gate8b_full_population.py`（17 用例）：parser=246、无未知解剖、命名确定性、L/R 正确、EN/ZH 唯一、Pilot ID 复用、xref 唯一、alias 保留、exact policy、NULL similarity/confidence、proposed/human/G3-only、246/246 完整、aggregation=0、schema 32/32。全量 regression **183 passed**。

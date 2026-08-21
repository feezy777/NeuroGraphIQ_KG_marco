# Function Ontology Hierarchy（O1.2 稳定设计）

## 核心模型

```
Function Concept      = ontology_terms.id
Function Hierarchy    = ontology_term_relations
Canonical direction   = child --subclass_of--> parent
Graph type            = DAG（多父）
Identity              = term_id
```

## 规则

1. **只存 `subclass_of`**：broader/narrower/has_subclass 由查询方向派生；
   inverse edge 不双写（O2 定义 inverse semantics 之前不做）。
2. **DAG 非 Tree**：child 可有多个 parent（working memory ⊂ memory 且 ⊂ cognitive control）；
   不用 parent_id，depth 查询时计算、不落库。
3. **Status 生命周期**（复用 ontology term 词汇）：
   `proposed`（默认，候选）→ `active`（正式，endpoints 须为 active Function）
   → `rejected` / `deprecated`（不参与有效 DAG）。
4. **Cycle guard**：创建与激活都检查；guard 图 = proposed + active 边
   （rejected/deprecated 排除）；cycle ⟺ parent 沿 parent 链可达 child。
5. **Endpoint 校验**：term 存在、term_type=function、term_code 规则、
   merged → canonical resolve、deprecated 不可作 endpoint。
6. **Merge 传播**：T1→T2 时 hierarchy 边 canonical 重指，duplicate-safe
   （目标边已存在则删除旧边），cycle 再检查。
7. **不投影**：本阶段不写入 mirror_kg_triples（hierarchy 属 TBox，
   mirror_kg_triples 是 Mirror ABox/Domain graph）。
8. **范围**：Brain Region partonomy 不属于本表（Allen structure 层级另行设计）。

## 查询

- parents / children：直接边（含 relation id、status、source、confidence）
- ancestors / descendants：多层遍历，DAG 去重取 minimum depth
- root/leaf：**仅 active hierarchy 参与节点**；isolated_active_terms 单独返回
  （当前真实 2,874 个 active term 未入 hierarchy 时全部计为 isolated）

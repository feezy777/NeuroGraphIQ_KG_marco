# Ontology Center 数据现状审计报告

- **日期**：2026-08-21
- **范围**：NeuroGraphIQ KG V3 本体层（canonical ontology）全面只读审计
- **数据库**：`neurographiq_kg_v3_mvp1_e2e`（backend/.env DATABASE_URL），public schema
- **方法**：SELECT-only 脚本（零 DDL/DML/写入），经 backend venv psycopg 执行
- **审计脚本**：`%TEMP%/ontology_audit.py`、`%TEMP%/ontology_audit2.py`（未入库，可复跑）

---

## 审计结论摘要

| 层 | 规模 | 状态 |
|----|------|------|
| canonical_brain_regions | **682**（全部 human / active） | 健康，层级单一树、零不一致边 |
| canonical_region_hierarchy | **681** 条 part_of 边 | 无环、无孤儿、无粒度倒挂 |
| Atlas 资源 | **1945** 行（4 个 atlas） | BNA/MMP 全映射；Allen 小鼠 1319 行未映射 |
| Cyto/Molecular | 21 细胞类型 / 15 分子实体 | 演示级种子数据，仅覆盖 5–12 个脑区 |
| canonical_connections | **2486** 条，全部 proposed | 端点全 canonical，但只覆盖 51/682 脑区 |
| canonical_circuits | **293** 个，全部 proposed | 成员齐备（715 区 + 100 连接 + 538 功能） |
| ontology_terms | **8189** 个（全 function） | 96% 有中文名 |

**核心判断**：区域本体层（region + hierarchy + atlas 映射）已达可演示质量；连接/回路层数据量充足但**全部处于 proposed 状态且未接入审阅链路**；cyto/molecular 层是种子规模。Ontology Center 下一步应以「区域树为主线、连接/回路为详情与图侧」来展示，并优先补齐演示叙事中的状态面与中文名问题。

---

## 1. canonical_brain_regions — 脑区本体现状

### 1.1 总量与分布

| 维度 | 分布 |
|------|------|
| 总数 | **682** |
| granularity_domain | brain_region_anatomical = 682（唯一值） |
| species | human = 682（唯一值） |
| status | active = 682（无 proposed/deprecated/merged） |
| source_summary 非空 | 682 / 682 |
| external_mappings 非空 | 629 / 682 |

### 1.2 按 granularity_level 分布（BR3 十级词表）

| granularity_level | level_order | 实际数量 | 说明 |
|------------------|-------------|---------|------|
| whole_brain | 0 | **1** | `ng:br:brain` |
| macro | 1 | **4** | cerebrum / diencephalon / brain_stem / cerebellum |
| clinical | 2 | **48** | Macro96 池（含 6 个脑室/CSF/白质） |
| meso | 3 | **609** | HCP-MMP 360 + Brainnetome 246 + 3 curated |
| subregion | 5 | **5** | 海马亚区（CA1/CA2/CA3/DG/Subiculum） |
| fine | 6 | **15** | Brodmann 分区（curated） |
| research | 4 | **0** | — |
| cyto | 7 | **0** | — |
| ultra_fine | 8 | **0** | — |
| molecular | 9 | **0** | — |

> 十级词表在 `ontology_vocabularies`（vocab_type=granularity_level）中全部 active。
> ⚠️ 一致性备注：DB 词表 order 为 research=4、subregion=5；代码 fallback
> `canonical_region_service._GRANULARITY_LEVEL_ORDER` 为 subregion=4、research=5。
> 运行时以 DB 词表为准（`_load_level_order` 优先读库），但建议后续统一两处定义。

### 1.3 每粒度随机抽查（name / code / parent / source / provenance）

- **whole_brain** — `ng:br:brain`「Brain/脑」；无父节点；source: Allen 根节点 `/997/` + Macro96 隐式根；created_by=br1_seed，conf=0.99。
- **macro** — 4 个节点全部直接挂 brain；source_summary 同时带 Allen 结构 ID 与 Macro96 支持（如 brain_stem：Allen structure_id=343）；created_by=br1_seed。
- **clinical** — 抽查 cuneus / inferior_temporal / white_matter：父 = cerebrum（macro）或 brain；source_summary 带 Macro96 pool key + laterality_values（如 cuneus: left/right）；created_by=br2_seed，conf=0.95。**无 external_mappings**。
- **meso** — MMP 节点（如 `mmp_dvt_l`）：父 = cerebrum（macro，官方名称文件无 gyrus 信息）；source: HCP MMP1.0 (Glasser 2016) + source_file；external_mappings 带 `hcp_mmp1`/`glasser_2016`；created_by=import:hcp_mmp，conf=1。BNA 节点同构（父 = 对应 clinical 或 cerebrum）。
- **subregion** — 抽查 CA2 / dentate_gyrus / subiculum：父 = hippocampal_formation（meso）；source: Winterburn 2013 atlas 或 BR3 curated seed；external_mappings 带 **UBERON IRI**；conf=1。
- **fine** — 抽查 BA32 / BA39 / BA1：父 = cerebrum / inferior_parietal / postcentral；source_summary 注明「Julich-Brain 3.1 bulk data unreachable — curated anchor」；external_mappings 带 `brodmann_1909`；created_by=curated:fine，conf=1。

> 结构备注：`canonical_brain_regions` **没有 parent_region_id 列**，父关系一律经
> `canonical_region_hierarchy` 边表解析（predicate 仅 `part_of`）。

### 1.4 命名与本地化

- clinical/macro/subregion/fine 均有中文名；**meso 层 609 个节点 cn=None**（MMP 360 + BNA 246 + dlpfc/vmpfc/hippocampal_formation 中 MMP/BNA 无中文名）。
- MMP/BNA 节点按半球拆分为左右独立节点（如 `mmp_dvt_l`/`mmp_dvt_r`），名称自带 "(left/right)" 后缀。

---

## 2. canonical_region_hierarchy — 层级检查

### 2.1 总体

- 边总数 **681**，predicate 全为 `part_of`。
- 节点 682、根节点 1（brain）、孤立节点 0 → **单一连通树**，叶子 653。
- 孤儿父边 0、孤儿子边 0、粒度倒挂边（子不细于父）**0**。

### 2.2 父→子粒度对矩阵（真实边）

| parent → child | 边数 | 构成 |
|----------------|------|------|
| macro → meso | 422 | MMP 360 + BNA 62（无 clinical 父） |
| clinical → meso | 187 | BNA 184 + dlpfc/vmpfc/hippocampal_formation |
| macro → clinical | 42 | Desikan 风格皮层区 |
| clinical → fine | 12 | Brodmann 区挂对应脑回 |
| whole_brain → clinical | 6 | 脑室×4 / CSF / white_matter |
| meso → subregion | 5 | hippocampal_formation → 海马亚区 |
| whole_brain → macro | 4 | 四大区 |
| macro → fine | 3 | BA6 / BA24 / BA32 直接挂 cerebrum |

### 2.3 关键过渡存在性（只报告，不补充）

| 过渡 | 状态 |
|------|------|
| whole_brain → macro | ✅ 4 条 |
| clinical → meso | ✅ 187 条 |
| meso → subregion | ✅ 5 条 |
| **subregion → fine** | ❌ **0 条（不存在）** |
| clinical → subregion | ❌ 0 条 |
| subregion → cyto / cyto → molecular | ❌ 0 条（且两层级本身零数据） |

### 2.4 真实树结构（Brain | ? | ?）

```
ng:br:brain (whole_brain)
├── brain_stem (macro)
├── cerebellum (macro)
│   └── 3 个 cerebellar vermal lobules (clinical)
├── cerebrum (macro)
│   ├── 42 个 clinical 脑区（amygdala/caudate/cuneus/hippocampus/insula/postcentral…）
│   │   ├── 184 个 BNA meso（如 hippocampus → bna_hipp_2_1_l/r）
│   │   ├── dlpfc / vmpfc / hippocampal_formation (meso)
│   │   │   └── hippocampal_formation → CA1/CA2/CA3/DG/Subiculum (subregion) ×5
│   │   └── 12 个 Brodmann fine（如 postcentral → ba1/ba2/ba3a/ba3b）
│   ├── 62 个 BNA meso 直挂（cingulate/IFG/MFG/striatum 等，无 clinical 父）
│   ├── 360 个 MMP meso 直挂（全部挂 cerebrum）
│   └── 3 个 fine 直挂（ba6/ba24/ba32）
├── diencephalon (macro)
│   ├── thalamus_proper (clinical) → 8 对 BNA 丘脑亚区 (meso)
└── 6 个 clinical 直挂 brain：3rd/4th ventricle, lateral ventricle,
    inferior lateral ventricle, CSF, white matter
```

### 2.5 结论

- 树**结构完整、无环、无脏边**；不一致为 0。
- 但**树深不均匀**：BNA 62 + MMP 360 跳过 clinical 直接挂 macro；6 个非皮层 clinical 直挂 brain。渲染时必须按真实边 + 节点 level 徽章，不能按深度推断层级（现有 Tree 实现已符合此原则）。
- 28 个 clinical 无 meso 子节点（叶）；20 个有 meso 子节点。

---

## 3. Atlas 数据层

### 3.1 atlas_region_resources（1945 行）

| Atlas | Version | Species | 行数 | 已映射 | 覆盖 canonical 数 |
|-------|---------|---------|------|--------|-------------------|
| HCP MMP1.0 (Glasser 2016) | MMP1.0 360-parcel | human | 360 | **360 / 360** | 360 |
| Brainnetome Atlas | BNA246 (2016) | human | 246 | **246 / 246** | 246 |
| Hippocampal Subfield Atlas | Winterburn 2013 | human | 12 | 10 / 12 | 5（CA1/CA2/CA3/DG/Subiculum） |
| Allen Mouse Brain Atlas | P56 structure ontology | mouse | 1327 | 10 / 1327 | 7（dlpfc/vmpfc/hippocampal_formation + 4 海马亚区） |

### 3.2 atlas_region_mappings（626 行）

- mapping_type：exact=621、uncertain=2、narrower=2、broader=1
- species_relation：same_species=616、homology=10（全部来自 Allen 小鼠）
- 全部 status=active；**无 NULL canonical 目标**（0 行悬空）
- 被映射覆盖的 canonical 脑区：**614 / 682**；无任何映射的 atlas 行：**1319**（几乎全部是 Allen 小鼠）

### 3.3 结论

BNA 与 MMP 已全量映射（= 全部 meso 节点来源）；跨物种（homology）映射仅 10 条示范性数据；Allen 小鼠 1327 行是「资源层已接入、映射层未展开」的状态，展示时应如实标注，不宜作为树节点来源。

---

## 4. Cyto / Molecular 层

| 表 | 行数 | 去重脑区 | 分布 |
|----|------|---------|------|
| cell_type_registry | **21** | — | 全 human |
| region_cell_alignment | **24** | **5**（cerebrum/hippocampus/middle_temporal/CA1/DG） | contains=23、marker=1 |
| molecular_entity_registry | **15** | — | gene=14、neurotransmitter=1 |
| region_molecular_alignment | **95** | **12**（amygdala/caudate/putamen/accumbens_area/hippocampus/rostral_anterior_cingulate/cerebellum/cerebrum/dlpfc/CA1/CA3/DG） | evidence_type 全 expression |

### 结论与建议：**选 B（脑区详情关联层），不进树**

- 数据规模是「多尺度能力演示种子」，且只覆盖 5–12 个脑区：作为树节点会让 99% 的脑区无子节点；作为**脑区详情 Tab（跨层关联）**则每个有数据的脑区都能展示真实内容。
- 现有 EntityDetailPanel 已按此方向实现（Region 关系摘要含 Cell Types / Molecules 计数 + cell_type/molecule 实体详情），无需改架构。

---

## 5. canonical_connections — 连接状态

### 5.1 总量与类型

- 总数 **2486**；status **全部 proposed**（无 active/deprecated → 未接入审阅/晋升链路）
- connection_type：structural=1965、functional=354、uncertain=164、association=3
- directionality_policy：unspecified=975、bidirectional=907、directed=604
- 连接自身 granularity_level：全部 clinical
- confidence：全部有值（min=0、avg=0.351、max=1）——展示时 0 值需如实呈现，不宜隐去

### 5.2 端点 canonical 化

- **悬挂端点 = 0**：FK NOT NULL + 数据完整，所有 source/target 均指向 canonical_brain_regions ✅
- 但覆盖范围窄：仅 **51 / 682** 个脑区参与连接（48 clinical + 3 macro：brain_stem/cerebellum/diencephalon）
- 端点粒度对：clinical↔clinical=2210、macro→clinical=164、clinical→macro=107、macro↔macro=5
- **无任何 meso/subregion/fine 层连接**

### 5.3 结论

连接本体在 clinical 层已形成可浏览的图谱（51 节点、2486 边、类型/方向/置信度齐备），但全部为 proposed 状态；meso 以下无连接数据。Graph Explorer 现有实现（按脑区为中心展开连接）与此数据形态匹配。

---

## 6. canonical_circuits — 回路状态

### 6.1 总量

- 总数 **293**；status 全部 proposed；granularity_level 全部 clinical
- circuit_type：network=287、uncertain=6（**无 pathway/reflex/functional_loop 实例**）

### 6.2 成员规模

| 成员表 | 行数 | 去重 |
|--------|------|------|
| canonical_circuit_regions | 715 | 51 脑区（48 clinical + 3 macro） |
| canonical_circuit_connections | 100 | 40 连接 |
| canonical_circuit_functions | 538 | 242 功能术语 |

- role 分布：region：input=323 / core_region=148 / intermediate=134 / output=110；connection：全 supporting；function relation：全 associated_with
- 无任何成员的回路：**0**（全部回路至少 1 个成员）✅
- 最大回路：default_mode_network（29 区 + 7 功能）；右皮质脊髓运动通路（24 区 + 27 功能）
- 连接成员稀疏：top-25 回路中仅 1 个（r3_hub_divergent_pathway）有连接成员（8 条）

### 6.3 数据质量观察

- **DMN 重复变体**：default_mode_network / _dmn / _bilateral / _core_nodes / _left_precuneus_posterior_cingulate 等 5+ 个高度重叠回路——合并（replaced_by_circuit_id 链）的候选对象
- **占位名回路**：2 个 `unknown_region_to_unknown_region_*` 回路（LLM 提取残留），演示前应清理或隐藏
- 6 个 uncertain 回路（脑室/白质结构回路）名称尚可但类型标注为 uncertain

### 6.4 Graph Explorer 就绪度

**可以进入，但建议作为「过滤/叠加层」而非主画布**：回路有区域拓扑（715 成员行）+ 功能（538 行），可作为脑区图的高亮集合；但连接成员只有 40 条（占 2486 的 1.6%），回路内部的连接拓扑基本画不出来。

---

## 7. 下一阶段设计建议

### 7.1 树应展示哪些层级

**建议：树 = 区域本体全层级（L0→L6 实际数据），默认展开至 clinical，meso 默认折叠。**

| 层级 | 展示策略 |
|------|---------|
| L0 whole_brain / L1 macro | 默认展开（5 个节点） |
| L2 clinical | 默认展开（48 个，含 6 个直挂 brain 的非皮层节点） |
| L3 meso | **默认折叠**（609 个且 L/R 重复，直接展开会压垮树）；行上给 atlas 徽章（BNA/MMP/curated）区分来源 |
| L5 subregion / L6 fine | 默认折叠，挂在各自父节点下 |
| research/cyto/ultra_fine/molecular | 零数据，不渲染（空层级不造假） |

配套：meso 无中文名 → 树行显示英文名 + 徽章；后续补中文名（如「左侧 DVT (HCP-MMP)」）可显著改善医生演示观感。

### 7.2 哪些进树、哪些作为详情页 Tab

**进树（区域节点本体）**：
- canonical_brain_regions 682 个 + hierarchy 边（已实现）
- Connection / Circuit / Function 三个独立根（已实现，数据充足可继续填充）

**作为脑区详情 Tab / 关系卡片（不扩树）**：
- Connections（51 个脑区有数据）
- Circuits（51 个脑区有数据，role 徽章已有）
- Functions（经回路派生，标注来源——已实现）
- **Atlas mappings**（614 个脑区有映射；现详情缺此 Tab，属最该补的一块）
- **Cell Types / Molecules**（5–12 个脑区；B 方案，已实现计数+实体面板）
- Provenance / 候选锚点（96 个候选已锚定 canonical；candidate 链接可作溯源 Tab）

### 7.3 自然语言查询第一阶段问题（基于现有数据能力）

数据能如实回答的问题模板（区域/连接/回路/功能四域）：

1. 「X 的子区域有哪些？」→ hierarchy 子节点（如：海马体 → BNA 亚区 + 海马结构）
2. 「X 属于哪个大区？」→ ancestors 链
3. 「哪些脑区与 X 有连接？类型是什么？」→ 出/入向连接 + connection_type（仅 clinical/macro 层）
4. 「X 参与哪些回路？」→ circuit_regions 反查 + role
5. 「回路 Z 包含哪些脑区/功能？」→ circuit 成员展开
6. 「X 有哪些 atlas 来源？」→ atlas mappings（BNA/MMP/Winterburn/Allen-homology）
7. 「BA44 在哪？」→ fine 层 + 父链（pars_opercularis → cerebrum → brain）

**第一阶段不应承诺的问题**（数据不支持）：meso/subregion 层连接查询（无数据）、细胞/分子层系统查询（种子规模）、跨物种连接（homology 映射仅 10 条）、任何 status 层面的「已验证」结论（全部 proposed）。

### 7.4 距离医生演示版本缺什么（按优先级）

| # | 缺口 | 影响 | 建议 |
|---|------|------|------|
| 1 | **连接/回路全部 proposed** | 演示「知识图谱已治理」的叙事不成立 | 提供审阅→激活的最小闭环，或 UI 诚实标注「候选知识（未审阅）」，不渲染为定论 |
| 2 | **meso 609 节点无中文名** | 中文演示树一半内容是英文代码（DVT/IFJa…） | 批量补 cn（可先机翻+人工抽查，或显示中英双语） |
| 3 | 连接仅覆盖 51/682 脑区、无 meso 连接 | 医生点开 BNA/MMP 子区无连接可看 | 演示时用 clinical 层做连接主线；meso 层连接进入后续 CN 阶段 |
| 4 | 62 BNA + 360 MMP 跳过 clinical 直挂 cerebrum | 层级浏览观感「断层」 | 虚拟分组（按 atlas 或按 gyrus 聚合徽章），不改数据 |
| 5 | DMN 重复回路 + 2 个 unknown_region 占位回路 | 回路列表观感粗糙 | 演示前做一次回路合并/隐藏的 curation pass |
| 6 | 1319 行 Allen 小鼠未映射、homology 仅 10 | 多物种叙事只有骨架 | 如实展示为「资源层已接入」，不吹跨物种能力 |
| 7 | subregion→fine 无过渡、cyto/molecular 层零脑区 | 「多尺度五级」叙事只到第三级 | 演示聚焦 macro→clinical→meso→subregion 四级真实数据 |
| 8 | 无 NL 查询端点 | 「自然语言问图谱」是 PPT 卖点但无实现 | 用 7.3 问题模板做第一阶段规则化查询（ontology 检索，非 LLM 生成） |

---

## 附：审计方法与约束遵守

- 全程 SELECT-only（`information_schema` / `pg_tables` 只读目录查询 + 聚合统计 + 随机抽查），未修改数据库、未修改 migration、未修改前端、未创建任何测试数据。
- 脚本存于系统临时目录（未入库），可复跑验证本报告数字。
- 唯一执行写操作的仅为本报告文件（`.superpowers/sdd/`）。

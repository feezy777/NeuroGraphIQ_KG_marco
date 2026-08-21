# Task 2 Report: Ontology Center 信息架构优化（五阶段）

## Status: DONE

约束核查：**未改 API、未改数据库、未增 Graph Explorer、未增推理功能**。全部改动在 `frontend/src/`（信息展示层），后端零改动。

---

## 验收输出 1：Entity Inspector 类型化展示改造说明

信息优先级五层模型落地：**① 人类可读名称 → ② 关系结构 → ③ ontology code → ④ provenance**；code 禁止出现在视觉第一层。

| 实体 | 主标题 | 副标题/类型行 | 卡片结构 |
|------|--------|---------------|----------|
| **Region** | 英文名（人类可读） | code 行 + `Macro (L1) Brain Region` 类型行 | 面包屑 → Overview → Hierarchy（Parent/Ancestors/Children）→ Relations 摘要（Connections/Circuits/Functions 计数）→ Provenance |
| **Connection** | **类型标题**（如 `Association connection`） | `Pars triangularis ↓ Posterior cingulate`（真实脑区名 + ↓ 箭头） | **Source Region 卡 / Target Region 卡**（可点击跳转）→ Properties 卡（type/direction/confidence，**Code 下沉到此处**）→ Provenance |
| **Circuit** | `auditory_brainstem_thalamocortical_pathway` | code 行 + 类型行（`Network`） | Overview → **Region topology**（角色/序/置信度）→ **Connections**（`Brainstem ↓ Thalamus` 卡）→ **Functions** → Provenance |
| **Function** | 术语名（如 `Somatosensory processing`） | code 行 + 类型行 | Overview → **Hierarchy**（Parent/Children，取自 `/api/ontology/hierarchy/terms`）→ **Associated regions** → **Associated circuits** → Provenance |

关键变化：Connection 主标题不再被 `ng:cn:xxxxx` 占据（原来整屏第一行是 code）；现在 code 只出现在 Properties 卡一行。测试断言 `.oc-entity-code` 在 connection header 中为 null。

## 验收输出 2：四类展示截图说明

（截图见运行环境 `npm run dev` → `#/ontology-center?tab=browser`；以下为各屏视觉描述）

1. **Region 屏**：Inspector 顶 = 名称 + 灰色 code 行 + 类型徽章行；下方面包屑 `Brain / Cerebrum`；Overview 卡含中文名/半球策略/物种；Hierarchy 卡 Parent（Brain）→ Ancestors → Children（Hippocampus 可点击）；Relations 卡显示 连接数/回路数/功能数统计。
2. **Connection 屏**：主标题 `Association connection`，副标题 `Pars triangularis ↓ Posterior cingulate`（端点名 + 蓝色箭头图标）；Source Region 卡 / Target Region 卡各含端点全名+code+状态徽章，点击跳转对应脑区；Properties 卡第一行才是 `ng:cn:...` code（mono 字体）。
3. **Circuit 屏**：主标题 = 回路名；Region topology 卡列出 `Thalamus · 核心区域 · 序1`；Connections 卡每行 `Brainstem ↓ Thalamus` + 置信度。
4. **Function 屏**：主标题 = 术语名；Hierarchy 卡 Parent=`Perception`（有层级时）/ `No parent on record`（无时，诚实空态）；Associated 两卡在无反向 API 时显示「后端 API 待接入（不展示假数据）」。

## 验收输出 3：Tree 是否还显示 code

**不再显示。** 左树每行 = 名称 + level 徽章 + 状态 chip；code 仅保留在行 `title` 属性（hover tooltip）与选中后 Inspector 的 Properties 中。分组行（Folder 图标 + 计数徽章）本身无 code。搜索下拉同样显示人类可读名称（如 `pars triangularis → posterior cingulate`）。

分组结构：
- Connection → 按 connection_type 分组（Structural/Functional/Association/Uncertain，稳定顺序，无空组，默认折叠）
- Circuit → 按 circuit_type 分组（Network/Pathway/Functional loop/Uncertain）
- Function → 扁平列表（见偏差声明）

## 验收输出 4：Relation 是否解决截断

**已解决。** 三管齐下：
- 名称最大两行（`-webkit-line-clamp: 2` + `word-break`），不再单行省略号截断
- code 从名称行分离，独占一行（mono 12px），不再与名称抢宽度
- 连接卡片名称改为 `Source ↓ Target` 结构（如 `Hippocampus ↓ Pars triangularis`），一眼可读；方向箭头上下行 + type/confidence/direction 逐行 meta

右栏宽度 420px（320→420），1280px 以下默认折叠、可手动展开。

## 验收输出 5：npm run build

```
✓ built in 2.58s — 0 TS errors
```
仅剩既有 chunk-size 警告（index 1.6MB），与本任务无关。

## 验收输出 6：npm test（vitest）

```
Test Files  1 failed | 45 passed (46)
Tests       1 failed | 388 passed | 1 skipped (390)
```

- **失败 1 例 = 既有失败**：`EvidenceCandidatesErrorState.test.tsx`（evidence-center hash 导航断言），来自上一会话的 evidence 工作，本任务未触碰该模块。
- 本任务新增/更新测试：`ontologyApi.test.ts`（新建，10 个 adapter 用例：分组顺序、display name 推导、批量 region map 解析、Function hierarchy 映射、Source↓Target 关系名、诚实空状态）、`EntityDetailPanel.test.tsx`（重写为四类 typed fixtures，10 用例）、`TreeNodeRow.test.tsx`（+分组行用例）。ontology-center 全部 10 个测试文件 68 用例全绿。

## 数据适配层改动（ontologyApi.ts）

- `connectionTypeTitle` / `connectionDisplayName`：code 启发式推导人类可读名（去 `ng:cn:`、去类型前缀、`_to_`→` → `）
- `canonicalRegionMap`：1 次 `listCanonicalRegions` 批量解析所有 source/target 脑区名（避免 N×2 请求）
- `groupedConnections` / `groupedCircuits`：虚拟分组节点（inline children，零额外请求，默认折叠）
- `connectionDetail`：`typeTitle` / `source` / `target` 三字段
- `functionDetail`：接入 term hierarchy parents/children 端点
- 区域/回路关系卡统一输出 `Source ↓ Target` 名称

## 与规格的偏差（诚实声明）

1. **Function Tree 未按 hierarchy 分组**：后端 `ontology_term_hierarchy` 实际 0 条边（isolated_active_terms 2874），且无 function roots 端点 → 保持扁平列表。Function Inspector 内 Hierarchy 卡已按规格实现（有层级时显示）。**不写假数据**。
2. **截图以文字说明代替**：本环境无浏览器截图能力，四类展示以逐屏视觉描述给出；dev server 运行中可直接核对。

## 文件清单

- 改：`src/api/ontologyApi.ts`、`src/api/endpoints.ts`（+2 hierarchy 端点函数）、`src/pages/ontology-center/detail/{EntityDetailPanel,RelationSection}.tsx`、`ui/{RelationCard,EntityChip}.tsx`、`browser/{OntologyBrowser.tsx,tree/{OntologyTree,TreeNodeRow,OntologyTreeNode}.ts}`、`src/styles.css`
- 测试：`src/api/ontologyApi.test.ts`（新）、`src/pages/ontology-center/detail/EntityDetailPanel.test.tsx`（重写）、`tree/TreeNodeRow.test.tsx`（+1）

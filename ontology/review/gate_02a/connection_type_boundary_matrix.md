# Gate 2A — ConnectionType 边界矩阵（Boundary Matrix）

比较 6 个候选概念（含 KEEP 4 个 + 需审查的 FiberTractConnection 与 Coactivation），
在 9 个正交维度上的取值，用于验证「类型之间边界是否清楚」。

## 1. 主矩阵

| 概念 | Physical pathway | Directed | Statistical relation | Model inferred | Tracer support | DTI support | fMRI support | Can imply direct anatomy | Recommended ontology status |
|---|---|---|---|---|---|---|---|---|---|
| **StructuralConnection** | ✅ 是 | directed / reciprocal / direction_unknown | ❌ 否 | ❌ 否 | ✅ 是（金标准） | ✅ 是（间接） | ❌ 否 | ◐ **部分**（physical 是；突触级 directness 证据未必充分；polysynaptic 不压缩为单条） | **KEEP** |
| **Projection** | ✅ 是 | ✅ **是（必）** | ❌ 否 | ❌ 否 | ✅ 是（顺/逆行判向） | ◐ 部分（可辅助候选通路，但**不可判向**） | ❌ 否 | ✅ **是** | **KEEP**（⊑ StructuralConnection） |
| **FiberTractConnection** | ✅ 是（纤维束） | ◐ direction_unknown（DTI 无法判定 afferent/efferent） | ❌ 否 | ◐ 部分（追踪重建即模型） | ◐ 部分（可叠加示踪） | ✅ 是（主证据） | ❌ 否 | ◐ **仅部分**（DTI 是间接重建，有伪迹） | **DEFER** |
| **FunctionalConnectivity** | ❌ 否 | ❌ 否 | ✅ **是** | ◐ 部分（部分方法需模型） | ❌ 否 | ❌ 否 | ✅ 是（静息/任务态） | ❌ **否** | **KEEP** |
| **EffectiveConnectivity** | ❌ 否 | ✅ **是** | ❌ 否（但基于时间数据） | ✅ **是（强）** | ❌ 否（但扰动/光遗传为干预证据） | ❌ 否 | ✅ 是（DCM 常用于 fMRI） | ❌ **否** | **KEEP** |
| **Coactivation** | ❌ 否 | ❌ 否 | ✅ 是（跨研究共激活） | ✅ 是（ALE 元模型） | ❌ 否 | ❌ 否 | ✅ 是（任务态） | ❌ **否** | **REMOVE**（functional observation / evidence candidate） |

### 图例

- ✅ = 该维度是本概念的核心/可靠支撑
- ◐ = 部分/有条件支撑
- ❌ = 该维度不适用或不可作为依据

## 2. 边界判读：三组「最容易混淆」的对照

### 2.1 StructuralConnection vs FunctionalConnectivity（最关键边界）

| 维度 | StructuralConnection | FunctionalConnectivity |
|---|---|---|
| 是否声明物理通路 | 是 | **否** |
| 是否可由统计相关推出 | 否（需独立结构证据） | 是（本就是统计） |
| 能否互相蕴含 | 结构可能伴随功能，但**功能不蕴含结构** | 功能相关不声明结构 |

**一句话规则：** FunctionalConnectivity 记录「是否相关」；StructuralConnection 记录「是否物理相连」。相关 ≠ 相连，除非另有独立结构证据。

### 2.2 Projection vs EffectiveConnectivity（方向性最易混）

| 维度 | Projection | EffectiveConnectivity |
|---|---|---|
| 声称的对象 | 有向**物理通路** | 有向**影响/耦合** |
| 是否必须是物理通路 | 是（否则不成立） | **否**（可多突触/间接） |
| 证据 | 示踪/解剖 | DCM / Granger / 扰动 |

**一句话规则：** 「A→B 投射」说的是「A 的轴突终止于 B」；「A→B 有效连接」说的是「A 对 B 施加影响」。方向相同，语义不同。

### 2.3 FiberTractConnection vs StructuralConnection vs Projection

| 维度 | StructuralConnection | FiberTractConnection | Projection |
|---|---|---|---|
| 本质 | 物理通路存在 | 通路的**物理实现/重建**（具体纤维束） | 有向物理通路 |
| 是否一种「连接类型」 | 是 | **更像证据/通路描述** | 是 |
| 是否有天然方向 | directed / reciprocal / direction_unknown | direction_unknown（DTI 无法判定 afferent/efferent） | 必是有向（directed） |

**一句话规则：** WhiteMatterTract 是**解剖实体**（物理纤维束），DTI tractography 是**方法/证据**（重建该实体的手段）。FiberTract 不是「本身即证据」，而是「一个由 DTI 等方法重建/定义的解剖实体」，它回答「通路怎么被观测/定义」，而非「这是什么类型的连接」。故 DEFER，不建类型。

## 3. 判定结论（由矩阵导出）

- **唯一能「隐含物理解剖连接」的类型 = StructuralConnection（及其子类 Projection）。** 其余三类（FC / EC / Coactivation）一律不隐含物理解剖。但突触级 directness 证据未必充分；polysynaptic / indirect pathway 由中间脑区介导时，不应压缩成单条 StructuralConnection，应由 Path / Circuit / Inference 表达。
- **三个正交维度分别界定 KEEP 三兄弟的语义（不互斥）：**
  - Physical pathway → StructuralConnection
  - Statistical relation → FunctionalConnectivity
  - Model inferred directed influence → EffectiveConnectivity
- **方向性不构成「新类型」，只构成「层级/子类」：** 有明确 source→target 的轴突投射型结构 = Projection ⊑ StructuralConnection（仅 direction_known 不足，还需 axonal projection 语义/证据）；有向影响/耦合 = EffectiveConnectivity（顶层）。
- **FiberTract 与 Coactivation 都无法通过「是独立连接类型」检验**，分别落入 DEFER（解剖实体 + 方法/证据分离）与 REMOVE（functional observation / evidence candidate）。

## 4. 边界完整性自检

- [x] KEEP 类型具有可区分的语义标准（物理通路 / 统计关系 / 模型推断有向影响），但不互斥
- [x] 同一脑区对可同时存在 StructuralConnection / FunctionalConnectivity / EffectiveConnectivity
- [x] 方向性被正确建模为「子类」而非「新顶层类型」
- [x] 证据方法（tracer/DTI/fMRI/DCM）未被误建为连接类型
- [x] 统计关联未被自动解释为解剖连接
- [x] 有效连接（有向影响）未被自动解释为结构连接

# Gate 6E-A — 学习版说明（Evidence / Assertion）

---

### Publication / 文献
- 是什么：论文/文献载体。
- 例：一篇 PubMed 论文。

### ResearchStudy / 研究
- 是什么：真正开展的研究活动。
- 例：一项 fMRI 研究。

### Evidence / 证据
- 是什么：论文/数据库中具体支撑知识的证据单元。
- 例：论文中一段结果、一个图表结果、一个数据库记录。

### Assertion / 断言
- 是什么：可以被支持、反驳或限定的一条具体知识命题。
- 例：Hippocampus participatesIn Memory。

### Connection / 连接（为什么特殊）
- 是什么：Connection 已经是 reified scientific entity，不能再简单复制成第二条 edge truth。
- 例：CA1 → mPFC（Projection）。

### reported vs inferred
- reported：外部来源直接报告。
- inferred：系统根据已有知识推出来（roll-up 等）。

### 证据怎么挂
- 普通关系：Publication → Evidence → Assertion（DB 层）。
- Connection：Publication → Evidence → Connection（直接或经 observation）。
- 一句话：普通边要 assertion 节点；复杂 reified 事实自身就是 knowledge object。

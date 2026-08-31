# Gate 7B-B Phase 1 — 学习版说明

### kg_entities 是什么？

相当于整个知识图谱的「总身份证库」。

以后：海马、APOE、某条 Connection、某个 Circuit，都会先在这里有一个唯一身份。

它有**两个号**：
- 内部号 `entity_pk`（101、102、103…，全局递增，给数据库用）。
- 对外号 `entity_id`（`NGIQ-BR-00000001`，给人看、给外部引用）。

两个号是**分开计数**的：第 101 个实体，可能是第 1 个脑区（`NGIQ-BR-00000001`）。这就是为什么不会打架——内部号全局唯一，对外号按类型各自从 1 数起。

### 为什么一张表管所有类型？

因为「海马」和「APOE」虽然是完全不同的东西，但都需要一个「我是谁、我叫什么、我什么状态」的统一身份。集中在一张表，后面脑区表、基因表只要「挂」回这个身份就行（shared-PK），不用各自再造一套名字和 ID。

### alias 是什么？

一个东西的其他名字。

例如：Hippocampus、海马、hippocampal region，都可以指向同一个 canonical entity。

### xref 是什么？

外部数据库给这个东西的编号。

例如：我们自己的 `NGIQ-BR-00000001`，和 Brainnetome / HGNC / MONDO 的外部 ID 建立对应关系。

### source 是什么？

这条知识来自哪个科学资源（Julich-Brain、PubMed、HGNC…），**不是**哪个 AI 把它提取出来。DeepSeek / GPT 是「干活的人」（provenance agent），不是「知识出处」（scientific source）——所以 `llm` 不能当 source_type。

### 为什么不直接删，而是标状态？

因为公开 ID 一旦发出去就**永不复用**。东西被合并/废弃了，旧 ID 还留着（lineage），只是标成 `deprecated`/`merged`。所以删除有 alias 的实体会被数据库拒绝（RESTRICT）——防止误删把别名和交叉引用一起物理抹掉。

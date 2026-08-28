# Gate 7A — Human Species Policy（物种范围策略）

本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 冻结：Homo sapiens only

NeuroGraphIQ V1 production knowledge scope = **Homo sapiens only**。NCBI Taxonomy taxon_id = 9606。BrainRegion / Connection / Circuit / Atlas production mapping / RegionMapping / granularity roll-up 均仅针对 Homo sapiens。

## 2. 排除非人脑生产数据

不得进入 V1 canonical production：Allen Mouse Brain Atlas、Allen Mouse CCF、Allen Mouse Connectivity Atlas、mouse/rat/macaque/chimpanzee brain data、其他非人脑 atlas。可作为未来 comparative neuroscience / homology / cross-species mapping 来源，但 production_eligible=FALSE。

## 3. Allen 物种 guard

任何资源名含 "Allen" 必须先解析 Allen Human 或 Allen Mouse，禁止直接进 production。
- Allen Mouse：species_taxon_id != 9606 → production_eligible=FALSE，禁止进入 canonical BrainRegion / human Connection / human Circuit / G1–G4。
- Allen Human：只有明确验证 species_taxon_id=9606 才作为 human auxiliary source。
- 注意 Allen Human Brain Atlas 大量 microarray sampling sites 不能误解释为 canonical BrainRegion 数量。

## 4. 物种字段

| 表 | 字段 |
|---|---|
| atlases | species_taxon_id、species_name_en、species_name_zh、species_verification_status（verified/pending/rejected）、production_eligible |
| external_regions | species_taxon_id、species_verification_status |
| brain_regions | species_taxon_id（V1 canonical 必须 = 9606） |

- 只有 verified + 9606 才允许 production_eligible=TRUE。
- Human：species_taxon_id=9606、species_name_en=Homo sapiens、species_name_zh=人。

## 5. Scientific Source ≠ Provenance Agent（延续）

- Scientific Source：Julich-Brain、Human Brainnetome、AAL3、HCP、Schaefer、PubMed、Publication。
- Provenance Agent：DeepSeek / GPT / BioSEPBERT / Human curator / ImportPipeline / RuleEngine。
- LLM 不能成为 scientific source。

## 6. BrainRegion aggregation 不依赖简单名称匹配

cross-granularity roll-up 依赖显式 mapping（+ 空间/解剖证据），禁止仅凭名称相似做聚合。

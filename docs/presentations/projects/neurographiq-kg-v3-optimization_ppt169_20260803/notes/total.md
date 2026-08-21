# 01_cover

各位老师、同事，大家好。今天汇报 NeuroGraphIQ KG V3 的多粒度脑区知识图谱构建过程。核心命题一句话：让 LLM 成为受控提取工具，而不是知识终审者。

# 02_problem_thesis

先谈问题。多源脑图谱难统一接入，跨粒度命名冲突易诱发隐式合并，LLM 又可能带来幻觉，审核若成黑盒就无法追责。因此我们设下硬边界：LLM 不写 final_*，Final 只收经审核知识，跨粒度只允许显式 mapping。

# 03_positioning

项目定位是多粒度脑区知识基础设施。目标是多粒度图谱，任务是全链路构建与治理，架构是五级粒度 Schema 隔离。当前已落地宏观临床层，接入 AAL3 与 Macro96。

# 04_principles

九项硬约束构成底线：LLM 隔离、统一入口、双重审核、正式库纯净、全链路溯源，以及粒度隔离、显式映射、输出留痕、全程日志。没有审核记录，就不得进入下一环节。

# 05_knowledge_layers

知识组织采用七层：实体、连接、回路、功能、证据、三元组、映射。自下而上构建，避免结构功能证据混在同一平面。

# 06_funnel_pipeline

构建漏斗五阶段：导入解析、候选生成、校验增强、LLM 提取、审核晋升。这一页合并了原版重复的流水线说明。自动化解决规模，人工把关解决可信。

# 07_global_architecture

全局架构是生产—治理—消费闭环。Raw/Staging 到 Candidate，再到 LLM/Mirror，经 Review 进入 Final，最后服务消费侧。Mirror 是唯一预正式缓冲层，晋升必须预览确认后执行。

# 08_import_candidate

导入与候选：资源登记、双轨文件、批次审计、单向解析、溯源候选。输出是带 provenance 的标准化候选记录。

# 09_rules_enhance

规则校验在前：12 条确定性规则，BLOCKER 直接熔断，并给出 0–100 质量分。增强分两层：Tier1 规则自动修复，Tier2 LLM 建议必须人工复核。增强不等于入库。

# 10_llm_mirror

LLM 侧：Provider 抽象、七类关系提取、异步编排与调用日志。Mirror 侧：写入去重、双模型盲审、回路投射交叉验证。所有提取结果先入 Mirror。

# 11_gates_promote

三道闸门：规则校验、模型盲审、专家终审。通过后进入晋升：预览变更、人工确认、系统执行，并写入标准三元组与 12 种谓词。

# 12_consumption

消费侧四入口：数据中心、图谱探索、症状查询、知识导出。它们共用同一 Final KG 查询面。

# 13_traceability

原版写“七步”，实际是八个节点：Final fact、Promotion、Review、Validation、Extraction、Candidate、Import batch、Resource file。证据链保留原文、LLM 输出、规则日志与审核意见。

# 14_tech_scale

技术栈是 FastAPI、React+TypeScript、PostgreSQL Schema 隔离。工程规模指标来自仓库统计：5 粒度、AAL3/Macro96、12 规则、7 类提取、42 路由、88 服务、1173 测试。这里不做“零故障”或“响应极快”这类不可核验承诺。

# 15_conclusion_qa

三点结论：受控 LLM 加 Mirror 是关键；八步溯源保证可追责；宏观临床层已落地并可继续扩展。我的汇报到此，欢迎提问。

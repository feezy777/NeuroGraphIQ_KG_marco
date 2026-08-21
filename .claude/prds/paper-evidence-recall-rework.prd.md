# 论文证据提取:召回与人工审核链路改造

## Problem

领域数据审核员在数据中心工作台对 Mirror KG 对象做论文佐证时,多选论文点击「提取所选论文」,实际只有单篇论文被送入提取流程;且提取命中率几乎为零——被提取论文无一通过原文核验,`source_verified` 全为 false,没有任何片段能进入人工审核。论文佐证功能事实上不可用:知识对象无法获得文献证据支撑,置信度无法通过证据链更新,审核链路空转。此外,论文匹配纯词法(关键词 AND 拼接),无法判断语义相关性;对连接/回路类对象,论文可能只证明「对象存在」(如解剖投射)而不涉及功能,现有链路无法区分存在性支撑与功能性支撑。

## Evidence

- 用户观察(2026-08-10):工作台多选 5 篇论文点击提取,仅单篇论文送入提取流程,其余无结果。
- 用户观察:提取命中率≈0 —— 全部提取失败,无一篇论文产出可审核片段。
- 代码诊断(2026-08-10,已确认):
  - 前端「提取所选论文」循环调用单篇提取接口;批量多篇提取接口(支持并发、论文排序、每篇错误隔离)后端已实现、前端已封装,但工作台未接线 → 多选只送单篇的架构根因。
  - 后端片段验证要求段落 id 完全命中 + 文本逐字匹配(仅容忍空白折叠/NFKC/少数标点),任何轻微改写即判死,且验证失败不重试、不降级 → 命中率≈0 的架构根因。
  - 摘要 HTML 实体/标签未清理;提取环节与入库环节使用不同来源的全文文本 → 提取时已核验片段在入库时可能二次被拒。
  - 论文匹配与筛选全词法(`ABSTRACT/BODY:"term"` AND 拼接);`mode`(existence 存在性佐证)只存在于早期单篇接口,批量/工作台链路未贯穿,DeepSeek 判定不区分「存在性支撑」与「功能性支撑」。

## Users

- **Primary**: 领域数据审核员。触发场景:在数据中心对某个连接/功能/回路对象需要论文佐证;或批量预处理任务产出草稿后需要人工审核。
- **Not for**: 最终晋升/终审用户(本 PRD 不涉及 Final KG 写入)。

## Hypothesis

我们相信**将原文验证从「生死闸门」改为「分级匹配(近似匹配降级为人工确认)」、以语义相关性筛选论文、并显式区分存在性/功能性支撑**将**让多篇论文的摘要与原文片段可靠、精准地进入人工审核流程**给**领域数据审核员**。
We'll know we're right when **被提取论文中至少产出 1 个可审核片段的比例 ≥ 60%(现≈0),多选提取对每篇论文逐篇返回结果,且连接类对象在存在性模式下能稳定命中「对象存在」类证据**。

## Success Metrics

| Metric | Target | How measured |
|---|---|---|
| 单篇提取可用率(≥1 个可审核片段 ÷ 被提取论文数) | ≥ 60% | 工作台提取结果统计;批量任务 `passages_json` 中有 `source_verified=true` 的条目占比 |
| 多选提取完成率(逐篇返回结果或明确失败原因) | 100% | 批量接口返回 results 数量 = 所选论文数;无静默丢失 |
| 语义筛选精准率(被筛选跳过的论文中确无有效片段的比例) | ≥ 80% | 语义筛选日志 vs 提取结果比对(防误杀) |
| 存在性模式命中(连接/回路类对象在 existence 模式下的提取可用率) | ≥ 50%(TBD,需基线) | 按 mode 统计提取可用率 |
| 审核入库转化率(辅助) | ≥ 30%(TBD,需基线) | 人工确认入库的 evidence 数 ÷ 可审核片段数 |
| 提取-入库一致率(辅助) | attach 不再因二次验证拒绝 | attach 失败率监控(400 错误计数) |

## Scope

**MVP**(7 项一次交付):

1. **验证分级**:`exact` → `normalized`(现有)→ 新增 `similarity`(近似匹配)。similarity 通过的片段可进入人工审核,标记 `verification_method=similarity`,UI 明示「近似匹配,请人工核对原文」。
2. **段落定位模糊化**:不再硬依赖模型输出的段落 id;片段按内容相似度在论文段落中定位最佳匹配,定位失败才标未验证。
3. **输入覆盖与数据一致性**:摘要全量进入候选;全文召回窗口扩大;摘要/全文统一做 HTML 实体解码与标签清理;提取环节与入库环节使用同一份归一化文本。
4. **提取前语义筛选**:DeepSeek 对候选论文(标题+摘要)做相关性评分,低于阈值的论文跳过提取(省 token、提升排序精准);被筛选跳过的论文记录原因,可查看、可关闭筛选。
5. **存在性佐证模式 + 判定维度**:`mode=existence` 贯穿工作台/批量链路(检索式只用源/靶脑区,不拼接功能词);DeepSeek 判定显式区分该论文证明的是「对象存在」(relation/连接成分)还是「功能」(function 成分),UI 展示标签。
6. **前端多选接线批量提取接口**:多选论文一次提交,后端并发提取,逐篇返回结果并展示在对应论文下方(UI 交互保持现状)。
7. **未验证片段保留展示**:未通过原文校验的片段仍展示给人工审核并标注失败原因;人工可重新截取或手动确认(沿用现有 reselect 能力)。

**Out of scope**

- 向量检索 / embedding 召回 — 词法检索 + 语义筛选先验证指标,不足再引入。
- 双模型交叉验证 — 独立 feature,已有 `mirror_dual_model_verification`,不在此 PRD。
- 跳过人工审核自动入库 — 违反「LLM 输出必须人工审核」治理边界。
- 非 OA 全文获取 — 不通过未授权渠道获取全文。
- 批量任务状态机改造 — 已可用,仅按需接入新验证策略。

## Delivery Milestones

<!-- Business outcomes, not engineering tasks. /plan turns each into a plan. -->
<!-- Status: pending | in-progress | complete -->

| # | Milestone | Outcome | Status | Plan |
|---|---|---|---|---|
| 1 | 后端验证链路改造(分级验证 + 模糊定位 + 文本清理 + 提取/入库同源) | 提取结果中出现「近似匹配」片段而非全部失败 | in-progress | `.claude/plans/paper-evidence-recall-rework.plan.md` |
| 2 | 语义筛选 + 存在性模式(提取前相关性筛选、mode=existence 贯穿、存在性/功能性判定维度) | 候选论文按语义相关性筛选与排序;连接类对象可命中「对象存在」证据并带标签进入审核 | in-progress | `.claude/plans/paper-evidence-recall-rework.plan.md` |
| 3 | 前端多选接线批量接口 + 模式切换 UI | 多选 N 篇逐篇返回结果,不再只送单篇;可切换存在性/功能佐证模式 | in-progress | `.claude/plans/paper-evidence-recall-rework.plan.md` |
| 4 | 未验证片段保留 + 人工确认闭环 | 全部候选片段可进入审核,缺失项标注原因;attach 携带 verification_method 溯源 | in-progress | `.claude/plans/paper-evidence-recall-rework.plan.md` |

## Open Questions

- [ ] similarity 阈值取多少?(建议 token 级 Jaccard 或相似度比例;需用真实论文样本校准,避免误匹配与漏匹配失衡)
- [ ] 语义筛选的相关性评分阈值与模型?(需用真实检索结果校准;筛选结果是否常驻展示给用户复核)
- [ ] existence 模式对无方向对象(projection_function / region_function / circuit_function)是否适用,还是仅连接/回路类?
- [ ] 摘要截断(现 4000 字符)是否保留?摘要全量送入的成本与收益需验证。
- [ ] attach 对 similarity 片段是否强制人工二次确认(UI 勾选「已核对原文」)?治理上建议强制。

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| 近似匹配引入与原文不符的片段,削弱证据可信度 | Medium | High | 入库必须人工确认;similarity 片段 UI 高亮 + `verification_method` 溯源 + 审计记录 |
| 语义筛选误杀相关论文(低相关性被跳过) | Medium | High | 阈值保守(宁多勿杀);筛选原因可查看、可关闭;以「筛选精准率 ≥80%」指标监控 |
| 语义筛选增加一轮 DeepSeek 调用,token 成本上升 | High | Low-Medium | 筛选仅对检索结果(≤ 检索 limit)执行;低相关跳过节省的提取调用应大于筛选成本;并发受限流 |
| 存在性模式检索式过宽(无功能词)导致无关论文增多 | Medium | Medium | 语义筛选兜底;论文相关性排序优先 |
| 模糊定位误匹配到无关段落 | Medium | Medium | 定位取最高相似度且设阈值下限;低于阈值标未验证,不猜测 |
| 放松验证后人工审核工作量增大 | Medium | Medium | 片段按核验等级排序展示,exact/normalized 优先,similarity 靠后 |

---
*Status: DRAFT — requirements only. Implementation planning pending via /plan.*

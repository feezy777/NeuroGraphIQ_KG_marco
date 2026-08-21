# 论文证据并行提取与实时进度设计

日期：2026-08-12  
状态：已完成头脑风暴，待用户审阅书面规格

## 1. 目标

将用户手动选择 20 篇论文后的证据提取总耗时控制在 3 分钟以内，同时保持现有证据精度与治理边界：

- 每篇论文继续执行“高召回定位 → 严格证据判定 → 原文核验”。
- 不合并不同论文的 Prompt，不允许跨论文引用证据。
- 不降低 exact / normalized / similarity 原文核验要求。
- 用户手动选择的论文全部处理，不受批处理语义预筛静默过滤。
- 单篇失败不阻塞其他论文，页面可逐篇显示进度和结果。

## 2. 当前瓶颈

当前 `extract_candidates_for_target` 外层使用串行 `for paper in selected`。虽然内部存在 fetch 和 DeepSeek semaphore，但同一时刻只处理一篇论文，因此 semaphore 没有形成论文级并发。

一篇论文通常包含：

1. 元数据核验。
2. OA 全文下载。
3. XML 解析与段落持久化。
4. 段落召回与窗口构造。
5. DeepSeek 高召回定位。
6. DeepSeek 严格判定；定位为空时执行单阶段回退。
7. 原文核验、Coverage 计算和结果持久化。

20 篇论文按上述链路串行执行时，网络和 LLM 等待时间线性累加。DeepSeek Provider 还会为每次调用创建新的 HTTP client，无法充分复用连接。

## 3. 方案选择

### 采用：受控并发流水线

- 默认同时处理 4 篇论文。
- 每篇保留完整的独立提取流水线。
- fetch 与 LLM 使用独立 semaphore。
- 通过后台 Run 持久化进度，前端轮询并逐篇展示。
- 根据真实限流和延迟数据，将 LLM 并发在 2–6 之间动态调整。

### 暂不采用：跨论文批量 Prompt

多篇论文共用 locator Prompt 可以减少调用次数，但会增加 Prompt 体积、论文身份混淆和跨论文串证据风险。第一阶段不采用。

### 暂不采用：跳过定位的自适应快速路径

直接把高分段落送入 judge 速度更快，但可能改变召回率。第一阶段不改变现有两阶段算法。

## 4. 后端架构

### 4.1 API

新增异步提取接口：

- `POST /api/ontology/evidence/extraction-runs`
  - 请求沿用当前 target、papers、mode、only_oa 等字段。
  - 立即返回 `run_id`、`status=queued`、`total_items`。
- `GET /api/ontology/evidence/extraction-runs/{run_id}`
  - 返回 Run 汇总和逐篇 Item 状态。
- `POST /api/ontology/evidence/extraction-runs/{run_id}/cancel`
  - 取消尚未开始的 Item；正在进行的网络调用完成当前安全点后停止。
- `POST /api/ontology/evidence/extraction-runs/{run_id}/retry-failed`
  - 仅重新排队失败 Item。

保留现有同步 `/evidence/extract-selected` 作为兼容入口；证据中心前端切换到新接口。

### 4.2 持久化模型

新增 extraction run：

- id
- target_type / target_id
- mode
- status：queued / running / completed / partially_failed / failed / cancelled
- total_items
- completed_items
- evidence_hit_items
- no_evidence_items
- failed_items
- requested_concurrency
- active_concurrency
- request_json
- started_at / finished_at / created_at / updated_at

新增 extraction run item：

- id / run_id
- paper identity：pmid / pmcid / doi
- title / metadata snapshot
- status：queued / fetching / parsing / retrieving / locating / judging / verifying / completed / no_evidence / failed / cancelled
- progress_percent
- attempt_count
- result_json
- error_code / error_message
- stage_timings_json
- started_at / finished_at / updated_at

Run 与 Item 均使用手写 SQL migration，符合项目现有迁移约束。

### 4.3 执行器

后台执行器使用固定 worker queue，而不是一次创建 20 个无界任务：

- paper worker：默认 4。
- metadata/fulltext semaphore：默认 6。
- DeepSeek semaphore：默认 4。
- 每个 worker 创建独立 `AsyncSession`，禁止并发共享请求级 session。
- 每篇论文单独事务提交；一个 Item 失败不会回滚其他 Item。
- 使用 `return_exceptions=True` 或等价的隔离机制收集 Item 结果。

每篇 worker 复用现有：

- 元数据和全文获取。
- OA XML 解析。
- `score_paragraphs` / `build_windows`。
- `extract_passage_two_stage`。
- 原文核验、Coverage 和结果结构。

### 4.4 动态并发

初始 DeepSeek 并发为 4：

- 发生 429、连接超时或服务端 5xx 时，将并发降至 2，并使用带抖动的指数退避。
- 稳定窗口内连续成功后逐步恢复至 4。
- 第一阶段硬上限为 6，禁止无限提高。
- 重试只重试失败阶段或当前 Item，不重新处理已经完成的论文。

### 4.5 缓存与连接池

- 查询 `paper_sources` 与 `paper_passages`；缓存完整时跳过元数据下载、全文下载和 XML 解析。
- 缓存不完整时只补缺失部分。
- Paper fetch 与 DeepSeek Provider 使用可复用的 `httpx.AsyncClient` 连接池。
- 连接池生命周期由应用或服务管理，关闭时统一释放。
- 缓存键使用规范化 PMID / PMCID / DOI，避免同一论文重复下载。

## 5. 前端进度体验

用户点击“提取所选论文”后：

1. 创建 Run 并获得 `run_id`。
2. 每 1 秒轮询 Run；页面刷新后可通过 URL 或 Context 中的 `run_id` 恢复。
3. 主进度显示：
   - `已完成 8/20 · 40%`
   - `命中 3 · 无证据 4 · 失败 1 · 处理中 4`
   - 已用时间
4. 逐篇状态显示：
   - 等待中
   - 获取全文
   - 解析全文
   - 召回段落
   - 定位候选
   - 严格判定
   - 原文核验
   - 已命中 N 个片段 / 未发现证据 / 失败
5. 某篇完成后立即展示结果，不等待整个 Run。
6. Run 完成后保留“仅重试失败论文”操作。

总体进度以各 Item 的阶段进度平均计算，同时始终展示确定性的 `completed/total`，避免只有模拟百分比。

## 6. 精度与治理保护

- 模型、temperature、Prompt、窗口数量和 judge top-K 保持不变。
- 每次 LLM 调用仅包含一篇论文的段落。
- Paper identity 贯穿 Prompt、结果和数据库记录。
- 所有入选片段继续执行本地原文核验。
- `source_verified=false` 的片段不得自动进入正式证据。
- LLM 结果仍只进入候选与人工审核流程，不直接写 Final KG。
- 并发完成顺序不得影响最终论文去重、片段去重和排序。

## 7. 错误处理

- 论文源不可用：记录当前 Item 失败，其他 Item 继续。
- DeepSeek 429：降低并发并重试当前 Item。
- DeepSeek 超时或 5xx：按现有次数重试，耗尽后标记失败。
- JSON 解析失败：执行现有兼容解析或回退，不将错误误报为 `no_evidence`。
- 全文缺失：保留摘要提取路径。
- 服务重启：持久化 Run 可识别中断 Item；将中断项恢复为可重试状态。
- 取消：不删除已经完成的结果，只取消 queued Item。

## 8. 验收标准

### 8.1 性能

- 使用固定的 20 篇混合论文连续运行 3 次。
- 冷缓存总耗时不超过 3 分钟。
- 热缓存耗时应低于冷缓存。
- 单篇完成后 1 秒内更新到前端。
- 单篇失败不阻塞其余论文。
- 记录 fetch、parse、retrieve、locate、judge、verify 各阶段耗时。

### 8.2 精度

- 使用已有人工结论的基准论文。
- 串行基准与并发版本使用相同模型及参数。
- `source_verified` 片段集合不得减少。
- direction、evidence_level、supported_components 不得出现系统性漂移。
- 不同论文之间不得发生 passage 或 paper identity 串联。
- 覆盖 429、超时、畸形 JSON、全文缺失的故障注入测试。
- 若精度验收失败，即使速度达标也不得上线。

## 9. 测试范围

- 单元测试：Run/Item 状态机、进度聚合、并发限制、动态降并发。
- 服务测试：20 个 worker 中的最大同时 LLM 调用数不超过配置。
- 集成测试：缓存命中与未命中、独立事务、失败隔离、重试失败项。
- API 测试：创建、查询、取消、重试以及权限。
- 前端测试：进度条、逐篇状态、刷新恢复、部分失败和完成结果增量展示。
- 基准测试：串行与并发版本对同一 20 篇输入比较时间和证据结果。

## 10. 实施顺序

1. 新增 Run/Item migration、schema 和只读状态接口。
2. 抽取单论文 worker，使其可使用独立 session 运行。
3. 加入默认 4 路 worker queue 和并发保护。
4. 接入缓存与 HTTP 连接池复用。
5. 前端切换异步创建 Run，并增加进度条和逐篇状态。
6. 补齐故障测试与 20 篇基准测试。
7. 根据真实结果决定是否将并发从 4 调整为 5/6。

## 11. 非目标

- 不修改证据 Prompt。
- 不更换 LLM 模型。
- 不跨论文批量提交 Prompt。
- 不改变 Mirror KG → Human Review → Promotion 治理链路。
- 不在本阶段增加分布式队列或外部消息中间件。

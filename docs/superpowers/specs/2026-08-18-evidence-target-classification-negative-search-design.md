# 佐证流程:非神经靶标治理 + 自动反向检索 设计

- **日期**: 2026-08-18
- **状态**: 设计已与用户逐项确认(范围=④+②,方案 A:佐证流程层治理;④ 自动标记+人工确认;② 自动反向检索)
- **背景**: DeepSeek 对「右旁中央小叶 → 右侧脑室」投射验证的改进建议(连接类型分类/反向验证/证据等级/非神经靶标),本次落地其中两项:非神经靶标治理(④)+ 自动反向检索(②)。

---

## 1. 背景与问题

- 知识图谱中存在「脑区 → 脑室」这类**解剖学上不可能的连接**(如「右旁中央 → 右侧脑室」):侧脑室是充满脑脊液的空腔,不是神经核团,不存在神经纤维投射。
- 这类对象当前仍跑完整论文检索 → 必然 no_evidence_found → 反复人工处理,浪费 LLM/检索成本,且结论不明确(「无证据」≠「证据否定」)。
- 「无证据」与「证据否定」未区分:正向检索搜不到 ≠ 论文明确说无此连接;后者是更强的结论,应单独标记。

## 2. 目标

1. **④ 非神经靶标治理**:识别靶标为非神经结构(脑室/脑脊液/脑膜/脉络丛等)→ 对象自动标记「结构性不存在」,跳过论文检索,直接人工确认(确认不存在 / 误判继续检索)。
2. **② 自动反向检索**:正向检索无结果时,自动用否定向查询再搜一轮 → 区分「证据否定」(论文明确否定)与「无证据」(确实没找到)。
3. 治理结论留在佐证侧,不动镜像数据(镜像行是上游提取产物,不被佐证流程改写)。

## 3. 非目标

- 不做连接类型分类检索(解剖投射/功能连接/结构共变)——留待后续。
- 不做证据等级标注(弱证据/强证据)——留待后续。
- 不改镜像表结构/数据;不改证据晋升流程(否定证据确认后不进晋升,仅留痕)。
- 数据中心展示不变。

## 4. 设计

### 4.1 非神经靶标分类器(新模块 `backend/app/services/evidence_target_classifier.py`)

```python
TargetKind = 'neural' | 'non_neural' | 'unknown'

def classify_target(region_name_cn: str | None, region_name_en: str | None) -> TargetKind
```

- 中英关键词匹配(子串匹配,大小写不敏感):
  - 脑室:`ventricle` / `脑室`(侧脑室、第三/第四脑室…)
  - 脑脊液/蛛网膜下腔:`cistern` / `csf` / `subarachnoid` / `脑脊液` / `池`
  - 脑膜:`meninges` / `dura` / `pia` / `脑膜`
  - 其它非神经:`choroid plexus` / `脉络丛`、`falk` / `tentorium`
- 命中 → `non_neural`;未命中 → `unknown`(按神经处理,不误杀)。
- 纯函数、无 DB、可单测。

### 4.2 流程接入(④)

- **创建 item 时**(`create_batch_task` 的 per-object 循环):判定靶标(`_batch_scope_label` 拿到的名称或镜像行 target_region)→ `non_neural` → item 直接写入 `preprocess_outcome='non_neural_target'`、状态 `awaiting_review`,**不调度后台论文检索**。
- **对象卡/任务卡**:新徽章「结构性不存在:靶标为非神经结构」。
- **人工确认页**(进入对象后,当 `preprocess_outcome='non_neural_target'` 时替代候选工作区):
  - 「确认不存在」→ 审计记录 + item 标记 `evidence_negated`(等同证据否定,留痕;不入晋升)。
  - 「误判,继续检索」→ 清除 `non_neural_target` 标记,恢复普通流程(重新预处理/手动搜索)。
- 反向检索(§4.3)对非神经靶标对象不触发(已跳过检索)。

### 4.3 自动反向检索(②)

- **查询构造**:`build_search_query` 增加 `negative: bool = False` 参数。`negative=True` 时连接词替换为否定式:
  - 正向:`"X" AND "Y" AND (projection|connect|fiber|…)`
  - 否定:`"X" AND "Y" AND (no projection|does not connect|absence of connection|not connected|…)`
- **触发**:预处理正向检索无结果(no_evidence_found / EUROPE_PMC_NO_RESULT)且靶标非非神经时,自动用否定向查询再搜一轮(同论文数限制、同提取流程)。
- **分流**:
  - 否定向搜到论文 → 正常提取(方向自然标 `contradicts`)→ item `preprocess_outcome='evidence_negated'`,候选卡片带 contradicts 徽章,可进入审核(方向=contradicts)→ 人工确认后标记证据否定。
  - 否定向也无结果 → 保持 `no_evidence_found`(提示可手动继续搜)。
- **成本**:仅正向无结果的对象多一轮检索。

### 4.4 前端

| 元素 | 行为 |
|---|---|
| 任务/对象卡徽章 | 「结构性不存在」「证据否定」「无证据」新状态 chip(灰/红/橙) |
| 人工确认页 | 非神经靶标对象进入后显示确认卡(确认不存在 / 误判继续检索),不显示候选工作区 |
| 候选卡片 | contradicts 徽章复用现有 direction 展示 |
| 审核 | 否定证据方向=contradicts 正常走审核,确认后标记 |

### 4.5 状态语义

- `preprocess_outcome='non_neural_target'`:靶标非神经,结构性不存在(待人工确认)。
- `preprocess_outcome='evidence_negated'`:有论文明确否定该连接(证据否定,待人工确认)。
- `preprocess_outcome='no_evidence_found'`:正反检索均无结果(无证据)。
- 三者均不自动写入正式证据;人工确认后仅审计留痕。

## 5. 文件改动清单

| 文件 | 改动 |
|---|---|
| `backend/app/services/evidence_target_classifier.py` | 新增:分类器(名单+关键词+`classify_target`) |
| `backend/app/services/paper_evidence_service.py` | `create_batch_task` 判定靶标并跳过检索;`build_search_query` 加 `negative` 参数;预处理无结果时自动反向检索;新 outcome 状态 |
| `backend/app/services/paper_evidence_extraction_run_service.py` | 手动提取 run 的正向无结果也触发反向检索(可选,与预处理一致) |
| `frontend/src/pages/evidence-center/components/taskStatus.ts` | 新状态徽章标签与色调 |
| `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx` | 非神经靶标确认页(确认不存在/误判继续检索);contradicts 徽章 |
| `frontend/src/styles.css` | 新 chip 样式 |
| 测试 | 分类器单测、流程测试(见 §6) |

## 6. 测试计划

- **分类器单测**:脑室/脑膜/脉络丛中英文命中;正常脑区(杏仁核/皮质层/脑干核团)不误伤;未知名回退 `unknown`。
- **流程测试**:
  - 非神经靶标任务创建 → item 直接标记 `non_neural_target`、不调度检索。
  - 误判恢复:清除标记后重新进入普通流程。
  - 反向检索命中 → `evidence_negated` + contradicts 候选;未命中 → 保持 `no_evidence_found`。
  - 反向证据审核确认 → 审计留痕。
- **回归**:现有证据测试全绿(分类器默认 `unknown` 不改变现有行为;正向命中对象不触发反向检索)。

## 7. 用户确认记录

- 范围:④(非神经靶标治理)+ ②(自动反向检索),方案 A(佐证流程层治理)。
- ④ 行为:自动标记「结构性不存在」+ 人工确认(确认不存在 / 误判继续检索)。
- ② 行为:正向无结果时自动否定向检索;搜到 → 证据否定;仍无 → 无证据。

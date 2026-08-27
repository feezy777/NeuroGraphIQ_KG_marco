# NeuroGraphIQ 验证中心产品需求文档（PRD）V1.0

| 项目 | 内容 |
|------|------|
| 产品名称 | NeuroGraphIQ Knowledge Validation Center |
| 模块 | 验证中心 |
| 版本 | V1.0 |
| 产品定位 | Final KG 入库前的知识质量治理平台 |
| 核心目标 | 建立「候选知识 → 证据验证 → 专家审核 → Final KG」的可追溯闭环 |

---

## 1. 产品背景

当前知识图谱构建流程中，知识来源包括：

- LLM 自动提取；
- 文献发现；
- 数据库导入；
- 人工整理。

但直接将候选知识进入 Final KG 存在风险：

- LLM 可能产生错误连接；
- 论文共现不代表真实关系；
- 缺少人工专家确认；
- 缺少证据链绑定；
- 无法解释知识来源。

因此需要建立验证中心，对所有进入正式知识图谱的内容进行质量治理。

## 2. 产品定位

验证中心不是简单审核页面，而是：

> 一个面向知识图谱生产的质量控制（Quality Control）和证据治理（Evidence Governance）系统。

核心职责：

- 管理待验证知识任务；
- 管理论文和证据资产；
- 自动发现候选证据；
- AI 辅助语义判断；
- 专家最终确认；
- 生成完整 provenance；
- 控制 Final KG 晋升。

## 3. 总体流程设计

### 3.1 知识生命周期

```
Candidate Knowledge
        ↓
Task Center（任务管理）
        ↓
Paper Library（论文资产）
        ↓
Evidence Candidate（证据发现）
        ↓
Rule Validation（规则检查）
        ↓
AI Review（语义辅助审核）
        ↓
Human Review（专家审核）
        ↓
Evidence Promotion（最终晋升）
        ↓
Final KG（正式知识）
```

## 4. 验证中心页面结构

验证中心包含五个核心页面：

```
验证中心
├── 任务中心
├── 论文库
├── 证据候选
├── 人工审核
└── 证据晋升
```

### 页面一：任务中心（Task Center）

#### 1. 产品目标

任务中心负责管理所有进入验证流程的知识对象。

支持对象：

- Connection Candidate
- Circuit Candidate
- Function Candidate
- Evidence Candidate

#### 2. 核心功能

##### 2.1 当前任务

展示：待验证任务 / 验证中任务 / 待审核任务。

支持：创建任务、查询任务、编辑任务、删除任务、开始验证。

##### 2.2 任务卡片

```
Thalamus proper
        ↓
Precentral

类型:       Connection Candidate
来源:       Macro Paper Discovery
Supporting Papers: 36
AI Result:  SUPPORTED
Rule:       PASS
状态:       待人工审核
```

##### 2.3 历史任务

保存：已审核任务 / 已拒绝任务 / 已晋升任务。

展示：知识对象、最终状态、审核人员、完成时间、审核次数。

##### 2.4 回退机制

历史任务支持 Rollback。

回退原因：证据不足 / 审核错误 / 本体调整 / 新证据冲突。

回退后重新进入：

```
Rule Validation
↓
AI Review
↓
Human Review
↓
Promotion
```

### 页面二：论文库（Paper Library）

#### 1. 产品目标

论文库作为系统级科研文献资产中心。论文进入系统后永久保存，避免重复调用 LLM。

#### 2. 数据来源

论文来源：LLM 搜索发现 / PubMed / Europe PMC / OpenAlex / Semantic Scholar / Crossref / 人工添加。

#### 3. 核心流程

```
LLM发现论文 → 论文去重(PMID / DOI) → 保存数据库 → 全文解析 → 生成证据 → 供验证流程复用
```

#### 4. 功能需求

- **增删改查**：支持新增论文（PMID / DOI / URL）；自动获取标题、作者、年份、期刊、摘要、全文。
- **论文详情**：
  - 基础信息：Title / Authors / Journal / Year / PMID / DOI
  - 内容信息：Abstract / Full text / Sections
  - 证据信息：该论文产生的所有 evidence

### 页面三：证据候选（Evidence Candidate）

#### 1. 产品目标

负责从论文中发现可能支持知识的证据片段。不是最终判断。

#### 2. 证据发现流程

```
Paper Library → 文本处理 → 规则检索 → 候选片段 → LLM语义审核 → Evidence Candidate
```

#### 3. 证据发现方式

- **主要方式（规则/算法）**：脑区实体匹配 / 连接词识别 / 关系模式匹配 / 章节定位
- **LLM 辅助**：复杂语义判断 / 难解析关系 / 辅助搜索；不直接生成最终知识

#### 4. 页面展示

- 左侧（知识对象）：Thalamus ↓ Precentral；Connection Type: Projection
- 中间（证据片段）：Paper / Section / Original Text（如 "The thalamic projection reaches..."）
- 右侧（AI 分析）：Decision: SUPPORTED；Confidence: 0.91；Reason: 明确描述结构连接

### 页面四：人工审核（Human Review）

#### 1. 产品目标

人工审核是专家最终裁决环节：判断知识是否可信、调整置信度、绑定正式证据。

#### 2. 审核输入

① 候选知识：Source / Target / Connection Type / Direction
② 规则验证：Region Exists ✓ / Type Valid ✓ / Duplicate Check ✓
③ AI 审核结果：SUPPORTED / Confidence: 0.91 / Reason: 论文明确描述
④ 原始论文证据（必须展示）：论文 / PMID / DOI / Section / 原文片段

#### 3. 审核结果

- **Confirmed**：确认进入晋升
- **Weak Evidence**：证据不足，继续补充
- **Rejected**：拒绝
- **Modify**：修改 Connection Type / Direction / Confidence

#### 4. 证据绑定

审核通过后生成：

```
Connection
↓
Evidence Bundle
├── Paper
├── PMID
├── DOI
├── Sentence
├── Section
├── Reviewer
└── Confidence
```

### 页面五：证据晋升（Evidence Promotion）

#### 1. 产品目标

Final KG 入库前最终质量闸门。

#### 2. 核心职责

整合：规则验证 / AI 审核 / 人工审核 / 论文证据 / provenance，进行最终确认。

#### 3. 页面展示

- **知识摘要**：Thalamus ↓ Precentral；Type: Structural Projection
- **验证流水线**：Candidate Created ↓ Rule PASS ↓ AI SUPPORTED ↓ Human APPROVED ↓ Promotion READY
- **证据汇总**：论文数量 36 / 证据数量 56 / 直接证据 12
- **晋升门禁**（必须满足）：
  - ✓ Rule Validation PASS
  - ✓ AI Review Complete
  - ✓ Human Approved
  - ✓ Evidence Exists
  - ✓ No Duplicate
  - ✓ Provenance Complete

#### 4. 晋升操作

按钮：确认进入 Final KG / 退回人工审核 / 拒绝晋升。

#### 5. 回退

Final KG 后仍支持 Rollback。记录：原状态 / 新状态 / 原因 / 操作者 / 时间。

## 5. 全局状态模型

```
Created
↓
Rule Pending
↓
Rule Passed
↓
AI Review
↓
Human Review
↓
Approved
↓
Promotion Ready
↓
Promoted
↓
Final KG

任何阶段: Rollback
```

## 6. 设计原则

1. **原则1：论文资产化**——论文进入系统后，不重复搜索。
2. **原则2：证据优先**——所有 Final KG 知识必须绑定论文、原文片段、审核记录。
3. **原则3：AI 辅助，人类裁决**——LLM 负责发现和辅助判断；专家负责最终确认。
4. **原则4：全过程可追溯**——每条知识必须回答：来自哪篇论文？哪句话支持？谁审核？为什么进入 Final KG？何时被修改？

## 7. 第一阶段开发优先级

建议按数据链打通：

- **Phase 1**：任务中心 ↓ 论文库 ↓ 证据候选——让一个 Connection Candidate 完整显示：论文 → 证据片段
- **Phase 2**：人工审核——实现：证据绑定 + confidence 调整
- **Phase 3**：证据晋升——实现：Final KG 发布门禁
- **Phase 4**：历史、回退、再审核完善

> 本 PRD 作为验证中心后续构建的产品设计依据（Claude Code 可直接引用）。

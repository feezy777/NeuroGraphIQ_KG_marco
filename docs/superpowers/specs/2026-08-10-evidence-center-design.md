# 论文证据中心(Evidence Center)重构设计

日期:2026-08-10
状态:待用户确认

## 1. 背景与目标

`EvidenceReviewModal.tsx`(约 1150 行)同时承担对象队列、论文检索、论文候选、AI 提取、Passage、Coverage、Reviewer、Confidence、Attach 和队列导航,职责过多,且以底部弹窗承载完整业务。

本轮目标:迁移为独立一级页面 `/evidence-center`「论文证据中心」,五个业务模块(佐证任务/论文库/证据候选/人工审核/证据晋升),明确区分:

- **任务是什么**(佐证任务)
- **论文是什么**(论文库,真实 Paper 资源)
- **AI 找到的佐证是什么**(证据候选)
- **人工审核是什么**(人工决策)
- **正式晋升是什么**(正式 Evidence + confidence 应用)

**不改动**:Europe PMC、DeepSeek、Paper/Passage、source verification、attach、rollback、confidence 公式、批量任务后端逻辑。

## 2. 核心设计原则

### P1. AI 推荐,人工决策(最高原则)
- DeepSeek 全程只提供**推荐**:候选片段、model_direction、evidence_level、confidence、supported_components、coverage 判断
- **最终决策 100% 由人工**:方向、证据等级、置信度、组件归属、是否采纳/晋升,全部人工确定
- UI 上 AI 推荐与人工最终值**视觉区分**:AI 值灰字标注"AI 推荐",人工修改后高亮"人工确认"
- 置信度:AI semantic confidence 仅供参考,图谱 confidence 只由人工 reviewer_confidence 经公式计算

### P2. 模块职责严格隔离
- 论文库 = Paper Resource(禁 Reviewer/Coverage/Attach)
- 证据候选 = AI Candidate Evidence(禁改 confidence、禁 attach)
- 人工审核 = Human Decision(禁搜索控件、禁写库)
- 证据晋升 = Formal KG Evidence Application(唯一 attach 入口)

### P3. 迁移复用不重写
- 现有成熟逻辑(ClaimPanel/PassageEvidenceCard/CoveragePanel/ReviewerPanel/claimCoverage/types 等)移动复用,不复制第二份

### P4. 高自由度 + 明确反馈
- 人工可自由:多论文多片段混合审核、任意增删片段、修改一切决策值、重新截取
- 每个按钮功能明确,主操作(开始处理/加入审核/确认晋升)突出,辅助操作弱化

## 3. 路由与页面架构

### 路由
```
#/evidence-center?module=tasks|papers|candidates|review|promotion&task_id=&target_type=&target_id=&paper_id=
```
- 现有自研 hash 路由(`App.tsx` ROUTES 表)加 `/evidence-center` → `EvidenceCenterPage`
- module/task/target/paper 四级定位全部进 URL(与 data-center `?tab=` 同模式)
- 大数据(passages/draft)不进 URL:sessionStorage + 后端 draft 恢复

### 侧边栏
- `WorkbenchLayout.tsx` 导航数组加 `{ path: '/evidence-center', labelKey: 'nav.evidenceCenter' }`
- `i18n.ts` 加「论文证据中心」

### 页面结构
```
EvidenceCenterPage
├── EvidenceCenterHeader    # 模块导航(5) + 返回数据中心 + 颗粒度跟随(全局)
├── 当前模块内容区
└── EvidenceCenterContext    # 页面级 Provider
```

### 入口切换
- 数据中心勾选对象 →「论文佐证」→ `navigate(#/evidence-center?target_type=&target_id=&task_id=)`
- `EvidenceReviewModal` 保留为兼容壳:仅 open/onClose,内部渲染跳转链接/自动 navigate;不再承载业务
- 返回数据中心:Header 按钮 → `#/data-center?tab=<来源tab>`(route state 可用则恢复 granularity/filters)

## 4. 五个模块职责

### ① 佐证任务(EvidenceTasksModule)
- 职责:"哪些知识对象需要论文佐证,任务处理到哪里"
- 数据:`GET /api/ontology/evidence/batch`(列表)、`GET .../batch/{task_id}`、`GET .../batch/{task_id}/items`
- 展示:状态分组(待处理/预处理中/待人工审核/已审核/已完成/失败)
  - 列:对象名称 / target_type / current confidence / paper evidence count / preprocess status / review status / task status
- 操作:开始人工处理 / 创建批量预处理(CreateBatchTaskDialog)/ 打开已有任务 / 跳转待审核
- 禁止:论文全文、Passage、Reviewer Confidence

### ② 论文库(PaperLibraryModule)
- 职责:展示真实 Paper 资源,数据源以 `paper_sources` 为中心
- 数据(新增只读 API):
  - `GET /api/ontology/evidence/papers?search=&oa=&year=&has_fulltext=&page=&page_size=` → 分页列表
  - `GET /api/ontology/evidence/papers/{paper_id}` → 详情(metadata + abstract + section 段落 + 关联 evidence 数)
- 列表列:搜索 / OA / 年份 / 已解析全文 / PMID/PMCID/DOI / Journal / Abstract availability / OA fulltext availability / paragraph count
- PaperCard 点击 → PaperDetailDrawer(metadata / abstract / 全文 section 结构 / paragraph 数 / 关联 Evidence/Target 数)
- 禁止:Reviewer Confidence、Coverage、Attach、Reviewer Direction

### ③ 证据候选(EvidenceCandidatesModule)
- 职责:展示 DeepSeek 从论文中生成的 AI 证据候选
- 数据:`GET .../batch/{task_id}/items`(candidate_papers)、`GET .../batch/items/{item_id}/draft`、手动提取 `POST /api/ontology/evidence/extract-selected`
- 布局:左侧待处理对象队列(240px);主区域:当前 Claim + Claim Components + Candidate Papers
- 每个 Candidate Paper 显示:Paper metadata / model_direction / coverage / passage count / source verification count
- 操作:查看候选证据 / 加入人工审核(勾选片段)/ 排除 / 重新提取
- 禁止:修改 confidence、正式 attach

### ④ 人工审核(EvidenceReviewModule)
- 职责:回答唯一问题——"这些已核验原文是否足以支持当前 Claim?"
- 数据:候选载入 passages + `GET /api/ontology/evidence/target/{tt}/{tid}`(Claim DTO)
- 布局:左/中主区域 = Claim + Components + Paper + 全部选中 Passage(原文/翻译/evidence level/supported_components/verification)+ Coverage
- 右侧固定 ReviewerDecisionPanel(380px):Reviewer Direction / Overall Evidence Level / Reviewer Confidence / Reviewer Note / Confidence Preview
- AI 推荐展示:model_direction、AI confidence、coverage —— 灰字"AI 推荐",人工修改后高亮"人工确认"
- 操作:「返回证据候选」(可追加/移除论文与片段)、保存草稿(后端 autosave + sessionStorage)
- 禁止:Europe PMC 搜索控件、写库

### ⑤ 证据晋升(EvidencePromotionModule)
- 职责:将人工审核通过的证据正式应用到知识图谱
- 数据:`POST /api/ontology/evidence/attach-preview`、`POST /api/ontology/evidence/attach`、`GET /api/ontology/evidence/list`、`POST /api/ontology/evidence/{id}/rollback`
- 分组:待晋升 / 已晋升 / 已失效
- 展示:Claim / Paper / Coverage / Reviewer Decision / Reviewer Confidence / 当前 confidence / 预计应用后 confidence
- 操作:确认晋升(原 attach,文案统一「确认晋升」)/ 回滚 / Evidence Detail / Evidence→Target 导航
- 本轮 review 与 attach 未拆开:审核通过的证据在本模块执行 attach;`review_approved → awaiting_promotion` 独立状态留阶段 2

## 5. 组件迁移清单

### 移动(evidence-workbench/ → evidence-center/components/)
| 组件 | 新用途 |
|---|---|
| `ClaimPanel` | 候选/审核/晋升三模块展示 Claim |
| `PassageEvidenceCard` | 候选/审核片段卡 |
| `CoveragePanel` | 候选/审核/晋升覆盖度 |
| `ReviewerPanel` | 拆为 `ReviewerDecisionPanel`(人工审核右侧) |
| `AttachDialog` | 改名 `PromotionDialog`(证据晋升确认) |
| `CreateBatchTaskDialog` | 佐证任务模块 |
| `claimCoverage.ts` / `types.ts` | 计算与类型 |

### 新建
`EvidenceCenterPage` / `EvidenceCenterHeader` / `PaperCard` / `PaperDetailDrawer` / `EvidenceCandidatesPanel` / `ConfidencePreview` / `EvidenceDetailDrawer` / `EvidenceCenterContext`

### 兼容壳
`EvidenceReviewModal.tsx` 保留 open/onClose 签名,内部改为跳转 `/evidence-center`(保留原测试可过),不再 import 迁移后的业务组件。

## 6. 状态管理(EvidenceCenterContext)

```ts
interface EvidenceCenterState {
  module: 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'
  taskId: string | null
  targetType: string | null
  targetId: string | null
  paperId: string | null
  queue: QueueEntry[]                     // 佐证任务队列
  currentDraft: WorkbenchDraft            // 审核草稿
  reviewState: { passages; direction; evidenceLevel; confidence; note; selectedHashes; modelRecommendations }
  extractionResults: Record<pmid, ExtractionResult>  // 候选提取结果(候选→审核传递)
}
```
- URL 双向同步 module/task/target/paper
- draft:sessionStorage + 后端 autosave(500ms debounce)+ 手动保存;刷新从后端恢复
- granularity 跟随全局 `GranularityProvider`,不重复选择器

## 7. API 补充(最小只读)

1. `GET /api/ontology/evidence/papers` — paper_sources 分页列表(搜索/OA/年份/已解析全文过滤;聚合 paragraph count、evidence count)
2. `GET /api/ontology/evidence/papers/{paper_id}` — 详情(metadata + abstract + paper_passages section 结构 + 关联 evidence 列表)
- 只读,不改 Paper 模型;其余全部复用现有接口

## 8. 视觉规范

- 每模块顶部说明句(如:论文库 = "管理系统已经获取和解析的真实论文资源。")
- 视觉层级:模块标题(一级)/ Claim·Paper·Evidence 卡(二级)/ 技术字段弱化灰字(三级:PMID、paragraph_id、semantic confidence 不占主视觉)
- 布局:全宽工作区;左队列固定 240px;主内容 flex;Reviewer 区域 380px;长 Passage 折叠;Paper Detail 用 Drawer;确认用 Dialog
- 主操作按钮统一 `btn-primary`:开始处理/加入审核/确认晋升;辅助 btn-xs 灰阶
- 状态色:待处理灰/预处理中蓝/待审核琥珀/已晋升绿/已失效红(复用 StatusBadge)

## 9. 测试计划(vitest)

1. `/evidence-center` 路由渲染 + 五模块导航
2. 数据中心 → 证据中心(URL 参数)+ 返回数据中心
3. URL 刷新恢复(module/task/target)
4. 佐证任务列表(状态分组)
5. Paper Library 列表 + Detail Drawer(mock API)
6. 候选模块:对象队列 + 候选展示 + 加入审核/排除/重新提取
7. 候选 → 审核 → 候选往返,草稿不丢失
8. 审核 → 晋升:attach 从晋升模块执行 + 「确认晋升」文案
9. Evidence Detail + rollback
10. batch/manual queue 恢复 + granularity 跟随
11. 既有 EvidenceReviewModal 测试全保留(兼容壳)回归
12. `npm run build` + 后端 evidence 测试全回归

## 10. 阶段 2 预留(本轮不做)

- `review_approved → awaiting_promotion` 独立后端状态
- review 与 attach 状态机拆分
- 后端 review 表与 evidence 表解耦

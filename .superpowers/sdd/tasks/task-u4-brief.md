### Task U4: 其余四模块同语言(Review/Promotion/Tasks)

**Files:**
- Modify: `modules/EvidenceReviewModule.tsx`(标题体系「人工审核」;中栏分区 Claim+Paper+Passage+Coverage;右栏 ReviewerDecisionPanel 严格分区:AI初判(模型方向/Coverage)/分隔线/人工最终判断(方向/等级/置信度/备注)/分隔线/置信度影响(Current/Reviewer/Rule/Maximum/Final)/sticky[驳回][审核通过];无搜索控件)
- Modify: `modules/EvidencePromotionModule.tsx`(右栏 PromotionImpact:当前/Reviewer/晋升后 Confidence + Evidence数 + Passage数 + 最终状态;sticky[退回人工审核][确认晋升];Primary 仅确认晋升)
- Modify: `modules/EvidenceTasksModule.tsx` + `components/TaskSummary.tsx`(同语言:标题/间距/卡片)
- Modify: `styles.css`(review/promotion/tasks 组件样式统一)
- Test: 三模块视觉类断言 + 全量回归

**提交:** `style(evidence-center): Review/Promotion/Tasks 模块统一视觉语言`

---


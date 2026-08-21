# Task Report: Evidence Center CSS 优化

**Date**: 2026-08-11
**Scope**: `frontend/src/styles.css` 证据中心区块(约 11365-12424)+ 少量组件 className 微调
**Constraint**: 布局/功能零变化,全部 167 项测试通过,`tsc`/`build` 通过

## 1. 优化清单

### 合并 / 清理
| 项目 | 处理 |
|------|------|
| `.evidence-center` 重复定义(两处:11366 flex 列 + 12300 高度) | 合并为单条(高度 + flex 列) |
| `.evidence-task-row { cursor: pointer }` 重复规则(11471) | 并入基础规则 |
| 死类 `.evidence-center-body`(11393) | 删除 |
| 硬编码 `44px` 高度计算(12301) | 新增 `--main-padding-y: 22px` token,`.main` padding 与 `calc(... - 2 * var(--main-padding-y))` 双向引用,消除魔法数字 |
| 旧版佐证工作台死类(约 40 个:`evidence-review-panel/body`、`evidence-workbench`、`ew-header/resize/object-info/progress/step-label/actions/body/left*/queue*/status*/center/stepper/step/chips/chip/paper/paper-active/right/radio/bottom` 等) | 删除(已核对无任何引用) |
| 旧候选模块死类(约 25 个:`evidence-candidates-queue*`、`evidence-candidate-paper*`、`evidence-candidates-manual*`、`evidence-candidate-badge*`、`evidence-promotion-actions`) | 删除 |
| **保留**:`dc-evidence-*`、`pev-*`(数据中心/验证中心使用)、`ew-meta/oa/busy/passage*/ok/bad/warn/dimension-badge/section/field/preview*/trans`(PaperEvidenceColumn 与 PassageEvidenceCard 使用) | 原样保留并令牌化 |
| 硬编码色值(状态色以外)收敛到 `:root` 新 token | `--bg-soft`、`--selected-bg`、`--info-bg`、`--success-bg/fg`、`--warning-bg/fg`、`--danger-bg`、`--muted-bg` |

### 新增样式(此前无样式定义的 13+ 类)
`ew-level-badge`、`ew-passage-direction`、`ew-passage-context`(+summary/p)、`ew-reselect`、`ew-claim-text`、`ew-claim-meta`、`ew-components`、`ew-component-chip(+optional, em)`、`ew-coverage-list`、`ew-coverage-row`、`ew-overall`、`ew-claim-panel`、`ew-field label`、`evidence-queue-head gap`、`evidence-step-pill.done`

## 2. 视觉决策(按组件区域)

| 区域 | 决策 |
|------|------|
| 模块导航胶囊 | 默认透明(header 白底上更干净),hover = 主色浅底 + 主色描边,active = 实心主色 + 微投影 + 加粗;补 `:focus-visible` |
| ContextBar 信息分层 | 对象(label 14px/700 + 白色描边 chips)= 主信息;任务/进度组加 `border-left` 细分隔线 = 上下文信息;actions 右对齐 |
| StepPills 三态 | 未到态 = 灰底灰字;`done`(新增 className)= 绿色完成态;`active` = 实心主色;数字圆点随态变色 |
| 三栏骨架 | 白底栏加 1px 轻边框(灰底页面上自然分隔),保持 `230px/minmax(620px,1fr)/370px` 与 full 变体不变 |
| 卡片统一语言 | 所有卡(任务组/行、promotion 组/行、claim、search、stats、paper-card-candidate、review-paper 等)统一 `border 1px + radius 10 + shadow`;hover = 主色描边 + shadow;selected = `--selected-bg`;行元素补 `:focus-visible` |
| 徽章/状态色板 | ok/warn/bad/info/muted 五态统一映射到新 token(task-chip、queue-status、paper-badge/tag/result、stats-direction、queue-count 等全部收敛);chips 统一胶囊形(999px) |
| 字体层级 | 页面标题 15px/700,卡片标题 14px/700,正文 13px,技术性元信息(方向、query-term、paper ids、tag)11px mono + 灰底徽章;stats value 15→16px 强化 |
| 空态统一 | `evidence-task-empty` / `paper-empty` / `evidence-candidates-empty` / `evidence-promotion-empty` 统一为虚线边框白卡 |
| 抽屉 | 头渐变改用 `--bg-soft` token,close 按钮 hover 补主色浅底 + focus-visible |

## 3. 组件最小改动(必要)

- `StepPills.tsx`:为已完成步追加 `done` 修饰类(纯 className 拼接,无逻辑/结构变化),使五步流程三态可样式化
- `StepPills.test.tsx`:新增 1 个断言(done 态数量与内容)

## 4. 验证

- `npx vitest run`:**167 passed**(18 文件,含新增 done 态用例)
- `npx tsc --noEmit`:通过,0 错误
- `npm run build`:成功(chunk 体积警告为存量问题,与本次无关)
- 死类核对:脚本扫描确认 65 个目标类全部移除(注释内列举除外),高度计算仅引用 token

## 5. 说明 / 关注点

- 三栏从"无边框"恢复为"1px 轻边框":视觉上更清晰地与页面灰底分离(任务要求"三栏分隔线轻量化")
- `.ew-passage` 移除了旧 `margin-bottom: 8px`,间距统一由容器 `gap: 8px` 承担(证据中心实际间距 16px→8px,更紧凑;旧数据中心 PaperEvidenceColumn 的 `.pe-passages` 容器同理靠 gap 生效)
- 模块导航胶囊默认态从灰底改为透明,白底头部更干净
- 未改动任何布局数值(网格列宽、最大宽、sticky、队列 active 左侧竖条、左栏 claim 紧凑覆写均保留)

## 6. Critical 修复(2026-08-11):passage 卡间距恢复

- **问题**:`.ew-passage` 移除 `margin-bottom: 8px` 后,数据中心 `PaperEvidenceColumn.tsx:291` 的 `.pe-passages` 容器在 styles.css 无任何规则(无 gap),验证中心 `PaperEvidenceReviewPanel.tsx:149` 的 `ontology-detail-section`(仅 margin-top:10px,无 gap)→ 多张 passage 卡垂直间距变 0、卡片相接。
- **修复**(`frontend/src/styles.css`):
  - `.pe-passages { display: flex; flex-direction: column; gap: 8px; }`(置于 .pe-* 系列,第 11281 行)
  - `.ontology-detail-section .ew-passage + .ew-passage { margin-top: 8px; }`(最小影响方案:仅相邻 passage 兄弟节点间加间距,不影响该容器内 ul/table/pev-adjust 等其他子元素布局)
- **影响面核对**:`ontology-detail-section` 共 6 处使用(OntologyCenterPage 4 处为 ul/table 无 .ew-passage,PaperEvidenceColumn:373 与 PaperEvidenceReviewPanel:149 均为 .ew-passage 兄弟 → 规则生效且不破坏其余)。
- **验证**:`npx vitest run` 18 文件 167 用例全过;`npx tsc --noEmit` 0 错误;`npm run build` 成功(存量 chunk 警告无关)。

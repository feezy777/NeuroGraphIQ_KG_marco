# Task U1 Report: Evidence Center 页面骨架视觉重构

> 实现时间:2026-08-11 · 分支:codex/ontology-evidence · 前端 working dir:`frontend/`

## Status

**完成** — 全量测试 176/176 通过,`npx tsc --noEmit` EXIT 0,`npm run build` 成功。仅前端改动,后端零改动。

## 改动清单

### 1. 三栏骨架 + 页面背景(`styles.css` + `EvidenceCenterPage.tsx`)

- `:root` 新增 token `--evidence-bg: #f5f7fa`(视觉稿页面背景,放在现有 Evidence Center 视觉令牌块,命名规范)。
- `.evidence-center` 加 `background: var(--evidence-bg)` + `border-radius: var(--radius-md)`(浅蓝灰底面板)。
- `.evidence-center-layout` grid 改 `240px minmax(640px, 1fr) 340px`,gap 14px → 12px(紧凑)。
- `.evidence-left/.evidence-main/.evidence-right` 保留白底 + 1px `--border` + `--card-radius`,新增 `box-shadow: var(--shadow)`(少阴影)。
- **布局结构逻辑未动**:三栏高度 calc、`evidence-center-layout-full`(papers 全宽)、折叠行为、模块切换全部原样。

### 2. 模块导航胶囊(新建 `EvidenceModuleNav.tsx`)

- 从 `EvidenceCenterHeader.tsx` 拆出导航,新组件 `pages/evidence-center/components/EvidenceModuleNav.tsx`(含 `EVIDENCE_MODULES` 顺序常量)。
- Header 变为白卡容器,只渲染 `<EvidenceModuleNav moduleTitles={...} />`。
- 保留原 `data-testid="evidence-module-nav"` 与 `evidence-module-btn`(active)className 契约;新增 `aria-current="page"`。
- CSS:选中 = 蓝实底白字(不变),未选 = `--bg` 浅灰底 + `--text` 深灰字,高 34px(32-36 区间),圆角 999px,紧凑 padding 0 16px。

### 3. ContextBar 改造(`ContextBar.tsx` + `EvidenceCenterPage.tsx`)

- 整行背景 `--info-bg`(#eff6ff 浅蓝灰)。
- 左侧新结构:`[状态 Badge](evidence-context-badge)` + `[完整事实句](evidence-context-sentence)`;Badge = `taskStatus ?? '等待处理对象'`。
- 事实句来源:新增可选 prop `claimSentence`,由页面从 `candidateClaim`(candidates 模块 DTO 推送)与 queue 当前项合成 —— 新增导出纯函数 `composeClaimSentence(claimText, components, fallbackLabel)`:组件齐全时拼装「需要验证:{source} 到 {target} {relation}(方向性:{direction})」,组件不齐回退 claimText,再回退队列 label,全空返回 null。
- **不拆散字段**:props 接口原样保留,原有 label/类型/粒度/置信度/证据数/任务名/进度全部保留为紧凑 meta chips;仅原 taskStatus chip 由 Badge 取代(避免重复文本)。
- 右侧 [刷新](btn 白底描边)[返回数据中心](btn-primary 蓝主)不变。

### 4. StepPills 改造(`styles.css`,逻辑零改动)

- `deriveStep` 逻辑与 `EVIDENCE_STEPS` 不动。
- 视觉改为「圆形数字 + 文字 + 虚线连接」:pill 去掉胶囊底,`::after` 虚线连接(除末项);圆形 20px;当前 = 蓝圆白字(+ 光晕),完成 = 绿圆白字,未完成 = 浅灰圆。紧凑 padding。

## 测试

- 全量 `npx vitest run`:18 files / 176 tests 全过(evidence-center 15 files / 162 tests)。
- 新增/扩展断言:
  - 导航选中态:默认 tasks 胶囊 active、论文库非 active(`EvidenceCenterPage.test.tsx`)。
  - ContextBar 事实句渲染:页面级 DTO 组件拼装句「需要验证:R1 到 R2 存在投射连接(方向性:directed)」;组件级 `claimSentence` 渲染 + Badge 两态;`composeClaimSentence` 5 个单元用例。
  - Stepper 三态:done/active/无状态类 圆数字齐全(`StepPills.test.tsx`)。
  - 三栏背景类:页面根 `.evidence-center` 存在断言(背景/圆角由 CSS 承担,jsdom 无法断言计算样式)。
- 既有测试零修改(所有原文本/class 断言均保留语义)。

## 约束遵守

- 不改布局结构逻辑 / 不改功能逻辑 / 后端不动。
- 既有 className/data-testid 全部保留,仅新增样式类。

## Concerns

- 事实句在 review/promotion/tasks 模块回退为「需要验证:{队列 label}」(candidateClaim 仅 candidates 模块推送),待后续 U 系列若有 claim 推送扩展可增强。
- `.evidence-center` 新增圆角面板,`.main` 默认 padding(22/24)提供外距,视觉上为内嵌圆角面板,与三栏卡片层次一致。

## Commits

- `style(evidence-center): 骨架视觉重构(模块导航/ContextBar/Stepper/三栏背景)`

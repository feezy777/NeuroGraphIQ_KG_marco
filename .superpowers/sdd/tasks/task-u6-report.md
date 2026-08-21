# U6 报告:全量回归 + 分辨率验收

**日期:** 2026-08-11
**结论:** 全量回归全绿;发现 1 处分辨率缺陷(1366 横向溢出),已最小修复并单独 commit。

---

## 1. 验证命令与结果

### 1.1 前端全量

| 命令 | 结果 |
|------|------|
| `npx vitest run` | ✅ 27 files / **238 tests passed**(期望 238) |
| `npm run build` | ✅ ✓ built in 2.40s(仅有预存警告:chunk >500KB、endpoints.ts/client.ts 动态导入混用,非错误) |
| `npx tsc --noEmit` | ✅ exit 0 |

### 1.2 后端全量

| 命令 | 结果 |
|------|------|
| `pytest tests/test_paper_evidence*.py tests/test_paper_library_api.py tests/test_paper_retrieval_phase2.py -q` | ✅ **62 passed**, 2 warnings(FastAPI on_event 弃用警告,预存,与本任务无关) |

### 1.3 服务健康 / console

| 检查 | 结果 |
|------|------|
| `curl http://127.0.0.1:8002/api/health` | ✅ 200 |
| `curl http://localhost:5173/` | ✅ 200 |
| Vite dev-server 编译日志 | ⚠️ 限制:前端由 Start-Process Hidden 窗口启动,无日志文件,无法直接查看 dev console。替代验证:`npm run build` 零编译错误;vitest 全绿。浏览器运行时 console 错误无法在本环境观察(无 Playwright/浏览器),报告此限制。 |

---

## 2. 分辨率适配分析(基于 CSS 数值推理)

### 布局常量(styles.css 实测)
- 侧边栏 `--sidebar-w: 220px`(L2)、顶栏 `--topbar-h: 52px`(L3)、main padding 垂直 22px / 水平 24px(L31/L119)
- 三栏 grid `.evidence-center-layout { grid-template-columns: 240px minmax(640px, 1fr) 340px; gap: 12px }`(L11407-11409)
- 内容宽 = viewport − 220(侧栏) − 48(2×24 padding);grid 最小总宽 = 240+640+340+24 = **1244**

### 三档计算

| 分辨率 | 内容宽 | 中栏(现状) | 判定 |
|--------|--------|-----------|------|
| 1920×1080 | 1652 | 1048 | ✅ ≥640 |
| 1600×900 | 1332 | 728 | ✅ ≥640 |
| 1366×768 | 1098 | 494 | ❌ <640 → grid 撑到 1244,溢出 **146px** |

### 1366 结论:存在横向溢出(修复前)
- grid 轨道下限 minmax(640px,1fr) 使三栏总宽 1244px 无法压入 1098px 容器;
- `.main` 仅设 `overflow-y: auto`(styles.css:118),按 CSS 规范"一轴 auto 一轴 visible → visible 计算为 auto",`.main` 实际获得 `overflow-x: auto` → **1366 下出现横向滚动条**,违反视觉稿 §19/§25「1366 无横向滚动」;
- 全文件核实:`styles.css` 在 evidence-center V2 区段(L11378-12486)**无任何 @media 兜底**(L10669 之后零 media query),grid 也没有右栏折叠 Drawer。

### 修复(已实施,最小方案)
```css
/* styles.css,紧接 .evidence-center-layout 定义之后 */
@media (max-width: 1440px) {
  .evidence-center-layout { grid-template-columns: 240px minmax(530px, 1fr) 300px; }
}
```
- 修复后最小总宽 = 240+530+300+24 = **1094 ≤ 1098** → 1366 无横向滚动,中栏 534px;
- 1440 时中栏 608px(原方案 568px 也会溢出,一并修复);
- **1600/1920 完全不受影响**(媒体查询不生效,保持 728/1048);
- 右栏 300px 宽度验证:冲击格 5 等分单元格 ~50px,nowrap 键 "Maximum" ~40px(10px 字号)可容纳;方向 chips `flex-wrap: wrap`(L12169);队列 Tabs `flex: 1` — 均不溢出;
- 论文库全宽模式(`.evidence-center-layout-full`, grid 1fr)特异性更高,不受 MQ 覆盖,左/右栏 display:none 不变。

### 残余风险(接受,报告中说明)
- viewport < 1352px(如 1280×800)仍无法容纳三栏且中栏 ≥530 — 低于视觉稿 1366 下限,超出本任务验收范围。建议后续做右栏 Drawer 折叠作为长期方案;本任务选择最小 CSS 修复,不动 JS。

---

## 3. 关键视觉元素存在性(代码确认)

| 元素 | 位置 | 状态 |
|------|------|------|
| 导航选中态 | `.nav-item.active` 蓝底(styles.css:112) | ✅ |
| ContextBar | `.evidence-context-bar`(styles.css:11460):状态 Badge + 完整事实句 + 刷新/返回数据中心,flex-wrap | ✅ |
| Stepper | `StepPills.tsx` 五步:确认对象→查找论文→找到原文→人工审核→确认晋升,`deriveStep` 按 module+progress 推导高亮/完成态 | ✅ |
| 左栏 ClaimSummaryPanel 5 块 | `ClaimSummaryPanel.tsx`:类型块 + claim_components 动态块(源/靶/关系/方向等),典型连接 claim = 5 块;无 components 回退 claimText 单块 | ✅ |
| 中栏 搜索+状态条+候选卡 | `EvidenceCandidatesModule.tsx`:`PaperSearchPanel`(检索区/Query chips/过滤/批量)+ `PaperStatusSummary`(候选/已提取/已核验/覆盖/模型判断 + 进入人工审核)+ `PaperCandidateList`/`PaperCandidateCard` | ✅ |
| 右栏队列 Tabs+空态 | `EvidenceQueuePanel.tsx`:待审核/已完成/失败 Tabs + 数量徽标 + ☐只看未处理 + EmptyState(队列为空/查看全部对象) | ✅ |
| 审核右栏 sticky | `.ew-sticky-actions { position: sticky; bottom: 0 }`(styles.css:12158);ReviewerDecisionPanel [驳回证据][审核通过] primary 唯一(测试断言 EvidenceReviewModule.test.tsx:366-367) | ✅ |
| 晋升 Primary 唯一 | `PromotionImpact.tsx` [退回人工审核][确认晋升],仅确认晋升 btn-primary,禁用态有提示(测试断言 EvidencePromotionModule.test.tsx:317-320) | ✅ |
| 三栏独立滚动 | `.evidence-left/.evidence-main/.evidence-right { overflow-y: auto }`(styles.css:11421) | ✅ |

---

## 4. 提交

| commit | 内容 |
|--------|------|
| `0fde89b` | `fix(evidence-center): 1366 分辨率横向溢出修复(≤1440 媒体查询兜底)` — 单文件 `frontend/src/styles.css`,+5 行。修复前 1366 下 grid 最小宽 1244 > 内容宽 1098 造成横向滚动;新增 @media (max-width:1440px) 将右栏 340→300、中栏下限 640→530,最小总宽 1094 ≤ 1098;1600/1920 不变。 |

## 5. 其他发现

- 无其他回归问题。构建警告(单 chunk 1.6MB gzip 413KB、动态/静态导入混用)为预存状态,与本任务无关。
- 后端 2 条 DeprecationWarning(FastAPI on_event)为预存,未处理。

---

## 6. 复审修复:PaperCandidateCard Coverage 徽章 required 为空回退百分比

**Finding**: `PaperCandidateCard.tsx` `coverageSummaryCounts` 在 `required_components` 为空数组/缺失时返回 null,导致 Coverage 徽章整体消失(旧卡在 coverage_ratio 存在时必显示)。

**修复**:`coverageSummaryCounts` 返回 `{ supported, required, ratio }`;`required === 0` 且 `coverage_ratio` 存在时不再返回 null,JSX 回退渲染 `Coverage {Math.round(ratio*100)}%`(百分比格式与 `EvidenceDetailDrawer.tsx` 一致);两者皆无仍返回 null 不渲染徽章。正常路径 N/M 格式不变。

**测试**(TDD,先 RED 后 GREEN):新增 2 用例 — required_components 为空数组、字段缺失,均断言 `Coverage 50%` 出现。

| commit | 内容 |
|--------|------|
| `28d9ec8` | `fix(evidence-center): Coverage 徽章 required 为空时回退百分比` — `PaperCandidateCard.tsx` + `.test.tsx`,+33/-6 |

**验证**:`npx vitest run` 27 文件 240 用例全绿(含该文件 9/9);`npx tsc --noEmit` 0 错误;`npm run build` 成功(仅预存 chunk 体积警告)。
